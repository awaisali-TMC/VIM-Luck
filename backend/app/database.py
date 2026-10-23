import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from app.models.invoice import Base
from app.models.supplier import SupplierUser, OTPRecord  # noqa: F401 — register tables
from app.models.email_message import EmailMessage, EmailAttachment  # noqa: F401 — register tables
from app.models.purchase_order import (  # noqa: F401 — register tables
    PurchaseOrder, POLineItem,
    GoodsReceivedNote, GRNLineItem,
    ServiceEntrySheet, SESLineItem,
    POMatchResult, POLineMatchDetail,
)
from app.models.internal_user import InternalUser  # noqa: F401 — register tables
from app.models.audit_log import AuditLog  # noqa: F401 — register tables
from app.models.workflow import (  # noqa: F401 — register tables
    WorkflowTemplate, WorkflowStep,
    ApprovalRequest, ApprovalAction,
)
from app.models.gl_account import GLAccount, GLAssignment  # noqa: F401 — register tables
from app.models.comment import Comment, CurrencyRate  # noqa: F401 — register tables
from app.models.tax_rule import TaxRule  # noqa: F401 — register tables
from app.models.attachment import InvoiceAttachment  # noqa: F401 — register tables
from app.models.sap_tax_code import SapTaxCode  # noqa: F401 — register tables
from app.models.sap_currency import SapCurrency  # noqa: F401 — register tables
from app.models.notification import Notification  # noqa: F401 — register tables
from app.models.role_permission import RolePermission  # noqa: F401 — register tables
from app.models.role import Role  # noqa: F401 — register tables
from app.models.atl_taxpayer import AtlTaxpayer  # noqa: F401 — register tables

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_migrations():
    """Safely add new columns to existing tables (SQLite supports ADD COLUMN)."""
    migrations = [
        "ALTER TABLE invoices ADD COLUMN detected_taxes TEXT",
        "ALTER TABLE invoices ADD COLUMN parking_line_item_ids TEXT",
        "ALTER TABLE atl_taxpayers ADD COLUMN cnic VARCHAR(20)",
        "ALTER TABLE atl_taxpayers ADD COLUMN list_type VARCHAR(4)",
        "ALTER TABLE invoices ADD COLUMN source_type VARCHAR(20) DEFAULT 'upload'",
        "ALTER TABLE invoices ADD COLUMN source_email_id INTEGER",
        "ALTER TABLE invoices ADD COLUMN source_email_from VARCHAR(500)",
        # Product matching columns on line items
        "ALTER TABLE invoice_line_items ADD COLUMN matched_product_code VARCHAR(50)",
        "ALTER TABLE invoice_line_items ADD COLUMN matched_product_name VARCHAR(255)",
        "ALTER TABLE invoice_line_items ADD COLUMN matched_product_category VARCHAR(100)",
        "ALTER TABLE invoice_line_items ADD COLUMN match_confidence FLOAT",
        "ALTER TABLE invoice_line_items ADD COLUMN match_reasoning TEXT",
        # PO matching convenience columns
        "ALTER TABLE invoices ADD COLUMN matched_po_id INTEGER",
        "ALTER TABLE invoices ADD COLUMN latest_po_match_status VARCHAR(30)",
        # FBR ATL verification
        "ALTER TABLE invoices ADD COLUMN fbr_verification_status VARCHAR(30) DEFAULT 'not_verified'",
        "ALTER TABLE invoices ADD COLUMN fbr_verified_at TIMESTAMP",
        "ALTER TABLE invoices ADD COLUMN fbr_taxpayer_name VARCHAR(500)",
        "ALTER TABLE invoices ADD COLUMN fbr_filing_status VARCHAR(200)",
        "ALTER TABLE invoices ADD COLUMN wht_compliance_status VARCHAR(30)",
        # Credit/Debit note support
        "ALTER TABLE invoices ADD COLUMN linked_invoice_id INTEGER",
        "ALTER TABLE invoices ADD COLUMN credit_debit_reason TEXT",
        "ALTER TABLE invoices ADD COLUMN original_invoice_number VARCHAR(100)",
        # Multi-currency support
        "ALTER TABLE invoices ADD COLUMN base_currency VARCHAR(10) DEFAULT 'PKR'",
        "ALTER TABLE invoices ADD COLUMN exchange_rate FLOAT",
        "ALTER TABLE invoices ADD COLUMN base_total_amount FLOAT",
        # Object-level ownership — supplier who submitted the invoice
        "ALTER TABLE invoices ADD COLUMN supplier_id INTEGER",
        # Session token issue time — for token expiry
        "ALTER TABLE internal_users ADD COLUMN token_issued_at TIMESTAMP",
        "ALTER TABLE supplier_users ADD COLUMN token_issued_at TIMESTAMP",
        # SAP document status — "parked" (BAPI_INCOMINGINVOICE_PARK) | "posted"
        "ALTER TABLE invoices ADD COLUMN sap_doc_status VARCHAR(20)",
        # SAP tax code chosen for the invoice (AI-suggested, user-editable, used at park)
        "ALTER TABLE invoices ADD COLUMN sap_tax_code VARCHAR(10)",
        # SAP parking parameters — completed during review, locked at approval
        "ALTER TABLE invoices ADD COLUMN sap_layout VARCHAR(20)",
        "ALTER TABLE invoices ADD COLUMN sap_posting_date VARCHAR(50)",
        "ALTER TABLE invoices ADD COLUMN sap_header_text VARCHAR(50)",
        # Soft delete
        "ALTER TABLE invoices ADD COLUMN is_deleted INTEGER DEFAULT 0",
        "ALTER TABLE invoices ADD COLUMN deleted_at TIMESTAMP",
        # Baseline date (mandatory) + document currency selection
        "ALTER TABLE invoices ADD COLUMN sap_baseline_date VARCHAR(50)",
        "ALTER TABLE invoices ADD COLUMN sap_currency VARCHAR(10)",
        # Details-tab item text (SGTXT); header text (BKTXT) already exists
        "ALTER TABLE invoices ADD COLUMN sap_item_text VARCHAR(50)",
        # RBAC v2: per-page access level ("view" | "edit"); existing rows keep edit
        "ALTER TABLE role_permissions ADD COLUMN level VARCHAR(10) DEFAULT 'edit'",
        # SAP-backed supplier onboarding: vendor master link + account tax number
        "ALTER TABLE supplier_users ADD COLUMN sap_vendor_number VARCHAR(20)",
        "ALTER TABLE supplier_users ADD COLUMN ntn VARCHAR(50)",
        "CREATE INDEX IF NOT EXISTS ix_supplier_users_sap_vendor_number ON supplier_users (sap_vendor_number)",
        # PO ↔ SAP vendor link — scopes supplier-portal PO visibility
        "ALTER TABLE purchase_orders ADD COLUMN sap_vendor_number VARCHAR(20)",
        "CREATE INDEX IF NOT EXISTS ix_purchase_orders_sap_vendor_number ON purchase_orders (sap_vendor_number)",
        # Resolved SAP vendor, set on PO sync (routers/sap.py) and read by PO-flip.
        "ALTER TABLE invoices ADD COLUMN sap_vendor_number VARCHAR(20)",
        # Repair POs synced while the header total read EKKO RLWRT (0 for POs
        # without a release strategy): recompute from line values. Idempotent —
        # only touches rows whose stored total is still 0.
        "UPDATE purchase_orders SET total_amount = ("
        " SELECT COALESCE(SUM(amount), 0) FROM po_line_items"
        " WHERE po_line_items.po_id = purchase_orders.id)"
        " WHERE COALESCE(total_amount, 0) = 0",
        # Repair PO-created invoices stored with 0–1-scale confidence (rendered
        # as "1%"): the app-wide scale is 0–100. Idempotent (<=1 only).
        "UPDATE invoices SET overall_confidence = 100"
        " WHERE source_type = 'po_flip' AND overall_confidence IS NOT NULL AND overall_confidence <= 1",
        "UPDATE invoice_line_items SET description_confidence = 100, quantity_confidence = 100,"
        " unit_price_confidence = 100, amount_confidence = 100"
        " WHERE COALESCE(description_confidence, 0) <= 1 AND invoice_id IN"
        " (SELECT id FROM invoices WHERE source_type = 'po_flip')",
    ]
    # Each migration runs in its OWN transaction. On PostgreSQL a failed
    # statement (e.g. column already exists) aborts the entire transaction,
    # poisoning every subsequent statement with "current transaction is
    # aborted". Isolating each ALTER keeps an expected failure from blocking
    # later, still-needed migrations. (SQLite auto-commits per statement, so
    # this was previously masked in local dev.)
    logger = logging.getLogger(__name__)
    for sql in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception as e:
            # Usually "column already exists" — expected on every restart, but
            # keep a debug trace so a genuinely failed migration is diagnosable.
            logger.debug("Migration skipped (%s): %s", e.__class__.__name__, sql)


async def get_db():
    async with async_session() as session:
        yield session
