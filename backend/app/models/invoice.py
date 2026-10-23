import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_PROCESSING = "pending_processing"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXCEPTION = "exception"
    PARKED = "parked"
    POSTED = "posted"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source file
    original_filename = Column(String(255), nullable=False)
    stored_filepath = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(Integer)
    page_count = Column(Integer)

    # Extracted header fields
    invoice_number = Column(String(100))
    invoice_date = Column(String(50))
    due_date = Column(String(50))
    currency = Column(String(10), default="PKR")

    # Vendor
    supplier_name = Column(String(255))
    supplier_address = Column(Text)
    supplier_ntn = Column(String(50))

    # Receiver
    receiver_name = Column(String(255))
    receiver_address = Column(Text)

    # Amounts
    subtotal_amount = Column(Float)
    tax_amount = Column(Float)
    total_amount = Column(Float)

    # Pakistan tax specifics
    gst_amount = Column(Float)
    wht_amount = Column(Float)
    detected_taxes = Column(Text)  # JSON array of {tax_type, amount, rate, description}

    # Additional extracted fields
    po_reference = Column(String(100))
    bank_iban = Column(String(100))
    document_type = Column(String(50))

    # Credit/Debit note support
    linked_invoice_id = Column(Integer, nullable=True)           # links credit/debit note to original invoice
    credit_debit_reason = Column(Text, nullable=True)
    original_invoice_number = Column(String(100), nullable=True)

    # Multi-currency support
    base_currency = Column(String(10), default="PKR")            # company base currency
    exchange_rate = Column(Float, nullable=True)                  # rate to base currency
    base_total_amount = Column(Float, nullable=True)              # total in base currency

    # PO matching (denormalized convenience fields — source of truth is po_match_results)
    matched_po_id = Column(Integer, nullable=True)
    latest_po_match_status = Column(String(30), nullable=True)

    # AI Confidence
    overall_confidence = Column(Float)
    field_confidences = Column(Text)  # JSON string
    warnings = Column(Text)  # JSON array string
    processing_time_ms = Column(Integer)

    # Ownership — the supplier who submitted this invoice (NULL for internally
    # ingested invoices, e.g. email/admin upload). Used for object-level access
    # control so a supplier can only see/modify their own submissions.
    supplier_id = Column(Integer, nullable=True, index=True)

    # Source tracking — where the invoice came from
    source_type = Column(String(20), default="upload")       # "upload" | "web_upload" | "mobile_upload" | "email" | "supplier"
    source_email_id = Column(Integer, nullable=True)          # EmailMessage.id (if from email)
    source_email_from = Column(String(500), nullable=True)    # sender address (if from email)

    # FBR Active Taxpayer List verification
    fbr_verification_status = Column(String(30), default="not_verified")
    fbr_verified_at = Column(DateTime(timezone=True), nullable=True)
    fbr_taxpayer_name = Column(String(500), nullable=True)
    fbr_filing_status = Column(String(200), nullable=True)
    wht_compliance_status = Column(String(30), nullable=True)

    # SAP Posting
    sap_document_number = Column(String(50), nullable=True)
    sap_fiscal_year = Column(String(10), nullable=True)
    sap_company_code = Column(String(10), nullable=True)
    sap_posted_at = Column(DateTime(timezone=True), nullable=True)
    sap_doc_status = Column(String(20), nullable=True)  # "parked" | "posted"
    sap_tax_code = Column(String(10), nullable=True)    # SAP tax code chosen for this invoice (AI-suggested, user-editable)
    # SAP parking parameters — set during review (before approval), then locked.
    sap_layout = Column(String(20), nullable=True, default="goods")  # "goods" | "delivery" | "both"
    sap_posting_date = Column(String(50), nullable=True)             # SAP posting date (ISO)
    sap_baseline_date = Column(String(50), nullable=True)            # BLINE_DATE — payment baseline (mandatory in UI)
    sap_header_text = Column(String(50), nullable=True)             # Basic Data "Text" → HEADER_TXT (BKTXT)
    sap_item_text = Column(String(50), nullable=True)               # Details "Text" → ITEM_TEXT (SGTXT)
    sap_currency = Column(String(10), nullable=True)                # document currency chosen for posting

    # Resolved SAP vendor (LIFNR). Written on PO sync (routers/sap.py) and read
    # by the supplier-portal PO-flip gate.
    sap_vendor_number = Column(String(20), nullable=True)
    # Line items selected for parking (JSON list of invoice_line_item ids). Set
    # at submit-for-approval and locked thereafter — so the selection carries
    # through the workflow and everyone sees the same lines. Null = all lines.
    parking_line_item_ids = Column(Text, nullable=True)

    # Status
    status = Column(String(30), default=InvoiceStatus.DRAFT.value)

    # Soft delete — set when an invoice is removed on our side (e.g. after it is
    # unparked/reversed in SAP). A parked invoice cannot be hard-deleted here.
    is_deleted = Column(Integer, default=0)  # 0 = active, 1 = soft-deleted
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    line_items = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )

    # User-confirmed / corrected values
    description = Column(Text)
    quantity = Column(Float)
    unit = Column(String(50))
    unit_price = Column(Float)
    amount = Column(Float)

    # Original AI-extracted values (before user edits)
    ai_description = Column(Text)
    ai_quantity = Column(Float)
    ai_unit = Column(String(50))
    ai_unit_price = Column(Float)
    ai_amount = Column(Float)

    # Per-field confidence (from AI extraction)
    description_confidence = Column(Float)
    quantity_confidence = Column(Float)
    unit_price_confidence = Column(Float)
    amount_confidence = Column(Float)

    # Whether the user modified this line item
    user_modified = Column(Integer, default=0)  # 0=no, 1=yes

    # Gemini product/account matching (populated as background job after submission)
    matched_product_code = Column(String(50))
    matched_product_name = Column(String(255))
    matched_product_category = Column(String(100))
    match_confidence = Column(Float)
    match_reasoning = Column(Text)

    invoice = relationship("Invoice", back_populates="line_items")
