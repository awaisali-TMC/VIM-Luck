"""
Duplicate invoice detection service.

The BLOCKING rule (Lucky Cement): an invoice is a duplicate of an EARLIER live
invoice with the same key — Reference (invoice number), PO, supplier NTN, SAP
vendor and company code. See find_key_duplicates(). A duplicate cannot be
submitted for approval, moved forward by a status change, or sent to SAP.

Advisory warnings, shown on the invoice but never blocking:
  1. Same invoice number, any supplier
  2. Same supplier NTN + amount ± 1% + date ± 7 days
  3. Same amount ± 0.5% + same date, any supplier
"""

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder

logger = logging.getLogger(__name__)

# Statuses that no longer count as a live copy. Deleted invoices are excluded
# separately (is_deleted).
_DEAD_STATUSES = ("exception",)

KEY_FIELD_LABELS = {
    "reference": "Reference",
    "po": "PO",
    "ntn": "NTN",
    "vendor": "Vendor",
    "company_code": "Company Code",
}


# ── Key duplicate (blocking) ─────────────────────────────────────────────────

def _norm_ref(value: str | None) -> str:
    return (value or "").strip().lower()


def _norm_po(value: str | None) -> str:
    # SAP PO numbers are zero-padded to 10 digits; an extracted reference may not be.
    s = re.sub(r"\s", "", value or "").upper()
    return s.lstrip("0") or s


def _norm_ntn(value: str | None) -> str:
    # An NTN is 7 digits plus an optional check digit ("5433744-3"), and invoices
    # print it both ways, so compare the 7-digit base. Anything else (a 13-digit
    # CNIC) compares in full.
    digits = re.sub(r"\D", "", value or "")
    if 0 < len(digits) <= 8:
        return digits.zfill(7)[:7]
    return digits


def _norm_vendor(value: str | None) -> str:
    s = re.sub(r"\s", "", value or "")
    return s.lstrip("0") or s


def _norm_company(value: str | None) -> str:
    return (value or "").strip().upper()


def invoice_key(invoice: Invoice, po: PurchaseOrder | None) -> dict:
    """The duplicate key of an invoice. The PO, vendor and company code come from
    the matched PO, falling back to the PO reference printed on the invoice."""
    return {
        "reference": _norm_ref(invoice.invoice_number),
        "po": _norm_po(po.po_number if po else invoice.po_reference),
        "ntn": _norm_ntn(invoice.supplier_ntn),
        "vendor": _norm_vendor(invoice.sap_vendor_number or (po.sap_vendor_number if po else None)),
        "company_code": _norm_company(invoice.sap_company_code or (po.company_code if po else None)),
    }


def compare_keys(mine: dict, theirs: dict) -> list[str] | None:
    """Fields both keys matched on, or None when they are not the same invoice.

    Reference and PO must be present and equal. NTN, vendor and company code must
    be equal wherever both invoices carry them: a value missing on one side (NTN
    not extracted, PO synced before company codes were stored) is skipped rather
    than letting a duplicate through.
    """
    if not mine["reference"] or not mine["po"]:
        return None
    if mine["reference"] != theirs["reference"] or mine["po"] != theirs["po"]:
        return None
    matched = ["reference", "po"]
    for field in ("ntn", "vendor", "company_code"):
        if mine[field] and theirs[field]:
            if mine[field] != theirs[field]:
                return None
            matched.append(field)
    return matched


async def find_key_duplicates(db: AsyncSession, invoice: Invoice) -> list[dict]:
    """Earlier live invoices that share this invoice's duplicate key.

    Only EARLIER invoices count, so the first copy received stays the original and
    is never blocked by a later re-send; the re-send is the duplicate.
    """
    ref = _norm_ref(invoice.invoice_number)
    if not ref or invoice.id is None:
        return []

    candidates = (await db.execute(
        select(Invoice).where(
            func.lower(func.trim(Invoice.invoice_number)) == ref,
            Invoice.id < invoice.id,
            Invoice.is_deleted == 0,
            Invoice.status.notin_(_DEAD_STATUSES),
        ).order_by(Invoice.id)
    )).scalars().all()
    if not candidates:
        return []

    po_ids = {i.matched_po_id for i in (invoice, *candidates) if i.matched_po_id}
    pos = {}
    if po_ids:
        pos = {p.id: p for p in (await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids))
        )).scalars().all()}

    mine = invoice_key(invoice, pos.get(invoice.matched_po_id))
    duplicates = []
    for other in candidates:
        po = pos.get(other.matched_po_id)
        matched = compare_keys(mine, invoice_key(other, po))
        if matched is None:
            continue
        d = _to_match_dict(other, "duplicate")
        d["po_number"] = po.po_number if po else other.po_reference
        d["matched_on"] = [KEY_FIELD_LABELS[f] for f in matched]
        duplicates.append(d)
    return duplicates


def duplicate_block_message(duplicates: list[dict]) -> str:
    first = duplicates[0]
    more = f" (and {len(duplicates) - 1} more)" if len(duplicates) > 1 else ""
    return (
        f"Duplicate invoice: reference '{first['invoice_number']}' against PO "
        f"{first['po_number']} already exists as invoice #{first['id']} "
        f"({first['status']}){more}. Matched on {', '.join(first['matched_on'])}. "
        "Delete this copy, or mark the earlier invoice as exception, before continuing."
    )


# ── Advisory warnings + the key check, for the invoice banner ────────────────

async def check_duplicates(
    db: AsyncSession,
    invoice_number: str | None = None,
    supplier_ntn: str | None = None,
    supplier_name: str | None = None,
    total_amount: float | None = None,
    invoice_date: str | None = None,
    exclude_id: int | None = None,
    invoice: Invoice | None = None,
) -> dict:
    """
    Check for potential duplicate invoices. Pass `invoice` (a saved invoice) to
    also run the blocking key check.

    Returns:
        {
            "has_duplicates": bool,
            "is_duplicate": bool,         # blocked: key match with an earlier invoice
            "duplicate_matches": [...],   # earlier invoices with the same key
            "exact_matches": [...],       # same invoice number, any supplier
            "probable_matches": [...],    # same supplier + amount ± 1% + date ± 7 days
            "possible_matches": [...],    # same amount + date (any supplier)
        }
    """
    duplicates = await find_key_duplicates(db, invoice) if invoice is not None else []
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
        dup_ids = {m["id"] for m in duplicates}
        exact = [
            _to_match_dict(inv, "exact")
            for inv in result.scalars().all()
            if inv.id not in dup_ids
        ]

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
        # Exclude any already listed above
        exact_ids = {m["id"] for m in exact} | {m["id"] for m in duplicates}
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
        seen_ids = (
            {m["id"] for m in exact} | {m["id"] for m in probable} | {m["id"] for m in duplicates}
        )
        possible = [
            _to_match_dict(inv, "possible")
            for inv in result.scalars().all()
            if inv.id not in seen_ids
        ]

    has_duplicates = bool(duplicates or exact or probable or possible)
    return {
        "has_duplicates": has_duplicates,
        "is_duplicate": bool(duplicates),
        "duplicate_matches": duplicates,
        "exact_matches": exact,
        "probable_matches": probable,
        "possible_matches": possible,
        "total_matches": len(duplicates) + len(exact) + len(probable) + len(possible),
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
