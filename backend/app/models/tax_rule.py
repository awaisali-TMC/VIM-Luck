"""Configurable tax rules for FBR compliance (GST/WHT/SED rates and thresholds)."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from app.models.invoice import Base


class TaxRule(Base):
    __tablename__ = "tax_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Rule identification
    rule_code = Column(String(50), unique=True, nullable=False, index=True)
    rule_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Tax type: gst, wht, sed, customs, cess, etc.
    tax_type = Column(String(30), nullable=False, index=True)

    # Rate (percentage)
    rate = Column(Float, nullable=False)

    # Applicability conditions
    applies_to = Column(String(50), default="all")  # all, goods, services, import, export
    min_amount = Column(Float, nullable=True)  # Apply only if invoice >= this
    max_amount = Column(Float, nullable=True)  # Apply only if invoice <= this
    supplier_type = Column(String(50), nullable=True)  # registered, unregistered, null=any
    sector = Column(String(100), nullable=True)  # oil_gas, construction, null=any

    # FBR section/SRO reference
    fbr_section = Column(String(100), nullable=True)  # e.g. "Section 153(1)(a)"
    sro_reference = Column(String(100), nullable=True)  # e.g. "SRO 1125(I)/2011"

    # Effective dates
    effective_from = Column(String(20), nullable=True)  # YYYY-MM-DD
    effective_to = Column(String(20), nullable=True)  # YYYY-MM-DD, null=still active

    # Status
    is_active = Column(Integer, default=1)
    priority = Column(Integer, default=100)  # Lower = higher priority for matching

    # Audit
    created_by_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
