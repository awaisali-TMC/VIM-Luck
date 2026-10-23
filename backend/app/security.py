"""
Authentication & authorization dependencies.

Two principal types share the API:
  - Internal users (InternalUser.auth_token) — staff with a role (admin, ap_manager, …)
  - Suppliers     (SupplierUser.auth_token) — external vendor portal users

Tokens are accepted from the `Authorization: Bearer <token>` header (preferred)
or, for backward compatibility with existing clients, the `?token=` query param.
Query-param tokens are deprecated — they leak into logs — and should be removed
once all callers send the header.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.internal_user import InternalUser
from app.models.supplier import SupplierUser

logger = logging.getLogger(__name__)


def _token_expired(issued_at) -> bool:
    """True if a session token has outlived TOKEN_TTL_HOURS.

    A NULL issue time (legacy sessions created before expiry tracking) is NOT
    treated as expired, and TOKEN_TTL_HOURS <= 0 disables expiry entirely.
    """
    if not settings.TOKEN_TTL_HOURS or settings.TOKEN_TTL_HOURS <= 0:
        return False
    if issued_at is None:
        return False
    issued = issued_at if issued_at.tzinfo else issued_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - issued > timedelta(hours=settings.TOKEN_TTL_HOURS)


def _extract_token(authorization: Optional[str], token: Optional[str]) -> Optional[str]:
    """Pull a token from the Authorization header (Bearer) or the ?token= param."""
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        if len(parts) == 1 and parts[0]:
            return parts[0].strip()
    if token:
        return token.strip()
    return None


def _token_matches(candidate: str, stored: Optional[str]) -> bool:
    """Constant-time comparison to avoid timing side-channels on token lookup."""
    if not stored:
        return False
    return secrets.compare_digest(candidate, stored)


# ── Internal users ───────────────────────────────────────────────────────────

async def get_current_internal_user(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> InternalUser:
    """Resolve an internal-user session token to the InternalUser, or 401/403."""
    tok = _extract_token(authorization, token)
    if not tok:
        raise HTTPException(status_code=401, detail="Authentication required.")
    result = await db.execute(
        select(InternalUser).where(InternalUser.auth_token == tok)
    )
    user = result.scalar_one_or_none()
    if not user or not _token_matches(tok, user.auth_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if _token_expired(user.token_issued_at):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated.")
    return user


def require_roles(*roles: str):
    """Dependency factory: require an internal user whose role is in `roles`."""
    async def _dep(user: InternalUser = Depends(get_current_internal_user)) -> InternalUser:
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return user
    return _dep


require_admin = require_roles("admin")


# ── Suppliers ────────────────────────────────────────────────────────────────

async def get_current_supplier(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SupplierUser:
    """Resolve a supplier session token to the SupplierUser, or 401."""
    tok = _extract_token(authorization, token)
    if not tok:
        raise HTTPException(status_code=401, detail="Authentication required.")
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.auth_token == tok)
    )
    supplier = result.scalar_one_or_none()
    if not supplier or not _token_matches(tok, supplier.auth_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if _token_expired(supplier.token_issued_at):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return supplier


# ── Shared principal (internal OR supplier) ──────────────────────────────────

@dataclass
class Principal:
    kind: str                 # "internal" | "supplier"
    id: int
    role: Optional[str] = None


async def get_current_principal(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Authenticate as EITHER an internal user or a supplier.

    Used to gate shared business endpoints so that only logged-in callers reach
    them. (Object-level scoping — e.g. a supplier seeing only their own invoices
    — is a separate, finer-grained concern handled inside the routes.)
    """
    tok = _extract_token(authorization, token)
    if not tok:
        raise HTTPException(status_code=401, detail="Authentication required.")

    result = await db.execute(
        select(InternalUser).where(InternalUser.auth_token == tok)
    )
    user = result.scalar_one_or_none()
    if user and _token_matches(tok, user.auth_token):
        if _token_expired(user.token_issued_at):
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account deactivated.")
        return Principal(kind="internal", id=user.id, role=user.role)

    result = await db.execute(
        select(SupplierUser).where(SupplierUser.auth_token == tok)
    )
    supplier = result.scalar_one_or_none()
    if supplier and _token_matches(tok, supplier.auth_token):
        if _token_expired(supplier.token_issued_at):
            raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
        return Principal(kind="supplier", id=supplier.id)

    raise HTTPException(status_code=401, detail="Invalid or expired session.")
