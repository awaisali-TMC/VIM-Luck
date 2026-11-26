"""Client request (2026-11-26): the vendor NTN on the invoice must match the SAP PO's
vendor. A mismatch is shown as an error on the invoice page; it does not block
Submit or Park.

SAP side: the PO vendor's tax numbers from LFA1 (STCD1 = NTN, STCD2 = STRN,
STCD3 = CNIC on Lucky's system), stored on the PO at sync as
`purchase_orders.vendor_tax_numbers`. POs synced before that column existed are
read from SAP once, when an invoice matched to them is opened (best effort).

An NTN is compared on its 7-character base (with or without the check digit, so
"1234567-8" = "1234567"); a CNIC (13 digits) in full.
"""
import asyncio
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.purchase_order import PurchaseOrder

logger = logging.getLogger(__name__)


def tax_id_key(value: str | None) -> str:
    """Comparison key: letters/digits only, upper case; a 13-digit value (CNIC)
    in full, an 8-character NTN without its check digit."""
    s = re.sub(r"[^0-9A-Za-z]", "", value or "").upper()
    if s.isdigit() and len(s) == 13:
        return s
    if len(s) == 8:
        return s[:7]
    return s


def invoice_tax_id(raw: str | None) -> str:
    """The invoice's tax ID, taking a labelled NTN out of a field that bundles
    several numbers ("STRN # 3277876177886, NTN # 5433744-3")."""
    from app.services.fbr_verification import extract_ntn
    raw = (raw or "").strip()
    return extract_ntn(raw) or raw


def tax_numbers_json(numbers) -> str | None:
    vals = [str(n).strip() for n in (numbers or []) if str(n or "").strip()]
    return json.dumps(vals) if vals else json.dumps([])


def compare(invoice_ntn: str | None, sap_numbers: list[str]) -> str:
    """'match' | 'mismatch' | 'unknown' (one side has no tax number).

    Any invoice value that is not one of SAP's numbers is a mismatch, also a
    short or mistyped one ("13288" for "1328862-8")."""
    inv = tax_id_key(invoice_tax_id(invoice_ntn))
    keys = {tax_id_key(n) for n in sap_numbers if tax_id_key(n)}
    if not inv or not keys:
        return "unknown"
    return "match" if inv in keys else "mismatch"


async def _backfill(po: PurchaseOrder) -> None:
    """Read the PO vendor's tax numbers from SAP once. The caller commits."""
    if not settings.SAP_ENABLED or po.source_type != "sap" or not (po.sap_vendor_number or "").strip():
        return
    try:
        from app.routers.sap import _ensure_dll
        from app.services.sap_po_service import _fetch_vendor_master, _get_connector
        _ensure_dll()

        def _read():
            sap = _get_connector()
            sap.connect()
            try:
                return _fetch_vendor_master(sap, [po.sap_vendor_number.strip()])
            finally:
                sap.disconnect()

        vendors = await asyncio.to_thread(_read)
    except Exception:
        logger.warning("Vendor tax numbers (LFA1 STCD1-3) read failed for PO %s", po.po_number, exc_info=True)
        return
    vendor = (vendors or {}).get(po.sap_vendor_number.strip())
    if vendor is None:
        return
    po.vendor_tax_numbers = tax_numbers_json(vendor.get("tax_numbers"))
    if not (po.vendor_ntn or "").strip() and vendor.get("ntn"):
        po.vendor_ntn = vendor["ntn"]


async def vendor_ntn_check(db: AsyncSession, invoice) -> dict | None:
    """None when the invoice is not matched to a PO; otherwise
    {status, invoice_ntn, sap_tax_numbers, vendor_number, vendor_name, po_number}."""
    if not invoice.matched_po_id:
        return None
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == invoice.matched_po_id))).scalar_one_or_none()
    if po is None:
        return None
    if po.vendor_tax_numbers is None:
        await _backfill(po)
        if po.vendor_tax_numbers is not None:
            await db.commit()
    try:
        numbers = json.loads(po.vendor_tax_numbers) if po.vendor_tax_numbers else []
    except (TypeError, ValueError):
        numbers = []
    if not numbers and (po.vendor_ntn or "").strip():
        numbers = [po.vendor_ntn.strip()]
    return {
        "status": compare(invoice.supplier_ntn, numbers),
        "invoice_ntn": (invoice.supplier_ntn or "").strip() or None,
        "sap_tax_numbers": numbers,
        "vendor_number": (po.sap_vendor_number or "").strip() or None,
        "vendor_name": po.vendor_name,
        "po_number": po.po_number,
    }
