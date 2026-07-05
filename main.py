"""SitePilot — construction management for small/medium contractors.

Run:  uv run python -m app.main   (or: uvicorn app.main:app)
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import seed as seed_module
from .db import connect, migrate, rows, scalar
from .routers import auth_users, documents, finance, labour, materials, misc, projects, reports

log = logging.getLogger("sitepilot")

# public/ (not static/) so Vercel's CDN can serve these files directly without
# invoking the Python function — see "Serving static assets" in Vercel's
# FastAPI docs. Local/Docker/Render still serve it the same way, via the
# StaticFiles mount + catch-all route below.
STATIC_DIR = Path(__file__).resolve().parent.parent / "public"
ALERT_INTERVAL_HOURS = float(os.environ.get("ALERT_INTERVAL_HOURS", "24"))
ON_VERCEL = bool(os.environ.get("VERCEL"))
CRON_SECRET = os.environ.get("CRON_SECRET")


def run_due_alerts():
    """Daily sweep: overdue invoices, 45-day breaches, credit limits, low stock.

    Dedupes by skipping users already notified for the same entity+type.
    """
    conn = connect()
    try:
        today = date.today().isoformat()
        conn.execute("""UPDATE invoices SET status = 'overdue'
                        WHERE status IN ('submitted','under_review','approved') AND due_date < ?""", (today,))
        finance_users = [r["id"] for r in rows(
            conn, "SELECT id FROM users WHERE active = 1 AND role IN ('owner','accountant')")]

        def alert_once(uid, ntype, entity_type, entity_id, title, body):
            exists = scalar(conn, """SELECT COUNT(*) FROM notifications
                                     WHERE user_id = ? AND ntype = ? AND entity_type = ? AND entity_id = ?""",
                            (uid, ntype, entity_type, entity_id))
            if not exists:
                conn.execute("""INSERT INTO notifications (user_id, ntype, title, body, entity_type, entity_id)
                                VALUES (?,?,?,?,?,?)""", (uid, ntype, title, body, entity_type, entity_id))

        for inv in rows(conn, """SELECT i.*, v.name AS vendor_name,
                                        COALESCE((SELECT SUM(amount) FROM payments p WHERE p.invoice_id = i.id), 0) AS paid
                                 FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                                 WHERE i.status NOT IN ('paid','rejected')"""):
            balance = inv["total_amount"] - inv["paid"]
            if balance <= 0.01:
                continue
            age = (date.today() - date.fromisoformat(inv["invoice_date"])).days
            if inv["due_date"] < today:
                for uid in finance_users:
                    alert_once(uid, "payment_due", "invoice", inv["id"],
                               f"Invoice {inv['invoice_number']} is overdue",
                               f"{inv['vendor_name']}: balance {balance:,.2f}, was due {inv['due_date']}")
            if age > 45:
                for uid in finance_users:
                    alert_once(uid, "invoice_45d", "invoice", inv["id"],
                               f"Invoice {inv['invoice_number']} crossed 45 days",
                               f"{inv['vendor_name']}: {age} days old, balance {balance:,.2f}")

        for v in rows(conn, "SELECT * FROM vendors WHERE credit_limit > 0 AND active = 1"):
            outstanding = (scalar(conn, "SELECT SUM(total_amount) FROM invoices WHERE vendor_id = ? AND status != 'rejected'", (v["id"],)) or 0) \
                          - (scalar(conn, "SELECT SUM(amount) FROM payments WHERE vendor_id = ?", (v["id"],)) or 0)
            if outstanding > v["credit_limit"]:
                for uid in finance_users:
                    alert_once(uid, "credit_limit", "vendor", v["id"],
                               f"Credit limit crossed: {v['name']}",
                               f"Outstanding {outstanding:,.2f} vs limit {v['credit_limit']:,.2f}")

        for s in rows(conn, """SELECT s.*, m.name AS material_name FROM stock s
                               JOIN materials m ON m.id = s.material_id
                               WHERE s.min_level > 0 AND s.qty < s.min_level"""):
            targets = [r["user_id"] for r in rows(conn, """
                SELECT pm.user_id FROM project_members pm JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = ? AND u.active = 1 AND u.role IN ('pm','store')""", (s["project_id"],))]
            for uid in targets:
                alert_once(uid, "low_stock", "stock", s["id"],
                           f"Low stock: {s['material_name']}",
                           f"Project #{s['project_id']}: {s['qty']} left (min {s['min_level']})")
        conn.commit()
    finally:
        conn.close()


async def alert_loop():
    while True:
        try:
            await asyncio.to_thread(run_due_alerts)
        except Exception as exc:  # keep the loop alive
            print(f"[alerts] sweep failed: {exc}")
        await asyncio.sleep(ALERT_INTERVAL_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    if os.environ.get("SEED_DEMO_DATA", "1") == "1":
        try:
            seed_module.seed()
        except Exception:
            log.exception("Demo data seed failed (continuing without it)")
    task = None
    if not ON_VERCEL:
        # Serverless functions don't stay alive between requests, so this
        # in-process loop would never reliably fire on Vercel. There, the
        # same sweep runs instead via /api/cron/alerts + vercel.json crons.
        task = asyncio.create_task(alert_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="SitePilot", version="1.0.0", lifespan=lifespan)

for r in (auth_users, projects, documents, materials, labour, finance, reports, misc):
    app.include_router(r.router)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/cron/alerts")
@app.post("/api/cron/alerts")
def cron_alerts(authorization: str | None = Header(default=None)):
    """Runs the daily alert sweep once. Wired to vercel.json's crons entry
    (Vercel signs the request with `Authorization: Bearer $CRON_SECRET` when
    that env var is set); on non-Vercel hosts the in-process loop above
    already covers this and nothing calls this route."""
    if CRON_SECRET and authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Invalid cron secret")
    run_due_alerts()
    return {"ok": True}


app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Serve the single-page app for any non-API route."""
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8000")), reload=False)
