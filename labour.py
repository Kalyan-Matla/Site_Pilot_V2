"""Labour registry, daily attendance, wage computation and summaries."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db, insert, row, rows, scalar, update
from ..helpers import activity, audit, not_found, pagination
from ..security import check_project, current_user, project_filter, require

router = APIRouter(prefix="/api", tags=["labour"])

CATEGORIES = ("skilled", "semi_skilled", "unskilled", "staff")
ATT_STATUSES = ("present", "absent", "half_day")

PAY_EXPR = """SUM(CASE a.status WHEN 'present' THEN l.base_rate
                                WHEN 'half_day' THEN l.base_rate / 2 ELSE 0 END
                  + a.ot_hours * l.ot_rate)"""
DAYS_EXPR = "SUM(CASE a.status WHEN 'present' THEN 1 WHEN 'half_day' THEN 0.5 ELSE 0 END)"


class LabourerBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = "unskilled"
    vendor_id: int | None = None
    base_rate: float = Field(default=0, ge=0)
    ot_rate: float = Field(default=0, ge=0)
    active: bool = True


class AttendanceEntry(BaseModel):
    labourer_id: int
    status: str = "present"
    ot_hours: float = Field(default=0, ge=0, le=16)


class AttendanceBody(BaseModel):
    att_date: str
    entries: list[AttendanceEntry] = Field(min_length=1)


@router.get("/projects/{pid}/labourers")
def list_labourers(pid: int, page: int = 1, limit: int = 100, active_only: int = 1,
                   user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where = "l.project_id = ?" + (" AND l.active = 1" if active_only else "")
    total = scalar(conn, f"SELECT COUNT(*) FROM labourers l WHERE {where}", (pid,))
    data = rows(conn, f"""SELECT l.*, v.name AS vendor_name FROM labourers l
                          LEFT JOIN vendors v ON v.id = l.vendor_id
                          WHERE {where} ORDER BY l.name LIMIT ? OFFSET ?""", (pid, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/labourers", status_code=201)
def create_labourer(pid: int, body: LabourerBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if body.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    lid = insert(conn, "labourers", {**body.model_dump(), "project_id": pid, "active": 1 if body.active else 0})
    audit(conn, user, "create", "labourer", lid, after=body.model_dump())
    activity(conn, pid, user, "added labourer", "labourer", lid, body.name)
    return row(conn, "SELECT * FROM labourers WHERE id = ?", (lid,))


@router.patch("/labourers/{lid}")
def update_labourer(lid: int, body: LabourerBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    l = not_found(row(conn, "SELECT * FROM labourers WHERE id = ?", (lid,)), "Labourer")
    check_project(conn, user, l["project_id"])
    if body.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    update(conn, "labourers", lid, {**body.model_dump(), "active": 1 if body.active else 0})
    return row(conn, "SELECT * FROM labourers WHERE id = ?", (lid,))


@router.get("/projects/{pid}/attendance")
def get_attendance(pid: int, att_date: str | None = None, date_from: str | None = None,
                   date_to: str | None = None, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if att_date:
        date_from = date_to = att_date
    date_from = date_from or date.today().isoformat()
    date_to = date_to or date_from
    data = rows(conn, """SELECT a.*, l.name, l.category, l.vendor_id, v.name AS vendor_name
                         FROM attendance a
                         JOIN labourers l ON l.id = a.labourer_id
                         LEFT JOIN vendors v ON v.id = l.vendor_id
                         WHERE a.project_id = ? AND a.att_date BETWEEN ? AND ?
                         ORDER BY a.att_date DESC, l.name""", (pid, date_from, date_to))
    return {"data": data, "date_from": date_from, "date_to": date_to}


@router.post("/projects/{pid}/attendance")
def mark_attendance(pid: int, body: AttendanceBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    saved = 0
    for e in body.entries:
        if e.status not in ATT_STATUSES:
            raise HTTPException(422, f"status must be one of {ATT_STATUSES}")
        lab = row(conn, "SELECT id FROM labourers WHERE id = ? AND project_id = ?", (e.labourer_id, pid))
        if not lab:
            raise HTTPException(422, f"Labourer {e.labourer_id} does not belong to this project")
        conn.execute("""INSERT INTO attendance (project_id, labourer_id, att_date, status, ot_hours, marked_by)
                        VALUES (?,?,?,?,?,?)
                        ON CONFLICT (labourer_id, att_date)
                        DO UPDATE SET status = excluded.status, ot_hours = excluded.ot_hours,
                                      marked_by = excluded.marked_by""",
                     (pid, e.labourer_id, body.att_date, e.status, e.ot_hours, user["id"]))
        saved += 1
    activity(conn, pid, user, f"marked attendance for {saved} labourer(s) on {body.att_date}")
    return {"ok": True, "saved": saved}


@router.get("/projects/{pid}/labour-payable")
def labour_payable(pid: int, date_from: str, date_to: str,
                   user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    by_labourer = rows(conn, f"""
        SELECT l.id, l.name, l.category, v.name AS vendor_name,
               {DAYS_EXPR} AS days_worked, SUM(a.ot_hours) AS ot_hours,
               ROUND({PAY_EXPR}, 2) AS payable
        FROM attendance a JOIN labourers l ON l.id = a.labourer_id
        LEFT JOIN vendors v ON v.id = l.vendor_id
        WHERE a.project_id = ? AND a.att_date BETWEEN ? AND ?
        GROUP BY l.id, v.name ORDER BY l.name""", (pid, date_from, date_to))
    by_vendor = rows(conn, f"""
        SELECT COALESCE(v.name, 'In-house') AS vendor, COUNT(DISTINCT l.id) AS labourers,
               {DAYS_EXPR} AS days_worked, ROUND({PAY_EXPR}, 2) AS payable
        FROM attendance a JOIN labourers l ON l.id = a.labourer_id
        LEFT JOIN vendors v ON v.id = l.vendor_id
        WHERE a.project_id = ? AND a.att_date BETWEEN ? AND ?
        GROUP BY l.vendor_id, v.name ORDER BY vendor""", (pid, date_from, date_to))
    total = sum(r["payable"] or 0 for r in by_labourer)
    return {"by_labourer": by_labourer, "by_vendor": by_vendor, "total_payable": round(total, 2),
            "date_from": date_from, "date_to": date_to}


@router.get("/labour-summary")
def labour_summary(date_from: str, date_to: str, user=Depends(current_user), conn=Depends(get_db)):
    """Cross-project labour summary, grouped by project and vendor."""
    frag, params = project_filter(conn, user, "a.project_id")
    data = rows(conn, f"""
        SELECT p.name AS project, COALESCE(v.name, 'In-house') AS vendor,
               COUNT(DISTINCT l.id) AS labourers, {DAYS_EXPR} AS days_worked,
               SUM(a.ot_hours) AS ot_hours, ROUND({PAY_EXPR}, 2) AS payable
        FROM attendance a
        JOIN labourers l ON l.id = a.labourer_id
        JOIN projects p ON p.id = a.project_id
        LEFT JOIN vendors v ON v.id = l.vendor_id
        WHERE {frag} AND a.att_date BETWEEN ? AND ?
        GROUP BY a.project_id, p.name, l.vendor_id, v.name ORDER BY p.name, vendor""",
        (*params, date_from, date_to))
    return {"data": data, "date_from": date_from, "date_to": date_to}
