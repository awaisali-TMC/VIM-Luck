from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# ── PO Line Item schemas ─────────────────────────────

class POLineItemCreate(BaseModel):
    item_number: Optional[int] = None
    description: str
    quantity: float
    unit: Optional[str] = None
    unit_price: float
    amount: Optional[float] = None


class POLineItemUpdate(BaseModel):
    id: Optional[int] = None
    item_number: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class POLineItemResponse(BaseModel):
    id: int
    item_number: Optional[int] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    model_config = {"from_attributes": True}


# ── GRN schemas ───────────────────────────────────────

class GRNLineItemCreate(BaseModel):
    po_line_item_id: int
    received_quantity: float
    inspection_status: str = "accepted"


class GRNCreate(BaseModel):
    grn_number: str
    grn_date: Optional[str] = None
    po_id: int
    received_by: Optional[str] = None
    plant_location: Optional[str] = None
    notes: Optional[str] = None
    line_items: list[GRNLineItemCreate] = []


class GRNLineItemResponse(BaseModel):
    id: int
    po_line_item_id: int
    received_quantity: float
    inspection_status: str
    model_config = {"from_attributes": True}


class GRNResponse(BaseModel):
    id: int
    grn_number: str
    grn_date: Optional[str] = None
    po_id: int
    received_by: Optional[str] = None
    plant_location: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    line_items: list[GRNLineItemResponse] = []
    model_config = {"from_attributes": True}


# ── SES schemas ───────────────────────────────────────

class SESLineItemCreate(BaseModel):
    po_line_item_id: int
    completed_quantity: float
    completed_amount: Optional[float] = None


class SESCreate(BaseModel):
    ses_number: str
    ses_date: Optional[str] = None
    po_id: int
    service_period_from: Optional[str] = None
    service_period_to: Optional[str] = None
    notes: Optional[str] = None
    line_items: list[SESLineItemCreate] = []


class SESLineItemResponse(BaseModel):
    id: int
    po_line_item_id: int
    completed_quantity: float
    completed_amount: Optional[float] = None
    model_config = {"from_attributes": True}


class SESResponse(BaseModel):
    id: int
    ses_number: str
    ses_date: Optional[str] = None
    po_id: int
    service_period_from: Optional[str] = None
    service_period_to: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    line_items: list[SESLineItemResponse] = []
    model_config = {"from_attributes": True}


# ── Purchase Order schemas ─────────────────────────────

class POCreateRequest(BaseModel):
    po_number: str
    vendor_name: str
    vendor_ntn: Optional[str] = None
    po_date: Optional[str] = None
    po_type: str = "local"
    total_amount: Optional[float] = None
    currency: str = "PKR"
    status: str = "open"
    notes: Optional[str] = None
    source_type: str = "manual"
    original_filename: Optional[str] = None
    stored_filepath: Optional[str] = None
    line_items: list[POLineItemCreate] = []


class POUpdateRequest(BaseModel):
    po_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_ntn: Optional[str] = None
    po_date: Optional[str] = None
    po_type: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    line_items: Optional[list[POLineItemUpdate]] = None


class POResponse(BaseModel):
    id: int
    po_number: str
    vendor_name: str
    vendor_ntn: Optional[str] = None
    po_date: Optional[str] = None
    po_type: str
    total_amount: Optional[float] = None
    currency: str
    status: str
    notes: Optional[str] = None
    source_type: str = "manual"
    original_filename: Optional[str] = None
    created_at: Optional[datetime] = None
    line_items: list[POLineItemResponse] = []
    model_config = {"from_attributes": True}


class PODetailResponse(POResponse):
    """Extended response with GRNs, SESes, and match results."""
    stored_filepath: Optional[str] = None
    updated_at: Optional[datetime] = None
    grns: list[GRNResponse] = []
    ses_records: list[SESResponse] = []
    model_config = {"from_attributes": True}


class POListResponse(BaseModel):
    purchase_orders: list[POResponse]
    total: int


# ── Match schemas ─────────────────────────────────────

class MatchToleranceConfig(BaseModel):
    quantity_tolerance_pct: float = 5.0
    price_tolerance_pct: float = 2.0
    amount_tolerance_pct: float = 5.0


class TriggerMatchRequest(BaseModel):
    po_id: int
    tolerance: Optional[MatchToleranceConfig] = None
    match_type: str = "2-way"  # "2-way" | "3-way"


class LineMatchDetailResponse(BaseModel):
    id: int
    invoice_line_item_id: Optional[int] = None
    po_line_item_id: Optional[int] = None
    match_status: str
    quantity_match: int
    price_match: int
    quantity_diff: Optional[float] = None
    quantity_diff_pct: Optional[float] = None
    price_diff: Optional[float] = None
    price_diff_pct: Optional[float] = None
    grn_received_qty: Optional[float] = None
    ses_completed_qty: Optional[float] = None
    reasoning: Optional[str] = None
    # Denormalized for display
    invoice_line_description: Optional[str] = None
    invoice_line_qty: Optional[float] = None
    invoice_line_price: Optional[float] = None
    invoice_line_amount: Optional[float] = None
    po_line_description: Optional[str] = None
    po_line_qty: Optional[float] = None
    po_line_price: Optional[float] = None
    po_line_amount: Optional[float] = None
    model_config = {"from_attributes": True}


class MatchResultResponse(BaseModel):
    id: int
    invoice_id: int
    po_id: int
    match_status: str
    match_type: str
    overall_score: Optional[float] = None
    total_amount_diff: Optional[float] = None
    total_amount_diff_pct: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    po_number: Optional[str] = None
    line_matches: list[LineMatchDetailResponse] = []
    model_config = {"from_attributes": True}
