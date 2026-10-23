"""Analytics and reporting endpoints for advanced dashboards."""

import json
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.invoice import Invoice, InvoiceLineItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
async def get_overview(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """High-level KPIs for the main analytics dashboard."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total invoices in period
    total_q = select(func.count(Invoice.id)).where(Invoice.created_at >= cutoff)
    total = (await db.execute(total_q)).scalar() or 0

    # Total amount in period
    amount_q = select(func.sum(Invoice.total_amount)).where(Invoice.created_at >= cutoff)
    total_amount = (await db.execute(amount_q)).scalar() or 0

    # Status distribution
    status_q = (
        select(Invoice.status, func.count(Invoice.id).label("count"))
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.status)
    )
    status_rows = (await db.execute(status_q)).all()
    status_counts = {row[0]: row[1] for row in status_rows}

    # Average confidence
    conf_q = select(func.avg(Invoice.overall_confidence)).where(
        and_(Invoice.created_at >= cutoff, Invoice.overall_confidence.isnot(None))
    )
    avg_confidence = (await db.execute(conf_q)).scalar() or 0

    # Average processing time
    proc_q = select(func.avg(Invoice.processing_time_ms)).where(
        and_(Invoice.created_at >= cutoff, Invoice.processing_time_ms.isnot(None))
    )
    avg_processing_ms = (await db.execute(proc_q)).scalar() or 0

    # Exception rate
    exceptions = status_counts.get("exception", 0)
    exception_rate = round((exceptions / total * 100), 1) if total > 0 else 0

    # Straight-through rate (draft -> posted without exception)
    posted = status_counts.get("posted", 0) + status_counts.get("approved", 0)
    straight_through = round((posted / total * 100), 1) if total > 0 else 0

    # Pending approvals
    pending_approval = status_counts.get("pending_approval", 0)

    return {
        "period_days": days,
        "total_invoices": total,
        "total_amount": round(total_amount, 2),
        "status_counts": status_counts,
        "avg_confidence": round(avg_confidence, 1),
        "avg_processing_ms": round(avg_processing_ms),
        "exception_rate": exception_rate,
        "straight_through_rate": straight_through,
        "pending_approval": pending_approval,
    }


@router.get("/volume-trend")
async def get_volume_trend(
    days: int = 90,
    group_by: str = "week",  # day, week, month
    db: AsyncSession = Depends(get_db),
):
    """Invoice volume trend grouped by time period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # SQLite date functions
    if group_by == "day":
        date_expr = func.date(Invoice.created_at)
    elif group_by == "month":
        date_expr = func.strftime("%Y-%m", Invoice.created_at)
    else:  # week
        date_expr = func.strftime("%Y-W%W", Invoice.created_at)

    q = (
        select(
            date_expr.label("period"),
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
            func.avg(Invoice.overall_confidence).label("avg_confidence"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(date_expr)
        .order_by(date_expr)
    )

    rows = (await db.execute(q)).all()
    return {
        "group_by": group_by,
        "data": [
            {
                "period": str(r[0]) if r[0] else "Unknown",
                "count": r[1],
                "total_amount": round(r[2] or 0, 2),
                "avg_confidence": round(r[3] or 0, 1),
            }
            for r in rows
        ],
    }


@router.get("/by-supplier")
async def get_by_supplier(
    days: int = 90,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Top suppliers by invoice count and amount."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            Invoice.supplier_name,
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
            func.avg(Invoice.overall_confidence).label("avg_confidence"),
            func.sum(case((Invoice.status == "exception", 1), else_=0)).label("exception_count"),
        )
        .where(and_(Invoice.created_at >= cutoff, Invoice.supplier_name.isnot(None)))
        .group_by(Invoice.supplier_name)
        .order_by(func.sum(Invoice.total_amount).desc())
        .limit(limit)
    )

    rows = (await db.execute(q)).all()
    return {
        "suppliers": [
            {
                "supplier_name": r[0] or "Unknown",
                "invoice_count": r[1],
                "total_amount": round(r[2] or 0, 2),
                "avg_confidence": round(r[3] or 0, 1),
                "exception_count": r[4] or 0,
            }
            for r in rows
        ]
    }


@router.get("/by-status")
async def get_by_status(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Status distribution with amounts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            Invoice.status,
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.status)
        .order_by(func.count(Invoice.id).desc())
    )

    rows = (await db.execute(q)).all()
    return {
        "statuses": [
            {
                "status": r[0],
                "count": r[1],
                "total_amount": round(r[2] or 0, 2),
            }
            for r in rows
        ]
    }


@router.get("/by-document-type")
async def get_by_document_type(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """Distribution by document type."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            Invoice.document_type,
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.document_type)
        .order_by(func.count(Invoice.id).desc())
    )

    rows = (await db.execute(q)).all()
    return {
        "types": [
            {
                "document_type": r[0] or "invoice",
                "count": r[1],
                "total_amount": round(r[2] or 0, 2),
            }
            for r in rows
        ]
    }


@router.get("/tax-summary")
async def get_tax_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Aggregated tax amounts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = select(
        func.count(Invoice.id).label("count"),
        func.sum(Invoice.tax_amount).label("total_tax"),
        func.sum(Invoice.gst_amount).label("total_gst"),
        func.sum(Invoice.wht_amount).label("total_wht"),
        func.sum(Invoice.subtotal_amount).label("total_subtotal"),
        func.sum(Invoice.total_amount).label("total_amount"),
    ).where(Invoice.created_at >= cutoff)

    row = (await db.execute(q)).one()
    return {
        "invoice_count": row[0] or 0,
        "total_tax": round(row[1] or 0, 2),
        "total_gst": round(row[2] or 0, 2),
        "total_wht": round(row[3] or 0, 2),
        "total_subtotal": round(row[4] or 0, 2),
        "total_amount": round(row[5] or 0, 2),
    }


@router.get("/fbr-compliance")
async def get_fbr_compliance(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """FBR verification and WHT compliance stats."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # FBR verification status distribution
    fbr_q = (
        select(
            Invoice.fbr_verification_status,
            func.count(Invoice.id).label("count"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.fbr_verification_status)
    )
    fbr_rows = (await db.execute(fbr_q)).all()
    fbr_counts = {(r[0] or "not_verified"): r[1] for r in fbr_rows}

    # WHT compliance status distribution
    wht_q = (
        select(
            Invoice.wht_compliance_status,
            func.count(Invoice.id).label("count"),
        )
        .where(and_(Invoice.created_at >= cutoff, Invoice.wht_compliance_status.isnot(None)))
        .group_by(Invoice.wht_compliance_status)
    )
    wht_rows = (await db.execute(wht_q)).all()
    wht_counts = {r[0]: r[1] for r in wht_rows}

    return {
        "fbr_verification": fbr_counts,
        "wht_compliance": wht_counts,
        "total_verified": sum(v for k, v in fbr_counts.items() if k != "not_verified"),
        "total_invoices": sum(fbr_counts.values()),
    }


@router.get("/currency-breakdown")
async def get_currency_breakdown(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """Invoice breakdown by currency."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            Invoice.currency,
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.currency)
        .order_by(func.sum(Invoice.total_amount).desc())
    )

    rows = (await db.execute(q)).all()
    return {
        "currencies": [
            {
                "currency": r[0] or "PKR",
                "count": r[1],
                "total_amount": round(r[2] or 0, 2),
            }
            for r in rows
        ]
    }


@router.get("/aging")
async def get_aging(db: AsyncSession = Depends(get_db)):
    """Invoice aging analysis — how long invoices sit in each status."""
    now = datetime.now(timezone.utc)

    # Only look at non-terminal invoices
    q = (
        select(Invoice)
        .where(Invoice.status.notin_(["posted"]))
        .order_by(Invoice.created_at.asc())
    )
    result = await db.execute(q)
    invoices = result.scalars().all()

    buckets = {"0-7": 0, "8-14": 0, "15-30": 0, "31-60": 0, "60+": 0}
    aging_details = []

    for inv in invoices:
        created = inv.created_at
        if created and created.tzinfo is None:
            from datetime import timezone as tz
            created = created.replace(tzinfo=tz.utc)
        if not created:
            continue
        age_days = (now - created).days

        if age_days <= 7:
            buckets["0-7"] += 1
        elif age_days <= 14:
            buckets["8-14"] += 1
        elif age_days <= 30:
            buckets["15-30"] += 1
        elif age_days <= 60:
            buckets["31-60"] += 1
        else:
            buckets["60+"] += 1

        if age_days > 14:  # Only show aged items
            aging_details.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "supplier_name": inv.supplier_name,
                "total_amount": inv.total_amount,
                "status": inv.status,
                "age_days": age_days,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            })

    aging_details.sort(key=lambda x: x["age_days"], reverse=True)

    return {
        "buckets": buckets,
        "aged_invoices": aging_details[:20],  # Top 20 oldest
        "total_open": len(invoices),
    }


@router.get("/source-breakdown")
async def get_source_breakdown(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Invoice count by source (upload vs email)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            Invoice.source_type,
            func.count(Invoice.id).label("count"),
            func.sum(Invoice.total_amount).label("total_amount"),
        )
        .where(Invoice.created_at >= cutoff)
        .group_by(Invoice.source_type)
    )
    rows = (await db.execute(q)).all()
    return {
        "sources": [
            {
                "source": r[0] or "upload",
                "count": r[1],
                "total_amount": round(r[2] or 0, 2),
            }
            for r in rows
        ]
    }
