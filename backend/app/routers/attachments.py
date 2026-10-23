"""Invoice attachment endpoints — upload, list, download, delete supporting documents."""

import os
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attachment import InvoiceAttachment
from app.models.invoice import Invoice
from app.security import get_current_principal, Principal
from app.services.file_storage import save_uploaded_file, content_matches_type
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["attachments"])

# Allowed MIME types for supporting documents (broader than invoice uploads)
ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",   # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",         # .xlsx
    "application/msword",       # .doc
    "application/vnd.ms-excel", # .xls
}

VALID_DOC_TYPES = {"work_order", "scan", "payment_proof", "goods_receipt", "contract", "other"}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/api/invoices/{invoice_id}/attachments", status_code=201)
async def upload_attachment(
    invoice_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    description: str = Form(""),
    uploaded_by: str = Form(""),
    uploaded_by_role: str = Form(""),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Upload a supporting document for an invoice."""
    await _assert_invoice_access(invoice_id, principal, db)

    # Validate document type
    if document_type not in VALID_DOC_TYPES:
        document_type = "other"

    # Validate MIME
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, JPEG, PNG, TIFF, DOCX, XLSX",
        )

    # Read & validate size
    content = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB")

    # Verify the real file signature matches the claimed type (header is spoofable)
    if not content_matches_type(content, file.content_type):
        raise HTTPException(
            status_code=400,
            detail="File content does not match its declared type.",
        )

    # Store file
    stored_path = save_uploaded_file(content, file.filename)

    # Create DB record
    attachment = InvoiceAttachment(
        invoice_id=invoice_id,
        filename=file.filename,
        stored_filepath=stored_path,
        content_type=file.content_type,
        file_size=len(content),
        document_type=document_type,
        description=description.strip() or None,
        uploaded_by=uploaded_by or None,
        uploaded_by_role=uploaded_by_role or None,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    logger.info("Attachment %d uploaded for invoice %d: %s", attachment.id, invoice_id, file.filename)
    return _to_dict(attachment)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/api/invoices/{invoice_id}/attachments")
async def list_attachments(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List all attachments for an invoice, newest first."""
    await _assert_invoice_access(invoice_id, principal, db)
    result = await db.execute(
        select(InvoiceAttachment)
        .where(InvoiceAttachment.invoice_id == invoice_id)
        .order_by(InvoiceAttachment.created_at.desc())
    )
    rows = result.scalars().all()
    return [_to_dict(r) for r in rows]


# ── Download ──────────────────────────────────────────────────────────────────

@router.get("/api/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Download an attachment file."""
    att = await _get_or_404(attachment_id, db)
    await _assert_invoice_access(att.invoice_id, principal, db)
    filepath = Path(att.stored_filepath)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(filepath),
        filename=att.filename,
        media_type=att.content_type,
    )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/api/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Delete an attachment (record + file on disk)."""
    att = await _get_or_404(attachment_id, db)
    await _assert_invoice_access(att.invoice_id, principal, db)

    # Remove file from disk
    try:
        filepath = Path(att.stored_filepath)
        if filepath.exists():
            os.remove(filepath)
    except Exception as e:
        logger.warning("Could not delete file %s: %s", att.stored_filepath, e)

    await db.delete(att)
    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(attachment_id: int, db: AsyncSession) -> InvoiceAttachment:
    result = await db.execute(
        select(InvoiceAttachment).where(InvoiceAttachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return att


async def _assert_invoice_access(invoice_id: int, principal: Principal, db: AsyncSession) -> None:
    """Ensure the caller may touch attachments of this invoice.

    Internal staff can access any invoice's attachments. A supplier can only
    access attachments of invoices they submitted. Returns 404 (not 403) so we
    don't reveal the existence of other suppliers' invoices/attachments.
    """
    if principal.kind != "supplier":
        return
    result = await db.execute(
        select(Invoice.supplier_id).where(Invoice.id == invoice_id)
    )
    row = result.first()
    if not row or row.supplier_id != principal.id:
        raise HTTPException(status_code=404, detail="Invoice not found")


def _to_dict(att: InvoiceAttachment) -> dict:
    return {
        "id": att.id,
        "invoice_id": att.invoice_id,
        "filename": att.filename,
        "content_type": att.content_type,
        "file_size": att.file_size,
        "document_type": att.document_type,
        "description": att.description,
        "uploaded_by": att.uploaded_by,
        "uploaded_by_role": att.uploaded_by_role,
        "created_at": att.created_at.isoformat() if att.created_at else None,
        "download_url": f"/api/attachments/{att.id}/download",
    }
