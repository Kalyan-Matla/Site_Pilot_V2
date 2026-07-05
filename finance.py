"""Vendors, work orders, invoices, payments, payables ledger, ageing, credit control."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, insert, next_number, row, rows, scalar, update
from ..helpers import activity, audit, notify, notify_roles, not_found, pagination
from ..security import check_project, current_user, project_filter, require, vendor_guard
from .auth_users import EmailStr

router = APIRouter(prefix="/api", tags=["finance"])

INVOICE_STATUSES = ("submitted", "under_review", "approved", "paid", "overdue", "rejected")
AGEING_BUCKETS = ((0, 30, "0-30"), (31, 45, "31-45"), (46, 60, "46-60"), (61, 100000, "60+"))


class VendorBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_person: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    gst_no: str | None = None
    address: str | None = None
    vendor_type: str = "material"
    payment_terms: str | None = None
    credit_period_days: int = Field(default=45, ge=0, le=365)
    credit_limit: float = Field(default=0, ge=0)
    active: bool = True


class WorkOrderBody(BaseModel):
    project_id: int
    vendor_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    amount: float = Field(default=0, ge=0)
    start_date: str | None = None
    end_date: str | None = None
    status: str = "active"


class InvoiceBody(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=60)
    vendor_id: int
    project_id: int
    po_id: int | None = None
    wo_id: int | None = None
    invoice_date: str
    amount: float = Field(gt=0)
    tax_amount: float = Field(default=0, ge=0)
    notes: str | None = None


class InvoiceStatusBody(BaseModel):
    status: str
    notes: str | None = None


class PaymentBody(BaseModel):
    invoice_id: int | None = None
    vendor_id: int
    project_id: int | None = None
    pay_date: str
    amount: float = Field(gt=0)
    mode: str = "bank"
    reference: str | None = None
    notes: str | None = None


def vendor_outstanding(conn, vendor_id) -> float:
    inv = scalar(conn, """SELECT SUM(total_amount) FROM invoices
                          WHERE vendor_id = ? AND status NOT IN ('rejected')""", (vendor_id,))
    paid = scalar(conn, "SELECT SUM(amount) FROM payments WHERE vendor_id = ?", (vendor_id,))
    return round((inv or 0) - (paid or 0), 2)


def invoice_paid_amount(conn, invoice_id) -> float:
    return scalar(conn, "SELECT SUM(amount) FROM payments WHERE invoice_id = ?", (invoice_id,)) or 0


def refresh_overdue(conn):
    """Flag unpaid invoices past due date as overdue (computed lazily on reads)."""
    conn.execute("""UPDATE invoices SET status = 'overdue'
                    WHERE status IN ('submitted','under_review','approved') AND due_date < ?""",
                 (date.today().isoformat(),))


# ---------- vendors ----------

@router.get("/vendors")
def list_vendors(page: int = 1, limit: int = 100, q: str | None = None, vendor_type: str | None = None,
                 user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    where, params = ["1=1"], []
    if user["role"] == "vendor":
        where, params = ["id = ?"], [user.get("vendor_id") or -1]
    if q:
        where.append("(name LIKE ? OR contact_person LIKE ? OR gst_no LIKE ?)")
        params += [f"%{q}%"] * 3
    if vendor_type:
        where.append("vendor_type = ?")
        params.append(vendor_type)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM vendors WHERE {w}", params)
    data = rows(conn, f"SELECT * FROM vendors WHERE {w} ORDER BY name LIMIT ? OFFSET ?", (*params, limit, offset))
    for v in data:
        v["outstanding"] = vendor_outstanding(conn, v["id"])
        v["over_credit_limit"] = bool(v["credit_limit"] and v["outstanding"] > v["credit_limit"])
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/vendors", status_code=201)
def create_vendor(body: VendorBody, user=Depends(require("pm", "accountant")), conn=Depends(get_db)):
    vid = insert(conn, "vendors", {**body.model_dump(), "active": 1 if body.active else 0})
    audit(conn, user, "create", "vendor", vid, after=body.model_dump())
    return row(conn, "SELECT * FROM vendors WHERE id = ?", (vid,))


@router.patch("/vendors/{vid}")
def update_vendor(vid: int, body: VendorBody, user=Depends(require("pm", "accountant")), conn=Depends(get_db)):
    before = not_found(row(conn, "SELECT * FROM vendors WHERE id = ?", (vid,)), "Vendor")
    update(conn, "vendors", vid, {**body.model_dump(), "active": 1 if body.active else 0})
    audit(conn, user, "update", "vendor", vid, before=before, after=body.model_dump())
    return row(conn, "SELECT * FROM vendors WHERE id = ?", (vid,))


# ---------- work orders ----------

@router.get("/work-orders")
def list_work_orders(page: int = 1, limit: int = 25, project_id: int | None = None,
                     vendor_id: int | None = None, user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "w.project_id")
    where = [frag]
    if user["role"] == "vendor":
        where, params = ["w.vendor_id = ?"], [user.get("vendor_id") or -1]
    if project_id:
        where.append("w.project_id = ?")
        params.append(project_id)
    if vendor_id:
        where.append("w.vendor_id = ?")
        params.append(vendor_id)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM work_orders w WHERE {w}", params)
    data = rows(conn, f"""SELECT w.*, p.name AS project_name, v.name AS vendor_name
                          FROM work_orders w JOIN projects p ON p.id = w.project_id
                          JOIN vendors v ON v.id = w.vendor_id
                          WHERE {w} ORDER BY w.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/work-orders", status_code=201)
def create_work_order(body: WorkOrderBody, user=Depends(require("pm")), conn=Depends(get_db)):
    check_project(conn, user, body.project_id)
    not_found(row(conn, "SELECT id FROM vendors WHERE id = ? AND active = 1", (body.vendor_id,)), "Vendor")
    wid = insert(conn, "work_orders", {**body.model_dump(),
                                       "wo_number": next_number(conn, "work_orders", "wo_number", "WO"),
                                       "created_by": user["id"]})
    audit(conn, user, "create", "work_order", wid, after=body.model_dump())
    activity(conn, body.project_id, user, "created work order", "work_order", wid, body.title)
    return row(conn, "SELECT * FROM work_orders WHERE id = ?", (wid,))


@router.patch("/work-orders/{wid}")
def update_work_order(wid: int, body: WorkOrderBody, user=Depends(require("pm")), conn=Depends(get_db)):
    before = not_found(row(conn, "SELECT * FROM work_orders WHERE id = ?", (wid,)), "Work order")
    check_project(conn, user, before["project_id"])
    update(conn, "work_orders", wid, body.model_dump())
    audit(conn, user, "update", "work_order", wid, before=before, after=body.model_dump())
    return row(conn, "SELECT * FROM work_orders WHERE id = ?", (wid,))


# ---------- invoices ----------

@router.get("/invoices")
def list_invoices(page: int = 1, limit: int = 25, status: str | None = None,
                  project_id: int | None = None, vendor_id: int | None = None,
                  user=Depends(current_user), conn=Depends(get_db)):
    refresh_overdue(conn)
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "i.project_id")
    where = [frag]
    if user["role"] == "vendor":
        where, params = ["i.vendor_id = ?"], [user.get("vendor_id") or -1]
    if status:
        where.append("i.status = ?")
        params.append(status)
    if project_id:
        where.append("i.project_id = ?")
        params.append(project_id)
    if vendor_id:
        where.append("i.vendor_id = ?")
        params.append(vendor_id)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM invoices i WHERE {w}", params)
    data = rows(conn, f"""SELECT i.*, v.name AS vendor_name, p.name AS project_name, po.po_number, wo.wo_number,
                                 COALESCE((SELECT SUM(amount) FROM payments pay WHERE pay.invoice_id = i.id), 0) AS paid_amount
                          FROM invoices i
                          JOIN vendors v ON v.id = i.vendor_id
                          JOIN projects p ON p.id = i.project_id
                          LEFT JOIN purchase_orders po ON po.id = i.po_id
                          LEFT JOIN work_orders wo ON wo.id = i.wo_id
                          WHERE {w} ORDER BY i.invoice_date DESC, i.id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset))
    today = date.today()
    for i in data:
        i["balance"] = round(i["total_amount"] - i["paid_amount"], 2)
        i["age_days"] = (today - date.fromisoformat(i["invoice_date"])).days
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/invoices", status_code=201)
def create_invoice(body: InvoiceBody, user=Depends(require("accountant", "pm", "vendor")), conn=Depends(get_db)):
    vendor_guard(conn, user, body.vendor_id)
    if user["role"] != "vendor":
        check_project(conn, user, body.project_id)
    vendor = not_found(row(conn, "SELECT * FROM vendors WHERE id = ?", (body.vendor_id,)), "Vendor")
    if body.po_id and not row(conn, "SELECT id FROM purchase_orders WHERE id = ? AND vendor_id = ?",
                              (body.po_id, body.vendor_id)):
        raise HTTPException(422, "PO does not belong to this vendor")
    if row(conn, "SELECT id FROM invoices WHERE vendor_id = ? AND invoice_number = ?",
           (body.vendor_id, body.invoice_number)):
        raise HTTPException(409, "This vendor already has an invoice with that number")
    inv_date = date.fromisoformat(body.invoice_date)
    due = (inv_date + timedelta(days=vendor["credit_period_days"])).isoformat()
    total = round(body.amount + body.tax_amount, 2)
    iid = insert(conn, "invoices", {**body.model_dump(), "due_date": due, "total_amount": total,
                                    "created_by": user["id"]})
    audit(conn, user, "create", "invoice", iid, after={**body.model_dump(), "due_date": due, "total": total})
    activity(conn, body.project_id, user, "recorded invoice", "invoice", iid,
             f"{body.invoice_number} — {vendor['name']}")
    notify_roles(conn, ["owner", "accountant"], "invoice", f"New invoice from {vendor['name']}",
                 f"{body.invoice_number} for {total:,.2f}, due {due}", "invoice", iid,
                 project_id=body.project_id, exclude=user["id"])
    outstanding = vendor_outstanding(conn, body.vendor_id)
    if vendor["credit_limit"] and outstanding > vendor["credit_limit"]:
        notify_roles(conn, ["owner", "accountant"], "credit_alert",
                     f"Credit limit crossed: {vendor['name']}",
                     f"Outstanding {outstanding:,.2f} exceeds limit {vendor['credit_limit']:,.2f}",
                     "vendor", body.vendor_id)
    return row(conn, "SELECT * FROM invoices WHERE id = ?", (iid,))


@router.patch("/invoices/{iid}/status")
def set_invoice_status(iid: int, body: InvoiceStatusBody,
                       user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    inv = not_found(row(conn, "SELECT * FROM invoices WHERE id = ?", (iid,)), "Invoice")
    check_project(conn, user, inv["project_id"])
    if body.status not in INVOICE_STATUSES:
        raise HTTPException(422, f"status must be one of {INVOICE_STATUSES}")
    if body.status == "paid" and invoice_paid_amount(conn, iid) < inv["total_amount"] - 0.01:
        raise HTTPException(422, "Cannot mark paid: recorded payments do not cover the invoice total")
    update(conn, "invoices", iid, {"status": body.status,
                                   "notes": body.notes if body.notes is not None else inv["notes"]})
    audit(conn, user, "status_change", "invoice", iid,
          before={"status": inv["status"]}, after={"status": body.status})
    vendor_users = rows(conn, "SELECT id FROM users WHERE vendor_id = ? AND active = 1", (inv["vendor_id"],))
    notify(conn, [u["id"] for u in vendor_users], "invoice",
           f"Invoice {inv['invoice_number']}: {body.status}", body.notes, "invoice", iid, exclude=user["id"])
    return row(conn, "SELECT * FROM invoices WHERE id = ?", (iid,))


# ---------- payments ----------

@router.get("/payments")
def list_payments(page: int = 1, limit: int = 25, vendor_id: int | None = None,
                  project_id: int | None = None, mode: str | None = None,
                  user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    where, params = ["1=1"], []
    if user["role"] == "vendor":
        where, params = ["pay.vendor_id = ?"], [user.get("vendor_id") or -1]
    elif user["role"] not in ("owner", "accountant"):
        frag, params = project_filter(conn, user, "pay.project_id")
        where = [frag]
    if vendor_id:
        where.append("pay.vendor_id = ?")
        params.append(vendor_id)
    if project_id:
        where.append("pay.project_id = ?")
        params.append(project_id)
    if mode:
        where.append("pay.mode = ?")
        params.append(mode)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM payments pay WHERE {w}", params)
    data = rows(conn, f"""SELECT pay.*, v.name AS vendor_name, p.name AS project_name, i.invoice_number
                          FROM payments pay
                          JOIN vendors v ON v.id = pay.vendor_id
                          LEFT JOIN projects p ON p.id = pay.project_id
                          LEFT JOIN invoices i ON i.id = pay.invoice_id
                          WHERE {w} ORDER BY pay.pay_date DESC, pay.id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset))
    sums = row(conn, f"""SELECT ROUND(SUM(CASE WHEN pay.mode = 'cash' THEN pay.amount ELSE 0 END), 2) AS cash_total,
                                ROUND(SUM(CASE WHEN pay.mode != 'cash' THEN pay.amount ELSE 0 END), 2) AS bank_total
                         FROM payments pay WHERE {w}""", params)
    return {"data": data, "total": total, "page": page, "limit": limit, "totals": sums}


@router.post("/payments", status_code=201)
def record_payment(body: PaymentBody, user=Depends(require("accountant")), conn=Depends(get_db)):
    vendor = not_found(row(conn, "SELECT * FROM vendors WHERE id = ?", (body.vendor_id,)), "Vendor")
    project_id = body.project_id
    if body.invoice_id:
        inv = not_found(row(conn, "SELECT * FROM invoices WHERE id = ?", (body.invoice_id,)), "Invoice")
        if inv["vendor_id"] != body.vendor_id:
            raise HTTPException(422, "Invoice belongs to a different vendor")
        balance = inv["total_amount"] - invoice_paid_amount(conn, body.invoice_id)
        if body.amount > balance + 0.01:
            raise HTTPException(422, f"Payment {body.amount} exceeds invoice balance {round(balance, 2)}")
        project_id = inv["project_id"]
    pay_id = insert(conn, "payments", {**body.model_dump(), "project_id": project_id,
                                       "payment_no": next_number(conn, "payments", "payment_no", "PAY"),
                                       "created_by": user["id"]})
    if body.invoice_id:
        remaining = inv["total_amount"] - invoice_paid_amount(conn, body.invoice_id)
        if remaining <= 0.01:
            update(conn, "invoices", body.invoice_id, {"status": "paid"})
        vendor_users = rows(conn, "SELECT id FROM users WHERE vendor_id = ? AND active = 1", (body.vendor_id,))
        notify(conn, [u["id"] for u in vendor_users], "payment",
               f"Payment recorded against {inv['invoice_number']}",
               f"{body.amount:,.2f} via {body.mode}", "payment", pay_id)
    audit(conn, user, "create", "payment", pay_id, after=body.model_dump())
    if project_id:
        activity(conn, project_id, user, "recorded payment", "payment", pay_id,
                 f"{body.amount:,.2f} to {vendor['name']}")
    return row(conn, "SELECT * FROM payments WHERE id = ?", (pay_id,))


# ---------- payables ledger / ageing / alerts ----------

@router.get("/finance/payables")
def payables(user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    refresh_overdue(conn)
    by_vendor = rows(conn, """
        SELECT v.id, v.name, v.credit_limit, v.credit_period_days,
               ROUND(COALESCE(SUM(i.total_amount), 0), 2) AS invoiced,
               ROUND(COALESCE((SELECT SUM(amount) FROM payments p WHERE p.vendor_id = v.id), 0), 2) AS paid
        FROM vendors v LEFT JOIN invoices i ON i.vendor_id = v.id AND i.status != 'rejected'
        GROUP BY v.id HAVING invoiced > 0 OR paid > 0 ORDER BY v.name""")
    for v in by_vendor:
        v["outstanding"] = round(v["invoiced"] - v["paid"], 2)
        v["over_credit_limit"] = bool(v["credit_limit"] and v["outstanding"] > v["credit_limit"])
    by_project = rows(conn, """
        SELECT p.id, p.name,
               ROUND(COALESCE(SUM(i.total_amount), 0), 2) AS invoiced,
               ROUND(COALESCE((SELECT SUM(amount) FROM payments pay WHERE pay.project_id = p.id), 0), 2) AS paid
        FROM projects p LEFT JOIN invoices i ON i.project_id = p.id AND i.status != 'rejected'
        GROUP BY p.id HAVING invoiced > 0 OR paid > 0 ORDER BY p.name""")
    for p in by_project:
        p["outstanding"] = round(p["invoiced"] - p["paid"], 2)
    return {"by_vendor": by_vendor, "by_project": by_project}


@router.get("/finance/ageing")
def ageing(user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    refresh_overdue(conn)
    today = date.today()
    invoices = rows(conn, """
        SELECT i.*, v.name AS vendor_name, p.name AS project_name,
               COALESCE((SELECT SUM(amount) FROM payments pay WHERE pay.invoice_id = i.id), 0) AS paid_amount
        FROM invoices i JOIN vendors v ON v.id = i.vendor_id JOIN projects p ON p.id = i.project_id
        WHERE i.status NOT IN ('paid', 'rejected') ORDER BY i.invoice_date""")
    buckets = {label: {"label": label, "count": 0, "amount": 0.0, "invoices": []}
               for _, _, label in AGEING_BUCKETS}
    for inv in invoices:
        balance = round(inv["total_amount"] - inv["paid_amount"], 2)
        if balance <= 0:
            continue
        age = (today - date.fromisoformat(inv["invoice_date"])).days
        label = next(lbl for lo, hi, lbl in AGEING_BUCKETS if lo <= age <= hi)
        b = buckets[label]
        b["count"] += 1
        b["amount"] = round(b["amount"] + balance, 2)
        b["invoices"].append({"id": inv["id"], "invoice_number": inv["invoice_number"],
                              "vendor_name": inv["vendor_name"], "project_name": inv["project_name"],
                              "invoice_date": inv["invoice_date"], "due_date": inv["due_date"],
                              "balance": balance, "age_days": age, "status": inv["status"]})
    return {"buckets": list(buckets.values()),
            "total_outstanding": round(sum(b["amount"] for b in buckets.values()), 2)}


@router.get("/finance/alerts")
def finance_alerts(user=Depends(require("accountant", "pm")), conn=Depends(get_db)):
    refresh_overdue(conn)
    today = date.today()
    alerts = []
    for v in rows(conn, "SELECT * FROM vendors WHERE credit_limit > 0"):
        outstanding = vendor_outstanding(conn, v["id"])
        if outstanding > v["credit_limit"]:
            alerts.append({"type": "credit_limit", "severity": "high",
                           "message": f"{v['name']}: outstanding {outstanding:,.2f} exceeds credit limit {v['credit_limit']:,.2f}",
                           "vendor_id": v["id"]})
    old = rows(conn, """SELECT i.*, v.name AS vendor_name,
                               COALESCE((SELECT SUM(amount) FROM payments p WHERE p.invoice_id = i.id), 0) AS paid_amount
                        FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                        WHERE i.status NOT IN ('paid', 'rejected')""")
    for inv in old:
        if inv["total_amount"] - inv["paid_amount"] <= 0.01:
            continue
        age = (today - date.fromisoformat(inv["invoice_date"])).days
        if age > 45:
            alerts.append({"type": "invoice_age", "severity": "high" if age > 60 else "medium",
                           "message": f"Invoice {inv['invoice_number']} ({inv['vendor_name']}) is {age} days old, "
                                      f"balance {inv['total_amount'] - inv['paid_amount']:,.2f}",
                           "invoice_id": inv["id"]})
        elif inv["due_date"] < today.isoformat():
            alerts.append({"type": "overdue", "severity": "medium",
                           "message": f"Invoice {inv['invoice_number']} ({inv['vendor_name']}) is past due date {inv['due_date']}",
                           "invoice_id": inv["id"]})
    return {"alerts": alerts}
