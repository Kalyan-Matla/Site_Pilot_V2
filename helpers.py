"""Cross-cutting helpers: audit log, notifications, activity feed, pagination."""
import json

from fastapi import HTTPException

from .db import insert, rows


def audit(conn, user, action, entity_type, entity_id, before=None, after=None):
    insert(conn, "audit_log", {
        "user_id": user["id"] if user else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_json": json.dumps(before, default=str) if before else None,
        "after_json": json.dumps(after, default=str) if after else None,
    })


def activity(conn, project_id, user, action, entity_type=None, entity_id=None, detail=None):
    insert(conn, "activity", {
        "project_id": project_id,
        "user_id": user["id"] if user else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "detail": detail,
    })


def notify(conn, user_ids, ntype, title, body=None, entity_type=None, entity_id=None, exclude=None):
    for uid in set(u for u in user_ids if u and u != exclude):
        insert(conn, "notifications", {
            "user_id": uid, "ntype": ntype, "title": title, "body": body,
            "entity_type": entity_type, "entity_id": entity_id,
        })


def notify_roles(conn, roles, ntype, title, body=None, entity_type=None, entity_id=None,
                 project_id=None, exclude=None):
    """Notify all active users holding the given roles; non owner/accountant roles
    only if assigned to project_id (when given)."""
    ph = ",".join("?" * len(roles))
    users = rows(conn, f"SELECT id, role FROM users WHERE active = 1 AND role IN ({ph})", list(roles))
    targets = []
    if project_id:
        members = {r["user_id"] for r in rows(
            conn, "SELECT user_id FROM project_members WHERE project_id = ?", (project_id,))}
        for u in users:
            if u["role"] in ("owner", "accountant") or u["id"] in members:
                targets.append(u["id"])
    else:
        targets = [u["id"] for u in users]
    notify(conn, targets, ntype, title, body, entity_type, entity_id, exclude=exclude)


def pagination(page: int = 1, limit: int = 25):
    page = max(1, int(page or 1))
    limit = min(200, max(1, int(limit or 25)))
    return page, limit, (page - 1) * limit


def not_found(item, label="Record"):
    if not item:
        raise HTTPException(404, f"{label} not found")
    return item
