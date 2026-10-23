from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from app.models.invoice import Base


class SapCurrency(Base):
    """SAP currency codes (TCURC/TCURT) cached locally so the Park-to-SAP
    currency dropdown loads instantly without an RFC round-trip each time.
    Refreshed from SAP via POST /api/sap/currencies/sync.
    """
    __tablename__ = "sap_currencies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False)        # WAERS (currency key)
    name = Column(String(255))                       # TCURT long text
    iso_code = Column(String(10))                    # ISO currency code
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (UniqueConstraint("code", name="uq_sap_currency"),)
