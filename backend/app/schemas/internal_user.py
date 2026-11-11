"""Pydantic schemas for internal user management."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Request schemas ──────────────────────────────────────────────────────────

class InternalLoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    display_name: str
    password: str
    role: str = "ap_operator"
    department: Optional[str] = None
    sap_username: Optional[str] = None  # per-user SAP login (optional)
    sap_password: Optional[str] = None  # stored encrypted; never returned


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[int] = None
    # SAP login. None = leave unchanged; "" = clear. A non-empty sap_password is
    # re-encrypted and stored.
    sap_username: Optional[str] = None
    sap_password: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


# ── Response schemas ─────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    department: Optional[str] = None
    is_active: int = 1
    sap_username: Optional[str] = None
    sap_password_set: bool = False  # whether a SAP password is stored (never the value)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    counts: dict  # {total, admin, ap_manager, ...}
