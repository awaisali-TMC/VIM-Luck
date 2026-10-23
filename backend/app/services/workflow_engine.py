"""
Multi-level approval workflow engine.

Core functions:
  find_matching_template(db, invoice)  — match invoice to a workflow template
  initiate_approval(db, invoice_id, actor_id, actor_name)  — start approval process
  process_action(db, request_id, actor_id, actor_name, action, comments, delegated_to_id)
  get_pending_for_user(db, user_id, user_role, user_department)
  can_user_act_on_step(db, user, step)
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice
from app.models.internal_user import InternalUser
from app.models.workflow import (
    WorkflowTemplate,
    WorkflowStep,
    ApprovalRequest,
    ApprovalAction,
)
from app.services.audit_service import log_audit

logger = logging.getLogger(__name__)

VALID_ACTIONS = {"approved", "rejected", "returned", "delegated"}


async def find_matching_template(
    db: AsyncSession, invoice: Invoice
) -> WorkflowTemplate | None:
    """
    Find the highest-priority active workflow template that matches the invoice.

    Matching criteria:
    - invoice_type: matches or is "all"
    - currency: matches
    - amount range: invoice total within [min_amount, max_amount]
    - company_code: matches or is null (any)

    Returns the first match (lowest priority number = highest priority) or None.
    """
    query = (
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .where(WorkflowTemplate.is_active == 1)
        .order_by(WorkflowTemplate.priority.asc())
    )

    result = await db.execute(query)
    templates = result.scalars().all()

    invoice_amount = invoice.total_amount or 0

    for tmpl in templates:
        # Check invoice type
        if tmpl.invoice_type != "all":
            # Simple check — could be extended with more invoice type detection
            if tmpl.invoice_type == "po_material" and not invoice.po_reference:
                continue
            if tmpl.invoice_type == "non_po" and invoice.po_reference:
                continue

        # Check currency
        inv_currency = invoice.currency or "PKR"
        if tmpl.currency and tmpl.currency != inv_currency:
            continue

        # Check amount range
        if tmpl.min_amount is not None and invoice_amount < tmpl.min_amount:
            continue
        if tmpl.max_amount is not None and invoice_amount > tmpl.max_amount:
            continue

        # Check company code (if the template specifies one)
        if tmpl.company_code:
            # For now, invoices don't have company_code — skip this filter
            pass

        # Template matches — must have at least one step
        if tmpl.steps:
            return tmpl

    return None


async def initiate_approval(
    db: AsyncSession,
    invoice_id: int,
    actor_id: int | None = None,
    actor_name: str = "System",
) -> ApprovalRequest | None:
    """
    Start the approval workflow for an invoice.

    1. Load invoice
    2. Find matching template
    3. Create ApprovalRequest
    4. Auto-skip steps if auto_approve_below threshold met
    5. Update invoice status to 'pending_approval'

    Returns ApprovalRequest or None if no template matches.
    """
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        return None

    template = await find_matching_template(db, invoice)
    if not template:
        logger.info(f"No workflow template matches invoice {invoice_id} — skipping approval")
        return None

    sorted_steps = sorted(template.steps, key=lambda s: s.step_order)

    request = ApprovalRequest(
        invoice_id=invoice_id,
        workflow_template_id=template.id,
        current_step_order=1,
        total_steps=len(sorted_steps),
        overall_status="in_progress",
        initiated_by_id=actor_id,
    )
    db.add(request)
    await db.flush()  # get request.id

    # Auto-skip steps that are below the threshold
    invoice_amount = invoice.total_amount or 0
    for step in sorted_steps:
        if step.auto_approve_below and invoice_amount < step.auto_approve_below:
            # Auto-approve this step
            auto_action = ApprovalAction(
                approval_request_id=request.id,
                step_order=step.step_order,
                step_name=step.step_name,
                approver_name="System (Auto-Approved)",
                action="skipped",
                comments=f"Invoice amount ({invoice_amount}) below auto-approve threshold ({step.auto_approve_below})",
            )
            db.add(auto_action)
            request.current_step_order = step.step_order + 1
        else:
            break  # stop at first step that requires human approval

    # Check if all steps were auto-skipped
    if request.current_step_order > len(sorted_steps):
        request.overall_status = "approved"
        request.completed_at = datetime.now(timezone.utc)
        invoice.status = "approved"
        await log_audit(
            db, "invoice", invoice_id, "auto_approved",
            actor_id=actor_id, actor_type="system", actor_name="System",
            new_value={"workflow_template": template.name},
            metadata={"reason": "All steps auto-approved below threshold"},
        )
    else:
        invoice.status = "pending_approval"
        await log_audit(
            db, "invoice", invoice_id, "approval_initiated",
            actor_id=actor_id, actor_type="internal", actor_name=actor_name,
            new_value={
                "workflow_template": template.name,
                "total_steps": len(sorted_steps),
                "current_step": request.current_step_order,
            },
        )

    return request


async def process_action(
    db: AsyncSession,
    approval_request_id: int,
    actor_id: int,
    actor_name: str,
    action: str,
    comments: str | None = None,
    delegated_to_id: int | None = None,
) -> ApprovalRequest:
    """
    Process an approval action (approve/reject/return/delegate) on the current step.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}. Must be one of: {VALID_ACTIONS}")

    # Load request with actions
    result = await db.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.actions))
        .where(ApprovalRequest.id == approval_request_id)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise ValueError("Approval request not found")
    if request.overall_status != "in_progress":
        raise ValueError(f"Approval request is already {request.overall_status}")

    # Load the template + steps to find current step info
    tmpl_result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .where(WorkflowTemplate.id == request.workflow_template_id)
    )
    template = tmpl_result.scalar_one_or_none()
    sorted_steps = sorted(template.steps, key=lambda s: s.step_order) if template else []

    current_step = None
    for s in sorted_steps:
        if s.step_order == request.current_step_order:
            current_step = s
            break

    step_name = current_step.step_name if current_step else f"Step {request.current_step_order}"

    # Load invoice
    inv_result = await db.execute(select(Invoice).where(Invoice.id == request.invoice_id))
    invoice = inv_result.scalar_one_or_none()

    # Record the action
    approval_action = ApprovalAction(
        approval_request_id=request.id,
        step_order=request.current_step_order,
        step_name=step_name,
        approver_id=actor_id,
        approver_name=actor_name,
        action=action,
        comments=comments,
        delegated_to_id=delegated_to_id,
    )
    db.add(approval_action)

    if action == "approved":
        next_step_order = request.current_step_order + 1

        # Auto-skip subsequent steps if below threshold
        invoice_amount = invoice.total_amount or 0 if invoice else 0
        while next_step_order <= len(sorted_steps):
            next_step = sorted_steps[next_step_order - 1] if next_step_order <= len(sorted_steps) else None
            if next_step and next_step.auto_approve_below and invoice_amount < next_step.auto_approve_below:
                auto_action = ApprovalAction(
                    approval_request_id=request.id,
                    step_order=next_step.step_order,
                    step_name=next_step.step_name,
                    approver_name="System (Auto-Approved)",
                    action="skipped",
                    comments=f"Invoice amount below auto-approve threshold ({next_step.auto_approve_below})",
                )
                db.add(auto_action)
                next_step_order += 1
            else:
                break

        if next_step_order > len(sorted_steps):
            # All steps done — approved
            request.overall_status = "approved"
            request.completed_at = datetime.now(timezone.utc)
            request.current_step_order = len(sorted_steps)
            if invoice:
                invoice.status = "approved"
        else:
            request.current_step_order = next_step_order

    elif action == "rejected":
        request.overall_status = "rejected"
        request.completed_at = datetime.now(timezone.utc)
        if invoice:
            invoice.status = "rejected"

    elif action == "returned":
        request.overall_status = "cancelled"
        request.completed_at = datetime.now(timezone.utc)
        if invoice:
            invoice.status = "exception"

    elif action == "delegated":
        # Stay on the same step — just record the delegation
        pass

    # Audit log
    await log_audit(
        db, "invoice", request.invoice_id, f"approval_{action}",
        actor_id=actor_id, actor_type="internal", actor_name=actor_name,
        new_value={
            "step_order": approval_action.step_order,
            "step_name": step_name,
            "action": action,
            "comments": comments,
        },
    )

    return request


async def get_pending_for_user(
    db: AsyncSession,
    user_id: int,
    user_role: str,
    user_department: str | None = None,
) -> list[dict]:
    """
    Get all approval requests pending the given user's action.

    Matches by:
    - Specific user assignment (approver_user_id = user_id)
    - Role match (approver_role = user_role)
    - Department match (if specified on step)
    """
    # Get all in-progress approval requests
    result = await db.execute(
        select(ApprovalRequest)
        .options(selectinload(ApprovalRequest.actions))
        .where(ApprovalRequest.overall_status == "in_progress")
    )
    requests = result.scalars().all()

    pending = []
    for req in requests:
        # Load the template steps for this request
        tmpl_result = await db.execute(
            select(WorkflowTemplate)
            .options(selectinload(WorkflowTemplate.steps))
            .where(WorkflowTemplate.id == req.workflow_template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if not template:
            continue

        # Find the current step
        current_step = None
        for s in template.steps:
            if s.step_order == req.current_step_order:
                current_step = s
                break
        if not current_step:
            continue

        # Check if user can act on this step
        can_act = False

        # Admin can act on any step
        if user_role == "admin":
            can_act = True

        # Direct user assignment
        if current_step.approver_user_id and current_step.approver_user_id == user_id:
            can_act = True

        # Role-based match
        if current_step.approver_role and current_step.approver_role == user_role:
            if current_step.department:
                if user_department and current_step.department == user_department:
                    can_act = True
            else:
                can_act = True

        # Check for delegation
        for action_record in req.actions:
            if (
                action_record.action == "delegated"
                and action_record.step_order == req.current_step_order
                and action_record.delegated_to_id == user_id
            ):
                can_act = True

        if can_act:
            # Load invoice data
            inv_result = await db.execute(
                select(Invoice).where(Invoice.id == req.invoice_id)
            )
            invoice = inv_result.scalar_one_or_none()

            pending.append({
                "id": req.id,
                "invoice_id": req.invoice_id,
                "workflow_template_id": req.workflow_template_id,
                "current_step_order": req.current_step_order,
                "total_steps": req.total_steps,
                "overall_status": req.overall_status,
                "initiated_by_id": req.initiated_by_id,
                "initiated_at": req.initiated_at,
                "completed_at": req.completed_at,
                "actions": req.actions,
                "invoice_number": invoice.invoice_number if invoice else None,
                "supplier_name": invoice.supplier_name if invoice else None,
                "total_amount": invoice.total_amount if invoice else None,
                "currency": invoice.currency if invoice else None,
                "current_step_name": current_step.step_name,
                "current_step_role": current_step.approver_role,
                "workflow_name": template.name,
            })

    return pending


def can_user_act_on_step(user_id: int, user_role: str, user_department: str | None, step: WorkflowStep) -> bool:
    """Check if a user has authority to act on a workflow step."""
    if user_role == "admin":
        return True
    if step.approver_user_id and step.approver_user_id == user_id:
        return True
    if step.approver_role and step.approver_role == user_role:
        if step.department:
            return user_department == step.department
        return True
    return False
