import random
import secrets
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Header, HTTPException, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.security import _extract_token, _token_expired
from app.services.passwords import hash_password, verify_password, needs_rehash
from app.models.supplier import SupplierUser, OTPRecord, SupplierStatus
from app.schemas.supplier import OTPRequest, SupplierSignup, SupplierLogin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_EXPIRY_MINUTES = 10


def _hash_password(password: str) -> str:
    return hash_password(password)


def _verify_password(password: str, stored: str) -> bool:
    return verify_password(password, stored)


def _generate_token() -> str:
    return secrets.token_hex(32)


def _normalize_mobile(mobile: str) -> str:
    """Strip spaces and dashes for consistent storage."""
    return mobile.strip().replace(" ", "").replace("-", "")


@router.post("/supplier/request-otp")
async def request_otp(data: OTPRequest, db: AsyncSession = Depends(get_db)):
    """Generate a 6-digit OTP and store it. For demo, returns OTP in response."""
    mobile = _normalize_mobile(data.mobile)

    if data.purpose == "login":
        result = await db.execute(
            select(SupplierUser).where(SupplierUser.mobile == mobile)
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="No account found for this mobile number.")
        if supplier.status == SupplierStatus.PENDING:
            raise HTTPException(
                status_code=403,
                detail="Your account is pending admin verification. You will be notified once approved."
            )
        if supplier.status == SupplierStatus.REJECTED:
            raise HTTPException(
                status_code=403,
                detail=f"Your account has been rejected. {supplier.rejection_reason or 'Please contact support.'}"
            )

    if data.purpose == "signup":
        result = await db.execute(
            select(SupplierUser).where(SupplierUser.mobile == mobile)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="An account with this mobile number already exists. Please log in instead."
            )

    code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp = OTPRecord(
        mobile=mobile,
        code=code,
        purpose=data.purpose,
        expires_at=expires_at,
        used=False,
    )
    db.add(otp)
    await db.commit()

    # Never log the code itself — logs are not a secure channel.
    logger.info(f"OTP generated for {mobile} (purpose={data.purpose})")

    # NOTE: In production, integrate an SMS gateway here (e.g. Twilio, AWS SNS).
    # The `otp_demo` field is only echoed back when DEBUG is enabled (local dev).
    # In production (DEBUG=False) the code is never returned in the API response,
    # so it can only be obtained via the actual SMS channel.
    response = {
        "message": "OTP sent successfully",
        "expires_in_minutes": OTP_EXPIRY_MINUTES,
    }
    if settings.DEBUG:
        response["otp_demo"] = code
    return response


@router.post("/supplier/verify-otp")
async def verify_otp(data: SupplierLogin, db: AsyncSession = Depends(get_db)):
    """Check an OTP without consuming it (gates multi-step flows server-side).

    The OTP stays unused so the final signup/login submit can still consume it.
    """
    mobile = _normalize_mobile(data.mobile)
    result = await db.execute(
        select(OTPRecord)
        .where(
            OTPRecord.mobile == mobile,
            OTPRecord.code == data.otp_code,
            OTPRecord.used == False,
        )
        .order_by(OTPRecord.created_at.desc())
    )
    otp = result.scalar_one_or_none()
    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please check and try again.")
    now = datetime.now(timezone.utc)
    expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
    return {"valid": True}


@router.post("/supplier/signup")
async def supplier_signup(data: SupplierSignup, db: AsyncSession = Depends(get_db)):
    """Verify OTP and create a supplier account (status=pending, awaiting admin approval)."""
    mobile = _normalize_mobile(data.mobile)

    # Verify OTP
    result = await db.execute(
        select(OTPRecord)
        .where(
            OTPRecord.mobile == mobile,
            OTPRecord.code == data.otp_code,
            OTPRecord.purpose == "signup",
            OTPRecord.used == False,
        )
        .order_by(OTPRecord.created_at.desc())
    )
    otp = result.scalar_one_or_none()
    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please check and try again.")

    now = datetime.now(timezone.utc)
    expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=timezone.utc)
    if now > expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    # Guard duplicate
    existing = await db.execute(
        select(SupplierUser).where(SupplierUser.mobile == mobile)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Account already exists for this mobile number.")

    otp.used = True

    supplier = SupplierUser(
        name=data.name.strip(),
        company_name=data.company_name.strip(),
        mobile=mobile,
        email=data.email.strip() if data.email else None,
        password_hash=_hash_password(data.password) if data.password else None,
        status=SupplierStatus.PENDING,
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    logger.info(f"New supplier account created: id={supplier.id}, mobile={mobile}")

    return {
        "message": "Account created successfully. An admin will review and approve your account.",
        "supplier_id": supplier.id,
        "status": supplier.status,
    }


@router.post("/supplier/login")
async def supplier_login(data: SupplierLogin, db: AsyncSession = Depends(get_db)):
    """Verify OTP and issue a session token for a verified supplier."""
    mobile = _normalize_mobile(data.mobile)

    # Demo convenience: a configured fixed OTP always works — not looked up in
    # otp_records, never consumed, never expired. Empty in real deployments, so
    # only genuine single-use OTPs are accepted there.
    demo_otp = (settings.SUPPLIER_DEMO_OTP or "").strip()
    demo_ok = bool(demo_otp) and data.otp_code.strip() == demo_otp

    otp = None
    if not demo_ok:
        # Verify a real, single-use OTP
        result = await db.execute(
            select(OTPRecord)
            .where(
                OTPRecord.mobile == mobile,
                OTPRecord.code == data.otp_code,
                OTPRecord.purpose == "login",
                OTPRecord.used == False,
            )
            .order_by(OTPRecord.created_at.desc())
        )
        otp = result.scalar_one_or_none()
        if not otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code. Please check and try again.")

        now = datetime.now(timezone.utc)
        expires = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=timezone.utc)
        if now > expires:
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")

    # Get supplier
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.mobile == mobile)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Account not found.")
    if supplier.status == SupplierStatus.PENDING:
        raise HTTPException(
            status_code=403,
            detail="Your account is pending admin verification."
        )
    if supplier.status == SupplierStatus.REJECTED:
        raise HTTPException(
            status_code=403,
            detail=f"Your account has been rejected. {supplier.rejection_reason or 'Please contact support.'}"
        )

    if otp is not None:
        otp.used = True   # consume the real OTP (demo OTP is never consumed)
    token = _generate_token()
    supplier.auth_token = token
    now = datetime.now(timezone.utc)
    supplier.token_issued_at = now
    supplier.updated_at = now
    await db.commit()
    await db.refresh(supplier)

    return {
        "token": token,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "company_name": supplier.company_name,
            "mobile": supplier.mobile,
            "email": supplier.email,
            "status": supplier.status,
        },
    }


@router.get("/supplier/me")
async def get_me(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),  # deprecated fallback
    db: AsyncSession = Depends(get_db),
):
    """Validate session token (Authorization: Bearer) and return the supplier."""
    tok = _extract_token(authorization, token)
    if not tok:
        raise HTTPException(status_code=401, detail="Authentication required.")
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.auth_token == tok)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")
    if _token_expired(supplier.token_issued_at):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    return {
        "id": supplier.id,
        "name": supplier.name,
        "company_name": supplier.company_name,
        "mobile": supplier.mobile,
        "email": supplier.email,
        "status": supplier.status,
    }


@router.post("/supplier/logout")
async def logout(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),  # deprecated fallback
    db: AsyncSession = Depends(get_db),
):
    """Invalidate a session token."""
    tok = _extract_token(authorization, token)
    if not tok:
        return {"message": "Logged out successfully"}
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.auth_token == tok)
    )
    supplier = result.scalar_one_or_none()
    if supplier:
        supplier.auth_token = None
        await db.commit()
    return {"message": "Logged out successfully"}
