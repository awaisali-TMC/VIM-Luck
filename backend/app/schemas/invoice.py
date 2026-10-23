from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# --- Extraction results (returned from /upload) ---


class ExtractedField(BaseModel):
    label: str
    value: str
    field_name: str
    confidence: float  # 0-100


class ExtractedLineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    description_confidence: Optional[float] = None
    quantity_confidence: Optional[float] = None
    unit_price_confidence: Optional[float] = None
    amount_confidence: Optional[float] = None


class DetectedTax(BaseModel):
    tax_type: str
    amount: Optional[float] = None
    rate: Optional[float] = None
    description: Optional[str] = None


class ProductMatch(BaseModel):
    line_item_index: int
    product_code: str
    product_name: str
    product_category: Optional[str] = None
    confidence: float = 0.0
    reasoning: Optional[str] = None


class AttentionFlag(BaseModel):
    """A single item that needs human attention on an uploaded invoice."""
    severity: str          # "high" | "medium" | "low"
    category: str          # "currency" | "math" | "tax" | "missing_field" | "document" | "confidence"
    title: str             # short label, e.g. "Currency mismatch"
    message: str           # human-readable explanation
    detail: Optional[str] = None  # optional extra context / numbers


class ExtractionResult(BaseModel):
    fields: list[ExtractedField]
    line_items: list[ExtractedLineItem]
    overall_confidence: float
    document_type: Optional[str] = None
    page_count: int
    processing_time_ms: int
    warnings: list[str]
    original_filename: str
    stored_filepath: str
    raw_document_ai: Optional[Any] = None  # Full Document AI protobuf response as dict
    # Gemini tax detection
    detected_taxes: list[DetectedTax] = []
    tax_summary: Optional[str] = None
    gemini_confidence: Optional[float] = None
    gemini_processing_time_ms: Optional[int] = None
    # Gemini product matching
    product_matches: list[ProductMatch] = []
    product_match_processing_time_ms: Optional[int] = None
    # Line item extraction source: "document_ai" or "gemini"
    line_items_source: str = "document_ai"
    # Items needing human attention (anomalies / inconsistencies)
    attention_flags: list[AttentionFlag] = []


# --- Save invoice (POST /save) ---


class InvoiceLineItemCreate(BaseModel):
    # User-confirmed / corrected values
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    # Original AI-extracted values
    ai_description: Optional[str] = None
    ai_quantity: Optional[float] = None
    ai_unit: Optional[str] = None
    ai_unit_price: Optional[float] = None
    ai_amount: Optional[float] = None
    # Confidence scores
    description_confidence: Optional[float] = None
    quantity_confidence: Optional[float] = None
    unit_price_confidence: Optional[float] = None
    amount_confidence: Optional[float] = None
    # Whether user modified this line item
    user_modified: Optional[bool] = False


class InvoiceSaveRequest(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = "PKR"
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_ntn: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_address: Optional[str] = None
    subtotal_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    gst_amount: Optional[float] = None
    wht_amount: Optional[float] = None
    detected_taxes: Optional[list[DetectedTax]] = None
    po_reference: Optional[str] = None
    bank_iban: Optional[str] = None
    document_type: Optional[str] = None
    overall_confidence: Optional[float] = None
    field_confidences: Optional[dict] = None
    warnings: Optional[list[str]] = None
    processing_time_ms: Optional[int] = None
    original_filename: str
    stored_filepath: str
    mime_type: str = "application/pdf"
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    status: str = "draft"
    line_items: list[InvoiceLineItemCreate] = []
    # Source tracking
    source_type: Optional[str] = "upload"    # "upload" | "email"
    source_email_id: Optional[int] = None
    source_email_from: Optional[str] = None
    # Credit/Debit note fields
    linked_invoice_id: Optional[int] = None
    credit_debit_reason: Optional[str] = None
    original_invoice_number: Optional[str] = None
    # Multi-currency
    base_currency: str = "PKR"
    exchange_rate: Optional[float] = None
    base_total_amount: Optional[float] = None
    sap_vendor_number: Optional[str] = None


# --- Update invoice (PUT /{id}) ---


class InvoiceLineItemUpdate(BaseModel):
    id: Optional[int] = None  # existing item id (None = new item)
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class InvoiceUpdateRequest(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_ntn: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_address: Optional[str] = None
    subtotal_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    gst_amount: Optional[float] = None
    wht_amount: Optional[float] = None
    po_reference: Optional[str] = None
    bank_iban: Optional[str] = None
    document_type: Optional[str] = None
    sap_tax_code: Optional[str] = None
    sap_layout: Optional[str] = None
    sap_posting_date: Optional[str] = None
    sap_baseline_date: Optional[str] = None
    sap_header_text: Optional[str] = None
    sap_item_text: Optional[str] = None
    sap_currency: Optional[str] = None
    sap_vendor_number: Optional[str] = None
    exchange_rate: Optional[float] = None
    line_items: Optional[list[InvoiceLineItemUpdate]] = None


class StatusUpdateRequest(BaseModel):
    status: str


# --- Response models ---


class InvoiceLineItemResponse(BaseModel):
    id: int
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    ai_description: Optional[str] = None
    ai_quantity: Optional[float] = None
    ai_unit: Optional[str] = None
    ai_unit_price: Optional[float] = None
    ai_amount: Optional[float] = None
    description_confidence: Optional[float] = None
    quantity_confidence: Optional[float] = None
    unit_price_confidence: Optional[float] = None
    amount_confidence: Optional[float] = None
    user_modified: Optional[int] = 0
    # Product/account match (populated by background job after submission)
    matched_product_code: Optional[str] = None
    matched_product_name: Optional[str] = None
    matched_product_category: Optional[str] = None
    match_confidence: Optional[float] = None
    match_reasoning: Optional[str] = None

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str
    supplier_name: Optional[str] = None
    total_amount: Optional[float] = None
    overall_confidence: Optional[float] = None
    status: str
    document_type: Optional[str] = None
    original_filename: str
    created_at: datetime
    line_items: list[InvoiceLineItemResponse] = []
    source_type: Optional[str] = "upload"
    source_email_from: Optional[str] = None
    fbr_verification_status: Optional[str] = "not_verified"
    sap_doc_status: Optional[str] = None  # "parked" | "posted" — used to label the status

    model_config = {"from_attributes": True}


class InvoiceDetailResponse(BaseModel):
    id: int
    # File metadata
    original_filename: str
    stored_filepath: str
    mime_type: str
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
    # Header fields
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = "PKR"
    # Vendor info
    supplier_name: Optional[str] = None
    supplier_address: Optional[str] = None
    supplier_ntn: Optional[str] = None
    # Receiver info
    receiver_name: Optional[str] = None
    receiver_address: Optional[str] = None
    # Financial amounts
    subtotal_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    gst_amount: Optional[float] = None
    wht_amount: Optional[float] = None
    detected_taxes: Optional[list[DetectedTax]] = None
    # Additional
    po_reference: Optional[str] = None
    bank_iban: Optional[str] = None
    document_type: Optional[str] = None
    # AI data
    overall_confidence: Optional[float] = None
    field_confidences: Optional[dict] = None
    warnings: Optional[list[str]] = None
    processing_time_ms: Optional[int] = None
    # Status + timestamps
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Line items with confidence
    line_items: list[InvoiceLineItemResponse] = []
    # Source tracking
    source_type: Optional[str] = "upload"
    source_email_from: Optional[str] = None
    # FBR ATL verification
    fbr_verification_status: Optional[str] = "not_verified"
    fbr_verified_at: Optional[datetime] = None
    fbr_taxpayer_name: Optional[str] = None
    fbr_filing_status: Optional[str] = None
    wht_compliance_status: Optional[str] = None
    # Credit/Debit note fields
    linked_invoice_id: Optional[int] = None
    credit_debit_reason: Optional[str] = None
    original_invoice_number: Optional[str] = None
    # Multi-currency
    base_currency: str = "PKR"
    exchange_rate: Optional[float] = None
    base_total_amount: Optional[float] = None
    # SAP posting
    sap_document_number: Optional[str] = None
    sap_fiscal_year: Optional[str] = None
    sap_company_code: Optional[str] = None
    sap_posted_at: Optional[datetime] = None
    sap_doc_status: Optional[str] = None  # "parked" | "posted"
    sap_tax_code: Optional[str] = None    # AI-suggested / user-chosen SAP tax code
    sap_layout: Optional[str] = None      # "goods" | "delivery" | "both"
    sap_posting_date: Optional[str] = None
    sap_baseline_date: Optional[str] = None
    sap_header_text: Optional[str] = None
    sap_item_text: Optional[str] = None
    sap_currency: Optional[str] = None
    sap_vendor_number: Optional[str] = None              # resolved LIFNR
    parking_line_item_ids: Optional[list[int]] = None  # lines selected for parking (locked at submit)
    # PO matching
    matched_po_id: Optional[int] = None
    latest_po_match_status: Optional[str] = None

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceResponse]
    total: int
