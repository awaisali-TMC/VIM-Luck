from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class OTPRequest(BaseModel):
    mobile: str
    purpose: str = "signup"  # "signup" | "login"


class SupplierSignup(BaseModel):
    mobile: str
    otp_code: str
    name: str
    company_name: str
    email: Optional[str] = None
    password: Optional[str] = None


class SupplierLogin(BaseModel):
    mobile: str
    otp_code: str


class SupplierResponse(BaseModel):
    id: int
    name: str
    company_name: str
    mobile: str
    email: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminCreateSupplier(BaseModel):
    name: str
    company_name: str
    mobile: str
    email: Optional[str] = None
    password: Optional[str] = None
    # SAP vendor master link (LIFNR) — filled by the "Add from SAP" picker
    sap_vendor_number: Optional[str] = None
    ntn: Optional[str] = None


class AdminUpdateSupplier(BaseModel):
    """Partial update of account details (all fields optional)."""
    name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    sap_vendor_number: Optional[str] = None
    ntn: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str  # "verified" | "rejected"
    rejection_reason: Optional[str] = None
