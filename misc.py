"""Comments, notifications, equipment register, safety/quality checklists."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, insert, row, rows, scalar, update
from ..helpers import activity, audit, notify, not_found, pagination
from ..security import check_project, current_user, require

router = APIRouter(prefix="/api", tags=["misc"])

COMMENT_ENTITIES = ("task", "issue", "material_request", "purchase_order", "invoice",
                    "project", "document", "equipment", "checklist")

# entity_type -> (table, project column or None)
ENTITY_TABLES = {
    "task": ("tasks", "project_id"), "issue": ("issues", "project_id"),
    "material_request": ("material_requests", "project_id"),
    "purchase_order": ("purchase_orders", "project_id"),
    "invoice": ("invoices", "project_id"), "project": ("projects", "id"),
    "document": ("documents", "project_id"), "equipment": ("equipment", None),
    "checklist": ("checklists", "project_id"),
}


class CommentBody(BaseModel):
    entity_type: str
    entity_id: int
    body: str = Field(min_length=1, max_length=4000)


class EquipmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = None
    category: str | None = None
    project_id: int | None = None
    status: str = "available"
    maintenance_interval_hours: float = Field(default=0, ge=0)
    notes: str | None = None


class EquipmentLogBody(BaseModel):
    project_id: int | None = None
    log_date: str | None = None
    hours_used: float = Field(default=0, ge=0)
    is_maintenance: bool = False
    notes: str | None = None


class ChecklistItemBody(BaseModel):
    item: str = Field(min_length=1)
    outcome: str = "na"
    remarks: str | None = None


class ChecklistBody(BaseModel):
    ctype: str = "safety"
    title: str = Field(min_length=1, max_length=200)
    check_date: str | None = None
    status: str = "open"
    notes: str | None = None
    items: list[ChecklistItemBody] = Field(default_factory=list)


def check_entity_access(conn, user, entity_type, entity_id):
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(422, f"entity_type must be one of {COMMENT_ENTITIES}")
    table, pcol = ENTITY_TABLES[entity_type]
    rec = not_found(row(conn, f"SELECT * FROM {table} WHERE id = ?", (entity_id,)), entity_type)
    if pcol and user["role"] != "vendor":
        check_project(conn, user, rec[pcol] if pcol != "id" else rec["id"])
    if user["role"] == "vendor" and rec.get("vendor_id") != user.get("vendor_id"):
        raise HTTPException(403, "Vendors can only comment on their own records")
    return rec


# ---------- comments ----------

@router.get("/comments")
def list_comments(entity_type: str, entity_id: int, user=Depends(current_user), conn=Depends(get_db)):
    check_entity_access(conn, user, entity_type, entity_id)
    data = rows(conn, """SELECT c.*, u.name AS user_name, u.role AS user_role FROM comments c
                         JOIN users u ON u.id = c.user_id
                         WHERE c.entity_type = ? AND c.entity_id = ? ORDER BY c.id""",
                (entity_type, entity_id))
    return {"data": data}


@router.post("/comments", status_code=201)
def create_comment(body: CommentBody, user=Depends(current_user), conn=Depends(get_db)):
    rec = check_entity_access(conn, user, body.entity_type, body.entity_id)
    cid = insert(conn, "comments", {"entity_type": body.entity_type, "entity_id": body.entity_id,
                                    "user_id": user["id"], "body": body.body})
    # Notify other participants of the thread + record owner.
    participants = {c["user_id"] for c in rows(
        conn, "SELECT DISTINCT user_id FROM comments WHERE entity_type = ? AND entity_id = ?",
        (body.entity_type, body.entity_id))}
    for key in ("created_by", "requested_by", "raised_by", "assignee_id", "assigned_to"):
        if rec.get(key):
            participants.add(rec[key])
    notify(conn, participants, "comment", f"New comment on {body.entity_type.replace('_', ' ')} #{body.entity_id}",
           body.body[:200], body.entity_type, body.entity_id, exclude=user["id"])
    pcol = ENTITY_TABLES[body.entity_type][1]
    if pcol:
        activity(conn, rec[pcol] if pcol != "id" else rec["id"], user,
                 f"commented on {body.entity_type.replace('_', ' ')}", body.entity_type, body.entity_id)
    return row(conn, "SELECT c.*, u.name AS user_name FROM comments c JOIN users u ON u.id = c.user_id WHERE c.id = ?", (cid,))


# ---------- notifications ----------

@router.get("/notifications")
def list_notifications(page: int = 1, limit: int = 30, unread_only: int = 0,
                       user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    where = "user_id = ?" + (" AND is_read = 0" if unread_only else "")
    total = scalar(conn, f"SELECT COUNT(*) FROM notifications WHERE {where}", (user["id"],))
    unread = scalar(conn, "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user["id"],))
    data = rows(conn, f"SELECT * FROM notifications WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (user["id"], limit, offset))
    return {"data": data, "total": total, "unread": unread, "page": page, "limit": limit}


class MarkReadBody(BaseModel):
    ids: list[int] | None = None  # None = mark all


@router.post("/notifications/read")
def mark_read(body: MarkReadBody, user=Depends(current_user), conn=Depends(get_db)):
    if body.ids:
        ph = ",".join("?" * len(body.ids))
        conn.execute(f"UPDATE notifications SET is_read = 1 WHERE user_id = ? AND id IN ({ph})",
                     (user["id"], *body.ids))
    else:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
    return {"ok": True}


# ---------- equipment ----------

def equipment_view(e):
    due = bool(e["maintenance_interval_hours"] and
               e["usage_hours"] - e["hours_at_last_maintenance"] >= e["maintenance_interval_hours"])
    return {**e, "maintenance_due": due,
            "hours_since_maintenance": round(e["usage_hours"] - e["hours_at_last_maintenance"], 1)}


@router.get("/equipment")
def list_equipment(page: int = 1, limit: int = 50, project_id: int | None = None,
                   user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    where, params = "1=1", []
    if project_id:
        where, params = "e.project_id = ?", [project_id]
    total = scalar(conn, f"SELECT COUNT(*) FROM equipment e WHERE {where}", params)
    data = rows(conn, f"""SELECT e.*, p.name AS project_name FROM equipment e
                          LEFT JOIN projects p ON p.id = e.project_id
                          WHERE {where} ORDER BY e.name LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": [equipment_view(e) for e in data], "total": total, "page": page, "limit": limit}


@router.post("/equipment", status_code=201)
def create_equipment(body: EquipmentBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    eid = insert(conn, "equipment", body.model_dump())
    audit(conn, user, "create", "equipment", eid, after=body.model_dump())
    return equipment_view(row(conn, "SELECT * FROM equipment WHERE id = ?", (eid,)))


@router.patch("/equipment/{eid}")
def update_equipment(eid: int, body: EquipmentBody, user=Depends(require("pm", "store")), conn=Depends(get_db)):
    not_found(row(conn, "SELECT id FROM equipment WHERE id = ?", (eid,)), "Equipment")
    update(conn, "equipment", eid, body.model_dump())
    return equipment_view(row(conn, "SELECT * FROM equipment WHERE id = ?", (eid,)))


@router.post("/equipment/{eid}/logs", status_code=201)
def log_equipment(eid: int, body: EquipmentLogBody, user=Depends(require("pm", "site", "store")), conn=Depends(get_db)):
    e = not_found(row(conn, "SELECT * FROM equipment WHERE id = ?", (eid,)), "Equipment")
    d = body.log_date or date.today().isoformat()
    insert(conn, "equipment_logs", {"equipment_id": eid, "project_id": body.project_id or e["project_id"],
                                    "log_date": d, "hours_used": body.hours_used,
                                    "is_maintenance": 1 if body.is_maintenance else 0,
                                    "notes": body.notes, "logged_by": user["id"]})
    data = {"usage_hours": e["usage_hours"] + body.hours_used}
    if body.is_maintenance:
        data["hours_at_last_maintenance"] = e["usage_hours"] + body.hours_used
        data["last_maintenance_date"] = d
    update(conn, "equipment", eid, data)
    return equipment_view(row(conn, "SELECT * FROM equipment WHERE id = ?", (eid,)))


@router.get("/equipment/{eid}/logs")
def equipment_logs(eid: int, user=Depends(current_user), conn=Depends(get_db)):
    not_found(row(conn, "SELECT id FROM equipment WHERE id = ?", (eid,)), "Equipment")
    data = rows(conn, """SELECT el.*, u.name AS logged_by_name, p.name AS project_name
                         FROM equipment_logs el
                         LEFT JOIN users u ON u.id = el.logged_by
                         LEFT JOIN projects p ON p.id = el.project_id
                         WHERE el.equipment_id = ? ORDER BY el.log_date DESC, el.id DESC LIMIT 200""", (eid,))
    return {"data": data}


# ---------- safety / quality checklists ----------

@router.get("/projects/{pid}/checklists")
def list_checklists(pid: int, page: int = 1, limit: int = 50, ctype: str | None = None,
                    user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where, params = "c.project_id = ?", [pid]
    if ctype:
        where += " AND c.ctype = ?"
        params.append(ctype)
    total = scalar(conn, f"SELECT COUNT(*) FROM checklists c WHERE {where}", params)
    data = rows(conn, f"""SELECT c.*, u.name AS inspector_name,
                                 (SELECT COUNT(*) FROM checklist_items i WHERE i.checklist_id = c.id) AS item_count,
                                 (SELECT COUNT(*) FROM checklist_items i WHERE i.checklist_id = c.id AND i.outcome = 'fail') AS failed_count
                          FROM checklists c LEFT JOIN users u ON u.id = c.inspector_id
                          WHERE {where} ORDER BY c.check_date DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/checklists", status_code=201)
def create_checklist(pid: int, body: ChecklistBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if body.ctype not in ("safety", "quality"):
        raise HTTPException(422, "ctype must be safety or quality")
    cid = insert(conn, "checklists", {"project_id": pid, "ctype": body.ctype, "title": body.title,
                                      "check_date": body.check_date or date.today().isoformat(),
                                      "inspector_id": user["id"], "status": body.status, "notes": body.notes})
    for it in body.items:
        insert(conn, "checklist_items", {"checklist_id": cid, **it.model_dump()})
    activity(conn, pid, user, f"created {body.ctype} checklist", "checklist", cid, body.title)
    return get_checklist(cid, user, conn)


@router.get("/checklists/{cid}")
def get_checklist(cid: int, user=Depends(current_user), conn=Depends(get_db)):
    c = not_found(row(conn, "SELECT * FROM checklists WHERE id = ?", (cid,)), "Checklist")
    check_project(conn, user, c["project_id"])
    c["items"] = rows(conn, "SELECT * FROM checklist_items WHERE checklist_id = ? ORDER BY id", (cid,))
    return c


@router.patch("/checklists/{cid}")
def update_checklist(cid: int, body: ChecklistBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    c = not_found(row(conn, "SELECT * FROM checklists WHERE id = ?", (cid,)), "Checklist")
    check_project(conn, user, c["project_id"])
    update(conn, "checklists", cid, {"ctype": body.ctype, "title": body.title,
                                     "check_date": body.check_date or c["check_date"],
                                     "status": body.status, "notes": body.notes})
    if body.items:
        conn.execute("DELETE FROM checklist_items WHERE checklist_id = ?", (cid,))
        for it in body.items:
            insert(conn, "checklist_items", {"checklist_id": cid, **it.model_dump()})
    return get_checklist(cid, user, conn)
