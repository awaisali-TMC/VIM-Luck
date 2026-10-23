"""
FBR Active Taxpayer List (ATL) — one row per taxpayer.

Populated from FBR's weekly ATL publication (one-time import for now; a weekly
refresh job comes later). Used to verify a supplier's NTN is an active/filer
taxpayer without depending on FBR's live IRIS API at runtime.
"""
from sqlalchemy import Column, Integer, String, Index

from app.database import Base


class AtlTaxpayer(Base):
    __tablename__ = "atl_taxpayers"

    id = Column(Integer, primary_key=True, index=True)
    # NTN stored normalised (digits only, no dashes/spaces) for fast exact match,
    # plus the display form as published.
    ntn = Column(String(30), index=True)          # normalised (digits only)
    ntn_display = Column(String(40), nullable=True)  # as-published (e.g. 2469708-7)
    cnic = Column(String(20), index=True, nullable=True)  # normalised CNIC (ST list)
    name = Column(String(255), nullable=True)
    business_name = Column(String(255), nullable=True)
    filing_status = Column(String(30), nullable=True)   # "Active" (on ATL = active filer)
    list_type = Column(String(4), nullable=True)         # "IT" (income tax) | "ST" (sales tax)
    status_date = Column(String(30), nullable=True)
    last_updated = Column(String(30), nullable=True)

    __table_args__ = (
        Index("ix_atl_ntn", "ntn"),
    )
