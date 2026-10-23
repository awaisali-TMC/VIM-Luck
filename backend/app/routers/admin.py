import hashlib
import secrets
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.supplier import SupplierUser, SupplierStatus
from app.schemas.supplier import AdminCreateSupplier, AdminUpdateSupplier, StatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _supplier_dict(s: SupplierUser) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "company_name": s.company_name,
        "mobile": s.mobile,
        "email": s.email,
        "sap_vendor_number": s.sap_vendor_number,
        "ntn": s.ntn,
        "status": s.status,
        "rejection_reason": s.rejection_reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/suppliers")
async def list_suppliers(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List all supplier accounts, optionally filtered by status."""
    query = select(SupplierUser).order_by(SupplierUser.created_at.desc())
    if status and status in [s.value for s in SupplierStatus]:
        query = query.where(SupplierUser.status == status)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    suppliers = result.scalars().all()

    # Counts per status
    counts = {}
    for st in SupplierStatus:
        c = await db.execute(
            select(func.count(SupplierUser.id)).where(SupplierUser.status == st.value)
        )
        counts[st.value] = c.scalar() or 0

    total_result = await db.execute(select(func.count(SupplierUser.id)))
    total = total_result.scalar() or 0

    return {
        "suppliers": [_supplier_dict(s) for s in suppliers],
        "total": total,
        "counts": {
            "total": total,
            "pending": counts.get("pending", 0),
            "verified": counts.get("verified", 0),
            "rejected": counts.get("rejected", 0),
        },
    }


@router.post("/suppliers", status_code=201)
async def create_supplier(data: AdminCreateSupplier, db: AsyncSession = Depends(get_db)):
    """Admin creates a supplier account (auto-verified, no OTP needed)."""
    mobile = data.mobile.strip().replace(" ", "").replace("-", "")

    existing = await db.execute(
        select(SupplierUser).where(SupplierUser.mobile == mobile)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Mobile number already registered.")

    supplier = SupplierUser(
        name=data.name.strip(),
        company_name=data.company_name.strip(),
        mobile=mobile,
        email=data.email.strip() if data.email else None,
        password_hash=_hash_password(data.password) if data.password else None,
        sap_vendor_number=(data.sap_vendor_number or "").strip()[:20] or None,
        ntn=(data.ntn or "").strip()[:50] or None,
        status=SupplierStatus.VERIFIED,  # admin-created = auto-verified
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)

    logger.info(
        f"Admin created supplier: id={supplier.id}, mobile={mobile}, "
        f"sap_vendor={supplier.sap_vendor_number or '-'}"
    )
    return _supplier_dict(supplier)


@router.patch("/suppliers/{supplier_id}")
async def update_supplier_details(
    supplier_id: int,
    data: AdminUpdateSupplier,
    db: AsyncSession = Depends(get_db),
):
    """Update account details — e.g. attach the SAP vendor number to an
    account created before SAP onboarding existed."""
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.id == supplier_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    if data.name is not None and data.name.strip():
        supplier.name = data.name.strip()[:255]
    if data.company_name is not None and data.company_name.strip():
        supplier.company_name = data.company_name.strip()[:255]
    if data.email is not None:
        supplier.email = data.email.strip()[:255] or None
    if data.sap_vendor_number is not None:
        supplier.sap_vendor_number = data.sap_vendor_number.strip()[:20] or None
    if data.ntn is not None:
        supplier.ntn = data.ntn.strip()[:50] or None
    supplier.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(supplier)
    logger.info(f"Supplier {supplier_id} details updated (sap_vendor={supplier.sap_vendor_number or '-'})")
    return _supplier_dict(supplier)


@router.get("/suppliers/{supplier_id}")
async def get_supplier(supplier_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single supplier by ID."""
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.id == supplier_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return _supplier_dict(supplier)


@router.patch("/suppliers/{supplier_id}/status")
async def update_supplier_status(
    supplier_id: int,
    data: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a supplier account."""
    valid = [s.value for s in SupplierStatus]
    if data.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    result = await db.execute(
        select(SupplierUser).where(SupplierUser.id == supplier_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    supplier.status = data.status
    supplier.rejection_reason = data.rejection_reason if data.status == "rejected" else None
    supplier.updated_at = datetime.now(timezone.utc)

    # Revoke active session on rejection
    if data.status == "rejected":
        supplier.auth_token = None

    await db.commit()
    await db.refresh(supplier)

    logger.info(f"Supplier {supplier_id} status updated to {data.status}")
    return _supplier_dict(supplier)


@router.delete("/suppliers/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: int, db: AsyncSession = Depends(get_db)):
    """Hard-delete a supplier account (admin only)."""
    result = await db.execute(
        select(SupplierUser).where(SupplierUser.id == supplier_id)
    )
    supplier = result.scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    await db.delete(supplier)
    await db.commit()
