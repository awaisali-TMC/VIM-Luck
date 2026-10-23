"""Comment model for invoice collaboration."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Text

from app.models.invoice import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)   # "invoice", "po", etc.
    entity_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, nullable=True)                      # for threaded replies

    author_id = Column(Integer, nullable=False)
    author_name = Column(String(255), nullable=False)
    author_role = Column(String(50))

    content = Column(Text, nullable=False)
    mentioned_user_ids = Column(String(500), nullable=True)  # comma-separated user IDs
    is_internal = Column(Integer, default=1)     # 1 = internal only, 0 = visible to supplier
    is_resolved = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class CurrencyRate(Base):
    """Exchange rates for multi-currency support."""
    __tablename__ = "currency_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(10), nullable=False, index=True)
    to_currency = Column(String(10), nullable=False, default="PKR")
    rate = Column(String(30), nullable=False)              # stored as string for precision
    effective_date = Column(String(20), nullable=False)     # YYYY-MM-DD
    source = Column(String(50), default="manual")           # "manual" | "sbp" | "api"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
