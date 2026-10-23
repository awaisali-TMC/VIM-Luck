"""GL Account model for account assignment / coding."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, Text

from app.models.invoice import Base


class GLAccount(Base):
    __tablename__ = "gl_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))           # Asset, Liability, Expense, Revenue
    parent_code = Column(String(30))         # parent account for hierarchy
    company_code = Column(String(20))
    cost_center = Column(String(50))
    is_active = Column(Integer, default=1)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GLAssignment(Base):
    """Links invoice line items to GL accounts."""
    __tablename__ = "gl_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, nullable=False, index=True)
    line_item_id = Column(Integer, nullable=True)           # NULL = header-level assignment
    gl_account_id = Column(Integer, nullable=False)
    gl_code = Column(String(30), nullable=False)            # denormalized for convenience
    gl_name = Column(String(255))                           # denormalized
    amount = Column(Float)
    cost_center = Column(String(50))
    assignment_type = Column(String(20), default="manual")  # "manual" | "auto" | "ai"
    confidence = Column(Float)                               # for AI assignments
    assigned_by_id = Column(Integer)
    assigned_by_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
