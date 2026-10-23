"""Internal user model for RBAC."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime

from app.models.invoice import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    AP_MANAGER = "ap_manager"
    AP_OPERATOR = "ap_operator"
    TAX_MANAGER = "tax_manager"
    PROCUREMENT_MANAGER = "procurement_manager"
    AUDITOR = "auditor"
    FINANCE_DIRECTOR = "finance_director"
    DEPARTMENT_HEAD = "department_head"


class InternalUser(Base):
    __tablename__ = "internal_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)  # "{salt}:{sha256hash}"
    role = Column(String(30), default=UserRole.AP_OPERATOR.value)
    department = Column(String(100), nullable=True)
    is_active = Column(Integer, default=1)  # 0=disabled, 1=active
    auth_token = Column(String(100), nullable=True, index=True)
    # When the current session token was issued — used to expire stale sessions.
    token_issued_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
