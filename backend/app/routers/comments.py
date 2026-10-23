"""Comments / collaboration endpoints."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.comment import Comment
from app.models.notification import Notification
from app.models.internal_user import InternalUser
from app.security import get_current_principal, Principal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/comments", tags=["comments"])


class CommentCreate(BaseModel):
    entity_type: str
    entity_id: int
    content: str
    parent_id: Optional[int] = None
    is_internal: int = 1
    author_id: int
    author_name: str
    author_role: Optional[str] = None
    mentioned_user_ids: Optional[list[int]] = None


class CommentUpdate(BaseModel):
    content: Optional[str] = None
    is_resolved: Optional[int] = None


@router.get("/mentionable-users")
async def mentionable_users(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Active internal users for the @mention picker. Unlike /api/admin/users
    this is available to every internal user (not admin-only) and returns only
    the basics needed to render a mention.

    Suppliers deliberately get an EMPTY list: they may comment on their own
    invoices but not @mention staff — mentioning is an internal-collaboration
    feature (purchaser, AP manager, FD, etc.)."""
    if principal.kind != "internal":
        return {"users": []}
    result = await db.execute(
        select(InternalUser).where(InternalUser.is_active == 1).order_by(InternalUser.display_name)
    )
    return {
        "users": [
            {"id": u.id, "display_name": u.display_name, "email": u.email,
             "role": u.role, "department": u.department}
            for u in result.scalars().all()
        ]
    }


@router.get("/{entity_type}/{entity_id}")
async def list_comments(
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment)
        .where(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
        .order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()

    count_q = select(func.count(Comment.id)).where(
        Comment.entity_type == entity_type, Comment.entity_id == entity_id
    )
    total = (await db.execute(count_q)).scalar()

    return {
        "comments": [
            {
                "id": c.id, "entity_type": c.entity_type, "entity_id": c.entity_id,
                "parent_id": c.parent_id, "author_id": c.author_id,
                "author_name": c.author_name, "author_role": c.author_role,
                "content": c.content, "is_internal": c.is_internal,
                "is_resolved": c.is_resolved,
                "mentioned_user_ids": [int(x) for x in c.mentioned_user_ids.split(",") if x.strip()] if c.mentioned_user_ids else [],
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in comments
        ],
        "total": total,
    }


@router.post("")
async def create_comment(data: CommentCreate, db: AsyncSession = Depends(get_db)):
    mentioned_str = ",".join(str(uid) for uid in data.mentioned_user_ids) if data.mentioned_user_ids else None
    comment = Comment(
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        parent_id=data.parent_id,
        author_id=data.author_id,
        author_name=data.author_name,
        author_role=data.author_role,
        content=data.content,
        mentioned_user_ids=mentioned_str,
        is_internal=data.is_internal,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Notify each mentioned user (skip the author mentioning themselves).
    label = data.entity_type.replace("_", " ")
    for uid in (data.mentioned_user_ids or []):
        if uid == data.author_id:
            continue
        db.add(Notification(
            user_id=uid,
            type="mention",
            title=f"{data.author_name} mentioned you",
            message=f"{data.author_name} mentioned you in a comment on {label} #{data.entity_id}",
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            actor_name=data.author_name,
        ))
    if data.mentioned_user_ids:
        await db.commit()

    return {
        "id": comment.id, "content": comment.content,
        "author_name": comment.author_name,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.patch("/{comment_id}")
async def update_comment(
    comment_id: int, data: CommentUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(404, "Comment not found")

    if data.content is not None:
        comment.content = data.content
    if data.is_resolved is not None:
        comment.is_resolved = data.is_resolved

    await db.commit()
    await db.refresh(comment)
    return {"id": comment.id, "content": comment.content, "is_resolved": comment.is_resolved}


@router.delete("/{comment_id}")
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(404, "Comment not found")
    await db.delete(comment)
    await db.commit()
    return {"deleted": True}
