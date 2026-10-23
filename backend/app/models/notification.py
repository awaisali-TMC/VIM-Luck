from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.models.invoice import Base


class Notification(Base):
    """In-app notification for an internal user (e.g. an @mention in a comment)."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)   # recipient InternalUser.id
    type = Column(String(30), default="mention")            # "mention" | ...
    title = Column(String(150))
    message = Column(Text)
    entity_type = Column(String(30))                        # e.g. "invoice"
    entity_id = Column(Integer)                             # e.g. invoice id (for the link)
    actor_name = Column(String(150))                        # who triggered it
    is_read = Column(Integer, default=0)                    # 0 = unread, 1 = read
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
