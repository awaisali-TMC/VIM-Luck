"""Admin-editable runtime settings stored in the app database (`app_settings`).

Mounted under admin_dep in main.py, so every route here is admin-only.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.internal_user import InternalUser
from app.security import require_admin
from app.services.audit_service import log_audit

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])

SUPPLIER_DEMO_OTP_KEY = "supplier_demo_otp"
_OTP_RE = re.compile(r"^\d{4,10}$")


async def get_supplier_demo_otp(db: AsyncSession) -> str:
    """The configured demo OTP, or "" when disabled. Read on every supplier login."""
    row = await db.get(AppSetting, SUPPLIER_DEMO_OTP_KEY)
    return (row.value or "").strip() if row else ""


class DemoOtpUpdate(BaseModel):
    # Digits only, 4-10 long. Null or "" disables the demo OTP.
    otp: str | None = None


def _otp_response(row: AppSetting | None) -> dict:
    otp = (row.value or "").strip() if row else ""
    return {
        "otp": otp or None,
        "enabled": bool(otp),
        "updated_by": row.updated_by if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


@router.get("/supplier-demo-otp")
async def read_supplier_demo_otp(db: AsyncSession = Depends(get_db)):
    return _otp_response(await db.get(AppSetting, SUPPLIER_DEMO_OTP_KEY))


@router.put("/supplier-demo-otp")
async def update_supplier_demo_otp(
    data: DemoOtpUpdate,
    db: AsyncSession = Depends(get_db),
    admin: InternalUser = Depends(require_admin),
):
    otp = (data.otp or "").strip()
    if otp and not _OTP_RE.match(otp):
        raise HTTPException(status_code=422, detail="Demo OTP must be 4 to 10 digits.")

    row = await db.get(AppSetting, SUPPLIER_DEMO_OTP_KEY)
    was_enabled = bool(row and (row.value or "").strip())
    if row is None:
        row = AppSetting(key=SUPPLIER_DEMO_OTP_KEY)
        db.add(row)
    row.value = otp or None
    row.updated_by = admin.email

    # The code itself is a credential: record that it changed, never its value.
    await log_audit(
        db, entity_type="app_setting", entity_id=0,
        action="supplier_demo_otp_updated",
        actor_id=admin.id, actor_type="internal_user", actor_name=admin.display_name or admin.email,
        old_value={"enabled": was_enabled}, new_value={"enabled": bool(otp)},
    )
    await db.commit()
    await db.refresh(row)
    return _otp_response(row)
