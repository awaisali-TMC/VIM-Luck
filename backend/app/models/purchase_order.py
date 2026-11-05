import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.invoice import Base


class POStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    PARTIALLY_RECEIVED = "partially_received"
    FULLY_RECEIVED = "fully_received"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class POType(str, enum.Enum):
    LOCAL = "local"
    FOREIGN = "foreign"
    CONTRACT = "contract"


class MatchStatus(str, enum.Enum):
    FULL_MATCH = "full_match"
    PARTIAL_MATCH = "partial_match"
    MISMATCH = "mismatch"
    UNMATCHED = "unmatched"


# ── Purchase Order ────────────────────────────────────────────

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_number = Column(String(100), unique=True, nullable=False, index=True)
    vendor_name = Column(String(255), nullable=False)
    # SAP vendor master number (LIFNR) — set when the PO is synced from SAP.
    # Scopes supplier-portal PO visibility to the account's linked vendor.
    sap_vendor_number = Column(String(20), nullable=True, index=True)
    # SAP company code (EKKO-BUKRS) — set on SAP sync, backfilled at park.
    # Part of the duplicate-invoice key (services/duplicate_detection.py).
    company_code = Column(String(10), nullable=True)
    vendor_ntn = Column(String(50))
    po_date = Column(String(50))
    po_type = Column(String(20), default=POType.LOCAL.value)
    total_amount = Column(Float)
    currency = Column(String(10), default="PKR")
    status = Column(String(30), default=POStatus.OPEN.value)
    notes = Column(Text)

    # Source tracking
    source_type = Column(String(20), default="manual")  # "manual" | "file_upload"
    original_filename = Column(String(255))
    stored_filepath = Column(String(500))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    line_items = relationship(
        "POLineItem", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    grns = relationship(
        "GoodsReceivedNote", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    ses_records = relationship(
        "ServiceEntrySheet", back_populates="purchase_order", cascade="all, delete-orphan"
    )
    match_results = relationship("POMatchResult", back_populates="purchase_order")


# ── PO Line Item ──────────────────────────────────────────────

class POLineItem(Base):
    __tablename__ = "po_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(
        Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    item_number = Column(Integer)
    description = Column(Text, nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50))
    unit_price = Column(Float, nullable=False)
    amount = Column(Float)

    purchase_order = relationship("PurchaseOrder", back_populates="line_items")
    grn_line_items = relationship("GRNLineItem", back_populates="po_line_item")
    ses_line_items = relationship("SESLineItem", back_populates="po_line_item")


# ── Goods Received Note ───────────────────────────────────────

class GoodsReceivedNote(Base):
    __tablename__ = "goods_received_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grn_number = Column(String(100), unique=True, nullable=False, index=True)
    grn_date = Column(String(50))
    po_id = Column(
        Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    received_by = Column(String(255))
    plant_location = Column(String(255))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    purchase_order = relationship("PurchaseOrder", back_populates="grns")
    line_items = relationship(
        "GRNLineItem", back_populates="grn", cascade="all, delete-orphan"
    )


class GRNLineItem(Base):
    __tablename__ = "grn_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grn_id = Column(
        Integer, ForeignKey("goods_received_notes.id", ondelete="CASCADE"), nullable=False
    )
    po_line_item_id = Column(Integer, ForeignKey("po_line_items.id"), nullable=False)
    received_quantity = Column(Float, nullable=False)
    inspection_status = Column(String(30), default="accepted")  # accepted/rejected/pending

    grn = relationship("GoodsReceivedNote", back_populates="line_items")
    po_line_item = relationship("POLineItem", back_populates="grn_line_items")


# ── Service Entry Sheet ───────────────────────────────────────

class ServiceEntrySheet(Base):
    __tablename__ = "service_entry_sheets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ses_number = Column(String(100), unique=True, nullable=False, index=True)
    ses_date = Column(String(50))
    po_id = Column(
        Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    service_period_from = Column(String(50))
    service_period_to = Column(String(50))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    purchase_order = relationship("PurchaseOrder", back_populates="ses_records")
    line_items = relationship(
        "SESLineItem", back_populates="ses", cascade="all, delete-orphan"
    )


class SESLineItem(Base):
    __tablename__ = "ses_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ses_id = Column(
        Integer, ForeignKey("service_entry_sheets.id", ondelete="CASCADE"), nullable=False
    )
    po_line_item_id = Column(Integer, ForeignKey("po_line_items.id"), nullable=False)
    completed_quantity = Column(Float, nullable=False)
    completed_amount = Column(Float)

    ses = relationship("ServiceEntrySheet", back_populates="line_items")
    po_line_item = relationship("POLineItem", back_populates="ses_line_items")


# ── PO Match Result ───────────────────────────────────────────

class POMatchResult(Base):
    """Stores the result of matching an invoice against a PO."""
    __tablename__ = "po_match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    po_id = Column(
        Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    match_status = Column(String(30), default=MatchStatus.UNMATCHED.value)
    match_type = Column(String(20), default="2-way")  # "2-way" | "3-way"
    overall_score = Column(Float)
    total_amount_diff = Column(Float)
    total_amount_diff_pct = Column(Float)
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    purchase_order = relationship("PurchaseOrder", back_populates="match_results")
    invoice = relationship("Invoice", backref="po_match_results")
    line_matches = relationship(
        "POLineMatchDetail", back_populates="match_result", cascade="all, delete-orphan"
    )


# ── PO Line Match Detail ─────────────────────────────────────

class POLineMatchDetail(Base):
    """Per-line-item matching detail between invoice lines and PO lines."""
    __tablename__ = "po_line_match_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_result_id = Column(
        Integer, ForeignKey("po_match_results.id", ondelete="CASCADE"), nullable=False
    )
    invoice_line_item_id = Column(
        Integer, ForeignKey("invoice_line_items.id"), nullable=True
    )
    po_line_item_id = Column(
        Integer, ForeignKey("po_line_items.id"), nullable=True
    )
    match_status = Column(String(30), default=MatchStatus.UNMATCHED.value)
    quantity_match = Column(Integer, default=0)  # 0=no, 1=yes
    price_match = Column(Integer, default=0)     # 0=no, 1=yes
    quantity_diff = Column(Float)
    quantity_diff_pct = Column(Float)
    price_diff = Column(Float)
    price_diff_pct = Column(Float)
    grn_received_qty = Column(Float)
    ses_completed_qty = Column(Float)
    reasoning = Column(Text)

    match_result = relationship("POMatchResult", back_populates="line_matches")
