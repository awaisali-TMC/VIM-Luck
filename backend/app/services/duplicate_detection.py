"""
Duplicate invoice detection service.

Checks for potential duplicate invoices using multiple matching strategies:
  1. Exact match: same invoice_number + supplier_ntn
  2. Fuzzy match: same supplier + similar amount + close dates
  3. Hash match: same total_amount + same invoice_date + same supplier_name
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice

logger = logging.getLogger(__name__)


async def check_duplicates(
    db: AsyncSession,
    invoice_number: str | None = None,
    supplier_ntn: str | None = None,
    supplier_name: str | None = None,
    total_amount: float | None = None,
    invoice_date: str | None = None,
    exclude_id: int | None = None,
) -> dict:
    """
    Check for potential duplicate invoices.

    Returns:
        {
            "has_duplicates": bool,
            "exact_matches": [...],     # same inv number + supplier NTN
            "probable_matches": [...],  # same supplier + amount ± 1% + date ± 7 days
            "possible_matches": [...],  # same amount + date (different supplier)
        }
    """
    exact = []
    probable = []
    possible = []

    base_filter = []
    if exclude_id:
        base_filter.append(Invoice.id != exclude_id)
    # Never match against soft-deleted invoices — a deleted copy must not flag a
    # live invoice as a duplicate.
    base_filter.append(Invoice.is_deleted == 0)
    # Exclude cancelled/exception statuses from duplicate check
    base_filter.append(Invoice.status.notin_(["exception"]))

    # ── Strategy 1: Exact match on invoice number ────────────────────────
    # A shared invoice number is a duplicate-billing red flag EVEN when the
    # supplier differs (e.g. two vendors submitting the same invoice) — so we
    # match on the number alone rather than narrowing by NTN. This surfaces as
    # a "danger" banner instead of a soft "possible" one.
    if invoice_number and invoice_number.strip():
        exact_q = select(Invoice).where(
            and_(
                func.lower(Invoice.invoice_number) == invoice_number.strip().lower(),
                *base_filter,
            )
        )
        result = await db.execute(exact_q.limit(10))
        exact = [_to_match_dict(inv, "exact") for inv in result.scalars().all()]

    # ── Strategy 2: Probable — same supplier + similar amount + close dates ─
    if supplier_ntn and supplier_ntn.strip() and total_amount is not None:
        tolerance = total_amount * 0.01  # 1% tolerance
        low = total_amount - tolerance
        high = total_amount + tolerance

        probable_q = select(Invoice).where(
            and_(
                func.lower(Invoice.supplier_ntn) == supplier_ntn.strip().lower(),
                Invoice.total_amount.between(low, high),
                *base_filter,
            )
        )
        # Filter by date range if available
        if invoice_date:
            try:
                # Parse common date formats
                parsed = _parse_date(invoice_date)
                if parsed:
                    date_low = (parsed - timedelta(days=7)).strftime("%Y-%m-%d")
                    date_high = (parsed + timedelta(days=7)).strftime("%Y-%m-%d")
                    probable_q = probable_q.where(
                        Invoice.invoice_date.between(date_low, date_high)
                    )
            except Exception:
                pass

        result = await db.execute(probable_q.limit(10))
        probable_raw = result.scalars().all()
        # Exclude any already in exact matches
        exact_ids = {m["id"] for m in exact}
        probable = [
            _to_match_dict(inv, "probable")
            for inv in probable_raw
            if inv.id not in exact_ids
        ]

    # ── Strategy 3: Possible — same amount + same date (any supplier) ─────
    if total_amount is not None and invoice_date:
        tolerance = total_amount * 0.005  # 0.5% tolerance
        low = total_amount - tolerance
        high = total_amount + tolerance

        possible_q = select(Invoice).where(
            and_(
                Invoice.total_amount.between(low, high),
                Invoice.invoice_date == invoice_date,
                *base_filter,
            )
        )
        result = await db.execute(possible_q.limit(10))
        seen_ids = {m["id"] for m in exact} | {m["id"] for m in probable}
        possible = [
            _to_match_dict(inv, "possible")
            for inv in result.scalars().all()
            if inv.id not in seen_ids
        ]

    has_duplicates = bool(exact or probable or possible)
    return {
        "has_duplicates": has_duplicates,
        "exact_matches": exact,
        "probable_matches": probable,
        "possible_matches": possible,
        "total_matches": len(exact) + len(probable) + len(possible),
    }


def _to_match_dict(inv: Invoice, match_type: str) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "supplier_name": inv.supplier_name,
        "supplier_ntn": inv.supplier_ntn,
        "total_amount": inv.total_amount,
        "currency": inv.currency,
        "invoice_date": inv.invoice_date,
        "status": inv.status,
        "match_type": match_type,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


def _parse_date(date_str: str) -> datetime | None:
    """Try common date formats."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None
