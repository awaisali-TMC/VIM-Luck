"""Pydantic schemas for FBR ATL verification endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Request schemas ──────────────────────────────────────────────────────────

class VerifyNTNRequest(BaseModel):
    """Verify a single NTN or CNIC."""
    ntn: str                              # accepts NTN (7-digit) or CNIC (13-digit)
    check_live: bool = False              # fall back to live FBR API if not in local DB
    protocol_id: Optional[str] = None     # "1004" Income Tax, "1005" Sales Tax, "3001" AJK


class BatchVerifyRequest(BaseModel):
    """Verify multiple NTNs/CNICs in one call."""
    identifiers: list[str]                # mix of NTNs and CNICs
    check_live: bool = False
    protocol_id: Optional[str] = None


# ── Response schemas ─────────────────────────────────────────────────────────

class FBRVerificationResponse(BaseModel):
    ntn: str
    identifier_type: str = "NTN"          # "NTN" or "CNIC"
    protocol_id: str = "1004"
    status: str                           # verified_active | verified_inactive | not_found | error
    is_active: bool
    taxpayer_name: Optional[str] = None
    business_name: Optional[str] = None
    filing_status: Optional[str] = None
    status_date: Optional[str] = None
    registrations: Optional[list[str]] = None  # ATL lists found: ["IT","ST"]
    source: str = "local_db"              # "local_db" | "live_api"
    verified_at: datetime


class WHTComplianceResponse(BaseModel):
    status: str                           # compliant | non_compliant | needs_review
    is_supplier_atl: bool
    applicable_rate: Optional[float] = None
    detected_rate: Optional[float] = None
    detected_amount: Optional[float] = None
    message: str


class InvoiceVerifyFBRResponse(BaseModel):
    invoice_id: int
    fbr_verification: FBRVerificationResponse
    wht_compliance: Optional[WHTComplianceResponse] = None


class BatchVerifyResponse(BaseModel):
    results: list[FBRVerificationResponse]
    total: int
    active_count: int
    inactive_count: int
    not_found_count: int


class TokenStatusResponse(BaseModel):
    has_token: bool
    token_age_seconds: Optional[int] = None
    ttl_remaining_seconds: Optional[int] = None
    is_expired: bool
    api_url: str
    api_url_source: str                   # "bundle" | "config"
    live_lookup_enabled: bool
    refresh_success: Optional[bool] = None


class ATLStatsResponse(BaseModel):
    total_records: int
    db_path: str
    db_size_mb: float
    last_modified: Optional[str] = None
    status: str                           # available | not_found | error
