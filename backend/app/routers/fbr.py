"""
FBR Active Taxpayer List verification endpoints.

Endpoints:
  POST /api/fbr/verify-ntn                       — verify single NTN or CNIC
  POST /api/fbr/verify-batch                      — verify multiple NTNs/CNICs
  POST /api/fbr/invoices/{id}/verify-fbr          — verify invoice supplier + WHT
  GET  /api/fbr/atl-stats                         — ATL database statistics
  GET  /api/fbr/token-status                      — IRIS JWT token cache status
  POST /api/fbr/refresh-token                     — force re-extract IRIS JWT
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.invoice import Invoice
from app.schemas.fbr import (
    VerifyNTNRequest,
    BatchVerifyRequest,
    FBRVerificationResponse,
    BatchVerifyResponse,
    WHTComplianceResponse,
    InvoiceVerifyFBRResponse,
    ATLStatsResponse,
    TokenStatusResponse,
)
from app.services.fbr_verification import (
    verify_ntn,
    verify_batch,
    check_wht_compliance,
    get_atl_stats,
    get_token_status,
    refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fbr", tags=["fbr"])


# ── Single NTN/CNIC verification ────────────────────────────────────────────

@router.post("/verify-ntn", response_model=FBRVerificationResponse)
async def verify_ntn_endpoint(req: VerifyNTNRequest):
    """
    Verify a single NTN or CNIC against the FBR Active Taxpayer List.

    - Auto-detects NTN (<=8 digits) vs CNIC (13 digits)
    - Checks local ATL database first (7.5M records, instant)
    - If check_live=true and configured, falls back to live FBR IRIS 2.0 API
    - protocol_id: "1004" (Income Tax, default), "1005" (Sales Tax), "3001" (AJK)
    """
    if not req.ntn or not req.ntn.strip():
        raise HTTPException(status_code=400, detail="NTN or CNIC is required")
    result = await verify_ntn(req.ntn, check_live=req.check_live, protocol_id=req.protocol_id)
    return FBRVerificationResponse(**result)


# ── Batch verification ───────────────────────────────────────────────────────

@router.post("/verify-batch", response_model=BatchVerifyResponse)
async def verify_batch_endpoint(req: BatchVerifyRequest):
    """
    Verify multiple NTNs/CNICs in one call.

    Accepts a mix of NTNs and CNICs. Each identifier is auto-detected.
    Returns individual results plus summary counts.
    """
    if not req.identifiers:
        raise HTTPException(status_code=400, detail="At least one identifier is required")
    if len(req.identifiers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 identifiers per batch")

    results = await verify_batch(
        req.identifiers, check_live=req.check_live, protocol_id=req.protocol_id
    )

    response_items = [FBRVerificationResponse(**r) for r in results]
    return BatchVerifyResponse(
        results=response_items,
        total=len(response_items),
        active_count=sum(1 for r in response_items if r.status == "verified_active"),
        inactive_count=sum(1 for r in response_items if r.status == "verified_inactive"),
        not_found_count=sum(1 for r in response_items if r.status == "not_found"),
    )


# ── Invoice FBR verification ────────────────────────────────────────────────

@router.post("/invoices/{invoice_id}/verify-fbr", response_model=InvoiceVerifyFBRResponse)
async def verify_invoice_fbr(invoice_id: int, db: AsyncSession = Depends(get_db)):
    """
    Verify an invoice's supplier NTN and check WHT compliance.

    - Looks up supplier_ntn against ATL
    - If detected_taxes exist, checks WHT rate compliance (ATL vs non-ATL rates)
    - Persists results to the invoice record
    """
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.supplier_ntn or not invoice.supplier_ntn.strip():
        raise HTTPException(status_code=400, detail="Invoice has no supplier NTN")

    # Verify NTN
    verification = await verify_ntn(invoice.supplier_ntn)

    # Update invoice
    invoice.fbr_verification_status = verification["status"]
    invoice.fbr_verified_at = verification["verified_at"]
    invoice.fbr_taxpayer_name = verification.get("taxpayer_name")
    invoice.fbr_filing_status = verification.get("filing_status")

    # WHT compliance check
    wht_result = None
    if invoice.detected_taxes:
        try:
            taxes = json.loads(invoice.detected_taxes)
            compliance = check_wht_compliance(
                taxes, verification["is_active"], invoice.subtotal_amount
            )
            invoice.wht_compliance_status = compliance["status"]
            wht_result = WHTComplianceResponse(**compliance)
        except (json.JSONDecodeError, TypeError):
            pass

    await db.commit()

    return InvoiceVerifyFBRResponse(
        invoice_id=invoice_id,
        fbr_verification=FBRVerificationResponse(**verification),
        wht_compliance=wht_result,
    )


# ── ATL Database Stats ──────────────────────────────────────────────────────

@router.get("/atl-stats", response_model=ATLStatsResponse)
async def atl_stats_endpoint():
    """Get ATL database statistics (record count, file size, last modified)."""
    stats = await get_atl_stats()
    return ATLStatsResponse(**stats)


# ── IRIS Token Management ───────────────────────────────────────────────────

@router.get("/token-status", response_model=TokenStatusResponse)
async def token_status_endpoint():
    """
    Get the current IRIS JWT token cache status.

    Shows whether a token is cached, its age, TTL remaining,
    and the effective API URL (from bundle or config).
    """
    status = await get_token_status()
    return TokenStatusResponse(**status)


@router.post("/refresh-token", response_model=TokenStatusResponse)
async def refresh_token_endpoint():
    """
    Force re-extraction of the Bearer JWT from the IRIS Angular bundle.

    Invalidates the current cached token and fetches a fresh one by:
    1. Downloading the IRIS index page
    2. Finding the main.*.js bundle
    3. Extracting the JWT and API URL
    """
    status = await refresh_token()
    return TokenStatusResponse(**status)
