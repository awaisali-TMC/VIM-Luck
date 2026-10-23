"""Configurable FBR tax rules engine endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tax_rule import TaxRule

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tax-rules", tags=["tax-rules"])


class TaxRuleCreate(BaseModel):
    rule_code: str
    rule_name: str
    description: Optional[str] = None
    tax_type: str  # gst, wht, sed, customs, cess
    rate: float
    applies_to: str = "all"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    supplier_type: Optional[str] = None
    sector: Optional[str] = None
    fbr_section: Optional[str] = None
    sro_reference: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: int = 1
    priority: int = 100


class TaxRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    description: Optional[str] = None
    tax_type: Optional[str] = None
    rate: Optional[float] = None
    applies_to: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    supplier_type: Optional[str] = None
    sector: Optional[str] = None
    fbr_section: Optional[str] = None
    sro_reference: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    is_active: Optional[int] = None
    priority: Optional[int] = None


def _rule_to_dict(r: TaxRule) -> dict:
    return {
        "id": r.id,
        "rule_code": r.rule_code,
        "rule_name": r.rule_name,
        "description": r.description,
        "tax_type": r.tax_type,
        "rate": r.rate,
        "applies_to": r.applies_to,
        "min_amount": r.min_amount,
        "max_amount": r.max_amount,
        "supplier_type": r.supplier_type,
        "sector": r.sector,
        "fbr_section": r.fbr_section,
        "sro_reference": r.sro_reference,
        "effective_from": r.effective_from,
        "effective_to": r.effective_to,
        "is_active": r.is_active,
        "priority": r.priority,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("")
async def list_tax_rules(
    tax_type: str | None = None,
    applies_to: str | None = None,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(TaxRule)
    if active_only:
        q = q.where(TaxRule.is_active == 1)
    if tax_type:
        q = q.where(TaxRule.tax_type == tax_type)
    if applies_to:
        q = q.where(TaxRule.applies_to == applies_to)

    q = q.order_by(TaxRule.tax_type, TaxRule.priority, TaxRule.rule_code).offset(skip).limit(limit)
    result = await db.execute(q)
    rules = result.scalars().all()

    count_q = select(func.count(TaxRule.id))
    if active_only:
        count_q = count_q.where(TaxRule.is_active == 1)
    total = (await db.execute(count_q)).scalar()

    return {
        "rules": [_rule_to_dict(r) for r in rules],
        "total": total,
    }


@router.post("")
async def create_tax_rule(data: TaxRuleCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(TaxRule).where(TaxRule.rule_code == data.rule_code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Rule code '{data.rule_code}' already exists")

    rule = TaxRule(**data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.get("/{rule_id}")
async def get_tax_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxRule).where(TaxRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Tax rule not found")
    return _rule_to_dict(rule)


@router.put("/{rule_id}")
async def update_tax_rule(rule_id: int, data: TaxRuleUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxRule).where(TaxRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Tax rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.delete("/{rule_id}")
async def delete_tax_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaxRule).where(TaxRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Tax rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": True}


@router.get("/match/invoice")
async def match_rules_for_invoice(
    amount: float | None = None,
    applies_to: str = "all",
    supplier_type: str | None = None,
    sector: str | None = None,
    date: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Find applicable tax rules for a given invoice context."""
    q = select(TaxRule).where(TaxRule.is_active == 1)

    # Filter by applies_to
    q = q.where(TaxRule.applies_to.in_([applies_to, "all"]))

    # Filter by amount range
    if amount is not None:
        q = q.where(
            and_(
                (TaxRule.min_amount.is_(None)) | (TaxRule.min_amount <= amount),
                (TaxRule.max_amount.is_(None)) | (TaxRule.max_amount >= amount),
            )
        )

    # Filter by supplier type
    if supplier_type:
        q = q.where((TaxRule.supplier_type.is_(None)) | (TaxRule.supplier_type == supplier_type))

    # Filter by sector
    if sector:
        q = q.where((TaxRule.sector.is_(None)) | (TaxRule.sector == sector))

    # Filter by effective date
    if date:
        q = q.where(
            and_(
                (TaxRule.effective_from.is_(None)) | (TaxRule.effective_from <= date),
                (TaxRule.effective_to.is_(None)) | (TaxRule.effective_to >= date),
            )
        )

    q = q.order_by(TaxRule.priority, TaxRule.tax_type)
    result = await db.execute(q)
    rules = result.scalars().all()

    return {
        "matched_rules": [_rule_to_dict(r) for r in rules],
        "total": len(rules),
    }
