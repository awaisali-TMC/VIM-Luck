"""
Workflow template CRUD endpoints.

  GET    /api/workflow-templates             — list templates
  POST   /api/workflow-templates             — create template with steps
  GET    /api/workflow-templates/{id}        — get template with steps
  PUT    /api/workflow-templates/{id}        — update template
  DELETE /api/workflow-templates/{id}        — delete template
  POST   /api/workflow-templates/{id}/steps           — add step
  PUT    /api/workflow-templates/{id}/steps/{step_id} — update step
  DELETE /api/workflow-templates/{id}/steps/{step_id} — delete step
  POST   /api/workflow-templates/{id}/steps/reorder   — reorder steps
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.workflow import WorkflowTemplate, WorkflowStep
from app.schemas.workflow import (
    WorkflowTemplateCreate,
    WorkflowTemplateUpdate,
    WorkflowTemplateResponse,
    WorkflowStepCreate,
    WorkflowStepUpdate,
    WorkflowStepResponse,
    StepReorderRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow-templates", tags=["workflows"])


# ── Template CRUD ────────────────────────────────────────────────────────────

@router.get("", response_model=list[WorkflowTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    """List all workflow templates with their steps."""
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .order_by(WorkflowTemplate.priority.asc(), WorkflowTemplate.name.asc())
    )
    templates = result.scalars().all()
    return [WorkflowTemplateResponse.model_validate(t) for t in templates]


@router.post("", status_code=201, response_model=WorkflowTemplateResponse)
async def create_template(
    data: WorkflowTemplateCreate, db: AsyncSession = Depends(get_db)
):
    """Create a workflow template with optional initial steps."""
    template = WorkflowTemplate(
        name=data.name.strip(),
        description=data.description,
        invoice_type=data.invoice_type,
        company_code=data.company_code,
        min_amount=data.min_amount,
        max_amount=data.max_amount,
        currency=data.currency,
        is_active=data.is_active,
        priority=data.priority,
    )
    db.add(template)
    await db.flush()  # get template.id

    # Add steps
    for step_data in data.steps:
        step = WorkflowStep(
            template_id=template.id,
            step_order=step_data.step_order,
            step_name=step_data.step_name.strip(),
            approver_role=step_data.approver_role,
            approver_user_id=step_data.approver_user_id,
            department=step_data.department,
            is_required=step_data.is_required,
            auto_approve_below=step_data.auto_approve_below,
            sla_hours=step_data.sla_hours,
        )
        db.add(step)

    await db.commit()

    # Reload with steps
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .where(WorkflowTemplate.id == template.id)
    )
    return WorkflowTemplateResponse.model_validate(result.scalar_one())


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single workflow template with steps."""
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .where(WorkflowTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return WorkflowTemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=WorkflowTemplateResponse)
async def update_template(
    template_id: int,
    data: WorkflowTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update workflow template fields."""
    result = await db.execute(
        select(WorkflowTemplate)
        .options(selectinload(WorkflowTemplate.steps))
        .where(WorkflowTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    if data.name is not None:
        template.name = data.name.strip()
    if data.description is not None:
        template.description = data.description
    if data.invoice_type is not None:
        template.invoice_type = data.invoice_type
    if data.company_code is not None:
        template.company_code = data.company_code or None
    if data.min_amount is not None:
        template.min_amount = data.min_amount
    if data.max_amount is not None:
        template.max_amount = data.max_amount
    if data.currency is not None:
        template.currency = data.currency
    if data.is_active is not None:
        template.is_active = data.is_active
    if data.priority is not None:
        template.priority = data.priority

    await db.commit()
    await db.refresh(template)
    return WorkflowTemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a workflow template and all its steps."""
    result = await db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    await db.delete(template)
    await db.commit()


# ── Step Management ──────────────────────────────────────────────────────────

@router.post("/{template_id}/steps", status_code=201, response_model=WorkflowStepResponse)
async def add_step(
    template_id: int,
    data: WorkflowStepCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a step to a workflow template."""
    result = await db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow template not found")

    step = WorkflowStep(
        template_id=template_id,
        step_order=data.step_order,
        step_name=data.step_name.strip(),
        approver_role=data.approver_role,
        approver_user_id=data.approver_user_id,
        department=data.department,
        is_required=data.is_required,
        auto_approve_below=data.auto_approve_below,
        sla_hours=data.sla_hours,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return WorkflowStepResponse.model_validate(step)


@router.put("/{template_id}/steps/{step_id}", response_model=WorkflowStepResponse)
async def update_step(
    template_id: int,
    step_id: int,
    data: WorkflowStepUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a workflow step."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.id == step_id,
            WorkflowStep.template_id == template_id,
        )
    )
    step = result.scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if data.step_name is not None:
        step.step_name = data.step_name.strip()
    if data.approver_role is not None:
        step.approver_role = data.approver_role or None
    if data.approver_user_id is not None:
        step.approver_user_id = data.approver_user_id or None
    if data.department is not None:
        step.department = data.department or None
    if data.is_required is not None:
        step.is_required = data.is_required
    if data.auto_approve_below is not None:
        step.auto_approve_below = data.auto_approve_below
    if data.sla_hours is not None:
        step.sla_hours = data.sla_hours

    await db.commit()
    await db.refresh(step)
    return WorkflowStepResponse.model_validate(step)


@router.delete("/{template_id}/steps/{step_id}", status_code=204)
async def delete_step(
    template_id: int, step_id: int, db: AsyncSession = Depends(get_db)
):
    """Delete a workflow step."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.id == step_id,
            WorkflowStep.template_id == template_id,
        )
    )
    step = result.scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    await db.delete(step)
    await db.commit()


@router.post("/{template_id}/steps/reorder")
async def reorder_steps(
    template_id: int,
    data: StepReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reorder workflow steps by providing ordered list of step IDs."""
    result = await db.execute(
        select(WorkflowStep).where(WorkflowStep.template_id == template_id)
    )
    steps = {s.id: s for s in result.scalars().all()}

    for order, step_id in enumerate(data.step_ids, start=1):
        if step_id in steps:
            steps[step_id].step_order = order

    await db.commit()
    return {"message": "Steps reordered successfully"}
