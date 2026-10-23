import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.purchase_order import (
    PurchaseOrder, POLineItem,
    GoodsReceivedNote, GRNLineItem,
    ServiceEntrySheet, SESLineItem,
    POMatchResult, POLineMatchDetail,
)
from app.schemas.purchase_order import (
    TriggerMatchRequest, MatchResultResponse, LineMatchDetailResponse,
)
from app.services.po_matching_engine import match_invoice_to_po

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/po-matching", tags=["po-matching"])


# ── Trigger PO match for an invoice ────────────────────────────

@router.post("/invoices/{invoice_id}/match", response_model=MatchResultResponse)
async def trigger_po_match(
    invoice_id: int,
    req: TriggerMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    # Load invoice with line items
    inv_result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = inv_result.scalars().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Load PO with line items, GRNs, SESes
    po_result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.grns).selectinload(GoodsReceivedNote.line_items),
            selectinload(PurchaseOrder.ses_records).selectinload(ServiceEntrySheet.line_items),
        )
        .where(PurchaseOrder.id == req.po_id)
    )
    po = po_result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    # Prepare data for matching engine
    inv_lines = [
        {
            "id": li.id,
            "description": li.description,
            "quantity": li.quantity,
            "unit_price": li.unit_price,
            "amount": li.amount,
        }
        for li in invoice.line_items
    ]

    po_lines = [
        {
            "id": li.id,
            "item_number": li.item_number,
            "description": li.description,
            "quantity": li.quantity,
            "unit_price": li.unit_price,
            "amount": li.amount,
        }
        for li in po.line_items
    ]

    # Aggregate GRN data
    grn_data = None
    if req.match_type == "3-way" and po.grns:
        grn_agg = {}
        for grn in po.grns:
            for grn_li in grn.line_items:
                pid = grn_li.po_line_item_id
                grn_agg[pid] = grn_agg.get(pid, 0) + grn_li.received_quantity
        grn_data = [
            {"po_line_item_id": pid, "total_received_qty": qty}
            for pid, qty in grn_agg.items()
        ]

    # Aggregate SES data
    ses_data = None
    if req.match_type == "3-way" and po.ses_records:
        ses_agg = {}
        for ses in po.ses_records:
            for ses_li in ses.line_items:
                pid = ses_li.po_line_item_id
                ses_agg[pid] = ses_agg.get(pid, 0) + ses_li.completed_quantity
        ses_data = [
            {"po_line_item_id": pid, "total_completed_qty": qty}
            for pid, qty in ses_agg.items()
        ]

    # Tolerance config
    tolerance = req.tolerance
    qty_tol = tolerance.quantity_tolerance_pct if tolerance else 5.0
    price_tol = tolerance.price_tolerance_pct if tolerance else 2.0

    # Run matching engine
    result = match_invoice_to_po(
        invoice_line_items=inv_lines,
        po_line_items=po_lines,
        grn_data=grn_data,
        ses_data=ses_data,
        quantity_tolerance_pct=qty_tol,
        price_tolerance_pct=price_tol,
        match_type=req.match_type,
    )

    # Delete any previous match results for this invoice + PO pair
    old_results = await db.execute(
        select(POMatchResult).where(
            POMatchResult.invoice_id == invoice_id,
            POMatchResult.po_id == req.po_id,
        )
    )
    for old in old_results.scalars().all():
        await db.delete(old)
    await db.flush()

    # Save match result to DB
    match_result = POMatchResult(
        invoice_id=invoice_id,
        po_id=req.po_id,
        match_status=result["match_status"],
        match_type=result["match_type"],
        overall_score=result["overall_score"],
        total_amount_diff=result["total_amount_diff"],
        total_amount_diff_pct=result["total_amount_diff_pct"],
    )

    for lm in result["line_matches"]:
        match_result.line_matches.append(POLineMatchDetail(
            invoice_line_item_id=lm["invoice_line_item_id"],
            po_line_item_id=lm["po_line_item_id"],
            match_status=lm["match_status"],
            quantity_match=lm["quantity_match"],
            price_match=lm["price_match"],
            quantity_diff=lm["quantity_diff"],
            quantity_diff_pct=lm["quantity_diff_pct"],
            price_diff=lm["price_diff"],
            price_diff_pct=lm["price_diff_pct"],
            grn_received_qty=lm["grn_received_qty"],
            ses_completed_qty=lm["ses_completed_qty"],
            reasoning=lm["reasoning"],
        ))

    db.add(match_result)

    # Update convenience fields on invoice
    invoice.matched_po_id = req.po_id
    invoice.latest_po_match_status = result["match_status"]

    await db.commit()
    await db.refresh(match_result, ["line_matches"])

    # Build response with denormalized line data
    return _build_match_response(match_result, po, invoice)


# ── Get all match results for an invoice ───────────────────────

@router.get("/invoices/{invoice_id}/matches", response_model=list[MatchResultResponse])
async def get_invoice_matches(invoice_id: int, db: AsyncSession = Depends(get_db)):
    # Verify invoice exists
    inv_result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = inv_result.scalars().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    results = await db.execute(
        select(POMatchResult)
        .options(selectinload(POMatchResult.line_matches))
        .where(POMatchResult.invoice_id == invoice_id)
        .order_by(POMatchResult.created_at.desc())
    )
    match_results = results.scalars().all()

    responses = []
    for mr in match_results:
        # Load PO for denormalization
        po_result = await db.execute(
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.line_items))
            .where(PurchaseOrder.id == mr.po_id)
        )
        po = po_result.scalars().first()
        responses.append(_build_match_response(mr, po, invoice))

    return responses


# ── Get single match result ────────────────────────────────────

@router.get("/results/{match_id}", response_model=MatchResultResponse)
async def get_match_result(match_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(POMatchResult)
        .options(selectinload(POMatchResult.line_matches))
        .where(POMatchResult.id == match_id)
    )
    mr = result.scalars().first()
    if not mr:
        raise HTTPException(status_code=404, detail="Match result not found")

    # Load related invoice and PO
    inv_result = await db.execute(
        select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.id == mr.invoice_id)
    )
    invoice = inv_result.scalars().first()

    po_result = await db.execute(
        select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items)).where(PurchaseOrder.id == mr.po_id)
    )
    po = po_result.scalars().first()

    return _build_match_response(mr, po, invoice)


# ── Delete a match result ──────────────────────────────────────

@router.delete("/results/{match_id}", status_code=204)
async def delete_match_result(match_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(POMatchResult).where(POMatchResult.id == match_id)
    )
    mr = result.scalars().first()
    if not mr:
        raise HTTPException(status_code=404, detail="Match result not found")

    await db.delete(mr)
    await db.commit()


# ── Auto-suggest PO based on po_reference ──────────────────────

@router.post("/invoices/{invoice_id}/auto-suggest")
async def auto_suggest_po(invoice_id: int, db: AsyncSession = Depends(get_db)):
    # Load invoice
    inv_result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id)
    )
    invoice = inv_result.scalars().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    suggestions = []

    # Match by po_reference
    if invoice.po_reference:
        po_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.po_number.ilike(f"%{invoice.po_reference}%")
            ).limit(5)
        )
        for po in po_result.scalars().all():
            confidence = 1.0 if po.po_number == invoice.po_reference else 0.7
            suggestions.append({
                "po_id": po.id,
                "po_number": po.po_number,
                "vendor_name": po.vendor_name,
                "total_amount": po.total_amount,
                "confidence": confidence,
                "reason": "Matched by PO reference number",
            })

    # If no po_reference match, try vendor name
    if not suggestions and invoice.supplier_name:
        po_result = await db.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.vendor_name.ilike(f"%{invoice.supplier_name}%")
            ).limit(5)
        )
        for po in po_result.scalars().all():
            suggestions.append({
                "po_id": po.id,
                "po_number": po.po_number,
                "vendor_name": po.vendor_name,
                "total_amount": po.total_amount,
                "confidence": 0.5,
                "reason": "Matched by vendor name",
            })

    return suggestions


# ── Helper: Build response with denormalized data ─────────────

def _build_match_response(mr: POMatchResult, po, invoice) -> MatchResultResponse:
    """Build MatchResultResponse with denormalized line item data."""
    # Build lookup maps
    inv_lines = {li.id: li for li in (invoice.line_items if invoice else [])}
    po_lines = {li.id: li for li in (po.line_items if po else [])}

    line_responses = []
    for lm in mr.line_matches:
        inv_li = inv_lines.get(lm.invoice_line_item_id) if lm.invoice_line_item_id else None
        po_li = po_lines.get(lm.po_line_item_id) if lm.po_line_item_id else None

        line_responses.append(LineMatchDetailResponse(
            id=lm.id,
            invoice_line_item_id=lm.invoice_line_item_id,
            po_line_item_id=lm.po_line_item_id,
            match_status=lm.match_status,
            quantity_match=lm.quantity_match,
            price_match=lm.price_match,
            quantity_diff=lm.quantity_diff,
            quantity_diff_pct=lm.quantity_diff_pct,
            price_diff=lm.price_diff,
            price_diff_pct=lm.price_diff_pct,
            grn_received_qty=lm.grn_received_qty,
            ses_completed_qty=lm.ses_completed_qty,
            reasoning=lm.reasoning,
            # Denormalized
            invoice_line_description=inv_li.description if inv_li else None,
            invoice_line_qty=inv_li.quantity if inv_li else None,
            invoice_line_price=inv_li.unit_price if inv_li else None,
            invoice_line_amount=inv_li.amount if inv_li else None,
            po_line_description=po_li.description if po_li else None,
            po_line_qty=po_li.quantity if po_li else None,
            po_line_price=po_li.unit_price if po_li else None,
            po_line_amount=po_li.amount if po_li else None,
        ))

    return MatchResultResponse(
        id=mr.id,
        invoice_id=mr.invoice_id,
        po_id=mr.po_id,
        match_status=mr.match_status,
        match_type=mr.match_type,
        overall_score=mr.overall_score,
        total_amount_diff=mr.total_amount_diff,
        total_amount_diff_pct=mr.total_amount_diff_pct,
        notes=mr.notes,
        created_at=mr.created_at,
        po_number=po.po_number if po else None,
        line_matches=line_responses,
    )
