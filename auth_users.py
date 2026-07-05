"""Login, sign-up, current user, user administration, project membership."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from ..db import get_db, insert, row, rows, update
from ..helpers import audit, pagination
from ..security import (ROLES, create_token, current_user, hash_password,
                        require, verify_password)

router = APIRouter(prefix="/api", tags=["auth"])

# Deliberately loose: internal deployments use reserved TLDs like .test/.local.
EmailStr = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)]


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str | None = Field(default=None, min_length=8)
    role: str
    phone: str | None = None
    vendor_id: int | None = None
    active: bool = True


@router.post("/auth/login")
def login(body: LoginBody, conn=Depends(get_db)):
    user = row(conn, "SELECT * FROM users WHERE email = ?", (body.email,))
    if not user or not user["active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    user.pop("password_hash")
    return {"token": create_token(user), "user": user}


@router.post("/auth/register", status_code=201)
def register(body: RegisterBody, conn=Depends(get_db)):
    """Public self-signup — creates an Owner account for a new workspace.
    Disable by setting ALLOW_SIGNUP=0."""
    import os
    if os.environ.get("ALLOW_SIGNUP", "1") != "1":
        raise HTTPException(403, "Self-signup is disabled on this server")
    if row(conn, "SELECT id FROM users WHERE email = ?", (body.email,)):
        raise HTTPException(409, "An account with this email already exists — try signing in")
    uid = insert(conn, "users", {
        "name": body.name, "email": body.email,
        "password_hash": hash_password(body.password), "role": "owner",
    })
    audit(conn, {"id": uid}, "register", "user", uid, after={"email": body.email, "role": "owner"})
    user = row(conn, "SELECT * FROM users WHERE id = ?", (uid,))
    user.pop("password_hash")
    return {"token": create_token(user), "user": user}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.get("/users")
def list_users(page: int = 1, limit: int = 50, minimal: int = 0,
               user=Depends(current_user), conn=Depends(get_db)):
    if minimal:  # names for dropdowns — any authenticated user
        return {"data": rows(conn, "SELECT id, name, role FROM users WHERE active = 1 ORDER BY name"), "total": None}
    if user["role"] not in ("owner", "pm"):
        raise HTTPException(403, "Requires role: owner, pm")
    page, limit, offset = pagination(page, limit)
    total = row(conn, "SELECT COUNT(*) AS c FROM users")["c"]
    data = rows(conn, """SELECT u.id, u.name, u.email, u.role, u.phone, u.vendor_id, u.active, u.created_at,
                                v.name AS vendor_name
                         FROM users u LEFT JOIN vendors v ON v.id = u.vendor_id
                         ORDER BY u.name LIMIT ? OFFSET ?""", (limit, offset))
    return {"data": data, "total": total, "page": page, "limit": limit}


@router.post("/users", status_code=201)
def create_user(body: UserBody, user=Depends(require()), conn=Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if not body.password:
        raise HTTPException(422, "password is required (min 8 chars)")
    if row(conn, "SELECT id FROM users WHERE email = ?", (body.email,)):
        raise HTTPException(409, "Email already exists")
    uid = insert(conn, "users", {
        "name": body.name, "email": body.email, "password_hash": hash_password(body.password),
        "role": body.role, "phone": body.phone, "vendor_id": body.vendor_id,
        "active": 1 if body.active else 0,
    })
    audit(conn, user, "create", "user", uid, after={"name": body.name, "email": body.email, "role": body.role})
    return row(conn, "SELECT id, name, email, role, phone, vendor_id, active FROM users WHERE id = ?", (uid,))


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserBody, user=Depends(require()), conn=Depends(get_db)):
    existing = row(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
    if not existing:
        raise HTTPException(404, "User not found")
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    data = {"name": body.name, "email": body.email, "role": body.role, "phone": body.phone,
            "vendor_id": body.vendor_id, "active": 1 if body.active else 0}
    if body.password:
        data["password_hash"] = hash_password(body.password)
    update(conn, "users", user_id, data)
    audit(conn, user, "update", "user", user_id,
          before={"role": existing["role"], "active": existing["active"]},
          after={"role": body.role, "active": body.active})
    return row(conn, "SELECT id, name, email, role, phone, vendor_id, active FROM users WHERE id = ?", (user_id,))


@router.delete("/users/{user_id}")
def deactivate_user(user_id: int, user=Depends(require()), conn=Depends(get_db)):
    if user_id == user["id"]:
        raise HTTPException(422, "You cannot deactivate yourself")
    existing = row(conn, "SELECT id FROM users WHERE id = ?", (user_id,))
    if not existing:
        raise HTTPException(404, "User not found")
    update(conn, "users", user_id, {"active": 0})
    audit(conn, user, "deactivate", "user", user_id)
    return {"ok": True}
