"""
Create Invoice from PO — supplier-initiated invoicing against their SAP POs.

A supplier account is linked to a SAP vendor number at onboarding. "My POs"
shows THAT vendor's purchase orders — refreshed live from SAP on view (throttled,
best-effort) — and the supplier creates an invoice from one: the PO header and
lines become a draft invoice with clean data and a guaranteed PO match. The
supplier must supply their OWN tax-invoice number (it's the legal document
number FBR compliance and duplicate detection key on) and may adjust quantities
for partial deliveries.

  GET  /api/po-flip/open-pos                 caller's open POs (SAP-refreshed)
  POST /api/po-flip/{po_id}/create-invoice   create a draft invoice from a PO

Both endpoints are SUPPLIER-ONLY — internal users manage POs elsewhere.
"""

import asyncio
import json
import logging
import time
from typing import Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.purchase_order import (
    MatchStatus, POLineItem, POLineMatchDetail, POMatchResult, PurchaseOrder,
)
from app.models.supplier import SupplierUser
from app.security import Principal, get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/po-flip", tags=["po-flip"])

# PO statuses a supplier may still invoice against
FLIPPABLE_STATUSES = ("open", "partially_received", "fully_received")

# Live-refresh throttle: hit SAP at most once per vendor per TTL, no matter how
# often the supplier reloads My POs. Failures also wait out the TTL. The manual
# "Refresh from SAP" button bypasses the TTL (force=True) but never runs two
# refreshes for the same vendor concurrently.
SAP_REFRESH_TTL_SECONDS = 300
MAX_NEW_POS_PER_REFRESH = 10
_last_sap_refresh: dict[str, float] = {}
_refresh_inflight: set[str] = set()
# Keep references to fire-and-forget tasks so the event loop doesn't GC them.
_bg_tasks: set = set()


async def _current_supplier(principal: Principal, db: AsyncSession) -> SupplierUser:
    """Resolve the caller to a supplier account — these endpoints are supplier-only."""
    if principal.kind != "supplier":
        raise HTTPException(
            status_code=403,
            detail="Creating invoices from POs is a supplier-portal action.",
        )
    supplier = await db.get(SupplierUser, principal.id)
    if not supplier:
        raise HTTPException(status_code=401, detail="Supplier account not found.")
    return supplier


def _vendor_matches(po_vendor: str, company: str) -> bool:
    """Lenient vendor-name match — fallback for accounts/POs without a SAP link."""
    a = (po_vendor or "").strip().lower()
    b = (company or "").strip().lower()
    return bool(a and b) and (a == b or a in b or b in a)


def _po_belongs_to(po: PurchaseOrder, vendor_number: Optional[str], company_name: str) -> bool:
    """Ownership check: vendor-number match when both sides are SAP-linked,
    name match otherwise (manual POs / unlinked accounts). Takes plain values
    (not the SupplierUser instance) — a rollback in the SAP refresh expires ORM
    objects, and touching an expired instance in async code raises
    MissingGreenlet."""
    if vendor_number and po.sap_vendor_number:
        return po.sap_vendor_number == vendor_number
    return _vendor_matches(po.vendor_name, company_name)


async def _refresh_pos_from_sap(db: AsyncSession, vendor_number: str, force: bool = False) -> None:
    """Pull the vendor's POs from SAP and sync new ones into the local DB.

    Best-effort by design: any SAP failure just leaves the local copies as the
    source (which also keeps instances without live SAP working unchanged).
    Runs the blocking RFC calls in a worker thread. force=True (the manual
    refresh button) bypasses the TTL but not the in-flight guard.
    """
    now = time.time()
    if not force and now - _last_sap_refresh.get(vendor_number, 0) < SAP_REFRESH_TTL_SECONDS:
        return
    if vendor_number in _refresh_inflight:
        return
    _refresh_inflight.add(vendor_number)
    _last_sap_refresh[vendor_number] = now
    try:
        from app.services.sap_po_service import fetch_po_list, fetch_po_detail, sync_po_to_db

        headers = await anyio.to_thread.run_sync(
            lambda: fetch_po_list(max_rows=100, vendor=vendor_number)
        )
        if not headers:
            return
        po_numbers = [h["po_number"] for h in headers if h.get("po_number")]

        # Stamp the vendor number onto already-synced rows that predate the column.
        await db.execute(
            update(PurchaseOrder)
            .where(
                PurchaseOrder.po_number.in_(po_numbers),
                PurchaseOrder.sap_vendor_number.is_(None),
            )
            .values(sap_vendor_number=vendor_number)
        )

        existing = {
            r[0]
            for r in (
                await db.execute(
                    select(PurchaseOrder.po_number).where(PurchaseOrder.po_number.in_(po_numbers))
                )
            ).all()
        }
        new_numbers = [n for n in po_numbers if n not in existing][:MAX_NEW_POS_PER_REFRESH]

        synced = 0
        for po_number in new_numbers:
            detail = await anyio.to_thread.run_sync(fetch_po_detail, po_number)
            if not detail:
                continue
            po_data = sync_po_to_db(detail, None)
            po = PurchaseOrder(
                po_number=po_data["po_number"],
                vendor_name=po_data["vendor_name"],
                sap_vendor_number=vendor_number,
                company_code=po_data["company_code"],
                vendor_ntn=po_data["vendor_ntn"],
                po_date=po_data["po_date"],
                po_type=po_data["po_type"],
                total_amount=po_data["total_amount"],
                currency=po_data["currency"],
                status=po_data["status"],
                notes=po_data["notes"],
                source_type="sap",
            )
            db.add(po)
            await db.flush()
            for li_data in po_data["line_items"]:
                db.add(POLineItem(
                    po_id=po.id,
                    item_number=li_data["item_number"],
                    description=li_data["description"],
                    quantity=li_data["quantity"],
                    unit=li_data["unit"],
                    unit_price=li_data["unit_price"],
                    amount=li_data["amount"],
                ))
            synced += 1

        await db.commit()
        if synced:
            logger.info("SAP PO refresh for vendor %s: %d new PO(s) synced", vendor_number, synced)
    except Exception:
        await db.rollback()
        logger.warning("SAP PO refresh failed for vendor %s — serving local copies", vendor_number, exc_info=True)
    finally:
        _refresh_inflight.discard(vendor_number)


def _kick_background_refresh(vendor_number: str) -> None:
    """Fire-and-forget SAP refresh with its OWN db session — the request's
    session closes when the response is sent, so the task can't borrow it."""
    async def _run():
        from app.database import async_session
        async with async_session() as session:
            await _refresh_pos_from_sap(session, vendor_number)

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _load_pos_for(db: AsyncSession, vendor_number: Optional[str], company_name: str) -> list[dict]:
    """The caller's flippable POs from the local DB, serialized."""
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.status.in_(FLIPPABLE_STATUSES))
        .order_by(PurchaseOrder.created_at.desc())
    )
    pos = [po for po in result.scalars().all() if _po_belongs_to(po, vendor_number, company_name)]
    return [
        {
            "id": po.id,
            "po_number": po.po_number,
            "vendor_name": po.vendor_name,
            "sap_vendor_number": po.sap_vendor_number,
            "po_date": po.po_date,
            "po_type": po.po_type,
            "status": po.status,
            "currency": po.currency,
            "total_amount": po.total_amount,
            "vendor_ntn": po.vendor_ntn,
            "notes": po.notes,
            "line_items": [
                {
                    "id": li.id,
                    "item_number": li.item_number,
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit": li.unit,
                    "unit_price": li.unit_price,
                    "amount": li.amount,
                }
                for li in po.line_items
            ],
        }
        for po in pos
    ]


class FlipLineOverride(BaseModel):
    """Optional per-line override (e.g. partial delivery)."""
    po_line_item_id: int
    quantity: float


class FlipRequest(BaseModel):
    # The supplier's OWN tax-invoice number — required; see endpoint validation.
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    gst_rate_pct: float = 18
    notes: Optional[str] = None
    line_overrides: list[FlipLineOverride] = []


@router.get("/open-pos")
async def list_open_pos(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """The calling supplier's open POs — served instantly from the local DB.

    For SAP-linked accounts a background refresh is kicked off (TTL-throttled),
    so newly created SAP POs appear on the next load or via the Refresh button.
    """
    supplier = await _current_supplier(principal, db)
    # Plain copies — commits/rollbacks elsewhere may expire the ORM object.
    vendor_number = supplier.sap_vendor_number
    company_name = supplier.company_name

    if vendor_number:
        _kick_background_refresh(vendor_number)

    return await _load_pos_for(db, vendor_number, company_name)


@router.post("/refresh")
async def refresh_open_pos(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Manual "Refresh from SAP": waits for the sync, then returns the fresh
    list. Bypasses the TTL throttle (but never runs two refreshes at once)."""
    supplier = await _current_supplier(principal, db)
    vendor_number = supplier.sap_vendor_number
    company_name = supplier.company_name

    if vendor_number:
        await _refresh_pos_from_sap(db, vendor_number, force=True)

    return await _load_pos_for(db, vendor_number, company_name)


@router.post("/{po_id}/create-invoice", status_code=201)
async def create_invoice_from_po(
    po_id: int,
    req: FlipRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Create a draft invoice from a PO (header + lines, optional qty overrides).

    The invoice number must be the supplier's own tax-invoice number — it is
    required and duplicate-checked per vendor.
    """
    supplier = await _current_supplier(principal, db)
    supplier_id = supplier.id
    vendor_number = supplier.sap_vendor_number
    company_name = supplier.company_name
    account_ntn = supplier.ntn

    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == po_id)
    )
    po = result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if po.status not in FLIPPABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"PO status '{po.status}' cannot be invoiced against.",
        )
    if not _po_belongs_to(po, vendor_number, company_name):
        raise HTTPException(status_code=403, detail="This PO does not belong to your company.")

    invoice_number = (req.invoice_number or "").strip()
    if not invoice_number:
        raise HTTPException(
            status_code=422,
            detail="Your invoice number is required — enter the number from your own tax invoice.",
        )
    invoice_date = (req.invoice_date or "").strip()
    if not invoice_date:
        raise HTTPException(status_code=422, detail="Invoice date is required.")

    # Duplicate gate: the same vendor must not invoice the same number twice.
    dup = await db.execute(
        select(Invoice.id)
        .where(
            func.coalesce(Invoice.is_deleted, 0) == 0,
            func.lower(Invoice.invoice_number) == invoice_number.lower(),
            or_(Invoice.supplier_id == supplier_id, Invoice.supplier_name == po.vendor_name),
        )
        .limit(1)
    )
    if dup.first():
        raise HTTPException(
            status_code=409,
            detail=f"Invoice '{invoice_number}' already exists for your company — every tax invoice number must be unique.",
        )

    overrides = {o.po_line_item_id: o.quantity for o in req.line_overrides}

    lines = []
    pairs = []  # (invoice line, the PO line it was copied from)
    subtotal = 0.0
    for li in po.line_items:
        qty = overrides.get(li.id, li.quantity)
        if qty is None or qty <= 0:
            continue
        amount = round(qty * (li.unit_price or 0), 2)
        subtotal += amount
        line = InvoiceLineItem(
            description=li.description,
            quantity=qty,
            unit=li.unit,
            unit_price=li.unit_price,
            amount=amount,
            ai_description=li.description,
            ai_quantity=qty,
            ai_unit=li.unit,
            ai_unit_price=li.unit_price,
            ai_amount=amount,
            # Confidence is stored on a 0–100 scale (like AI extraction).
            # PO data is exact, so 100 — 1.0 would render as "1%".
            description_confidence=100.0,
            quantity_confidence=100.0,
            unit_price_confidence=100.0,
            amount_confidence=100.0,
            user_modified=1 if li.id in overrides else 0,
        )
        lines.append(line)
        pairs.append((line, li))
    if not lines:
        raise HTTPException(status_code=400, detail="No billable line items.")

    subtotal = round(subtotal, 2)
    gst = round(subtotal * req.gst_rate_pct / 100, 2)
    total = round(subtotal + gst, 2)

    invoice = Invoice(
        original_filename=f"Created from PO {po.po_number}",
        stored_filepath="po-flip",
        mime_type="application/json",
        invoice_number=invoice_number[:100],
        invoice_date=invoice_date[:50],
        currency=po.currency or "PKR",
        supplier_name=po.vendor_name,
        supplier_ntn=(po.vendor_ntn or account_ntn or None),
        subtotal_amount=subtotal,
        tax_amount=gst,
        gst_amount=gst,
        total_amount=total,
        detected_taxes=json.dumps([{
            "tax_type": "gst",
            "amount": gst,
            "rate": req.gst_rate_pct,
            "description": "GST applied at PO invoice creation",
        }]),
        po_reference=po.po_number,
        document_type="po_flip",
        matched_po_id=po.id,
        latest_po_match_status="full_match",  # the invoice IS the PO's data
        overall_confidence=100.0,  # 0–100 scale — PO data is exact
        supplier_id=supplier_id,
        source_type="po_flip",
        status="draft",
        line_items=lines,
    )
    db.add(invoice)
    await db.flush()

    # Record the match explicitly: every invoice line IS the PO line it was copied
    # from. Parking routes each line to a PO item by this saved match, and a line
    # with no match is refused rather than guessed onto an item by position.
    billed_po_line_ids = {po_li.id for _, po_li in pairs}
    db.add(POMatchResult(
        invoice_id=invoice.id,
        po_id=po.id,
        match_status=MatchStatus.FULL_MATCH.value,
        match_type="2-way",
        overall_score=100.0,
        notes="Created from the PO: each line is the PO line it was copied from.",
        line_matches=[
            POLineMatchDetail(
                invoice_line_item_id=line.id,
                po_line_item_id=po_li.id,
                match_status=MatchStatus.FULL_MATCH.value,
                quantity_match=1 if line.quantity == po_li.quantity else 0,
                price_match=1,
                quantity_diff=round((line.quantity or 0) - (po_li.quantity or 0), 4),
                price_diff=0.0,
                reasoning="Copied from this PO line.",
            )
            for line, po_li in pairs
        ] + [
            # PO lines not billed this time (zero quantity left), so the match
            # lists every PO line exactly once, as a normal match does.
            POLineMatchDetail(
                invoice_line_item_id=None,
                po_line_item_id=po_li.id,
                match_status=MatchStatus.UNMATCHED.value,
                reasoning="Not billed on this invoice.",
            )
            for po_li in po.line_items if po_li.id not in billed_po_line_ids
        ],
    ))
    await db.commit()
    await db.refresh(invoice, ["line_items"])

    logger.info(
        "Invoice from PO: PO %s -> invoice %s '%s' (%s lines, total %s) by supplier#%s",
        po.po_number, invoice.id, invoice_number, len(lines), total, supplier_id,
    )
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "po_number": po.po_number,
        "subtotal_amount": subtotal,
        "gst_amount": gst,
        "total_amount": total,
        "status": invoice.status,
        "line_count": len(lines),
    }
