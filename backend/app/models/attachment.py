"""Invoice attachment model for supporting documents."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.models.invoice import Base


class InvoiceAttachment(Base):
    __tablename__ = "invoice_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)          # original filename
    stored_filepath = Column(String(1000), nullable=False)  # server-side path
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)             # bytes

    document_type = Column(
        String(30), default="other"
    )  # work_order, scan, payment_proof, goods_receipt, contract, other
    description = Column(String(500), nullable=True)

    uploaded_by = Column(String(255), nullable=True)        # display name
    uploaded_by_role = Column(String(30), nullable=True)    # admin, supplier, etc.

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
