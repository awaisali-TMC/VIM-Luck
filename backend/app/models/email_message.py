import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class EmailStatus(str, enum.Enum):
    UNREAD = "unread"
    READ = "read"
    PROCESSED = "processed"


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, index=True)
    message_uid = Column(String(255), unique=True, index=True, nullable=False)
    from_address = Column(String(500))
    subject = Column(Text)
    body_text = Column(Text)
    received_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status = Column(String(30), default=EmailStatus.UNREAD.value)
    has_attachments = Column(Boolean, default=False)

    attachments = relationship(
        "EmailAttachment", back_populates="email", cascade="all, delete-orphan"
    )


class EmailAttachment(Base):
    __tablename__ = "email_attachments"

    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("email_messages.id"), nullable=False)
    filename = Column(String(500))
    content_type = Column(String(100))
    file_size = Column(Integer, nullable=True)
    stored_filepath = Column(String(1000), nullable=True)
    processed = Column(Boolean, default=False)
    invoice_id = Column(Integer, nullable=True)

    email = relationship("EmailMessage", back_populates="attachments")
