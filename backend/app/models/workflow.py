"""Workflow and approval models for multi-level invoice approval."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.invoice import Base


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Matching criteria — determines which invoices use this workflow
    invoice_type = Column(String(50), default="all")  # po_material, po_service, non_po, import, all
    company_code = Column(String(50), nullable=True)    # null = any company
    min_amount = Column(Float, nullable=True)            # null = no minimum
    max_amount = Column(Float, nullable=True)            # null = no maximum
    currency = Column(String(10), default=None)          # null = any currency

    is_active = Column(Integer, default=1)               # 0=disabled, 1=active
    priority = Column(Integer, default=100)              # lower = higher priority for matching

    created_by_id = Column(Integer, nullable=True)       # InternalUser.id
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    steps = relationship(
        "WorkflowStep",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.step_order",
    )


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(
        Integer, ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False
    )

    step_order = Column(Integer, nullable=False)           # 1, 2, 3...
    step_name = Column(String(255), nullable=False)        # e.g. "Manager Approval"

    # Who can approve — role-based OR specific user (user overrides role)
    approver_role = Column(String(30), nullable=True)      # e.g. "ap_manager"
    approver_user_id = Column(Integer, nullable=True)      # specific InternalUser.id
    department = Column(String(100), nullable=True)        # optional department filter

    is_required = Column(Integer, default=1)               # 0=can be skipped
    auto_approve_below = Column(Float, nullable=True)      # auto-skip if invoice < this amount
    sla_hours = Column(Integer, default=48)                # SLA deadline in hours

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    template = relationship("WorkflowTemplate", back_populates="steps")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_template_id = Column(
        Integer, ForeignKey("workflow_templates.id"), nullable=True
    )

    current_step_order = Column(Integer, default=1)
    overall_status = Column(String(30), default="in_progress")  # in_progress, approved, rejected, cancelled
    total_steps = Column(Integer, default=0)

    initiated_by_id = Column(Integer, nullable=True)       # InternalUser.id
    initiated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    actions = relationship(
        "ApprovalAction",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ApprovalAction.acted_at",
    )


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    approval_request_id = Column(
        Integer, ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )

    step_order = Column(Integer, nullable=False)
    step_name = Column(String(255))

    approver_id = Column(Integer, nullable=True)       # InternalUser.id
    approver_name = Column(String(255))                # denormalized
    action = Column(String(30), nullable=False)        # approved, rejected, returned, delegated, skipped
    comments = Column(Text, nullable=True)

    delegated_to_id = Column(Integer, nullable=True)   # InternalUser.id for delegation
    acted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    request = relationship("ApprovalRequest", back_populates="actions")
