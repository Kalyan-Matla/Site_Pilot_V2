"""Material master, site stock, indents, purchase orders, GRNs, usage logs."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, insert, next_number, row, rows, scalar, update
from ..helpers import activity, audit, notify, notify_roles, not_found, pagination
from ..security import check_project, current_user, project_filter, require, vendor_guard

router = APIRouter(prefix="/api", tags=["materials"])

PO_STATUSES = ("draft", "issued", "partially_received", "received", "closed", "cancelled")


class MaterialBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str | None = None
    unit: str = Field(min_length=1, max_length=20)
    default_rate: float = Field(default=0, ge=0)
    active: bool = True


class StockBody(BaseModel):
    material_id: int
    qty: float = Field(default=0, ge=0)
    min_level: float = Field(default=0, ge=0)
    reserved_qty: float = Field(default=0, ge=0)


class RequestItem(BaseModel):
    material_id: int
    qty: float = Field(gt=0)
    remarks: str | None = None


class RequestBody(BaseModel):
    project_id: int
    required_date: str | None = None
    notes: str | None = None
    items: list[RequestItem] = Field(min_length=1)


class DecisionBody(BaseModel):
    notes: str | None = None


class POItem(BaseModel):
    material_id: int
    qty: float = Field(gt=0)
    rate: float = Field(ge=0)


class POBody(BaseModel):
    project_id: int
    vendor_id: int
    request_id: int | None = None
    order_date: str | None = None
    expected_date: str | None = None
    notes: str | None = None
    items: list[POItem] = Field(min_length=1)


class POStatusBody(BaseModel):
    status: str


class GRNItem(BaseModel):
    po_item_id: int
    qty_received: float = Field(gt=0)
    remarks: str | None = None


class GRNBody(BaseModel):
    po_id: int
    received_date: str | None = None
    vehicle_no: str | None = None
    notes: str | None = None
    items: list[GRNItem] = Field(min_length=1)


class UsageBody(BaseModel):
    project_id: int
    material_id: int
    task_id: int | None = None
    usage_date: str | None = None
    qty: float = Field(gt=0)
    notes: str | None = None


# ---------- material master ----------

@router.get("/materials")
def list_materials(page: int = 1, limit: int = 100, q: str | None = None,
                   user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    where, params = "1=1", []
    if q:
        where, params = "(name LIKE ? OR category LIKE ?)", [f"%{q}%", f"%{q}%"]
    total = scalar(conn, f"SELECT COUNT(*) FROM materials WHERE {where}", params)
    data = rows(conn, f"SELECT * FROM materials WHERE {where} ORDER BY name LIMIT ? OFFSET ?",
                (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/materials", status_code=201)
def create_material(body: MaterialBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    if row(conn, "SELECT id FROM materials WHERE name = ?", (body.name,)):
        raise HTTPException(409, "Material already exists")
    mid = insert(conn, "materials", {**body.model_dump(), "active": 1 if body.active else 0})
    audit(conn, user, "create", "material", mid, after=body.model_dump())
    return row(conn, "SELECT * FROM materials WHERE id = ?", (mid,))


@router.patch("/materials/{mid}")
def update_material(mid: int, body: MaterialBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    not_found(row(conn, "SELECT id FROM materials WHERE id = ?", (mid,)), "Material")
    update(conn, "materials", mid, {**body.model_dump(), "active": 1 if body.active else 0})
    return row(conn, "SELECT * FROM materials WHERE id = ?", (mid,))


# ---------- site stock ----------

def adjust_stock(conn, project_id, material_id, delta):
    existing = row(conn, "SELECT * FROM stock WHERE project_id = ? AND material_id = ?", (project_id, material_id))
    if existing:
        conn.execute("UPDATE stock SET qty = qty + ? WHERE id = ?", (delta, existing["id"]))
        return existing["qty"] + delta
    insert(conn, "stock", {"project_id": project_id, "material_id": material_id, "qty": max(0, delta)})
    return delta


@router.get("/projects/{pid}/stock")
def project_stock(pid: int, page: int = 1, limit: int = 100, low_only: int = 0,
                  user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where = "s.project_id = ?" + (" AND s.qty < s.min_level" if low_only else "")
    total = scalar(conn, f"SELECT COUNT(*) FROM stock s WHERE {where}", (pid,))
    data = rows(conn, f"""SELECT s.*, m.name, m.unit, m.category, m.default_rate,
                                 (s.qty < s.min_level) AS is_low
                          FROM stock s JOIN materials m ON m.id = s.material_id
                          WHERE {where} ORDER BY m.name LIMIT ? OFFSET ?""", (pid, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.put("/projects/{pid}/stock")
def upsert_stock(pid: int, body: StockBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    not_found(row(conn, "SELECT id FROM materials WHERE id = ?", (body.material_id,)), "Material")
    existing = row(conn, "SELECT * FROM stock WHERE project_id = ? AND material_id = ?", (pid, body.material_id))
    if existing:
        update(conn, "stock", existing["id"], body.model_dump())
        sid = existing["id"]
    else:
        sid = insert(conn, "stock", {**body.model_dump(), "project_id": pid})
    audit(conn, user, "upsert", "stock", sid, before=existing, after=body.model_dump())
    return row(conn, "SELECT * FROM stock WHERE id = ?", (sid,))


# ---------- material requests (indents) ----------

def request_with_items(conn, rid):
    r = row(conn, """SELECT mr.*, p.name AS project_name, u.name AS requested_by_name, d.name AS decision_by_name
                     FROM material_requests mr
                     JOIN projects p ON p.id = mr.project_id
                     LEFT JOIN users u ON u.id = mr.requested_by
                     LEFT JOIN users d ON d.id = mr.decision_by
                     WHERE mr.id = ?""", (rid,))
    if r:
        r["items"] = rows(conn, """SELECT i.*, m.name, m.unit FROM material_request_items i
                                   JOIN materials m ON m.id = i.material_id WHERE i.request_id = ?""", (rid,))
    return r


@router.get("/material-requests")
def list_requests(page: int = 1, limit: int = 25, status: str | None = None, project_id: int | None = None,
                  user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "mr.project_id")
    where = [frag]
    if status:
        where.append("mr.status = ?")
        params.append(status)
    if project_id:
        check_project(conn, user, project_id)
        where.append("mr.project_id = ?")
        params.append(project_id)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM material_requests mr WHERE {w}", params)
    data = rows(conn, f"""SELECT mr.*, p.name AS project_name, u.name AS requested_by_name,
                                 (SELECT COUNT(*) FROM material_request_items i WHERE i.request_id = mr.id) AS item_count
                          FROM material_requests mr
                          JOIN projects p ON p.id = mr.project_id
                          LEFT JOIN users u ON u.id = mr.requested_by
                          WHERE {w} ORDER BY mr.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.get("/material-requests/{rid}")
def get_request(rid: int, user=Depends(current_user), conn=Depends(get_db)):
    r = not_found(request_with_items(conn, rid), "Request")
    check_project(conn, user, r["project_id"])
    return r


@router.post("/material-requests", status_code=201)
def create_request(body: RequestBody, user=Depends(require("pm", "site", "store")), conn=Depends(get_db)):
    check_project(conn, user, body.project_id)
    rid = insert(conn, "material_requests", {
        "request_no": next_number(conn, "material_requests", "request_no", "MR"),
        "project_id": body.project_id, "requested_by": user["id"],
        "required_date": body.required_date, "notes": body.notes,
    })
    for it in body.items:
        not_found(row(conn, "SELECT id FROM materials WHERE id = ?", (it.material_id,)), "Material")
        insert(conn, "material_request_items", {"request_id": rid, **it.model_dump()})
    audit(conn, user, "create", "material_request", rid, after=body.model_dump())
    activity(conn, body.project_id, user, "raised material request", "material_request", rid)
    notify_roles(conn, ["owner", "pm"], "material_request", "New material request",
                 f"{len(body.items)} item(s), required by {body.required_date or 'n/a'}",
                 "material_request", rid, project_id=body.project_id, exclude=user["id"])
    return request_with_items(conn, rid)


def decide_request(conn, user, rid, new_status, notes):
    r = not_found(row(conn, "SELECT * FROM material_requests WHERE id = ?", (rid,)), "Request")
    check_project(conn, user, r["project_id"])
    if r["status"] != "pending":
        raise HTTPException(422, f"Request is already {r['status']}")
    update(conn, "material_requests", rid, {
        "status": new_status, "decision_by": user["id"],
        "decision_at": date.today().isoformat(), "decision_notes": notes})
    audit(conn, user, new_status, "material_request", rid, before={"status": r["status"]})
    activity(conn, r["project_id"], user, f"{new_status} material request", "material_request", rid)
    notify(conn, [r["requested_by"]], "material_request", f"Request {r['request_no']} {new_status}",
           notes, "material_request", rid, exclude=user["id"])
    return request_with_items(conn, rid)


@router.post("/material-requests/{rid}/approve")
def approve_request(rid: int, body: DecisionBody, user=Depends(require("pm")), conn=Depends(get_db)):
    return decide_request(conn, user, rid, "approved", body.notes)


@router.post("/material-requests/{rid}/reject")
def reject_request(rid: int, body: DecisionBody, user=Depends(require("pm")), conn=Depends(get_db)):
    return decide_request(conn, user, rid, "rejected", body.notes)


# ---------- purchase orders ----------

def po_with_items(conn, po_id):
    po = row(conn, """SELECT po.*, p.name AS project_name, v.name AS vendor_name, u.name AS created_by_name,
                             mr.request_no
                      FROM purchase_orders po
                      JOIN projects p ON p.id = po.project_id
                      JOIN vendors v ON v.id = po.vendor_id
                      LEFT JOIN users u ON u.id = po.created_by
                      LEFT JOIN material_requests mr ON mr.id = po.request_id
                      WHERE po.id = ?""", (po_id,))
    if po:
        po["items"] = rows(conn, """SELECT i.*, m.name, m.unit, i.qty * i.rate AS amount
                                    FROM po_items i JOIN materials m ON m.id = i.material_id
                                    WHERE i.po_id = ?""", (po_id,))
        po["total_amount"] = round(sum(i["amount"] for i in po["items"]), 2)
        po["grns"] = rows(conn, "SELECT id, grn_number, received_date FROM grns WHERE po_id = ?", (po_id,))
    return po


@router.get("/purchase-orders")
def list_pos(page: int = 1, limit: int = 25, status: str | None = None, project_id: int | None = None,
             vendor_id: int | None = None, user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "po.project_id")
    where = [frag]
    if user["role"] == "vendor":
        where = ["po.vendor_id = ?"]
        params = [user.get("vendor_id") or -1]
    if status:
        where.append("po.status = ?")
        params.append(status)
    if project_id:
        where.append("po.project_id = ?")
        params.append(project_id)
    if vendor_id:
        where.append("po.vendor_id = ?")
        params.append(vendor_id)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM purchase_orders po WHERE {w}", params)
    data = rows(conn, f"""SELECT po.*, p.name AS project_name, v.name AS vendor_name,
                                 (SELECT ROUND(SUM(qty * rate), 2) FROM po_items i WHERE i.po_id = po.id) AS total_amount
                          FROM purchase_orders po
                          JOIN projects p ON p.id = po.project_id
                          JOIN vendors v ON v.id = po.vendor_id
                          WHERE {w} ORDER BY po.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.get("/purchase-orders/{po_id}")
def get_po(po_id: int, user=Depends(current_user), conn=Depends(get_db)):
    po = not_found(po_with_items(conn, po_id), "Purchase order")
    if user["role"] == "vendor":
        vendor_guard(conn, user, po["vendor_id"])
    else:
        check_project(conn, user, po["project_id"])
    return po


@router.post("/purchase-orders", status_code=201)
def create_po(body: POBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    check_project(conn, user, body.project_id)
    not_found(row(conn, "SELECT id FROM vendors WHERE id = ? AND active = 1", (body.vendor_id,)), "Vendor")
    if body.request_id:
        req = not_found(row(conn, "SELECT * FROM material_requests WHERE id = ?", (body.request_id,)), "Request")
        if req["status"] not in ("approved", "ordered"):
            raise HTTPException(422, "POs can only be raised from approved requests")
    po_id = insert(conn, "purchase_orders", {
        "po_number": next_number(conn, "purchase_orders", "po_number", "PO"),
        "project_id": body.project_id, "vendor_id": body.vendor_id, "request_id": body.request_id,
        "status": "issued", "order_date": body.order_date or date.today().isoformat(),
        "expected_date": body.expected_date, "notes": body.notes, "created_by": user["id"],
    })
    for it in body.items:
        not_found(row(conn, "SELECT id FROM materials WHERE id = ?", (it.material_id,)), "Material")
        insert(conn, "po_items", {"po_id": po_id, **it.model_dump()})
    if body.request_id:
        update(conn, "material_requests", body.request_id, {"status": "ordered"})
    audit(conn, user, "create", "purchase_order", po_id, after=body.model_dump())
    activity(conn, body.project_id, user, "issued PO", "purchase_order", po_id)
    vendor_users = rows(conn, "SELECT id FROM users WHERE vendor_id = ? AND active = 1", (body.vendor_id,))
    notify(conn, [u["id"] for u in vendor_users], "purchase_order", "New purchase order",
           f"PO issued for project #{body.project_id}", "purchase_order", po_id)
    return po_with_items(conn, po_id)


@router.patch("/purchase-orders/{po_id}/status")
def set_po_status(po_id: int, body: POStatusBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    po = not_found(row(conn, "SELECT * FROM purchase_orders WHERE id = ?", (po_id,)), "Purchase order")
    check_project(conn, user, po["project_id"])
    if body.status not in PO_STATUSES:
        raise HTTPException(422, f"status must be one of {PO_STATUSES}")
    update(conn, "purchase_orders", po_id, {"status": body.status})
    audit(conn, user, "status_change", "purchase_order", po_id,
          before={"status": po["status"]}, after={"status": body.status})
    activity(conn, po["project_id"], user, f"PO {body.status}", "purchase_order", po_id)
    return po_with_items(conn, po_id)


# ---------- GRNs ----------

@router.get("/grns")
def list_grns(page: int = 1, limit: int = 25, project_id: int | None = None,
              user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "g.project_id")
    where = [frag]
    if project_id:
        where.append("g.project_id = ?")
        params.append(project_id)
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM grns g WHERE {w}", params)
    data = rows(conn, f"""SELECT g.*, po.po_number, p.name AS project_name, v.name AS vendor_name,
                                 u.name AS received_by_name
                          FROM grns g
                          JOIN purchase_orders po ON po.id = g.po_id
                          JOIN projects p ON p.id = g.project_id
                          JOIN vendors v ON v.id = po.vendor_id
                          LEFT JOIN users u ON u.id = g.received_by
                          WHERE {w} ORDER BY g.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.get("/grns/{gid}")
def get_grn(gid: int, user=Depends(current_user), conn=Depends(get_db)):
    g = not_found(row(conn, """SELECT g.*, po.po_number, p.name AS project_name
                               FROM grns g JOIN purchase_orders po ON po.id = g.po_id
                               JOIN projects p ON p.id = g.project_id WHERE g.id = ?""", (gid,)), "GRN")
    check_project(conn, user, g["project_id"])
    g["items"] = rows(conn, """SELECT gi.*, m.name, m.unit FROM grn_items gi
                               JOIN materials m ON m.id = gi.material_id WHERE gi.grn_id = ?""", (gid,))
    return g


@router.post("/grns", status_code=201)
def create_grn(body: GRNBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    po = not_found(row(conn, "SELECT * FROM purchase_orders WHERE id = ?", (body.po_id,)), "Purchase order")
    check_project(conn, user, po["project_id"])
    if po["status"] in ("draft", "cancelled", "closed"):
        raise HTTPException(422, f"Cannot receive against a {po['status']} PO")
    gid = insert(conn, "grns", {
        "grn_number": next_number(conn, "grns", "grn_number", "GRN"),
        "po_id": body.po_id, "project_id": po["project_id"],
        "received_date": body.received_date or date.today().isoformat(),
        "vehicle_no": body.vehicle_no, "notes": body.notes, "received_by": user["id"],
    })
    for it in body.items:
        po_item = not_found(row(conn, "SELECT * FROM po_items WHERE id = ? AND po_id = ?",
                                (it.po_item_id, body.po_id)), "PO line")
        remaining = po_item["qty"] - po_item["received_qty"]
        if it.qty_received > remaining + 1e-9:
            raise HTTPException(422, f"Line {it.po_item_id}: receiving {it.qty_received} exceeds remaining {remaining}")
        insert(conn, "grn_items", {"grn_id": gid, "po_item_id": it.po_item_id,
                                   "material_id": po_item["material_id"],
                                   "qty_received": it.qty_received, "remarks": it.remarks})
        conn.execute("UPDATE po_items SET received_qty = received_qty + ? WHERE id = ?",
                     (it.qty_received, it.po_item_id))
        adjust_stock(conn, po["project_id"], po_item["material_id"], it.qty_received)
    fully = scalar(conn, "SELECT COUNT(*) FROM po_items WHERE po_id = ? AND received_qty < qty - 1e-9", (body.po_id,)) == 0
    update(conn, "purchase_orders", body.po_id, {"status": "received" if fully else "partially_received"})
    if po["request_id"] and fully:
        update(conn, "material_requests", po["request_id"], {"status": "fulfilled"})
    audit(conn, user, "create", "grn", gid, after=body.model_dump())
    activity(conn, po["project_id"], user, "recorded GRN", "grn", gid)
    return get_grn(gid, user, conn)


# ---------- usage ----------

@router.get("/projects/{pid}/usage")
def list_usage(pid: int, page: int = 1, limit: int = 50, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    total = scalar(conn, "SELECT COUNT(*) FROM material_usage WHERE project_id = ?", (pid,))
    data = rows(conn, """SELECT mu.*, m.name, m.unit, t.name AS task_name, u.name AS logged_by_name
                         FROM material_usage mu
                         JOIN materials m ON m.id = mu.material_id
                         LEFT JOIN tasks t ON t.id = mu.task_id
                         LEFT JOIN users u ON u.id = mu.logged_by
                         WHERE mu.project_id = ? ORDER BY mu.usage_date DESC, mu.id DESC
                         LIMIT ? OFFSET ?""", (pid, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/material-usage", status_code=201)
def log_usage(body: UsageBody, user=Depends(require("pm", "site", "store")), conn=Depends(get_db)):
    check_project(conn, user, body.project_id)
    stock = row(conn, "SELECT * FROM stock WHERE project_id = ? AND material_id = ?",
                (body.project_id, body.material_id))
    available = stock["qty"] if stock else 0
    if body.qty > available + 1e-9:
        raise HTTPException(422, f"Only {available} in stock at this site")
    uid = insert(conn, "material_usage", {**body.model_dump(),
                                          "usage_date": body.usage_date or date.today().isoformat(),
                                          "logged_by": user["id"]})
    new_qty = adjust_stock(conn, body.project_id, body.material_id, -body.qty)
    activity(conn, body.project_id, user, "logged material usage", "material_usage", uid)
    if stock and new_qty < stock["min_level"]:
        notify_roles(conn, ["pm", "store"], "stock", "Stock below minimum",
                     f"Material #{body.material_id} at project #{body.project_id}: {new_qty} left",
                     "stock", stock["id"], project_id=body.project_id)
    return row(conn, "SELECT * FROM material_usage WHERE id = ?", (uid,))


# ---------- requested vs received vs used ----------

@router.get("/projects/{pid}/material-summary")
def material_summary(pid: int, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    data = rows(conn, """
        SELECT m.id, m.name, m.unit,
          COALESCE((SELECT SUM(i.qty) FROM material_request_items i
                    JOIN material_requests r ON r.id = i.request_id
                    WHERE r.project_id = ? AND i.material_id = m.id AND r.status != 'rejected'), 0) AS requested,
          COALESCE((SELECT SUM(i.qty) FROM po_items i
                    JOIN purchase_orders po ON po.id = i.po_id
                    WHERE po.project_id = ? AND i.material_id = m.id
                      AND po.status NOT IN ('draft','cancelled')), 0) AS ordered,
          COALESCE((SELECT SUM(gi.qty_received) FROM grn_items gi
                    JOIN grns g ON g.id = gi.grn_id
                    WHERE g.project_id = ? AND gi.material_id = m.id), 0) AS received,
          COALESCE((SELECT SUM(u.qty) FROM material_usage u
                    WHERE u.project_id = ? AND u.material_id = m.id), 0) AS used,
          COALESCE((SELECT s.qty FROM stock s
                    WHERE s.project_id = ? AND s.material_id = m.id), 0) AS in_stock
        FROM materials m
        WHERE requested > 0 OR ordered > 0 OR received > 0 OR used > 0 OR in_stock > 0
        ORDER BY m.name""", (pid, pid, pid, pid, pid))
    return {"data": data}
