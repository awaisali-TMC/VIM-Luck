import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Boolean

from app.models.invoice import Base


class SupplierStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class SupplierUser(Base):
    __tablename__ = "supplier_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    mobile = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    # SAP vendor master link (LIFNR) — set by admin at onboarding via the
    # "Add from SAP" picker. This is what scopes the supplier to their own
    # SAP POs and what makes the account SAP-backed.
    sap_vendor_number = Column(String(20), nullable=True, index=True)
    # Tax number (NTN) — SAP's vendor master doesn't reliably carry it, so it
    # lives on the account (used as fallback for FBR checks on flipped invoices).
    ntn = Column(String(50), nullable=True)
    status = Column(String(20), default=SupplierStatus.PENDING, nullable=False)
    rejection_reason = Column(String(500), nullable=True)
    # Session token stored in DB (no JWT dependency needed)
    auth_token = Column(String(100), nullable=True, index=True)
    # When the current session token was issued — used to expire stale sessions.
    token_issued_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mobile = Column(String(20), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    purpose = Column(String(20), default="signup")  # "signup" | "login"
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
