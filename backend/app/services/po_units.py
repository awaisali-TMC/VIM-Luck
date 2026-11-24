"""Lucky Cement (observation B): the invoice line's unit of measure comes from the
PO as ME23N shows it, i.e. OPU (EKPO-BPRME, the order price unit), falling back to
the order unit (EKPO-MEINS). Only an EMPTY invoice unit is filled.

Display side only: parking sends PO_UNIT = EKPO-MEINS, read live from SAP.
"""
import asyncio
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.purchase_order import POMatchResult, PurchaseOrder

logger = logging.getLogger(__name__)


def po_line_unit(po_li) -> str:
    return ((po_li.price_unit or "").strip() or (po_li.unit or "").strip())


async def backfill_price_units(po: PurchaseOrder) -> None:
    """POs synced before price_unit existed: read it from SAP once. Best effort,
    a failure leaves the order unit in use. The caller commits."""
    if not settings.SAP_ENABLED or po.source_type != "sap" or all(li.price_unit for li in po.line_items):
        return
    try:
        from app.routers.sap import _ensure_dll
        from app.services.sap_po_service import fetch_po_detail
        _ensure_dll()
        detail = await asyncio.to_thread(fetch_po_detail, po.po_number)
    except Exception:
        logger.warning("Order price unit (EKPO-BPRME) read failed for PO %s", po.po_number, exc_info=True)
        return
    units = {li["item_number"]: li["price_unit"] for li in (detail or {}).get("line_items", [])}
    for li in po.line_items:
        if not li.price_unit and units.get(li.item_number):
            li.price_unit = units[li.item_number]


async def missing_line_units(db: AsyncSession, invoice, use_reference: bool) -> dict[int, str]:
    """{invoice line id: unit} for the lines that have no unit of their own.

    Matched PO: through the saved line pairing. Not matched yet (use_reference):
    the PO number printed on the invoice, if that PO is already in VIM and all
    its items share one unit, so no pairing is needed to know it."""
    empty = [li for li in invoice.line_items if not (li.unit or "").strip()]
    if not empty:
        return {}
    q = select(PurchaseOrder).options(selectinload(PurchaseOrder.line_items))
    if invoice.matched_po_id:
        po = (await db.execute(q.where(PurchaseOrder.id == invoice.matched_po_id))).scalar_one_or_none()
        if not po:
            return {}
        mr = (await db.execute(
            select(POMatchResult).options(selectinload(POMatchResult.line_matches))
            .where(POMatchResult.invoice_id == invoice.id, POMatchResult.po_id == po.id)
            .order_by(POMatchResult.created_at.desc(), POMatchResult.id.desc())
        )).scalars().first()
        if mr is None:
            units = {po_line_unit(li) for li in po.line_items}
            unit = units.pop() if len(units) == 1 else ""
            return {li.id: unit for li in empty} if unit else {}
        by_id = {li.id: li for li in po.line_items}
        pairs = {m.invoice_line_item_id: by_id.get(m.po_line_item_id)
                 for m in mr.line_matches if m.invoice_line_item_id}
        return {li.id: po_line_unit(pairs[li.id]) for li in empty
                if pairs.get(li.id) is not None and po_line_unit(pairs[li.id])}
    ref = (invoice.po_reference or "").strip()
    if not use_reference or not ref:
        return {}
    numbers = set(re.findall(r"(?<!\d)\d{10}(?!\d)", ref)) or {ref}
    pos = (await db.execute(q.where(PurchaseOrder.po_number.in_(numbers)))).scalars().all()
    units = {po_line_unit(li) for po in pos for li in po.line_items}
    if len(units) != 1 or not (unit := units.pop()):
        return {}
    return {li.id: unit for li in empty}
