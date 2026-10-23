"""GL Account management and assignment endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.gl_account import GLAccount, GLAssignment

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gl-accounts", tags=["gl-accounts"])


# ── GL Account CRUD ──────────────────────────────────────────────────────────

@router.get("")
async def list_gl_accounts(
    category: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(GLAccount).where(GLAccount.is_active == 1)
    if category:
        q = q.where(GLAccount.category == category)
    if search:
        q = q.where(
            GLAccount.code.contains(search) | GLAccount.name.contains(search)
        )
    q = q.order_by(GLAccount.code).offset(skip).limit(limit)
    result = await db.execute(q)
    accounts = result.scalars().all()

    count_q = select(func.count(GLAccount.id)).where(GLAccount.is_active == 1)
    total = (await db.execute(count_q)).scalar()

    return {
        "accounts": [
            {
                "id": a.id, "code": a.code, "name": a.name,
                "category": a.category, "parent_code": a.parent_code,
                "company_code": a.company_code, "cost_center": a.cost_center,
                "description": a.description,
            }
            for a in accounts
        ],
        "total": total,
    }


@router.post("")
async def create_gl_account(
    code: str, name: str,
    category: str | None = None,
    parent_code: str | None = None,
    company_code: str | None = None,
    cost_center: str | None = None,
    description: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(GLAccount).where(GLAccount.code == code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "GL account code already exists")

    acc = GLAccount(
        code=code, name=name, category=category,
        parent_code=parent_code, company_code=company_code,
        cost_center=cost_center, description=description,
    )
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return {"id": acc.id, "code": acc.code, "name": acc.name}


# ── GL Assignment ────────────────────────────────────────────────────────────

@router.get("/assignments/{invoice_id}")
async def get_invoice_assignments(invoice_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GLAssignment)
        .where(GLAssignment.invoice_id == invoice_id)
        .order_by(GLAssignment.line_item_id, GLAssignment.id)
    )
    assignments = result.scalars().all()
    return {
        "assignments": [
            {
                "id": a.id, "invoice_id": a.invoice_id, "line_item_id": a.line_item_id,
                "gl_code": a.gl_code, "gl_name": a.gl_name, "amount": a.amount,
                "cost_center": a.cost_center, "assignment_type": a.assignment_type,
                "confidence": a.confidence, "assigned_by_name": a.assigned_by_name,
            }
            for a in assignments
        ]
    }


@router.post("/assignments")
async def create_assignment(
    invoice_id: int,
    gl_code: str,
    amount: float | None = None,
    line_item_id: int | None = None,
    cost_center: str | None = None,
    assigned_by_id: int | None = None,
    assigned_by_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Lookup GL account
    result = await db.execute(select(GLAccount).where(GLAccount.code == gl_code))
    gl_acc = result.scalar_one_or_none()
    if not gl_acc:
        raise HTTPException(404, f"GL account {gl_code} not found")

    assignment = GLAssignment(
        invoice_id=invoice_id, line_item_id=line_item_id,
        gl_account_id=gl_acc.id, gl_code=gl_acc.code, gl_name=gl_acc.name,
        amount=amount, cost_center=cost_center or gl_acc.cost_center,
        assignment_type="manual",
        assigned_by_id=assigned_by_id, assigned_by_name=assigned_by_name,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return {"id": assignment.id, "gl_code": assignment.gl_code, "gl_name": assignment.gl_name}


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GLAssignment).where(GLAssignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    await db.delete(assignment)
    await db.commit()
    return {"deleted": True}
