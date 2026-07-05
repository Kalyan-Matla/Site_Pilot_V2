"""Document management: uploads, simple versioning, links to project/task/issue."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..db import get_db, insert, row, rows, scalar
from ..helpers import activity, audit, not_found, pagination
from ..security import check_project, current_user, require
from ..storage import delete_file, download_response, save_file

router = APIRouter(prefix="/api", tags=["documents"])

CATEGORIES = ("drawing", "boq", "schedule", "contract", "approval", "other")


def save_upload(file: UploadFile, prefix: str) -> str:
    data = file.file.read()
    safe = "".join(c for c in (file.filename or "file") if c.isalnum() or c in "._-")[:80]
    name = f"{prefix}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe}"
    return save_file(data, name)


@router.get("/projects/{pid}/documents")
def list_documents(pid: int, page: int = 1, limit: int = 50, category: str | None = None,
                   task_id: int | None = None, issue_id: int | None = None,
                   user=Depends(current_user), conn=Depends(get_db)):
    check_project(conn, user, pid)
    page, limit, offset = pagination(page, limit)
    where, params = "d.project_id = ?", [pid]
    if category:
        where += " AND d.category = ?"
        params.append(category)
    if task_id:
        where += " AND d.task_id = ?"
        params.append(task_id)
    if issue_id:
        where += " AND d.issue_id = ?"
        params.append(issue_id)
    total = scalar(conn, f"SELECT COUNT(*) FROM documents d WHERE {where}", params)
    data = rows(conn, f"""SELECT d.*, t.name AS task_name, i.title AS issue_title, u.name AS created_by_name,
                                 (SELECT COUNT(*) FROM document_versions v WHERE v.document_id = d.id) AS version_count,
                                 (SELECT MAX(uploaded_at) FROM document_versions v WHERE v.document_id = d.id) AS last_uploaded
                          FROM documents d
                          LEFT JOIN tasks t ON t.id = d.task_id
                          LEFT JOIN issues i ON i.id = d.issue_id
                          LEFT JOIN users u ON u.id = d.created_by
                          WHERE {where} ORDER BY d.created_at DESC LIMIT ? OFFSET ?""", (*params, limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/projects/{pid}/documents", status_code=201)
def create_document(pid: int, title: str = Form(...), category: str = Form("other"),
                    task_id: int | None = Form(None), issue_id: int | None = Form(None),
                    notes: str | None = Form(None), file: UploadFile = File(...),
                    user=Depends(require("pm", "site", "store", "accountant")), conn=Depends(get_db)):
    check_project(conn, user, pid)
    if category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    did = insert(conn, "documents", {"project_id": pid, "task_id": task_id or None,
                                     "issue_id": issue_id or None, "category": category,
                                     "title": title, "created_by": user["id"]})
    path = save_upload(file, f"doc{did}_v1")
    insert(conn, "document_versions", {"document_id": did, "version_no": 1, "file_path": path,
                                       "original_name": file.filename, "notes": notes,
                                       "uploaded_by": user["id"]})
    audit(conn, user, "create", "document", did, after={"title": title, "category": category})
    activity(conn, pid, user, "uploaded document", "document", did, title)
    return get_document(did, user, conn)


@router.post("/documents/{did}/versions", status_code=201)
def add_version(did: int, notes: str | None = Form(None), file: UploadFile = File(...),
                user=Depends(require("pm", "site", "store", "accountant")), conn=Depends(get_db)):
    doc = not_found(row(conn, "SELECT * FROM documents WHERE id = ?", (did,)), "Document")
    check_project(conn, user, doc["project_id"])
    next_v = scalar(conn, "SELECT COALESCE(MAX(version_no), 0) + 1 FROM document_versions WHERE document_id = ?", (did,))
    path = save_upload(file, f"doc{did}_v{next_v}")
    insert(conn, "document_versions", {"document_id": did, "version_no": next_v, "file_path": path,
                                       "original_name": file.filename, "notes": notes,
                                       "uploaded_by": user["id"]})
    audit(conn, user, "new_version", "document", did, after={"version": next_v})
    activity(conn, doc["project_id"], user, f"uploaded v{next_v}", "document", did, doc["title"])
    return get_document(did, user, conn)


@router.get("/documents/{did}")
def get_document(did: int, user=Depends(current_user), conn=Depends(get_db)):
    doc = not_found(row(conn, "SELECT * FROM documents WHERE id = ?", (did,)), "Document")
    check_project(conn, user, doc["project_id"])
    doc["versions"] = rows(conn, """SELECT v.*, u.name AS uploaded_by_name FROM document_versions v
                                    LEFT JOIN users u ON u.id = v.uploaded_by
                                    WHERE v.document_id = ? ORDER BY v.version_no DESC""", (did,))
    return doc


@router.get("/documents/versions/{vid}/download")
def download_version(vid: int, user=Depends(current_user), conn=Depends(get_db)):
    v = not_found(row(conn, """SELECT v.*, d.project_id FROM document_versions v
                               JOIN documents d ON d.id = v.document_id WHERE v.id = ?""", (vid,)), "Version")
    check_project(conn, user, v["project_id"])
    return download_response(v["file_path"], v["original_name"])


@router.delete("/documents/{did}")
def delete_document(did: int, user=Depends(require("pm")), conn=Depends(get_db)):
    doc = not_found(row(conn, "SELECT * FROM documents WHERE id = ?", (did,)), "Document")
    check_project(conn, user, doc["project_id"])
    for v in rows(conn, "SELECT file_path FROM document_versions WHERE document_id = ?", (did,)):
        delete_file(v["file_path"])
    conn.execute("DELETE FROM documents WHERE id = ?", (did,))
    audit(conn, user, "delete", "document", did, before={"title": doc["title"]})
    activity(conn, doc["project_id"], user, "deleted document", "document", did, doc["title"])
    return {"ok": True}
