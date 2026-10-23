"""
Approval action endpoints.

  GET  /api/approvals/pending                    — my pending approvals
  GET  /api/approvals/invoice/{invoice_id}       — approval status for invoice
  POST /api/approvals/invoice/{invoice_id}/initiate — start approval workflow
  POST /api/approvals/{request_id}/action        — approve/reject/return/delegate
  GET  /api/approvals/history                    — completed approvals
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.security import get_current_internal_user
from app.models.invoice import Invoice
from app.models.internal_user import InternalUser
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowStep,
    ApprovalRequest,
    ApprovalAction,
)
from app.schemas.workflow import (
    ApprovalActionRequest,
    ApprovalRequestResponse,
    ApprovalActionResponse,
    PendingApprovalsResponse,
)
from app.services.workflow_engine import (
    initiate_approval,
    process_action,
    get_pending_for_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _build_request_response(req, invoice=None, template=None, current_step=None):
    """Build a response dict from an ApprovalRequest."""
    return {
        "id": req.id,
        "invoice_id": req.invoice_id,
        "workflow_template_id": req.workflow_template_id,
        "current_step_order": req.current_step_order,
        "total_steps": req.total_steps,
        "overall_status": req.overall_status,
        "initiated_by_id": req.initiated_by_id,
        "initiated_at": req.initiated_at,
        "completed_at": req.completed_at,
        "actions": [ApprovalActionResponse.model_validate(a) for a in (req.actions or [])],
        "invoice_number": invoice.invoice_number if invoice else None,
        "supplier_name": invoice.supplier_name if invoice else None,
        "total_amount": invoice.total_amount if invoice else None,
        "currency": invoice.currency if invoice else None,
        "current_step_name": current_step.step_name if current_step else None,
        "current_step_role": current_step.approver_role if current_step else None,
        "workflow_name": template.name if template else None,
    }


@router.get("/pending", response_model=PendingApprovalsResponse)
async def get_pending(
    user: InternalUser = Depends(get_current_internal_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all approval requests pending the current user's action."""
    pending = await get_pending_for_user(
        db, user.id, user.role, user.department
    )

    # Counts
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    approved_today = await db.execute(
        select(func.count(ApprovalAction.id)).where(
            ApprovalAction.approver_id == user.id,
            ApprovalAction.action == "approved",
            ApprovalAction.acted_at >= today_start,
        )
    )
    rejected_today = await db.execute(
        select(func.count(ApprovalAction.id)).where(
            ApprovalAction.approver_id == user.id,
            ApprovalAction.action == "rejected",
            ApprovalAction.acted_at >= today_start,
        )
    )

    return PendingApprovalsResponse(
        approvals=[ApprovalRequestResponse(**p) for p in pending],
        total=len(pending),
        counts={
            "pending": len(pending),
            "approved_today": approved_today.scalar() or 0,
            "rejected_today": rejected_today.scalar() or 0,
        },
    )


@router.get("/invoice/{invoice_id}")
async def get_invoice_approval(
    invoice_id: int, db: AsyncSession = Depends(get_db)
):
    """Get the approval status for a specific invoice."""
    result = await db.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.actions))
        .where(ApprovalRequest.invoice_id == invoice_id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    requests = result.scalars().all()

    if not requests:
        return {"approval": None, "has_approval": False}

    req = requests[0]  # latest

    # Load template and current step info
    template = None
    current_step = None
    if req.workflow_template_id:
        tmpl_result = await db.execute(
            select(WorkflowTemplate)
            .options(selectinload(WorkflowTemplate.steps))
            .where(WorkflowTemplate.id == req.workflow_template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if template:
            for s in template.steps:
                if s.step_order == req.current_step_order:
                    current_step = s

    # Load invoice
    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()

    approval_data = _build_request_response(req, invoice, template, current_step)

    # Include all steps for display
    steps_info = []
    if template:
        for s in sorted(template.steps, key=lambda x: x.step_order):
            step_actions = [a for a in req.actions if a.step_order == s.step_order]
            step_status = "pending"
            step_actor = None
            step_acted_at = None
            for a in step_actions:
                if a.action in ("approved", "skipped"):
                    step_status = a.action
                    step_actor = a.approver_name
                    step_acted_at = a.acted_at
                elif a.action == "rejected":
                    step_status = "rejected"
                    step_actor = a.approver_name
                    step_acted_at = a.acted_at
                elif a.action == "returned":
                    step_status = "returned"
                    step_actor = a.approver_name
                    step_acted_at = a.acted_at

            if s.step_order > req.current_step_order and req.overall_status == "in_progress":
                step_status = "upcoming"

            steps_info.append({
                "step_order": s.step_order,
                "step_name": s.step_name,
                "approver_role": s.approver_role,
                "approver_user_id": s.approver_user_id,
                "sla_hours": s.sla_hours,
                "status": step_status,
                "actor_name": step_actor,
                "acted_at": step_acted_at.isoformat() if step_acted_at else None,
            })

    return {
        "approval": approval_data,
        "has_approval": True,
        "steps": steps_info,
    }


@router.post("/invoice/{invoice_id}/initiate")
async def initiate_invoice_approval(
    invoice_id: int,
    user: InternalUser = Depends(get_current_internal_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually initiate the approval workflow for an invoice."""
    # Check invoice exists and is in valid state
    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in ("validated", "approved", "rejected", "exception", "pending_approval"):
        raise HTTPException(
            status_code=400,
            detail=f"Invoice must be in 'validated', 'rejected', or 'exception' status to initiate approval (current: {invoice.status})"
        )

    request = await initiate_approval(db, invoice_id, user.id, user.display_name)

    if not request:
        # Submission requires a matching workflow — block instead of silently
        # skipping, so the invoice can't drift forward without approvals.
        raise HTTPException(
            status_code=409,
            detail=(
                "No active approval workflow matches this invoice "
                f"(type/currency {invoice.currency or 'PKR'}/amount). "
                "Create or adjust a workflow template first (Admin → Workflows)."
            ),
        )

    await db.commit()

    return {
        "message": f"Approval workflow initiated ({request.total_steps} steps)",
        "approval_id": request.id,
        "status": request.overall_status,
    }


@router.post("/{request_id}/action")
async def take_action(
    request_id: int,
    data: ApprovalActionRequest,
    user: InternalUser = Depends(get_current_internal_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, return, or delegate on the current step."""
    try:
        request = await process_action(
            db,
            approval_request_id=request_id,
            actor_id=user.id,
            actor_name=user.display_name,
            action=data.action,
            comments=data.comments,
            delegated_to_id=data.delegated_to_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    return {
        "message": f"Action '{data.action}' recorded successfully",
        "approval_id": request.id,
        "overall_status": request.overall_status,
        "current_step_order": request.current_step_order,
    }


@router.get("/history")
async def approval_history(
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get completed approval history."""
    query = (
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.actions))
    )

    if status:
        query = query.where(ApprovalRequest.overall_status == status)
    else:
        query = query.where(ApprovalRequest.overall_status != "in_progress")

    total_q = select(func.count(ApprovalRequest.id))
    if status:
        total_q = total_q.where(ApprovalRequest.overall_status == status)
    else:
        total_q = total_q.where(ApprovalRequest.overall_status != "in_progress")
    total = (await db.execute(total_q)).scalar() or 0

    query = query.order_by(ApprovalRequest.completed_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    requests = result.scalars().all()

    items = []
    for req in requests:
        inv_result = await db.execute(select(Invoice).where(Invoice.id == req.invoice_id))
        invoice = inv_result.scalar_one_or_none()
        items.append({
            "id": req.id,
            "invoice_id": req.invoice_id,
            "overall_status": req.overall_status,
            "total_steps": req.total_steps,
            "initiated_at": req.initiated_at,
            "completed_at": req.completed_at,
            "invoice_number": invoice.invoice_number if invoice else None,
            "supplier_name": invoice.supplier_name if invoice else None,
            "total_amount": invoice.total_amount if invoice else None,
            "actions": [ApprovalActionResponse.model_validate(a) for a in req.actions],
        })

    return {"history": items, "total": total}
