"""
Internal user authentication and management endpoints.

Auth:
  POST /api/auth/internal/login     — email + password → token
  GET  /api/auth/internal/me        — validate token, return user
  POST /api/auth/internal/logout    — invalidate token

Admin CRUD:
  GET    /api/admin/users           — list internal users
  POST   /api/admin/users           — create user
  GET    /api/admin/users/{id}      — get single user
  PATCH  /api/admin/users/{id}      — update user
  POST   /api/admin/users/{id}/reset-password — reset password
"""

import secrets
import logging
from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import _extract_token, _token_expired
from app.services.passwords import hash_password, verify_password, needs_rehash
from app.models.internal_user import InternalUser, UserRole
from app.schemas.internal_user import (
    InternalLoginRequest,
    CreateUserRequest,
    UpdateUserRequest,
    ResetPasswordRequest,
    UserResponse,
    UserListResponse,
)

logger = logging.getLogger(__name__)


# ── Helpers (same pattern as auth.py for suppliers) ──────────────────────────

def _hash_password(password: str) -> str:
    return hash_password(password)


def _verify_password(password: str, stored: str) -> bool:
    return verify_password(password, stored)


def _generate_token() -> str:
    return secrets.token_hex(32)


def _user_response(u: InternalUser) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "role": u.role,
        "department": u.department,
        "is_active": u.is_active,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


VALID_ROLES = {r.value for r in UserRole}  # built-in fallback (pre-seed)


async def _valid_roles(db) -> set[str]:
    """Valid role keys — the dynamic roles table (RBAC v2), falling back to the
    built-in enum if the table hasn't been seeded yet."""
    from app.models.role import Role
    from sqlalchemy import select as _select
    keys = {r for (r,) in (await db.execute(_select(Role.key))).all()}
    return keys or VALID_ROLES


# ── Auth Router ──────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/api/auth/internal", tags=["internal-auth"])


@auth_router.post("/login")
async def login(data: InternalLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate internal user with email + password, return session token."""
    email = data.email.strip().lower()
    result = await db.execute(
        select(InternalUser).where(InternalUser.email == email)
    )
    user = result.scalar_one_or_none()

    if not user or not _verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account has been deactivated.")

    # Transparently upgrade legacy/weaker password hashes on successful login.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)

    token = _generate_token()
    user.auth_token = token
    now = datetime.now(timezone.utc)
    user.token_issued_at = now
    user.updated_at = now
    await db.commit()
    await db.refresh(user)

    return {"token": token, "user": _user_response(user)}


@auth_router.get("/me")
async def get_me(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),  # deprecated fallback
    db: AsyncSession = Depends(get_db),
):
    """Validate session token (Authorization: Bearer) and return current user."""
    tok = _extract_token(authorization, token)
    if not tok:
        raise HTTPException(status_code=401, detail="Authentication required.")
    result = await db.execute(
        select(InternalUser).where(InternalUser.auth_token == tok)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if _token_expired(user.token_issued_at):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated.")
    return _user_response(user)


@auth_router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),  # deprecated fallback
    db: AsyncSession = Depends(get_db),
):
    """Invalidate session token."""
    tok = _extract_token(authorization, token)
    if not tok:
        return {"message": "Logged out successfully"}
    result = await db.execute(
        select(InternalUser).where(InternalUser.auth_token == tok)
    )
    user = result.scalar_one_or_none()
    if user:
        user.auth_token = None
        await db.commit()
    return {"message": "Logged out successfully"}


# ── Admin CRUD Router ────────────────────────────────────────────────────────

admin_users_router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@admin_users_router.get("", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 50,
    role: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List internal users with optional role filter and search."""
    query = select(InternalUser)

    if role:
        query = query.where(InternalUser.role == role)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            (InternalUser.email.ilike(pattern))
            | (InternalUser.display_name.ilike(pattern))
            | (InternalUser.department.ilike(pattern))
        )

    # Total count
    count_query = select(func.count(InternalUser.id))
    if role:
        count_query = count_query.where(InternalUser.role == role)
    if search:
        pattern = f"%{search}%"
        count_query = count_query.where(
            (InternalUser.email.ilike(pattern))
            | (InternalUser.display_name.ilike(pattern))
        )
    total = (await db.execute(count_query)).scalar() or 0

    # Role counts
    role_counts = {}
    for r in UserRole:
        c = await db.execute(
            select(func.count(InternalUser.id)).where(InternalUser.role == r.value)
        )
        role_counts[r.value] = c.scalar() or 0
    role_counts["total"] = total

    # Active / inactive counts
    active_count = (await db.execute(
        select(func.count(InternalUser.id)).where(InternalUser.is_active == 1)
    )).scalar() or 0
    role_counts["active"] = active_count
    role_counts["inactive"] = total - active_count

    # Fetch page
    query = query.order_by(InternalUser.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
        counts=role_counts,
    )


@admin_users_router.post("", status_code=201)
async def create_user(data: CreateUserRequest, db: AsyncSession = Depends(get_db)):
    """Create a new internal user."""
    email = data.email.strip().lower()

    valid = await _valid_roles(db)
    if data.role not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid))}")

    # Check duplicate email
    existing = await db.execute(
        select(InternalUser).where(InternalUser.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    user = InternalUser(
        email=email,
        display_name=data.display_name.strip(),
        password_hash=_hash_password(data.password),
        role=data.role,
        department=data.department.strip() if data.department else None,
        is_active=1,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Internal user created: id={user.id}, email={email}, role={data.role}")
    return _user_response(user)


@admin_users_router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single internal user."""
    result = await db.execute(
        select(InternalUser).where(InternalUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_response(user)


@admin_users_router.patch("/{user_id}")
async def update_user(
    user_id: int, data: UpdateUserRequest, db: AsyncSession = Depends(get_db)
):
    """Update an internal user's role, department, name, or active status."""
    result = await db.execute(
        select(InternalUser).where(InternalUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    if data.role is not None:
        if data.role not in await _valid_roles(db):
            raise HTTPException(status_code=400, detail=f"Invalid role: {data.role}")
        user.role = data.role
    if data.department is not None:
        user.department = data.department.strip() or None
    if data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            user.auth_token = None  # revoke session on deactivation

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    return _user_response(user)


@admin_users_router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """Reset an internal user's password (admin action)."""
    result = await db.execute(
        select(InternalUser).where(InternalUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not data.new_password or len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    user.password_hash = _hash_password(data.new_password)
    user.auth_token = None  # force re-login
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"message": "Password reset successfully. User must log in again."}
