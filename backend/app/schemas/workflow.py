"""Pydantic schemas for workflow templates and approvals."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Workflow Step schemas ────────────────────────────────────────────────────

class WorkflowStepCreate(BaseModel):
    step_order: int
    step_name: str
    approver_role: Optional[str] = None
    approver_user_id: Optional[int] = None
    department: Optional[str] = None
    is_required: int = 1
    auto_approve_below: Optional[float] = None
    sla_hours: int = 48


class WorkflowStepUpdate(BaseModel):
    step_name: Optional[str] = None
    approver_role: Optional[str] = None
    approver_user_id: Optional[int] = None
    department: Optional[str] = None
    is_required: Optional[int] = None
    auto_approve_below: Optional[float] = None
    sla_hours: Optional[int] = None


class WorkflowStepResponse(BaseModel):
    id: int
    template_id: int
    step_order: int
    step_name: str
    approver_role: Optional[str] = None
    approver_user_id: Optional[int] = None
    department: Optional[str] = None
    is_required: int = 1
    auto_approve_below: Optional[float] = None
    sla_hours: int = 48
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Workflow Template schemas ────────────────────────────────────────────────

class WorkflowTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    invoice_type: str = "all"
    company_code: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    is_active: int = 1
    priority: int = 100
    steps: list[WorkflowStepCreate] = []


class WorkflowTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    invoice_type: Optional[str] = None
    company_code: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    is_active: Optional[int] = None
    priority: Optional[int] = None


class WorkflowTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    invoice_type: str = "all"
    company_code: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    currency: Optional[str] = None
    is_active: int = 1
    priority: int = 100
    created_by_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    steps: list[WorkflowStepResponse] = []

    model_config = {"from_attributes": True}


class StepReorderRequest(BaseModel):
    step_ids: list[int]  # ordered list of step IDs in new order


# ── Approval schemas ─────────────────────────────────────────────────────────

class InitiateApprovalRequest(BaseModel):
    """Optional body for manual initiation — usually auto-triggered."""
    pass


class ApprovalActionRequest(BaseModel):
    action: str  # approved, rejected, returned, delegated
    comments: Optional[str] = None
    delegated_to_id: Optional[int] = None


class ApprovalActionResponse(BaseModel):
    id: int
    approval_request_id: int
    step_order: int
    step_name: Optional[str] = None
    approver_id: Optional[int] = None
    approver_name: Optional[str] = None
    action: str
    comments: Optional[str] = None
    delegated_to_id: Optional[int] = None
    acted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApprovalRequestResponse(BaseModel):
    id: int
    invoice_id: int
    workflow_template_id: Optional[int] = None
    current_step_order: int
    total_steps: int = 0
    overall_status: str
    initiated_by_id: Optional[int] = None
    initiated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actions: list[ApprovalActionResponse] = []
    # Denormalized invoice data for list views
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    # Current step info
    current_step_name: Optional[str] = None
    current_step_role: Optional[str] = None
    workflow_name: Optional[str] = None

    model_config = {"from_attributes": True}


class PendingApprovalsResponse(BaseModel):
    approvals: list[ApprovalRequestResponse]
    total: int
    counts: dict  # {pending, approved_today, rejected_today}
