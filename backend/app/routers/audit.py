"""
Audit log query endpoints.

  GET /api/audit-logs                        — query logs with filters
  GET /api/audit-logs/entity/{type}/{id}     — all logs for a specific entity
"""

import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


def _format_entry(log: AuditLog) -> dict:
    """Format an AuditLog row for JSON response."""
    return {
        "id": log.id,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "action": log.action,
        "actor_id": log.actor_id,
        "actor_type": log.actor_type,
        "actor_name": log.actor_name,
        "old_value": json.loads(log.old_value) if log.old_value else None,
        "new_value": json.loads(log.new_value) if log.new_value else None,
        "metadata": json.loads(log.metadata_json) if log.metadata_json else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


@router.get("")
async def query_logs(
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    actor_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Query audit logs with optional filters."""
    query = select(AuditLog)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)

    # Count
    count_q = select(func.count(AuditLog.id))
    if entity_type:
        count_q = count_q.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        count_q = count_q.where(AuditLog.entity_id == entity_id)
    if action:
        count_q = count_q.where(AuditLog.action == action)
    if actor_id is not None:
        count_q = count_q.where(AuditLog.actor_id == actor_id)
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {"logs": [_format_entry(l) for l in logs], "total": total}


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity_logs(
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all audit logs for a specific entity, newest first."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.created_at.desc())
    )
    logs = result.scalars().all()
    return {"logs": [_format_entry(l) for l in logs], "total": len(logs)}
