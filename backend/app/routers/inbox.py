import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.email_message import EmailAttachment, EmailMessage, EmailStatus
from app.schemas.invoice import (
    DetectedTax,
    ExtractionResult,
    ExtractedField,
    ExtractedLineItem,
)
# Extraction uses app.services.gemini_extract (imported lazily in the process
# endpoint) — the same single-call pipeline as the web upload.
from app.services.gmail_imap import fetch_new_emails

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/inbox", tags=["inbox"])

MIME_MAP = {
    "application/pdf": "application/pdf",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/tiff": "image/tiff",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _attachment_dict(att: EmailAttachment) -> dict:
    return {
        "id": att.id,
        "email_id": att.email_id,
        "filename": att.filename,
        "content_type": att.content_type,
        "file_size": att.file_size,
        "processed": att.processed,
        "invoice_id": att.invoice_id,
    }


def _email_dict(msg: EmailMessage, include_body: bool = False) -> dict:
    d = {
        "id": msg.id,
        "message_uid": msg.message_uid,
        "from_address": msg.from_address,
        "subject": msg.subject,
        "received_at": msg.received_at.isoformat() if msg.received_at else None,
        "fetched_at": msg.fetched_at.isoformat() if msg.fetched_at else None,
        "status": msg.status,
        "has_attachments": msg.has_attachments,
        "attachments": [_attachment_dict(a) for a in (msg.attachments or [])],
    }
    if include_body:
        d["body_text"] = msg.body_text
    return d


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_inbox_config():
    """Return the configured Gmail account address (for display in the UI)."""
    return {
        "gmail_address": settings.GMAIL_ADDRESS or None,
        "configured": bool(settings.GMAIL_ADDRESS and settings.GMAIL_APP_PASSWORD),
    }


@router.post("/fetch")
async def fetch_emails(db: AsyncSession = Depends(get_db)):
    """
    Fetch UNSEEN emails from the configured Gmail account via IMAP,
    save new emails+attachments to the DB (skips already-fetched UIDs).
    Returns a summary of what was fetched.
    """
    try:
        parsed = fetch_new_emails(
            gmail_address=settings.GMAIL_ADDRESS,
            gmail_app_password=settings.GMAIL_APP_PASSWORD,
            upload_dir=settings.UPLOAD_DIR,
            imap_host=settings.GMAIL_IMAP_HOST,
            imap_port=settings.GMAIL_IMAP_PORT,
            folder=settings.GMAIL_FETCH_FOLDER,
            max_fetch=settings.GMAIL_MAX_FETCH,
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    saved = 0
    skipped = 0

    for email_data in parsed:
        # Dedup: check if we already have this UID
        existing = await db.execute(
            select(EmailMessage).where(EmailMessage.message_uid == email_data["message_uid"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        msg = EmailMessage(
            message_uid=email_data["message_uid"],
            from_address=email_data["from_address"],
            subject=email_data["subject"],
            body_text=email_data["body_text"],
            received_at=email_data["received_at"],
            fetched_at=datetime.now(timezone.utc),
            status=EmailStatus.UNREAD.value,
            has_attachments=bool(email_data["attachments"]),
        )
        db.add(msg)
        await db.flush()  # get msg.id

        for att_data in email_data["attachments"]:
            att = EmailAttachment(
                email_id=msg.id,
                filename=att_data["filename"],
                content_type=att_data["content_type"],
                file_size=att_data["file_size"],
                stored_filepath=att_data["stored_filepath"],
                processed=False,
            )
            db.add(att)

        saved += 1

    await db.commit()
    return {"fetched": len(parsed), "saved": saved, "skipped": skipped}


@router.get("/")
async def list_emails(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """List emails stored in the DB, most recent first, with their attachments."""
    q = (
        select(EmailMessage)
        .options(selectinload(EmailMessage.attachments))
        .order_by(EmailMessage.received_at.desc().nulls_last())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(q)
    messages = result.scalars().all()

    total_q = await db.execute(select(func.count(EmailMessage.id)))
    total = total_q.scalar() or 0

    unread_q = await db.execute(
        select(func.count(EmailMessage.id)).where(EmailMessage.status == EmailStatus.UNREAD.value)
    )
    unread = unread_q.scalar() or 0

    with_att_q = await db.execute(
        select(func.count(EmailMessage.id)).where(EmailMessage.has_attachments == True)  # noqa: E712
    )
    with_attachments = with_att_q.scalar() or 0

    processed_q = await db.execute(
        select(func.count(EmailMessage.id)).where(EmailMessage.status == EmailStatus.PROCESSED.value)
    )
    processed = processed_q.scalar() or 0

    return {
        "emails": [_email_dict(m) for m in messages],
        "total": total,
        "stats": {
            "total": total,
            "unread": unread,
            "with_attachments": with_attachments,
            "processed": processed,
        },
    }


@router.get("/{email_id}")
async def get_email(email_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single email with full body. Marks it as read."""
    q = (
        select(EmailMessage)
        .options(selectinload(EmailMessage.attachments))
        .where(EmailMessage.id == email_id)
    )
    result = await db.execute(q)
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Email not found")

    if msg.status == EmailStatus.UNREAD.value:
        msg.status = EmailStatus.READ.value
        await db.commit()

    return _email_dict(msg, include_body=True)


@router.post("/attachments/{attachment_id}/process", response_model=ExtractionResult)
async def process_email_attachment(attachment_id: int, db: AsyncSession = Depends(get_db)):
    """
    Process an email attachment through the Document AI + Gemini pipeline.
    Returns an ExtractionResult — identical to the invoice upload endpoint response.
    The frontend routes to ExtractionResultsPage so admin can review before saving.
    """
    q = (
        select(EmailAttachment)
        .options(selectinload(EmailAttachment.email))
        .where(EmailAttachment.id == attachment_id)
    )
    result = await db.execute(q)
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if not att.stored_filepath:
        raise HTTPException(status_code=400, detail="Attachment file path not available")

    try:
        with open(att.stored_filepath, "rb") as f:
            file_content = f.read()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not read attachment file: {e}")

    mime_type = MIME_MAP.get(att.content_type or "")
    if not mime_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported attachment type: {att.content_type}. Allowed: PDF, JPEG, PNG, TIFF",
        )

    # --- Extraction: single Gemini call (the active pipeline, same as web
    # upload). Replaces the legacy Document AI → gemini-tax → gemini-line-items
    # chain, which required a GCP service-account key. ---
    try:
        from app.services.gemini_extract import extract_invoice
        result = extract_invoice(file_content, mime_type)
    except Exception:
        logger.exception("Email attachment extraction failed")
        raise HTTPException(status_code=500, detail="Invoice extraction failed — see server logs.")

    return ExtractionResult(
        fields=[ExtractedField(**f) for f in result["fields"]],
        line_items=[ExtractedLineItem(**li) for li in result["line_items"]],
        overall_confidence=result["overall_confidence"],
        document_type=result["document_type"],
        page_count=result["page_count"],
        processing_time_ms=result["processing_time_ms"],
        warnings=result["warnings"],
        original_filename=att.filename or f"attachment_{attachment_id}",
        stored_filepath=att.stored_filepath,
        raw_document_ai=None,
        detected_taxes=[DetectedTax(**t) for t in result["detected_taxes"]],
        tax_summary=result.get("tax_summary"),
        gemini_confidence=result.get("gemini_confidence"),
        gemini_processing_time_ms=result.get("gemini_processing_time_ms"),
        product_matches=[],
        line_items_source=result.get("line_items_source", "gemini"),
    )


class MarkProcessedRequest(BaseModel):
    invoice_id: int | None = None


@router.patch("/attachments/{attachment_id}/mark-processed")
async def mark_attachment_processed(
    attachment_id: int,
    body: MarkProcessedRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark an attachment as processed and optionally link the resulting invoice ID."""
    q = (
        select(EmailAttachment)
        .options(selectinload(EmailAttachment.email))
        .where(EmailAttachment.id == attachment_id)
    )
    result = await db.execute(q)
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    att.processed = True
    att.invoice_id = body.invoice_id

    # If all attachments of this email are processed, mark email as processed
    email_msg = att.email
    if email_msg:
        all_atts_q = await db.execute(
            select(EmailAttachment).where(EmailAttachment.email_id == email_msg.id)
        )
        all_atts = all_atts_q.scalars().all()
        if all(a.processed for a in all_atts):
            email_msg.status = EmailStatus.PROCESSED.value

    await db.commit()
    return {"ok": True, "attachment_id": attachment_id, "invoice_id": body.invoice_id}
