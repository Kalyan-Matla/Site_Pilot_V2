"""Auth: JWT tokens, password hashing, role and project-scope enforcement."""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

from .db import get_db, row, rows

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_HOURS = int(os.environ.get("JWT_HOURS", "12"))

ROLES = ("owner", "pm", "site", "store", "accountant", "vendor")
# Roles that see every project without explicit assignment.
ALL_PROJECT_ROLES = ("owner", "accountant")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(request: Request, conn=Depends(get_db)) -> dict:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = row(conn, "SELECT * FROM users WHERE id = ? AND active = 1", (payload["sub"],))
    if not user:
        raise HTTPException(401, "User not found or deactivated")
    user.pop("password_hash", None)
    return user


def require(*roles):
    """Dependency factory: allow listed roles (owner always allowed)."""

    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "owner" and user["role"] not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user

    return checker


def project_ids_for(conn, user) -> list[int] | None:
    """None means unrestricted access to all projects."""
    if user["role"] in ALL_PROJECT_ROLES:
        return None
    return [r["project_id"] for r in rows(conn, "SELECT project_id FROM project_members WHERE user_id = ?", (user["id"],))]


def check_project(conn, user, project_id: int):
    if not row(conn, "SELECT id FROM projects WHERE id = ?", (project_id,)):
        raise HTTPException(404, "Project not found")
    allowed = project_ids_for(conn, user)
    if allowed is not None and int(project_id) not in allowed:
        raise HTTPException(403, "You are not assigned to this project")


def project_filter(conn, user, column="project_id"):
    """Returns (sql_fragment, params) restricting a query to accessible projects."""
    allowed = project_ids_for(conn, user)
    if allowed is None:
        return "1=1", []
    if not allowed:
        return "1=0", []
    return f"{column} IN ({','.join('?' * len(allowed))})", list(allowed)


def vendor_guard(conn, user, vendor_id):
    """Vendor-role users may only touch their own vendor's records."""
    if user["role"] == "vendor" and user.get("vendor_id") != vendor_id:
        raise HTTPException(403, "Vendors can only access their own records")
