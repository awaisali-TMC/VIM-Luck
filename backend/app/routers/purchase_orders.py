import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.purchase_order import (
    PurchaseOrder, POLineItem,
    GoodsReceivedNote, GRNLineItem,
    ServiceEntrySheet, SESLineItem,
)
from app.schemas.purchase_order import (
    POCreateRequest, POUpdateRequest, POResponse, PODetailResponse, POListResponse,
    GRNCreate, GRNResponse,
    SESCreate, SESResponse,
)
from app.services.file_storage import save_uploaded_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])

VALID_PO_TRANSITIONS = {
    "draft": ["open", "cancelled"],
    "open": ["partially_received", "fully_received", "closed", "cancelled"],
    "partially_received": ["fully_received", "closed", "cancelled"],
    "fully_received": ["closed"],
    "closed": ["open"],
    "cancelled": ["draft"],
}


# ── Create PO (manual) ────────────────────────────────────────

@router.post("/", response_model=POResponse, status_code=201)
async def create_purchase_order(req: POCreateRequest, db: AsyncSession = Depends(get_db)):
    # Check for duplicate po_number
    existing = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.po_number == req.po_number)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"PO number '{req.po_number}' already exists")

    po = PurchaseOrder(
        po_number=req.po_number,
        vendor_name=req.vendor_name,
        vendor_ntn=req.vendor_ntn,
        po_date=req.po_date,
        po_type=req.po_type,
        total_amount=req.total_amount,
        currency=req.currency,
        status=req.status,
        notes=req.notes,
        source_type=req.source_type,
        original_filename=req.original_filename,
        stored_filepath=req.stored_filepath,
    )

    # Add line items
    for idx, li in enumerate(req.line_items):
        po.line_items.append(POLineItem(
            item_number=li.item_number or (idx + 1),
            description=li.description,
            quantity=li.quantity,
            unit=li.unit,
            unit_price=li.unit_price,
            amount=li.amount or (li.quantity * li.unit_price),
        ))

    # Auto-calculate total if not provided
    if po.total_amount is None and po.line_items:
        po.total_amount = sum(li.amount or (li.quantity * li.unit_price) for li in po.line_items)

    db.add(po)
    await db.commit()
    await db.refresh(po, ["line_items"])
    return po


# ── Upload PO file → Gemini extraction ────────────────────────

@router.post("/upload", response_model=POResponse, status_code=201)
async def upload_purchase_order(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    allowed = [
        "application/pdf",
        "image/jpeg", "image/png", "image/tiff",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ]
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Supported: PDF, JPEG, PNG, TIFF, Excel."
        )

    content = await file.read()

    # Save file
    stored_path = save_uploaded_file(content, file.filename)

    # Extract using Gemini
    try:
        from app.services.gemini_po_extract import extract_po_from_file
        result = extract_po_from_file(content, file.content_type)
    except Exception:
        logger.exception("PO extraction failed")
        raise HTTPException(status_code=500, detail="PO extraction failed — see server logs.")

    # Save extracted PO to database
    po_number = result.get("po_number") or f"UPLOAD-{file.filename}"

    # Check for duplicate po_number
    existing = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"PO number '{po_number}' already exists")

    po = PurchaseOrder(
        po_number=po_number,
        vendor_name=result.get("vendor_name") or "Unknown Vendor",
        vendor_ntn=result.get("vendor_ntn"),
        po_date=result.get("po_date"),
        po_type=result.get("po_type") or "local",
        total_amount=result.get("total_amount"),
        currency=result.get("currency") or "PKR",
        status="open",
        notes=result.get("notes"),
        source_type="file_upload",
        original_filename=file.filename,
        stored_filepath=stored_path,
    )

    for idx, li in enumerate(result.get("line_items", [])):
        po.line_items.append(POLineItem(
            item_number=li.get("item_number") or (idx + 1),
            description=li.get("description") or "",
            quantity=li.get("quantity") or 0,
            unit=li.get("unit"),
            unit_price=li.get("unit_price") or 0,
            amount=li.get("amount") or ((li.get("quantity") or 0) * (li.get("unit_price") or 0)),
        ))

    # Auto-calculate total if not extracted
    if po.total_amount is None and po.line_items:
        po.total_amount = sum(li.amount for li in po.line_items)

    db.add(po)
    await db.commit()
    await db.refresh(po, ["line_items"])
    return po


# ── List POs ───────────────────────────────────────────────────

@router.get("/", response_model=POListResponse)
async def list_purchase_orders(
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    vendor_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items))

    if status:
        query = query.where(PurchaseOrder.status == status)
    if vendor_name:
        query = query.where(PurchaseOrder.vendor_name.ilike(f"%{vendor_name}%"))
    if search:
        query = query.where(
            PurchaseOrder.po_number.ilike(f"%{search}%")
            | PurchaseOrder.vendor_name.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count()).select_from(PurchaseOrder)
    if status:
        count_query = count_query.where(PurchaseOrder.status == status)
    if vendor_name:
        count_query = count_query.where(PurchaseOrder.vendor_name.ilike(f"%{vendor_name}%"))
    if search:
        count_query = count_query.where(
            PurchaseOrder.po_number.ilike(f"%{search}%")
            | PurchaseOrder.vendor_name.ilike(f"%{search}%")
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(PurchaseOrder.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    pos = result.scalars().all()

    return POListResponse(purchase_orders=pos, total=total)


# ── Quick-search POs (for autocomplete) ───────────────────────

@router.get("/search")
async def search_purchase_orders(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PurchaseOrder)
        .where(
            PurchaseOrder.po_number.ilike(f"%{q}%")
            | PurchaseOrder.vendor_name.ilike(f"%{q}%")
        )
        .order_by(PurchaseOrder.created_at.desc())
        .limit(10)
    )
    result = await db.execute(query)
    pos = result.scalars().all()
    return [
        {
            "id": po.id,
            "po_number": po.po_number,
            "vendor_name": po.vendor_name,
            "total_amount": po.total_amount,
            "currency": po.currency,
            "status": po.status,
        }
        for po in pos
    ]


# ── Get PO detail ─────────────────────────────────────────────

@router.get("/{po_id}", response_model=PODetailResponse)
async def get_purchase_order(po_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.grns).selectinload(GoodsReceivedNote.line_items),
            selectinload(PurchaseOrder.ses_records).selectinload(ServiceEntrySheet.line_items),
        )
        .where(PurchaseOrder.id == po_id)
    )
    po = result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")
    return po


# ── Update PO ──────────────────────────────────────────────────

@router.put("/{po_id}", response_model=PODetailResponse)
async def update_purchase_order(
    po_id: int, req: POUpdateRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == po_id)
    )
    po = result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    # Update header fields
    for field in ["po_number", "vendor_name", "vendor_ntn", "po_date", "po_type",
                  "total_amount", "currency", "status", "notes"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(po, field, val)

    # Replace line items if provided
    if req.line_items is not None:
        # Delete existing
        for li in po.line_items:
            await db.delete(li)
        await db.flush()

        # Create new
        po.line_items = []
        for idx, li in enumerate(req.line_items):
            po.line_items.append(POLineItem(
                item_number=li.item_number or (idx + 1),
                description=li.description or "",
                quantity=li.quantity or 0,
                unit=li.unit,
                unit_price=li.unit_price or 0,
                amount=li.amount or ((li.quantity or 0) * (li.unit_price or 0)),
            ))

        # Recalculate total
        if po.line_items:
            po.total_amount = sum(li.amount for li in po.line_items)

    await db.commit()

    # Reload with all relationships
    result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.grns).selectinload(GoodsReceivedNote.line_items),
            selectinload(PurchaseOrder.ses_records).selectinload(ServiceEntrySheet.line_items),
        )
        .where(PurchaseOrder.id == po_id)
    )
    return result.scalars().first()


# ── Change PO status ───────────────────────────────────────────

@router.patch("/{po_id}/status", response_model=PODetailResponse)
async def change_po_status(po_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    new_status = body.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing 'status' field")

    result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    )
    po = result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    valid = VALID_PO_TRANSITIONS.get(po.status, [])
    if new_status not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{po.status}' to '{new_status}'. Valid: {valid}"
        )

    po.status = new_status
    await db.commit()

    result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.grns).selectinload(GoodsReceivedNote.line_items),
            selectinload(PurchaseOrder.ses_records).selectinload(ServiceEntrySheet.line_items),
        )
        .where(PurchaseOrder.id == po_id)
    )
    return result.scalars().first()


# ── Delete PO ──────────────────────────────────────────────────

@router.delete("/{po_id}", status_code=204)
async def delete_purchase_order(po_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PurchaseOrder).where(PurchaseOrder.id == po_id)
    )
    po = result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    await db.delete(po)
    await db.commit()


# ── GRN endpoints ─────────────────────────────────────────────

@router.post("/{po_id}/grn", response_model=GRNResponse, status_code=201)
async def create_grn(po_id: int, req: GRNCreate, db: AsyncSession = Depends(get_db)):
    # Verify PO exists
    po_result = await db.execute(
        select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == po_id)
    )
    po = po_result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    # Check duplicate GRN number
    existing = await db.execute(
        select(GoodsReceivedNote).where(GoodsReceivedNote.grn_number == req.grn_number)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"GRN number '{req.grn_number}' already exists")

    # Validate PO line item IDs
    po_line_ids = {li.id for li in po.line_items}
    for li in req.line_items:
        if li.po_line_item_id not in po_line_ids:
            raise HTTPException(
                status_code=400,
                detail=f"PO line item ID {li.po_line_item_id} does not belong to PO {po_id}"
            )

    grn = GoodsReceivedNote(
        grn_number=req.grn_number,
        grn_date=req.grn_date,
        po_id=po_id,
        received_by=req.received_by,
        plant_location=req.plant_location,
        notes=req.notes,
    )

    for li in req.line_items:
        grn.line_items.append(GRNLineItem(
            po_line_item_id=li.po_line_item_id,
            received_quantity=li.received_quantity,
            inspection_status=li.inspection_status,
        ))

    db.add(grn)

    # Auto-update PO status based on received quantities
    await _update_po_received_status(po, db)

    await db.commit()
    await db.refresh(grn, ["line_items"])
    return grn


@router.get("/{po_id}/grns", response_model=list[GRNResponse])
async def list_grns(po_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GoodsReceivedNote)
        .options(selectinload(GoodsReceivedNote.line_items))
        .where(GoodsReceivedNote.po_id == po_id)
        .order_by(GoodsReceivedNote.created_at.desc())
    )
    return result.scalars().all()


# ── SES endpoints ─────────────────────────────────────────────

@router.post("/{po_id}/ses", response_model=SESResponse, status_code=201)
async def create_ses(po_id: int, req: SESCreate, db: AsyncSession = Depends(get_db)):
    # Verify PO exists
    po_result = await db.execute(
        select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == po_id)
    )
    po = po_result.scalars().first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase Order not found")

    # Check duplicate SES number
    existing = await db.execute(
        select(ServiceEntrySheet).where(ServiceEntrySheet.ses_number == req.ses_number)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"SES number '{req.ses_number}' already exists")

    # Validate PO line item IDs
    po_line_ids = {li.id for li in po.line_items}
    for li in req.line_items:
        if li.po_line_item_id not in po_line_ids:
            raise HTTPException(
                status_code=400,
                detail=f"PO line item ID {li.po_line_item_id} does not belong to PO {po_id}"
            )

    ses = ServiceEntrySheet(
        ses_number=req.ses_number,
        ses_date=req.ses_date,
        po_id=po_id,
        service_period_from=req.service_period_from,
        service_period_to=req.service_period_to,
        notes=req.notes,
    )

    for li in req.line_items:
        ses.line_items.append(SESLineItem(
            po_line_item_id=li.po_line_item_id,
            completed_quantity=li.completed_quantity,
            completed_amount=li.completed_amount,
        ))

    db.add(ses)

    # Auto-update PO status
    await _update_po_received_status(po, db)

    await db.commit()
    await db.refresh(ses, ["line_items"])
    return ses


@router.get("/{po_id}/ses", response_model=list[SESResponse])
async def list_ses(po_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ServiceEntrySheet)
        .options(selectinload(ServiceEntrySheet.line_items))
        .where(ServiceEntrySheet.po_id == po_id)
        .order_by(ServiceEntrySheet.created_at.desc())
    )
    return result.scalars().all()


# ── Helpers ────────────────────────────────────────────────────

async def _update_po_received_status(po: PurchaseOrder, db: AsyncSession):
    """Auto-update PO status based on total received/completed quantities."""
    # Reload PO with all GRN and SES data
    full_result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.line_items),
            selectinload(PurchaseOrder.grns).selectinload(GoodsReceivedNote.line_items),
            selectinload(PurchaseOrder.ses_records).selectinload(ServiceEntrySheet.line_items),
        )
        .where(PurchaseOrder.id == po.id)
    )
    po_full = full_result.scalars().first()
    if not po_full or not po_full.line_items:
        return

    all_fully_received = True
    any_received = False

    for po_line in po_full.line_items:
        # Sum GRN received quantities for this line
        grn_total = sum(
            grn_li.received_quantity
            for grn in po_full.grns
            for grn_li in grn.line_items
            if grn_li.po_line_item_id == po_line.id
        )
        # Sum SES completed quantities for this line
        ses_total = sum(
            ses_li.completed_quantity
            for ses in po_full.ses_records
            for ses_li in ses.line_items
            if ses_li.po_line_item_id == po_line.id
        )
        total_received = grn_total + ses_total

        if total_received > 0:
            any_received = True
        if total_received < po_line.quantity:
            all_fully_received = False

    if all_fully_received and any_received:
        po.status = "fully_received"
    elif any_received:
        po.status = "partially_received"
