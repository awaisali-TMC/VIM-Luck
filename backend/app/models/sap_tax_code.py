from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint

from app.models.invoice import Base


class SapTaxCode(Base):
    """SAP tax codes (e.g. Pakistan procedure TAXPK) cached locally so the
    Park-to-SAP dropdown loads instantly without an RFC round-trip each time.
    Refreshed from SAP via POST /api/sap/tax-codes/sync.
    """
    __tablename__ = "sap_tax_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_code = Column(String(10), nullable=False, index=True)
    country = Column(String(5))
    procedure = Column(String(20))
    code = Column(String(10), nullable=False)
    description = Column(String(255))
    tax_type = Column(String(20))          # "input" | "output"
    rate = Column(Float, nullable=True)     # parsed from the description (% ), null if none
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("company_code", "code", name="uq_sap_tax_code"),)
