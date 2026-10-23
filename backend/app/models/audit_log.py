"""Audit log model for tracking all user and system actions."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text

from app.models.invoice import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # What was affected
    entity_type = Column(String(50), nullable=False, index=True)  # invoice, po, user, supplier, approval
    entity_id = Column(Integer, nullable=False, index=True)

    # What happened
    action = Column(String(50), nullable=False)  # created, updated, status_changed, approved, rejected, etc.

    # Who did it
    actor_id = Column(Integer, nullable=True)        # InternalUser.id or null for system actions
    actor_type = Column(String(20), default="system")  # internal, supplier, system
    actor_name = Column(String(255))                   # denormalized for display

    # Before/after state
    old_value = Column(Text, nullable=True)   # JSON string
    new_value = Column(Text, nullable=True)   # JSON string

    # Extra context
    metadata_json = Column(Text, nullable=True)  # JSON string

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
