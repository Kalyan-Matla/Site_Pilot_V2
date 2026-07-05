"""Projects, membership, tasks, issues, progress logs, DPR/WPR, activity feed."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..db import get_db, insert, row, rows, scalar, update
from ..helpers import activity, audit, notify, notify_roles, not_found, pagination
from ..security import (check_project, current_user, project_filter, require)
from ..storage import download_response, save_file

router = APIRouter(prefix="/api", tags=["projects"])

PROJECT_STATUSES = ("planned", "active", "on_hold", "completed", "cancelled")
TASK_STATUSES = ("todo", "in_progress", "done", "blocked")


# ---------- models ----------

class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str = "planned"
    description: str | None = None
    budget: float = Field(default=0, ge=0)
    contract_value: float = Field(default=0, ge=0)


class TaskBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_milestone: bool = False
    planned_start: str | None = None
    planned_end: str | None = None
    actual_start: str | None = None
    actual_end: str | None = None
    status: str = "todo"
    assignee_id: int | None = None
    progress_pct: float = Field(default=0, ge=0, le=100)
    weight: float = Field(default=1, gt=0)


class IssueBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    task_id: int | None = None
    severity: str = "medium"
    status: str = "open"
    assigned_to: int | None = None


class ProgressBody(BaseModel):
    task_id: int | None = None
    log_date: str
    work_description: str | None = None
    quantity_done: float | None = None
    unit: str | None = None
    labour_count: int | None = None
    notes: str | None = None
    issues_text: str | None = None


class MemberBody(BaseModel):
    user_id: int


# ---------- metrics ----------

def project_metrics(conn, pid):
    today = date.today().isoformat()
    progress = scalar(conn, """SELECT SUM(progress_pct * weight) / NULLIF(SUM(weight), 0)
                               FROM tasks WHERE project_id = ?""", (pid,), default=0) or 0
    return {
        "progress_pct": round(progress, 1),
        "tasks_total": scalar(conn, "SELECT COUNT(*) FROM tasks WHERE project_id = ?", (pid,)),
        "tasks_done": scalar(conn, "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = 'done'", (pid,)),
        "tasks_delayed": scalar(conn, """SELECT COUNT(*) FROM tasks WHERE project_id = ?
                                         AND status != 'done' AND planned_end IS NOT NULL AND planned_end < ?""",
                                (pid, today)),
        "open_issues": scalar(conn, "SELECT COUNT(*) FROM issues WHERE project_id = ? AND status IN ('open','in_progress')", (pid,)),
        "po_committed": scalar(conn, """SELECT SUM(i.qty * i.rate) FROM po_items i
                                        JOIN purchase_orders p ON p.id = i.po_id
                                        WHERE p.project_id = ? AND p.status NOT IN ('draft','cancelled')""", (pid,)),
        "invoiced": scalar(conn, "SELECT SUM(total_amount) FROM invoices WHERE project_id = ? AND status != 'rejected'", (pid,)),
        "paid": scalar(conn, "SELECT SUM(amount) FROM payments WHERE project_id = ?", (pid,)),
    }


def labour_cost(conn, pid, d_from=None, d_to=None):
    where, params = "a.project_id = ?", [pid]
    if d_from:
        where += " AND a.att_date >= ?"
        params.append(d_from)
    if d_to:
        where += " AND a.att_date <= ?"
        params.append(d_to)
    return scalar(conn, f"""
        SELECT SUM(CASE a.status WHEN 'present' THEN l.base_rate WHEN 'half_day' THEN l.base_rate / 2 ELSE 0 END
                   + a.ot_hours * l.ot_rate)
        FROM attendance a JOIN labourers l ON l.id = a.labourer_id WHERE {where}""", params, default=0) or 0


# ---------- projects ----------

@router.get("/projects")
def list_projects(page: int = 1, limit: int = 25, status: str | None = None, q: str | None = None,
                  user=Depends(current_user), conn=Depends(get_db)):
    page, limit, offset = pagination(page, limit)
    frag, params = project_filter(conn, user, "id")
    where = [frag]
    if status:
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("(name LIKE ? OR client_name LIKE ? OR location LIKE ?)")
        params += [f"%{q}%"] * 3
    w = " AND ".join(where)
    total = scalar(conn, f"SELECT COUNT(*) FROM projects WHERE {w}", params)
    data = rows(conn, f"SELECT * FROM projects WHERE {w} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset))
    for p in data:
        p["metrics"] = project_metrics(conn, p["id"])
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects", status_code=201)
def create_project(body: ProjectBody, user=Depends(require("pm")), conn=Depends(get_db)):
    if body.status not in PROJECT_STATUSES:
        raise HTTPException(422, f"status must be one of {PROJECT_STATUSES}")
    pid = insert(conn, "projects", {**body.model_dump(), "created_by": user["id"]})
    if user["role"] != "owner":
        insert(conn, "project_members", {"project_id": pid, "user_id": user["id"]})
    audit(conn, user, "create", "project", pid, after=body.model_dump())
    activity(conn, pid, user, "created project", "project", pid, body.name)
    return row(conn, "SELECT * FROM projects WHERE id = ?", (pid,))


@router.get("/projects/{pid}")
def get_project(pid: int, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    p = row(conn, "SELECT * FROM projects WHERE id = ?", (pid,))
    p["metrics"] = project_metrics(conn, pid)
    p["metrics"]["labour_cost"] = round(labour_cost(conn, pid), 2)
    p["members"] = rows(conn, """SELECT pm.id, u.id AS user_id, u.name, u.role FROM project_members pm
                                 JOIN users u ON u.id = pm.user_id WHERE pm.project_id = ? ORDER BY u.name""", (pid,))
    return p


@router.patch("/projects/{pid}")
def update_project(pid: int, body: ProjectBody, user=Depends(require("pm")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    before = not_found(row(conn, "SELECT * FROM projects WHERE id = ?", (pid,)), "Project")
    if body.status not in PROJECT_STATUSES:
        raise HTTPException(422, f"status must be one of {PROJECT_STATUSES}")
    update(conn, "projects", pid, body.model_dump())
    audit(conn, user, "update", "project", pid, before=before, after=body.model_dump())
    activity(conn, pid, user, "updated project", "project", pid)
    return row(conn, "SELECT * FROM projects WHERE id = ?", (pid,))


@router.delete("/projects/{pid}")
def delete_project(pid: int, user=Depends(require()), conn=Depends(get_db)):
    before = not_found(row(conn, "SELECT * FROM projects WHERE id = ?", (pid,)), "Project")
    conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
    audit(conn, user, "delete", "project", pid, before=before)
    return {"ok": True}


@router.post("/projects/{pid}/members", status_code=201)
def add_member(pid: int, body: MemberBody, user=Depends(require("pm")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    member = not_found(row(conn, "SELECT id, name FROM users WHERE id = ? AND active = 1", (body.user_id,)), "User")
    if row(conn, "SELECT id FROM project_members WHERE project_id = ? AND user_id = ?", (pid, body.user_id)):
        raise HTTPException(409, "User already assigned")
    insert(conn, "project_members", {"project_id": pid, "user_id": body.user_id})
    notify(conn, [body.user_id], "project", "Added to project",
           f"You were assigned to project #{pid}", "project", pid)
    activity(conn, pid, user, "added member", "user", body.user_id, member["name"])
    return {"ok": True}


@router.delete("/projects/{pid}/members/{user_id}")
def remove_member(pid: int, user_id: int, user=Depends(require("pm")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    conn.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (pid, user_id))
    activity(conn, pid, user, "removed member", "user", user_id)
    return {"ok": True}


# ---------- tasks ----------

@router.get("/projects/{pid}/tasks")
def list_tasks(pid: int, page: int = 1, limit: int = 100, status: str | None = None,
               user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where, params = "t.project_id = ?", [pid]
    if status:
        where += " AND t.status = ?"
        params.append(status)
    total = scalar(conn, f"SELECT COUNT(*) FROM tasks t WHERE {where}", params)
    data = rows(conn, f"""SELECT t.*, u.name AS assignee_name FROM tasks t
                          LEFT JOIN users u ON u.id = t.assignee_id
                          WHERE {where} ORDER BY t.planned_start IS NULL, t.planned_start, t.id
                          LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/tasks", status_code=201)
def create_task(pid: int, body: TaskBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if body.status not in TASK_STATUSES:
        raise HTTPException(422, f"status must be one of {TASK_STATUSES}")
    tid = insert(conn, "tasks", {**body.model_dump(), "is_milestone": 1 if body.is_milestone else 0, "project_id": pid})
    if body.assignee_id:
        notify(conn, [body.assignee_id], "task", "New task assigned", body.name, "task", tid, exclude=user["id"])
    activity(conn, pid, user, "created task", "task", tid, body.name)
    return row(conn, "SELECT * FROM tasks WHERE id = ?", (tid,))


@router.patch("/tasks/{tid}")
def update_task(tid: int, body: TaskBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    t = not_found(row(conn, "SELECT * FROM tasks WHERE id = ?", (tid,)), "Task")
    check_project(conn, user, t["project_id"])
    if body.status not in TASK_STATUSES:
        raise HTTPException(422, f"status must be one of {TASK_STATUSES}")
    data = {**body.model_dump(), "is_milestone": 1 if body.is_milestone else 0}
    if body.status == "done" and t["status"] != "done":
        data["progress_pct"] = 100
        data.setdefault("actual_end", None)
        data["actual_end"] = body.actual_end or date.today().isoformat()
    update(conn, "tasks", tid, data)
    if body.assignee_id and body.assignee_id != t["assignee_id"]:
        notify(conn, [body.assignee_id], "task", "Task assigned to you", body.name, "task", tid, exclude=user["id"])
    elif body.status != t["status"] and t["assignee_id"]:
        notify(conn, [t["assignee_id"]], "task", f"Task status: {body.status}", body.name, "task", tid, exclude=user["id"])
    activity(conn, t["project_id"], user, f"updated task ({body.status})", "task", tid, body.name)
    return row(conn, "SELECT * FROM tasks WHERE id = ?", (tid,))


@router.delete("/tasks/{tid}")
def delete_task(tid: int, user=Depends(require("pm")), conn=Depends(get_db)):
    t = not_found(row(conn, "SELECT * FROM tasks WHERE id = ?", (tid,)), "Task")
    check_project(conn, user, t["project_id"])
    conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))
    activity(conn, t["project_id"], user, "deleted task", "task", tid, t["name"])
    return {"ok": True}


# ---------- issues ----------

@router.get("/projects/{pid}/issues")
def list_issues(pid: int, page: int = 1, limit: int = 50, status: str | None = None,
                user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where, params = "i.project_id = ?", [pid]
    if status:
        where += " AND i.status = ?"
        params.append(status)
    total = scalar(conn, f"SELECT COUNT(*) FROM issues i WHERE {where}", params)
    data = rows(conn, f"""SELECT i.*, ur.name AS raised_by_name, ua.name AS assigned_to_name, t.name AS task_name
                          FROM issues i
                          LEFT JOIN users ur ON ur.id = i.raised_by
                          LEFT JOIN users ua ON ua.id = i.assigned_to
                          LEFT JOIN tasks t ON t.id = i.task_id
                          WHERE {where} ORDER BY i.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/issues", status_code=201)
def create_issue(pid: int, body: IssueBody, user=Depends(require("pm", "site", "store")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    iid = insert(conn, "issues", {**body.model_dump(), "project_id": pid, "raised_by": user["id"]})
    notify_roles(conn, ["owner", "pm"], "issue", f"New issue: {body.title}",
                 f"Severity {body.severity}", "issue", iid, project_id=pid, exclude=user["id"])
    if body.assigned_to:
        notify(conn, [body.assigned_to], "issue", "Issue assigned to you", body.title, "issue", iid, exclude=user["id"])
    activity(conn, pid, user, "raised issue", "issue", iid, body.title)
    return row(conn, "SELECT * FROM issues WHERE id = ?", (iid,))


@router.patch("/issues/{iid}")
def update_issue(iid: int, body: IssueBody, user=Depends(require("pm", "site", "store")), conn=Depends(get_db)):
    i = not_found(row(conn, "SELECT * FROM issues WHERE id = ?", (iid,)), "Issue")
    check_project(conn, user, i["project_id"])
    data = body.model_dump()
    if body.status in ("resolved", "closed") and i["status"] not in ("resolved", "closed"):
        data["resolved_at"] = datetime.utcnow().isoformat(timespec="seconds")
    update(conn, "issues", iid, data)
    if i["raised_by"]:
        notify(conn, [i["raised_by"]], "issue", f"Issue {body.status}: {body.title}", None, "issue", iid, exclude=user["id"])
    activity(conn, i["project_id"], user, f"updated issue ({body.status})", "issue", iid, body.title)
    return row(conn, "SELECT * FROM issues WHERE id = ?", (iid,))


# ---------- progress logs ----------

@router.get("/projects/{pid}/progress")
def list_progress(pid: int, page: int = 1, limit: int = 50, date_from: str | None = None,
                  date_to: str | None = None, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where, params = "p.project_id = ?", [pid]
    if date_from:
        where += " AND p.log_date >= ?"
        params.append(date_from)
    if date_to:
        where += " AND p.log_date <= ?"
        params.append(date_to)
    total = scalar(conn, f"SELECT COUNT(*) FROM progress_logs p WHERE {where}", params)
    data = rows(conn, f"""SELECT p.*, t.name AS task_name, u.name AS created_by_name
                          FROM progress_logs p
                          LEFT JOIN tasks t ON t.id = p.task_id
                          LEFT JOIN users u ON u.id = p.created_by
                          WHERE {where} ORDER BY p.log_date DESC, p.id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset))
    for d in data:
        d["photos"] = rows(conn, "SELECT id, original_name FROM progress_photos WHERE progress_log_id = ?", (d["id"],))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/progress", status_code=201)
def create_progress(pid: int, body: ProgressBody, user=Depends(require("pm", "site")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    lid = insert(conn, "progress_logs", {**body.model_dump(), "project_id": pid, "created_by": user["id"]})
    activity(conn, pid, user, "logged progress", "progress_log", lid, body.work_description)
    return row(conn, "SELECT * FROM progress_logs WHERE id = ?", (lid,))


@router.post("/progress/{lid}/photos", status_code=201)
def upload_progress_photo(lid: int, file: UploadFile = File(...),
                          user=Depends(require("pm", "site")), conn=Depends(get_db)):
    log = not_found(row(conn, "SELECT * FROM progress_logs WHERE id = ?", (lid,)), "Progress log")
    check_project(conn, user, log["project_id"])
    safe = "".join(c for c in (file.filename or "photo") if c.isalnum() or c in "._-")[:80]
    name = f"progress_{lid}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe}"
    handle = save_file(file.file.read(), name)
    photo_id = insert(conn, "progress_photos", {
        "progress_log_id": lid, "file_path": handle, "original_name": file.filename})
    return {"id": photo_id, "original_name": file.filename}


@router.get("/progress-photos/{photo_id}")
def get_progress_photo(photo_id: int, user=Depends(current_user), conn=Depends(get_db)):
    p = not_found(row(conn, """SELECT pp.*, pl.project_id FROM progress_photos pp
                               JOIN progress_logs pl ON pl.id = pp.progress_log_id
                               WHERE pp.id = ?""", (photo_id,)), "Photo")
    check_project(conn, user, p["project_id"])
    return download_response(p["file_path"], p["original_name"])


# ---------- DPR / WPR ----------

def report_payload(conn, pid, d_from, d_to):
    project = row(conn, "SELECT * FROM projects WHERE id = ?", (pid,))
    logs = rows(conn, """SELECT p.*, t.name AS task_name, u.name AS created_by_name
                         FROM progress_logs p LEFT JOIN tasks t ON t.id = p.task_id
                         LEFT JOIN users u ON u.id = p.created_by
                         WHERE p.project_id = ? AND p.log_date BETWEEN ? AND ?
                         ORDER BY p.log_date, p.id""", (pid, d_from, d_to))
    materials = rows(conn, """SELECT m.name, m.unit, SUM(mu.qty) AS qty_used
                              FROM material_usage mu JOIN materials m ON m.id = mu.material_id
                              WHERE mu.project_id = ? AND mu.usage_date BETWEEN ? AND ?
                              GROUP BY m.id ORDER BY m.name""", (pid, d_from, d_to))
    labour = rows(conn, """SELECT l.category,
                                  SUM(CASE a.status WHEN 'present' THEN 1 WHEN 'half_day' THEN 0.5 ELSE 0 END) AS days,
                                  SUM(a.ot_hours) AS ot_hours
                           FROM attendance a JOIN labourers l ON l.id = a.labourer_id
                           WHERE a.project_id = ? AND a.att_date BETWEEN ? AND ?
                           GROUP BY l.category""", (pid, d_from, d_to))
    issues = rows(conn, """SELECT title, severity, status, created_at FROM issues
                           WHERE project_id = ? AND date(created_at) BETWEEN ? AND ?""", (pid, d_from, d_to))
    return {
        "project": project, "date_from": d_from, "date_to": d_to,
        "progress_pct": project_metrics(conn, pid)["progress_pct"],
        "logs": logs, "materials_used": materials, "labour": labour, "issues": issues,
        "labour_cost": round(labour_cost(conn, pid, d_from, d_to), 2),
    }


@router.get("/projects/{pid}/dpr")
def dpr(pid: int, report_date: str | None = None, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    d = report_date or date.today().isoformat()
    return report_payload(conn, pid, d, d)


@router.get("/projects/{pid}/wpr")
def wpr(pid: int, week_start: str | None = None, user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if week_start:
        start = date.fromisoformat(week_start)
    else:
        today = date.today()
        start = today - timedelta(days=today.weekday())
    return report_payload(conn, pid, start.isoformat(), (start + timedelta(days=6)).isoformat())


# ---------- activity feed ----------

@router.get("/projects/{pid}/activity")
def project_activity(pid: int, page: int = 1, limit: int = 50,
                     user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    total = scalar(conn, "SELECT COUNT(*) FROM activity WHERE project_id = ?", (pid,))
    data = rows(conn, """SELECT a.*, u.name AS user_name FROM activity a
                         LEFT JOIN users u ON u.id = a.user_id
                         WHERE a.project_id = ? ORDER BY a.id DESC LIMIT ? OFFSET ?""", (pid, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}
