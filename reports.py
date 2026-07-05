"""Management dashboard and CSV / PDF exports for key reports."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..db import get_db, rows, scalar
from ..security import check_project, current_user, project_filter, require
from .finance import ageing as ageing_endpoint
from .finance import payables as payables_endpoint
from .finance import refresh_overdue
from .labour import DAYS_EXPR, PAY_EXPR
from .projects import labour_cost, project_metrics, report_payload

router = APIRouter(prefix="/api", tags=["reports"])


# ---------- dashboard ----------

@router.get("/dashboard")
def dashboard(user=Depends(current_user), conn=Depends(get_db)):
    refresh_overdue(conn)
    frag, params = project_filter(conn, user, "id")
    projects = rows(conn, f"SELECT * FROM projects WHERE {frag} ORDER BY status = 'active' DESC, created_at DESC", params)
    cards = []
    totals = {"budget": 0, "committed": 0, "invoiced": 0, "paid": 0, "labour": 0}
    for p in projects:
        m = project_metrics(conn, p["id"])
        lab = round(labour_cost(conn, p["id"]), 2)
        cost = round((m["po_committed"] or 0) + lab, 2)
        cards.append({
            "id": p["id"], "name": p["name"], "client_name": p["client_name"], "status": p["status"],
            "location": p["location"], "start_date": p["start_date"], "end_date": p["end_date"],
            "budget": p["budget"], "contract_value": p["contract_value"],
            "progress_pct": m["progress_pct"], "tasks_delayed": m["tasks_delayed"],
            "open_issues": m["open_issues"], "tasks_total": m["tasks_total"], "tasks_done": m["tasks_done"],
            "po_committed": round(m["po_committed"] or 0, 2), "labour_cost": lab,
            "total_cost": cost, "invoiced": round(m["invoiced"] or 0, 2), "paid": round(m["paid"] or 0, 2),
            "margin": round((p["contract_value"] or p["budget"] or 0) - cost, 2),
        })
        totals["budget"] += p["budget"] or 0
        totals["committed"] += m["po_committed"] or 0
        totals["invoiced"] += m["invoiced"] or 0
        totals["paid"] += m["paid"] or 0
        totals["labour"] += lab
    summary = {
        "projects_active": sum(1 for c in cards if c["status"] == "active"),
        "projects_total": len(cards),
        "tasks_delayed": sum(c["tasks_delayed"] for c in cards),
        "open_issues": sum(c["open_issues"] for c in cards),
        **{k: round(v, 2) for k, v in totals.items()},
    }
    if user["role"] in ("owner", "accountant", "pm"):
        summary["outstanding_payables"] = round(
            (scalar(conn, "SELECT SUM(total_amount) FROM invoices WHERE status != 'rejected'") or 0)
            - (scalar(conn, "SELECT SUM(amount) FROM payments") or 0), 2)
        summary["overdue_invoices"] = scalar(conn, "SELECT COUNT(*) FROM invoices WHERE status = 'overdue'")
    return {"projects": cards, "summary": summary}


# ---------- export helpers ----------

def csv_response(filename, header, data_rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(data_rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def pdf_response(filename, title, sections):
    """sections: list of (heading, header_row, data_rows)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 4 * mm)]
    for heading, header, data in sections:
        story.append(Paragraph(heading, styles["Heading2"]))
        if not data:
            story.append(Paragraph("No records.", styles["Normal"]))
            story.append(Spacer(1, 3 * mm))
            continue
        cells = [[Paragraph(str(h), styles["Normal"]) for h in header]]
        for r in data:
            cells.append([Paragraph("" if v is None else str(v), styles["Normal"]) for v in r])
        t = Table(cells, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 5 * mm))
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def dpr_sections(payload):
    return [
        ("Work done", ["Date", "Task", "Description", "Qty", "Unit", "Labour", "Notes", "By"],
         [[l["log_date"], l["task_name"], l["work_description"], l["quantity_done"], l["unit"],
           l["labour_count"], l["notes"], l["created_by_name"]] for l in payload["logs"]]),
        ("Materials used", ["Material", "Unit", "Qty used"],
         [[m["name"], m["unit"], m["qty_used"]] for m in payload["materials_used"]]),
        ("Labour", ["Category", "Man-days", "OT hours"],
         [[l["category"], l["days"], l["ot_hours"]] for l in payload["labour"]]),
        ("Issues raised", ["Title", "Severity", "Status", "Raised at"],
         [[i["title"], i["severity"], i["status"], i["created_at"]] for i in payload["issues"]]),
    ]


# ---------- exports ----------

@router.get("/reports/dpr/{pid}")
def export_dpr(pid: int, fmt: str = "pdf", report_date: str | None = None,
               user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    d = report_date or date.today().isoformat()
    payload = report_payload(conn, pid, d, d)
    name = payload["project"]["name"]
    title = f"Daily Progress Report — {name} — {d} (overall {payload['progress_pct']}%)"
    if fmt == "csv":
        rows_ = [["DPR", name, d, f"progress {payload['progress_pct']}%"], []]
        for heading, header, data in dpr_sections(payload):
            rows_ += [[heading], header, *data, []]
        return csv_response(f"dpr_{pid}_{d}.csv", [], rows_)
    return pdf_response(f"dpr_{pid}_{d}.pdf", title, dpr_sections(payload))


@router.get("/reports/wpr/{pid}")
def export_wpr(pid: int, fmt: str = "pdf", week_start: str | None = None,
               user=Depends(current_user), conn=Depends(get_db)):
    from datetime import timedelta
    check_project(conn, user, pid)
    start = date.fromisoformat(week_start) if week_start else date.today() - timedelta(days=date.today().weekday())
    end = start + timedelta(days=6)
    payload = report_payload(conn, pid, start.isoformat(), end.isoformat())
    name = payload["project"]["name"]
    title = f"Weekly Progress Report — {name} — {start} to {end} (overall {payload['progress_pct']}%)"
    if fmt == "csv":
        rows_ = [["WPR", name, f"{start} to {end}", f"progress {payload['progress_pct']}%"], []]
        for heading, header, data in dpr_sections(payload):
            rows_ += [[heading], header, *data, []]
        return csv_response(f"wpr_{pid}_{start}.csv", [], rows_)
    return pdf_response(f"wpr_{pid}_{start}.pdf", title, dpr_sections(payload))


@router.get("/reports/stock/{pid}")
def export_stock(pid: int, fmt: str = "csv", user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    data = rows(conn, """SELECT m.name, m.category, m.unit, s.qty, s.min_level, s.reserved_qty
                         FROM stock s JOIN materials m ON m.id = s.material_id
                         WHERE s.project_id = ? ORDER BY m.name""", (pid,))
    header = ["Material", "Category", "Unit", "In stock", "Min level", "Reserved"]
    body = [[d["name"], d["category"], d["unit"], d["qty"], d["min_level"], d["reserved_qty"]] for d in data]
    if fmt == "pdf":
        return pdf_response(f"stock_{pid}.pdf", f"Site Stock — project {pid}", [("Stock", header, body)])
    return csv_response(f"stock_{pid}.csv", header, body)


@router.get("/reports/material-flow/{pid}")
def export_material_flow(pid: int, fmt: str = "csv", user=Depends(current_user), conn=Depends(get_db)):
    from .materials import material_summary
    payload = material_summary(pid, user, conn)
    header = ["Material", "Unit", "Requested", "Ordered", "Received", "Used", "In stock"]
    body = [[d["name"], d["unit"], d["requested"], d["ordered"], d["received"], d["used"], d["in_stock"]]
            for d in payload["data"]]
    if fmt == "pdf":
        return pdf_response(f"material_flow_{pid}.pdf", f"Requested vs Received vs Used — project {pid}",
                            [("Material flow", header, body)])
    return csv_response(f"material_flow_{pid}.csv", header, body)


@router.get("/reports/labour")
def export_labour(date_from: str, date_to: str, fmt: str = "csv",
                  user=Depends(current_user), conn=Depends(get_db)):
    frag, params = project_filter(conn, user, "a.project_id")
    data = rows(conn, f"""
        SELECT p.name AS project, COALESCE(v.name, 'In-house') AS vendor, l.category,
               COUNT(DISTINCT l.id) AS labourers, {DAYS_EXPR} AS days_worked,
               SUM(a.ot_hours) AS ot_hours, ROUND({PAY_EXPR}, 2) AS payable
        FROM attendance a JOIN labourers l ON l.id = a.labourer_id
        JOIN projects p ON p.id = a.project_id
        LEFT JOIN vendors v ON v.id = l.vendor_id
        WHERE {frag} AND a.att_date BETWEEN ? AND ?
        GROUP BY a.project_id, p.name, l.vendor_id, v.name, l.category ORDER BY p.name, vendor""",
        (*params, date_from, date_to))
    header = ["Project", "Vendor", "Category", "Labourers", "Man-days", "OT hours", "Payable"]
    body = [[d["project"], d["vendor"], d["category"], d["labourers"], d["days_worked"],
             d["ot_hours"], d["payable"]] for d in data]
    title = f"Labour Report {date_from} to {date_to}"
    if fmt == "pdf":
        return pdf_response("labour_report.pdf", title, [("Labour & payable", header, body)])
    return csv_response("labour_report.csv", header, body)


@router.get("/reports/ageing")
def export_ageing(fmt: str = "csv", user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    payload = ageing_endpoint(user, conn)
    header = ["Bucket", "Invoice", "Vendor", "Project", "Invoice date", "Due date", "Age (days)", "Balance"]
    body = []
    for b in payload["buckets"]:
        for i in b["invoices"]:
            body.append([b["label"], i["invoice_number"], i["vendor_name"], i["project_name"],
                         i["invoice_date"], i["due_date"], i["age_days"], i["balance"]])
    title = f"Payables Ageing — total outstanding {payload['total_outstanding']:,.2f}"
    if fmt == "pdf":
        return pdf_response("ageing.pdf", title, [("Ageing", header, body)])
    return csv_response("ageing.csv", header, body)


@router.get("/reports/payables")
def export_payables(fmt: str = "csv", user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    payload = payables_endpoint(user, conn)
    v_header = ["Vendor", "Invoiced", "Paid", "Outstanding", "Credit limit", "Over limit"]
    v_body = [[v["name"], v["invoiced"], v["paid"], v["outstanding"], v["credit_limit"],
               "YES" if v["over_credit_limit"] else ""] for v in payload["by_vendor"]]
    p_header = ["Project", "Invoiced", "Paid", "Outstanding"]
    p_body = [[p["name"], p["invoiced"], p["paid"], p["outstanding"]] for p in payload["by_project"]]
    if fmt == "pdf":
        return pdf_response("payables.pdf", "Payables Ledger",
                            [("By vendor", v_header, v_body), ("By project", p_header, p_body)])
    rows_ = [["By vendor"], v_header, *v_body, [], ["By project"], p_header, *p_body]
    return csv_response("payables.csv", [], rows_)


@router.get("/audit-log")
def audit_log(page: int = 1, limit: int = 50, entity_type: str | None = None,
              user=Depends(require("accountant")), conn=Depends(get_db)):
    from ..helpers import pagination
    page, limit, offset = pagination(page, limit)
    where, params = "1=1", []
    if entity_type:
        where, params = "a.entity_type = ?", [entity_type]
    total = scalar(conn, f"SELECT COUNT(*) FROM audit_log a WHERE {where}", params)
    data = rows(conn, f"""SELECT a.*, u.name AS user_name FROM audit_log a
                          LEFT JOIN users u ON u.id = a.user_id
                          WHERE {where} ORDER BY a.id DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}
