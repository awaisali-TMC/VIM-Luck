"""In-app notifications for internal users (e.g. @mentions in comments)."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.notification import Notification
from app.security import get_current_principal, Principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "actor_name": n.actor_name,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("")
async def list_notifications(
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Current user's notifications (newest first) + unread count."""
    if principal.kind != "internal":
        return {"notifications": [], "unread": 0}
    res = await db.execute(
        select(Notification)
        .where(Notification.user_id == principal.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    rows = res.scalars().all()
    unread = (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == principal.id, Notification.is_read == 0
        )
    )).scalar()
    return {"notifications": [_serialize(n) for n in rows], "unread": unread or 0}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    res = await db.execute(select(Notification).where(Notification.id == notification_id))
    n = res.scalar_one_or_none()
    if not n or n.user_id != principal.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = 1
    await db.commit()
    return {"success": True}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == principal.id, Notification.is_read == 0)
        .values(is_read=1)
    )
    await db.commit()
    return {"success": True}
