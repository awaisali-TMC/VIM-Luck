"""Audit logging service — call from any router to record actions."""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    action: str,
    actor_id: int | None = None,
    actor_type: str = "system",
    actor_name: str = "System",
    old_value: dict | list | None = None,
    new_value: dict | list | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """
    Record an audit log entry.

    NOTE: Does NOT commit — the caller's transaction will handle it.
    This allows audit logs to be part of the same atomic transaction
    as the action being logged.
    """
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_name=actor_name,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(entry)
    logger.debug(
        f"Audit: {entity_type}/{entity_id} — {action} by {actor_name} ({actor_type})"
    )
    return entry
