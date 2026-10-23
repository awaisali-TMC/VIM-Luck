from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from app.models.invoice import Base


class Role(Base):
    """A user role. The original 8 are seeded as system roles (is_system=1,
    not deletable); admins can create/rename/delete custom roles.
    `key` is the stable slug stored on internal_users.role and in
    role_permissions.role; `label` is the display name.
    """
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), nullable=False)
    label = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_system = Column(Integer, default=0)  # 1 = built-in, cannot be deleted
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("key", name="uq_role_key"),)
