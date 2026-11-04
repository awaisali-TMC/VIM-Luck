import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db, async_session
from app.security import get_current_principal, Principal
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from app.models.supplier import SupplierUser
from app.schemas.invoice import (
    ExtractionResult,
    ExtractedField,
    ExtractedLineItem,
    DetectedTax,
    ProductMatch,
    AttentionFlag,
    InvoiceSaveRequest,
    InvoiceResponse,
    InvoiceDetailResponse,
    InvoiceUpdateRequest,
    StatusUpdateRequest,
    InvoiceListResponse,
)
from app.models.product import Product
from app.services.gemini_extract import extract_invoice
from app.services.gemini_product_match import match_products
from app.services.file_storage import (
    save_uploaded_file,
    content_matches_type,
    resolve_stored_file,
    sniff_inline_type,
)
from app.services.duplicate_detection import check_duplicates
from app.services.invoice_classifier import classify_invoice

logger = logging.getLogger(__name__)

# ── Serial matching queue ─────────────────────────────────────────────────────
# One worker processes jobs one-by-one in FIFO order.
_matching_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None


async def _queue_worker() -> None:
    """Consume the matching queue serially — one invoice at a time."""
    while True:
        invoice_id = await _matching_queue.get()
        try:
            await _run_product_matching(invoice_id)
        except Exception as exc:
            logger.error(f"Queue worker unhandled error for invoice {invoice_id}: {exc}")
        finally:
            _matching_queue.task_done()


async def start_matching_queue() -> asyncio.Task:
    """Create queue + start the single serial worker. Called from app lifespan."""
    global _matching_queue, _worker_task
    _matching_queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_queue_worker(), name="matching-queue-worker")
    logger.info("Product matching queue worker started")
    return _worker_task


async def stop_matching_queue() -> None:
    """Cancel the worker on shutdown."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    logger.info("Product matching queue worker stopped")

# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

MIME_MAP = {
    "application/pdf": "application/pdf",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/tiff": "image/tiff",
}

# Valid status transitions (state machine)
# validated → pending_approval (if workflow matches) or → posted (if no workflow)
# pending_approval → approved/rejected (controlled by workflow engine)
# approved → posted
VALID_TRANSITIONS = {
    "draft": ["pending_processing"],
    "pending_processing": ["validated", "exception"],
    "validated": ["pending_approval", "parked", "posted", "exception"],
    "pending_approval": ["approved", "rejected"],
    "approved": ["parked", "posted", "exception"],
    "rejected": ["exception", "pending_processing", "pending_approval", "validated"],
    "exception": ["pending_processing", "validated"],
    "parked": ["posted", "exception"],  # parked in SAP; a SAP user posts it (or it's reversed)
    "posted": [],  # terminal state
}


def _clamp(v, n):
    """Truncate a string to the column length — Postgres enforces VARCHAR
    limits (SQLite doesn't), and AI-extracted or user-edited text can exceed
    them (e.g. a long bank/remit-to block in bank_iban). Used by every path
    that INSERTs an Invoice (draft creation and /save)."""
    s = str(v).strip() if v is not None else None
    return s[:n] if s else None


# Legal-form noise that legitimately differs between a registered company name
# and how it is printed on invoice documents.
_COMPANY_STOPWORDS = {
    "pvt", "private", "ltd", "limited", "co", "company", "inc", "incorporated",
    "llc", "corp", "corporation", "enterprises", "enterprise", "traders",
    "trading", "industries", "the", "and", "of", "&",
}


def _company_tokens(name: str | None) -> set[str]:
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return {t for t in s.split() if t and t not in _COMPANY_STOPWORDS}


def _supplier_name_matches(extracted: str | None, registered: str | None) -> bool:
    """Lenient company-name comparison for the supplier-upload vendor gate.

    Tolerates legal-form suffixes, punctuation and partial names ("Al-Badar"
    vs "AL-BADAR ENTERPRISES (Pvt) Ltd") while rejecting genuinely different
    companies. Empty/unparseable names count as a match — the gate only fires
    on a confident mismatch.
    """
    a, b = _company_tokens(extracted), _company_tokens(registered)
    if not a or not b:
        return True
    if a <= b or b <= a:
        return True
    return len(a & b) / min(len(a), len(b)) >= 0.6


def _scope_query_to_principal(query, principal: Principal):
    """Restrict an Invoice query to rows the principal is allowed to see.

    Internal users (staff) see everything. Suppliers see only invoices they
    submitted (invoices.supplier_id == their id). This is the object-level
    access control layer — the router-level dependency only proves the caller
    is authenticated, not that they own a given row.
    """
    if principal.kind == "supplier":
        return query.where(Invoice.supplier_id == principal.id)
    return query


def _assert_can_access(invoice: Invoice, principal: Principal) -> None:
    """Raise 404 if a supplier tries to touch an invoice that isn't theirs.

    We return 404 (not 403) so the API doesn't leak the existence of invoices
    belonging to other suppliers.
    """
    if principal.kind == "supplier" and invoice.supplier_id != principal.id:
        raise HTTPException(status_code=404, detail="Invoice not found")


def _build_detail_response(invoice: Invoice) -> InvoiceDetailResponse:
    """Build an InvoiceDetailResponse from an ORM Invoice, parsing JSON text fields."""
    field_confidences = None
    if invoice.field_confidences:
        try:
            field_confidences = json.loads(invoice.field_confidences)
        except (json.JSONDecodeError, TypeError):
            field_confidences = None

    warnings = None
    if invoice.warnings:
        try:
            warnings = json.loads(invoice.warnings)
        except (json.JSONDecodeError, TypeError):
            warnings = None

    detected_taxes = None
    if invoice.detected_taxes:
        try:
            detected_taxes = json.loads(invoice.detected_taxes)
        except (json.JSONDecodeError, TypeError):
            detected_taxes = None

    return InvoiceDetailResponse(
        id=invoice.id,
        original_filename=invoice.original_filename,
        stored_filepath=invoice.stored_filepath,
        mime_type=invoice.mime_type,
        file_size_bytes=invoice.file_size_bytes,
        page_count=invoice.page_count,
        document_available=resolve_stored_file(invoice.stored_filepath) is not None,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        currency=invoice.currency or "PKR",
        supplier_name=invoice.supplier_name,
        supplier_address=invoice.supplier_address,
        supplier_ntn=invoice.supplier_ntn,
        receiver_name=invoice.receiver_name,
        receiver_address=invoice.receiver_address,
        subtotal_amount=invoice.subtotal_amount,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        gst_amount=invoice.gst_amount,
        wht_amount=invoice.wht_amount,
        detected_taxes=detected_taxes,
        po_reference=invoice.po_reference,
        bank_iban=invoice.bank_iban,
        document_type=invoice.document_type,
        overall_confidence=invoice.overall_confidence,
        field_confidences=field_confidences,
        warnings=warnings,
        processing_time_ms=invoice.processing_time_ms,
        status=invoice.status,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        line_items=invoice.line_items,
        source_type=invoice.source_type or "upload",
        source_email_from=invoice.source_email_from,
        fbr_verification_status=invoice.fbr_verification_status or "not_verified",
        fbr_verified_at=invoice.fbr_verified_at,
        fbr_taxpayer_name=invoice.fbr_taxpayer_name,
        fbr_filing_status=invoice.fbr_filing_status,
        wht_compliance_status=invoice.wht_compliance_status,
        # Credit/Debit note fields
        linked_invoice_id=invoice.linked_invoice_id,
        credit_debit_reason=invoice.credit_debit_reason,
        original_invoice_number=invoice.original_invoice_number,
        # Multi-currency
        base_currency=invoice.base_currency or "PKR",
        exchange_rate=invoice.exchange_rate,
        base_total_amount=invoice.base_total_amount,
        # SAP posting
        sap_document_number=invoice.sap_document_number,
        sap_fiscal_year=invoice.sap_fiscal_year,
        sap_company_code=invoice.sap_company_code,
        sap_posted_at=invoice.sap_posted_at,
        sap_doc_status=invoice.sap_doc_status,
        sap_tax_code=invoice.sap_tax_code,
        sap_layout=invoice.sap_layout,
        sap_posting_date=invoice.sap_posting_date,
        sap_baseline_date=invoice.sap_baseline_date,
        sap_header_text=invoice.sap_header_text,
        sap_item_text=invoice.sap_item_text,
        sap_currency=invoice.sap_currency,
        sap_vendor_number=invoice.sap_vendor_number,
        parking_line_item_ids=(json.loads(invoice.parking_line_item_ids) if invoice.parking_line_item_ids else None),
        # PO matching
        matched_po_id=invoice.matched_po_id,
        latest_po_match_status=invoice.latest_po_match_status,
    )


def _validate_upload(file_content: bytes, content_type: str) -> None:
    """Shared upload validations: type allowed, size cap, signature match."""
    if content_type not in MIME_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, JPEG, PNG, TIFF",
        )
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )
    if not content_matches_type(file_content, MIME_MAP[content_type]):
        raise HTTPException(
            status_code=400,
            detail="File content does not match its declared type.",
        )


def _pnum(v):
    """Parse a possibly comma-formatted number string to float (None-safe)."""
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _extraction_to_draft(result: dict, filename: str, stored_path: str,
                         mime_type: str, size: int,
                         supplier_id: int | None = None,
                         source_type: str = "upload") -> Invoice:
    """Build a DRAFT Invoice (with line items) from an extraction result —
    the server-side equivalent of the extraction-review screen's save.

    supplier_id/source_type scope the draft to its owner: when a SUPPLIER
    uploads (incl. multi-invoice split / batch), the drafts must carry their
    supplier_id or the supplier can't see their own uploads (the list filters
    on supplier_id)."""
    fm = {f["field_name"]: f["value"] for f in result.get("fields", [])}
    cm = {f["field_name"]: f.get("confidence") for f in result.get("fields", [])}

    clamp = _clamp

    invoice = Invoice(
        original_filename=clamp(filename, 255),
        stored_filepath=stored_path,
        mime_type=clamp(mime_type, 100),
        file_size_bytes=size,
        page_count=result.get("page_count"),
        invoice_number=clamp(fm.get("invoice_id") or fm.get("invoice_number"), 100),
        invoice_date=clamp(fm.get("invoice_date"), 50),
        due_date=clamp(fm.get("due_date"), 50),
        currency=clamp(fm.get("currency"), 10) or "PKR",
        supplier_name=clamp(fm.get("supplier_name"), 255),
        supplier_address=fm.get("supplier_address"),
        supplier_ntn=clamp(fm.get("supplier_tax_id"), 50),
        receiver_name=clamp(fm.get("receiver_name"), 255),
        receiver_address=fm.get("receiver_address"),
        subtotal_amount=_pnum(fm.get("net_amount")),
        tax_amount=_pnum(fm.get("total_tax_amount")),
        total_amount=_pnum(fm.get("total_amount")),
        po_reference=clamp(fm.get("purchase_order"), 100),
        bank_iban=clamp(fm.get("remit_to_address"), 100),
        document_type=clamp(result.get("document_type"), 50),
        overall_confidence=result.get("overall_confidence"),
        field_confidences=json.dumps(cm) if cm else None,
        warnings=json.dumps(result.get("warnings")) if result.get("warnings") else None,
        detected_taxes=json.dumps(result.get("detected_taxes")) if result.get("detected_taxes") else None,
        processing_time_ms=result.get("processing_time_ms"),
        status=InvoiceStatus.DRAFT.value,
        supplier_id=supplier_id,
        source_type=source_type,
        base_currency="PKR",
    )
    for li in result.get("line_items", []):
        invoice.line_items.append(InvoiceLineItem(
            description=li.get("description"),
            quantity=li.get("quantity"),
            unit=li.get("unit"),
            unit_price=li.get("unit_price"),
            amount=li.get("amount"),
            description_confidence=li.get("description_confidence"),
            quantity_confidence=li.get("quantity_confidence"),
            unit_price_confidence=li.get("unit_price_confidence"),
            amount_confidence=li.get("amount_confidence"),
        ))
    return invoice


def _split_pdf_by_ranges(file_content: bytes, ranges: list) -> list[bytes]:
    """Split a PDF into one sub-PDF per [start,end] 1-based page range."""
    import io
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(file_content))
    total = len(reader.pages)
    parts = []
    for r in ranges:
        try:
            start, end = int(r[0]), int(r[1])
        except (TypeError, ValueError, IndexError):
            continue
        start, end = max(1, start), min(total, end)
        if start > end:
            continue
        writer = PdfWriter()
        for p in range(start - 1, end):
            writer.add_page(reader.pages[p])
        buf = io.BytesIO()
        writer.write(buf)
        parts.append(buf.getvalue())
    return parts


def _pdf_page_count(file_content: bytes) -> int:
    import io
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(file_content)).pages)


def _merge_images_to_pdf(images: list[bytes]) -> bytes:
    """Merge image files (in order) into a single multi-page PDF. Used when a
    batch upload contains several photos: pages of ONE invoice photographed
    separately become one document — segmentation then decides whether the
    combined document is one invoice or several."""
    import io
    from PIL import Image
    pages = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


async def _save_multi_invoice_drafts(db: AsyncSession, file_content: bytes,
                                     content_type: str, filename: str,
                                     first_result: dict,
                                     supplier_id: int | None = None,
                                     source_type: str = "upload") -> list[Invoice]:
    """A file contains several distinct invoices: run a DEDICATED segmentation
    pass (per-page invoice mapping — reliable even for 20-page files with 1/2/
    3/5-page invoices), split the PDF per invoice, extract each part, and save
    every invoice as a DRAFT. A part that still looks multi-invoice gets one
    second-chance split. Returns the drafts.

    supplier_id/source_type are stamped on every draft so supplier uploads stay
    scoped to their owner."""
    from app.services.gemini_extract import segment_invoice_pages

    def _draft(result, name, stored, mime_t, size):
        return _extraction_to_draft(result, name, stored, mime_t, size,
                                    supplier_id=supplier_id, source_type=source_type)

    drafts: list[Invoice] = []
    mime = MIME_MAP[content_type]
    stem = (filename or "invoice").rsplit(".", 1)[0]

    async def _flush() -> list[Invoice]:
        for d in drafts:
            db.add(d)
        await db.commit()
        for d in drafts:
            await db.refresh(d)
        return drafts

    parts: list[tuple[bytes, str]] = []
    if mime == "application/pdf":
        total_pages = _pdf_page_count(file_content)
        # Dedicated boundary detection (not the extraction call's guess).
        ranges = segment_invoice_pages(file_content, mime, total_pages)
        if len(ranges) >= 2:
            for i, part in enumerate(_split_pdf_by_ranges(file_content, ranges), start=1):
                parts.append((part, f"{stem}_invoice{i}.pdf"))

    if not parts:
        # Can't split (image, or segmentation says one span) — save the whole
        # file as ONE draft using the first invoice's extraction, flagged.
        first_result.setdefault("warnings", []).append(
            f"File appears to contain {first_result.get('invoice_count')} invoices "
            "but could not be split automatically — review and split manually."
        )
        stored = save_uploaded_file(file_content, filename)
        drafts.append(_draft(first_result, filename, stored, mime, len(file_content)))
        return await _flush()

    for part_bytes, part_name in parts:
        try:
            part_result = extract_invoice(part_bytes, "application/pdf")
        except Exception:
            logger.exception("Extraction failed for split part %s", part_name)
            continue

        # Second chance: a missed boundary leaves a part that itself contains
        # several invoices — re-segment and split that part once more.
        if part_result.get("multiple_invoices"):
            sub_pages = _pdf_page_count(part_bytes)
            sub_ranges = segment_invoice_pages(part_bytes, "application/pdf", sub_pages) if sub_pages > 1 else []
            if len(sub_ranges) >= 2:
                logger.info("Re-splitting part %s into %d invoices", part_name, len(sub_ranges))
                sub_stem = part_name.rsplit(".", 1)[0]
                for j, sub in enumerate(_split_pdf_by_ranges(part_bytes, sub_ranges), start=1):
                    try:
                        sub_result = extract_invoice(sub, "application/pdf")
                    except Exception:
                        logger.exception("Extraction failed for re-split part %s_%d", sub_stem, j)
                        continue
                    stored = save_uploaded_file(sub, f"{sub_stem}_{j}.pdf")
                    drafts.append(_draft(sub_result, f"{sub_stem}_{j}.pdf",
                                         stored, "application/pdf", len(sub)))
                continue
            part_result.setdefault("warnings", []).append(
                "This part may still contain more than one invoice — review manually."
            )

        stored = save_uploaded_file(part_bytes, part_name)
        drafts.append(_draft(part_result, part_name, stored,
                             "application/pdf", len(part_bytes)))

    return await _flush()


def _draft_summary(inv: Invoice, source_file: str) -> dict:
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "supplier_name": inv.supplier_name,
        "total_amount": inv.total_amount,
        "currency": inv.currency,
        "status": inv.status,
        "source_file": source_file,
    }


@router.post("/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Upload ONE invoice file and return extraction results for review.

    If the file turns out to contain MULTIPLE distinct invoices, it is split
    automatically: each invoice is saved as a DRAFT and the response is
    {batch: true, invoices: [...]} instead of an extraction result — the UI
    then lands on the Invoice Inbox with the new drafts highlighted."""
    content_type = file.content_type or ""
    file_content = await file.read()
    _validate_upload(file_content, content_type)

    # Scope drafts to their owner: a supplier's uploads must carry supplier_id
    # (and source_type=supplier) or the supplier can't see them.
    owner_supplier_id = principal.id if principal.kind == "supplier" else None
    src_type = "supplier" if principal.kind == "supplier" else "upload"

    stored_path = save_uploaded_file(file_content, file.filename)

    # Single Gemini call — extracts fields, line items, and taxes together
    try:
        result = extract_invoice(file_content, MIME_MAP[content_type])
    except Exception:
        logger.exception("Invoice extraction failed")
        raise HTTPException(
            status_code=500, detail="Invoice extraction failed — see server logs."
        )

    if result.get("multiple_invoices"):
        drafts = await _save_multi_invoice_drafts(
            db, file_content, content_type, file.filename, result,
            supplier_id=owner_supplier_id, source_type=src_type,
        )
        return {
            "batch": True,
            "invoice_count": len(drafts),
            "invoices": [_draft_summary(d, file.filename) for d in drafts],
        }

    return ExtractionResult(
        fields=[ExtractedField(**f) for f in result["fields"]],
        line_items=[ExtractedLineItem(**li) for li in result["line_items"]],
        overall_confidence=result["overall_confidence"],
        document_type=result["document_type"],
        page_count=result["page_count"],
        processing_time_ms=result["processing_time_ms"],
        warnings=result["warnings"],
        original_filename=file.filename,
        stored_filepath=stored_path,
        raw_document_ai=None,
        detected_taxes=[DetectedTax(**t) for t in result["detected_taxes"]],
        tax_summary=result.get("tax_summary"),
        gemini_confidence=result.get("gemini_confidence"),
        gemini_processing_time_ms=result.get("gemini_processing_time_ms"),
        product_matches=[],
        product_match_processing_time_ms=None,
        line_items_source=result.get("line_items_source", "gemini"),
        attention_flags=[AttentionFlag(**f) for f in result.get("attention_flags", [])],
    )


@router.post("/upload-batch")
async def upload_invoices_batch(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Upload SEVERAL invoice files at once. Every invoice found is saved as a
    DRAFT — no per-invoice review screen; the UI lands on the Invoice Inbox
    with the new drafts highlighted.

    IMAGE files in the batch are merged (in order) into ONE document first —
    pages of a single invoice photographed as separate images become one
    invoice; if the combined document actually holds several invoices, the
    segmentation pass splits it correctly. PDFs are processed individually
    (a PDF is already a complete document)."""
    created: list[dict] = []
    errors: list[dict] = []

    # Scope drafts to their owner (supplier uploads must carry supplier_id).
    owner_supplier_id = principal.id if principal.kind == "supplier" else None
    src_type = "supplier" if principal.kind == "supplier" else "upload"

    async def _process_document(file_content: bytes, content_type: str, fname: str):
        result = extract_invoice(file_content, MIME_MAP[content_type])
        if result.get("multiple_invoices"):
            return await _save_multi_invoice_drafts(
                db, file_content, content_type, fname, result,
                supplier_id=owner_supplier_id, source_type=src_type,
            )
        stored = save_uploaded_file(file_content, fname)
        draft = _extraction_to_draft(result, fname, stored, MIME_MAP[content_type], len(file_content),
                                     supplier_id=owner_supplier_id, source_type=src_type)
        db.add(draft)
        await db.commit()
        await db.refresh(draft)
        return [draft]

    # Read + validate everything up front, partition images vs PDFs.
    images: list[tuple[bytes, str, str]] = []   # (content, filename, content_type)
    pdfs: list[tuple[bytes, str, str]] = []
    for file in files:
        fname = file.filename or "invoice"
        try:
            content_type = file.content_type or ""
            file_content = await file.read()
            _validate_upload(file_content, content_type)
            if MIME_MAP[content_type] == "application/pdf":
                pdfs.append((file_content, fname, content_type))
            else:
                images.append((file_content, fname, content_type))
        except HTTPException as e:
            errors.append({"file": fname, "error": str(e.detail)})

    # Images: several photos = pages of one document → merge, then let the
    # multi-invoice pipeline decide (1 invoice, or split into N).
    if len(images) >= 2:
        fname = images[0][1].rsplit(".", 1)[0] + "_combined.pdf"
        try:
            merged = _merge_images_to_pdf([b for b, _, _ in images])
            drafts = await _process_document(merged, "application/pdf", fname)
            created.extend(_draft_summary(d, fname) for d in drafts)
        except Exception:
            logger.exception("Batch upload failed for combined images %s", fname)
            errors.append({"file": fname, "error": "Extraction failed — see server logs."})
        images = []

    for content, fname, ctype in images + pdfs:
        try:
            drafts = await _process_document(content, ctype, fname)
            created.extend(_draft_summary(d, fname) for d in drafts)
        except Exception:
            logger.exception("Batch upload failed for %s", fname)
            errors.append({"file": fname, "error": "Extraction failed — see server logs."})

    return {
        "batch": True,
        "invoice_count": len(created),
        "invoices": created,
        "errors": errors,
    }


@router.post("/save", response_model=InvoiceResponse)
async def save_invoice(
    data: InvoiceSaveRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Save extracted (and possibly user-corrected) invoice to database."""
    # Stamp ownership: a supplier-submitted invoice is bound to that supplier so
    # object-level access control can later restrict them to their own records.
    owner_supplier_id = principal.id if principal.kind == "supplier" else None

    # Vendor gate: a supplier may only invoice as their own registered company.
    # A confident mismatch records a prominent WARNING on the invoice (shown to
    # AP on the detail page) but does NOT change the status — the Exception
    # status is reserved for approvers explicitly flagging an invoice. OCR
    # noise and trading-name variants need a human eye, not a hard wall.
    warnings = list(data.warnings or [])
    status = data.status
    if owner_supplier_id is not None and data.supplier_name:
        supplier = await db.get(SupplierUser, owner_supplier_id)
        registered = supplier.company_name if supplier else None
        if registered and not _supplier_name_matches(data.supplier_name, registered):
            warnings.append(
                f"Vendor name on the document ('{data.supplier_name}') does not match "
                f"the registered supplier company ('{registered}'). Please verify before approval."
            )
            logger.warning(
                "Supplier vendor-name mismatch: supplier_id=%s registered=%r document=%r",
                owner_supplier_id, registered, data.supplier_name,
            )

    # _clamp: Postgres enforces VARCHAR lengths (SQLite dev doesn't) — an
    # over-long extracted/edited field must not 500 the whole save.
    invoice = Invoice(
        supplier_id=owner_supplier_id,
        original_filename=_clamp(data.original_filename, 255),
        stored_filepath=_clamp(data.stored_filepath, 500),
        mime_type=_clamp(data.mime_type, 100),
        file_size_bytes=data.file_size_bytes,
        page_count=data.page_count,
        invoice_number=_clamp(data.invoice_number, 100),
        invoice_date=_clamp(data.invoice_date, 50),
        due_date=_clamp(data.due_date, 50),
        currency=_clamp(data.currency, 10),
        supplier_name=_clamp(data.supplier_name, 255),
        supplier_address=data.supplier_address,
        supplier_ntn=_clamp(data.supplier_ntn, 50),
        receiver_name=_clamp(data.receiver_name, 255),
        receiver_address=data.receiver_address,
        subtotal_amount=data.subtotal_amount,
        tax_amount=data.tax_amount,
        total_amount=data.total_amount,
        gst_amount=data.gst_amount,
        wht_amount=data.wht_amount,
        detected_taxes=json.dumps([t.model_dump() for t in data.detected_taxes]) if data.detected_taxes else None,
        po_reference=_clamp(data.po_reference, 100),
        bank_iban=_clamp(data.bank_iban, 100),
        document_type=_clamp(data.document_type, 50),
        overall_confidence=data.overall_confidence,
        field_confidences=json.dumps(data.field_confidences) if data.field_confidences else None,
        warnings=json.dumps(warnings) if warnings else None,
        processing_time_ms=data.processing_time_ms,
        status=status,
        source_type=_clamp(data.source_type, 20) or "upload",
        source_email_id=data.source_email_id,
        source_email_from=_clamp(data.source_email_from, 500),
        # Credit/Debit note fields
        linked_invoice_id=data.linked_invoice_id,
        credit_debit_reason=data.credit_debit_reason,
        original_invoice_number=_clamp(data.original_invoice_number, 100),
        # Multi-currency
        base_currency=_clamp(data.base_currency, 10) or "PKR",
        exchange_rate=data.exchange_rate,
        base_total_amount=data.base_total_amount,
        # Non-PO lane marker + resolved vendor (both None for the PO flow)
        sap_vendor_number=_clamp(data.sap_vendor_number, 20),
    )

    for li_data in data.line_items:
        line_item = InvoiceLineItem(
            description=li_data.description,
            quantity=li_data.quantity,
            unit=_clamp(li_data.unit, 50),
            unit_price=li_data.unit_price,
            amount=li_data.amount,
            ai_description=li_data.ai_description,
            ai_quantity=li_data.ai_quantity,
            ai_unit=_clamp(li_data.ai_unit, 50),
            ai_unit_price=li_data.ai_unit_price,
            ai_amount=li_data.ai_amount,
            description_confidence=li_data.description_confidence,
            quantity_confidence=li_data.quantity_confidence,
            unit_price_confidence=li_data.unit_price_confidence,
            amount_confidence=li_data.amount_confidence,
            user_modified=1 if li_data.user_modified else 0,
        )
        invoice.line_items.append(line_item)

    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # Re-load with line items to avoid lazy-load error in async
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice.id)
    )
    invoice = result.scalar_one_or_none()

    # Auto-verify FBR if supplier NTN is present
    if data.supplier_ntn and data.supplier_ntn.strip():
        try:
            from app.services.fbr_verification import verify_ntn as _verify_ntn, check_wht_compliance
            verification = await _verify_ntn(data.supplier_ntn)
            invoice.fbr_verification_status = verification["status"]
            invoice.fbr_verified_at = verification["verified_at"]
            invoice.fbr_taxpayer_name = verification.get("taxpayer_name")
            invoice.fbr_filing_status = verification.get("filing_status")

            if data.detected_taxes:
                taxes_dicts = [t.model_dump() for t in data.detected_taxes]
                compliance = check_wht_compliance(
                    taxes_dicts, verification["is_active"], data.subtotal_amount
                )
                invoice.wht_compliance_status = compliance["status"]

            await db.commit()
        except Exception as exc:
            logger.warning(f"FBR auto-verify failed for invoice {invoice.id}: {exc}")

    # Re-load with line_items to avoid async lazy-load error in response serialization
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice.id)
    )
    invoice = result.scalar_one()

    return invoice


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List saved invoices with pagination, optionally filtered by status."""
    query = select(Invoice).options(selectinload(Invoice.line_items)).where(Invoice.is_deleted == 0)
    count_query = select(func.count(Invoice.id)).where(Invoice.is_deleted == 0)

    if status:
        query = query.where(Invoice.status == status)
        count_query = count_query.where(Invoice.status == status)

    # Suppliers only see their own submissions; internal staff see all.
    query = _scope_query_to_principal(query, principal)
    count_query = _scope_query_to_principal(count_query, principal)

    # A supplier's DRAFT is their private work-in-progress (e.g. an invoice
    # just created from a PO, not yet submitted) — it reaches the internal
    # inbox only once they Submit for Processing. Internal-created drafts
    # (supplier_id NULL) stay visible to staff as before.
    if principal.kind == "internal":
        not_supplier_draft = or_(Invoice.status != "draft", Invoice.supplier_id.is_(None))
        query = query.where(not_supplier_draft)
        count_query = count_query.where(not_supplier_draft)

    result = await db.execute(
        query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
    )
    invoices = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return InvoiceListResponse(invoices=invoices, total=total)


async def _run_product_matching(invoice_id: int) -> None:
    """Background task: run Gemini product matching and persist results to DB."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Invoice)
                .options(selectinload(Invoice.line_items))
                .where(Invoice.id == invoice_id)
            )
            invoice = result.scalar_one_or_none()
            if not invoice or not invoice.line_items:
                return

            prod_result = await db.execute(select(Product).order_by(Product.code))
            all_products = prod_result.scalars().all()
            product_dicts = [
                {"code": p.code, "name": p.name, "category": p.category, "description": p.description}
                for p in all_products
            ]

            line_item_dicts = [
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "amount": li.amount,
                }
                for li in invoice.line_items
            ]

            # match_products is sync/blocking — run in thread pool to not block event loop
            loop = asyncio.get_event_loop()
            match_result = await loop.run_in_executor(
                None, match_products, line_item_dicts, product_dicts
            )

            match_map = {m["line_item_index"]: m for m in match_result.get("matches", [])}
            for i, li in enumerate(invoice.line_items):
                m = match_map.get(i)
                if m:
                    li.matched_product_code = m["product_code"]
                    li.matched_product_name = m["product_name"]
                    li.matched_product_category = m.get("product_category")
                    li.match_confidence = m["confidence"]
                    li.match_reasoning = m.get("reasoning")

            await db.commit()
            logger.info(f"Product matching complete for invoice {invoice_id}: {len(match_map)} matches")
    except Exception as exc:
        logger.error(f"Background product matching failed for invoice {invoice_id}: {exc}")


@router.post("/{invoice_id}/match-products", status_code=202)
async def trigger_product_matching(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Add invoice to the serial product-matching queue (FIFO, one at a time)."""
    result = await db.execute(
        select(Invoice.id, Invoice.supplier_id).where(Invoice.id == invoice_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if principal.kind == "supplier" and row.supplier_id != principal.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    await _matching_queue.put(invoice_id)
    position = _matching_queue.qsize()  # items still waiting (including this one)
    logger.info(f"Invoice {invoice_id} added to matching queue (queue size: {position})")
    return {"message": "Product matching queued", "invoice_id": invoice_id, "queue_position": position}


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Get a single invoice with all fields and line items."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id, Invoice.is_deleted == 0)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)
    return _build_detail_response(invoice)


def _document_download_name(original: str | None, invoice_id: int, path) -> str:
    """A safe save-as name: the uploader's file name, with its real extension."""
    name = re.split(r"[\\/]", (original or "").strip())[-1]
    name = re.sub(r"[\x00-\x1f\x7f\"]", "", name)[:150]
    if not name or name.lower() == "unknown":
        name = f"invoice-{invoice_id}"
    if path.suffix and not name.lower().endswith(path.suffix.lower()):
        name += path.suffix
    return name


@router.get("/{invoice_id}/document")
async def get_invoice_document(
    invoice_id: int,
    download: bool = False,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Return the originally uploaded invoice file.

    Shown inline (PDF/image) by default; ?download=true asks the browser to
    save it. Suppliers only reach their own invoices (404 otherwise, as for
    every other invoice route). Only files the app stored itself are served:
    see resolve_stored_file(), since stored_filepath is client-supplied.
    """
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted == 0)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    path = resolve_stored_file(invoice.stored_filepath)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="The original document for this invoice is not available.",
        )
    # Trust the file's bytes, not the client-supplied mime_type column.
    inline_type = sniff_inline_type(path)
    return FileResponse(
        path=str(path),
        media_type=inline_type or "application/octet-stream",
        filename=_document_download_name(invoice.original_filename, invoice_id, path),
        content_disposition_type="inline" if inline_type and not download else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.put("/{invoice_id}", response_model=InvoiceDetailResponse)
async def update_invoice(
    invoice_id: int,
    data: InvoiceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Update editable fields of an invoice."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    update_data = data.model_dump(exclude_unset=True)

    # Handle line_items separately from scalar fields
    new_line_items = update_data.pop("line_items", None)

    for field, value in update_data.items():
        setattr(invoice, field, value)

    # Replace line items if provided (full replacement strategy)
    if new_line_items is not None:
        # Same rule as patch_line_item: a line billing an amount with no
        # quantity or price is derived from nothing, and a null quantity reaches
        # SAP as QUANTITY=0. This path takes `amount` from the client verbatim
        # (it never recomputes), so it is the easier of the two doors to walk
        # through — check it here before anything is deleted.
        for i, li_data in enumerate(new_line_items):
            for f in ("quantity", "unit_price"):
                if f in li_data and li_data[f] is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Line {i + 1}: {f.replace('_', ' ')} cannot be empty.",
                    )

        # Editing line items invalidates any existing PO match — and its
        # detail rows FK-reference the line items we're about to delete, so they
        # must go first or the delete fails (surfaces as a "Network Error" in the
        # browser). Drop the match; the invoice must be re-matched before parking.
        from app.models.purchase_order import POMatchResult, POLineMatchDetail
        from sqlalchemy import delete as sa_delete
        mr_ids = (
            await db.execute(select(POMatchResult.id).where(POMatchResult.invoice_id == invoice_id))
        ).scalars().all()
        if mr_ids:
            await db.execute(sa_delete(POLineMatchDetail).where(POLineMatchDetail.match_result_id.in_(mr_ids)))
            await db.execute(sa_delete(POMatchResult).where(POMatchResult.id.in_(mr_ids)))
            invoice.matched_po_id = None
            invoice.latest_po_match_status = None

        # Remove existing line items
        for existing_li in list(invoice.line_items):
            await db.delete(existing_li)
        await db.flush()

        # Add updated line items
        invoice.line_items = []
        for li_data in new_line_items:
            li_data.pop("id", None)  # strip id, always create fresh
            line_item = InvoiceLineItem(**li_data)
            invoice.line_items.append(line_item)

    await db.commit()
    await db.refresh(invoice)

    # Re-load with line items after refresh
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    return _build_detail_response(invoice)


@router.patch("/{invoice_id}/status", response_model=InvoiceDetailResponse)
async def update_invoice_status(
    invoice_id: int,
    data: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Transition invoice status with validation."""
    # Validate the target status is a real enum value
    try:
        target = InvoiceStatus(data.status)
    except ValueError:
        valid = [s.value for s in InvoiceStatus]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: '{data.status}'. Must be one of: {valid}",
        )

    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    allowed = VALID_TRANSITIONS.get(invoice.status, [])
    if target.value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{invoice.status}' to '{target.value}'. Allowed transitions: {allowed}",
        )

    invoice.status = target.value
    await db.commit()
    await db.refresh(invoice)

    # Re-load with line items after refresh
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    return _build_detail_response(invoice)


@router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Soft-delete an invoice.

    An invoice that is parked/posted in SAP CANNOT be deleted here — it must be
    unparked/reversed in SAP first (POST /api/sap/invoices/{id}/unpark), which
    soft-deletes it. This guard keeps our records consistent with SAP.
    """
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted == 0))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    if invoice.sap_document_number:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invoice is {invoice.sap_doc_status or 'parked'} in SAP as document "
                f"{invoice.sap_document_number}/{invoice.sap_fiscal_year}. Unpark it from SAP "
                f"before deleting."
            ),
        )

    invoice.is_deleted = 1
    invoice.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True, "id": invoice_id, "soft_deleted": True}


class LineItemPatch(BaseModel):
    """Partial update for a single invoice line item (inline editing)."""
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None


class ParkingSelection(BaseModel):
    line_item_ids: list[int]


@router.put("/{invoice_id}/parking-selection")
async def set_parking_selection(
    invoice_id: int,
    data: ParkingSelection,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Persist which line items are selected for parking. Set at submit-for-
    approval so the selection carries through the workflow (locked thereafter)
    and every approver sees the same lines."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted == 0))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)
    invoice.parking_line_item_ids = json.dumps(list(data.line_item_ids))
    await db.commit()
    return {"success": True, "parking_line_item_ids": data.line_item_ids}


@router.post("/{invoice_id}/line-items")
async def add_line_item(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Append a blank line item (inline 'Add line'). Returns its new id so the
    UI can edit it in place. Existing lines / PO match are untouched."""
    result = await db.execute(
        select(Invoice).options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id, Invoice.is_deleted == 0)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)
    if invoice.sap_document_number:
        raise HTTPException(status_code=409, detail="Invoice is in SAP — unpark it before editing line items.")

    line = InvoiceLineItem(
        invoice_id=invoice_id, description="", quantity=None, unit=None,
        unit_price=None, amount=None, user_modified=1,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return {"success": True, "line_item": {"id": line.id, "description": "", "quantity": None,
                                           "unit": None, "unit_price": None, "amount": None}}


@router.patch("/{invoice_id}/line-items/{line_item_id}")
async def patch_line_item(
    invoice_id: int,
    line_item_id: int,
    data: LineItemPatch,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Update one line item IN PLACE (inline editing).

    Unlike the whole-invoice PUT (which deletes + recreates all lines and thus
    invalidates the PO match), this keeps the line's id stable — so the PO match
    linkage survives. Amount is recomputed as qty × unit_price when either
    changes; the invoice subtotal/total are recomputed from all lines.
    """
    result = await db.execute(
        select(Invoice).options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id, Invoice.is_deleted == 0)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)
    if invoice.sap_document_number:
        raise HTTPException(status_code=409, detail="Invoice is in SAP — unpark it before editing line items.")

    line = next((li for li in invoice.line_items if li.id == line_item_id), None)
    if not line:
        raise HTTPException(status_code=404, detail="Line item not found on this invoice")

    fields = data.model_dump(exclude_unset=True)
    # exclude_unset distinguishes "field not sent" (a normal partial update)
    # from "sent as null". An explicit null clears the field while `amount`
    # keeps its old value below, leaving the line derived from nothing — and a
    # null quantity reaches SAP as QUANTITY=0. Refuse it; omit the field to
    # leave it alone.
    for f in ("quantity", "unit_price"):
        if f in fields and fields[f] is None:
            raise HTTPException(
                status_code=400,
                detail=f"{f.replace('_', ' ')} cannot be empty. Send a number, or omit the field to leave it unchanged.",
            )
    for f, v in fields.items():
        setattr(line, f, v)
    line.user_modified = 1
    # Amount follows qty × unit_price (independent inputs).
    if "quantity" in fields or "unit_price" in fields:
        qty, price = line.quantity, line.unit_price
        if qty is not None and price is not None:
            line.amount = round(float(qty) * float(price), 2)

    new_subtotal = round(sum(float(li.amount or 0) for li in invoice.line_items), 2)
    invoice.subtotal_amount = new_subtotal
    invoice.total_amount = round(new_subtotal + float(invoice.tax_amount or 0), 2)
    await db.commit()
    await db.refresh(line)
    return {
        "success": True,
        "line_item": {
            "id": line.id, "description": line.description, "quantity": line.quantity,
            "unit": line.unit, "unit_price": line.unit_price, "amount": line.amount,
        },
        "subtotal_amount": invoice.subtotal_amount,
        "total_amount": invoice.total_amount,
    }


@router.delete("/{invoice_id}/line-items/{line_item_id}")
async def delete_line_item(
    invoice_id: int,
    line_item_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Permanently delete a single invoice line item.

    Used when an invoice line has no matching PO line (so the invoice can't be
    parked): the operator removes the offending line so the rest can post. Also
    drops any PO match-detail rows referencing the line (FK) and recomputes the
    invoice subtotal/total from the remaining lines.
    """
    from app.models.purchase_order import POLineMatchDetail

    result = await db.execute(
        select(Invoice).options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id, Invoice.is_deleted == 0)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    if invoice.sap_document_number:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invoice is {invoice.sap_doc_status or 'parked'} in SAP as document "
                f"{invoice.sap_document_number}/{invoice.sap_fiscal_year}. Unpark it before "
                f"editing line items."
            ),
        )

    line = next((li for li in invoice.line_items if li.id == line_item_id), None)
    if not line:
        raise HTTPException(status_code=404, detail="Line item not found on this invoice")

    # Drop match-detail rows that reference this line (FK), then the line itself.
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(POLineMatchDetail).where(POLineMatchDetail.invoice_line_item_id == line_item_id)
    )
    await db.delete(line)
    await db.flush()

    # Recompute subtotal/total from the remaining lines (tax unchanged).
    remaining = [li for li in invoice.line_items if li.id != line_item_id]
    new_subtotal = round(sum(float(li.amount or 0) for li in remaining), 2)
    invoice.subtotal_amount = new_subtotal
    invoice.total_amount = round(new_subtotal + float(invoice.tax_amount or 0), 2)
    await db.commit()

    return {
        "success": True,
        "invoice_id": invoice_id,
        "deleted_line_item_id": line_item_id,
        "remaining_line_items": len(remaining),
        "subtotal_amount": invoice.subtotal_amount,
        "total_amount": invoice.total_amount,
    }


# ── Duplicate Detection ─────────────────────────────────────────────────────


@router.post("/check-duplicates")
async def check_invoice_duplicates(
    invoice_number: str | None = None,
    supplier_ntn: str | None = None,
    supplier_name: str | None = None,
    total_amount: float | None = None,
    invoice_date: str | None = None,
    exclude_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Check for potential duplicate invoices before saving."""
    return await check_duplicates(
        db,
        invoice_number=invoice_number,
        supplier_ntn=supplier_ntn,
        supplier_name=supplier_name,
        total_amount=total_amount,
        invoice_date=invoice_date,
        exclude_id=exclude_id,
    )


@router.get("/{invoice_id}/duplicates")
async def get_invoice_duplicates(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Find potential duplicates for an existing invoice."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    # Duplicate detection is global (cross-supplier): the same invoice submitted
    # by different suppliers is a duplicate-billing risk we want flagged.
    return await check_duplicates(
        db,
        invoice_number=invoice.invoice_number,
        supplier_ntn=invoice.supplier_ntn,
        supplier_name=invoice.supplier_name,
        total_amount=invoice.total_amount,
        invoice_date=invoice.invoice_date,
        exclude_id=invoice.id,
    )


# ── Invoice Classification ──────────────────────────────────────────────────


@router.get("/{invoice_id}/classify")
async def classify_existing_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Auto-classify an existing invoice based on its extracted data."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    # Parse detected taxes if stored as JSON
    detected_taxes = None
    if invoice.detected_taxes:
        try:
            detected_taxes = json.loads(invoice.detected_taxes)
        except (json.JSONDecodeError, TypeError):
            detected_taxes = None

    line_item_dicts = [
        {"description": li.description, "quantity": li.quantity, "amount": li.amount}
        for li in (invoice.line_items or [])
    ]

    classification = classify_invoice(
        document_type=invoice.document_type,
        invoice_number=invoice.invoice_number,
        supplier_name=invoice.supplier_name,
        po_reference=invoice.po_reference,
        line_items=line_item_dicts,
        currency=invoice.currency,
        total_amount=invoice.total_amount,
        detected_taxes=detected_taxes,
    )

    return {
        "invoice_id": invoice.id,
        "current_document_type": invoice.document_type,
        **classification,
    }


@router.post("/{invoice_id}/apply-classification")
async def apply_classification(
    invoice_id: int,
    invoice_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Apply classification result to invoice's document_type field."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _assert_can_access(invoice, principal)

    # If no type provided, auto-classify
    if not invoice_type:
        detected_taxes = None
        if invoice.detected_taxes:
            try:
                detected_taxes = json.loads(invoice.detected_taxes)
            except (json.JSONDecodeError, TypeError):
                detected_taxes = None

        line_item_dicts = [
            {"description": li.description}
            for li in (invoice.line_items or [])
        ]
        classification = classify_invoice(
            document_type=invoice.document_type,
            invoice_number=invoice.invoice_number,
            supplier_name=invoice.supplier_name,
            po_reference=invoice.po_reference,
            line_items=line_item_dicts,
            currency=invoice.currency,
            total_amount=invoice.total_amount,
            detected_taxes=detected_taxes,
        )
        invoice_type = classification["invoice_type"]

    invoice.document_type = invoice_type
    await db.commit()
    await db.refresh(invoice)

    # Reload with line items
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    return _build_detail_response(invoice)
