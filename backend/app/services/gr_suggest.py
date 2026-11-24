"""Lucky Cement (observation F): which goods receipts to tick by default.

A supplier's invoice names its PO and a total quantity, not its GRs. When ALL the
open GRs of a PO item add up to exactly what the invoice bills for that item, there
is nothing to choose, so the card ticks them. When the upload carries a GRN
summary, its SRNs are the choice instead, under the same condition. Anything else is
left to the user.
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice
from app.models.purchase_order import POMatchResult, PurchaseOrder
from app.services.invoice_line_rules import route_invoice_lines
from app.services.srn_list import listed_numbers
from app.services.srn_list import listed_numbers


async def billed_by_po_item(db: AsyncSession, invoice: Invoice, po: PurchaseOrder) -> dict[int, float]:
    """{PO item: quantity billed}, mapped to PO items the way parking does it."""
    item_no = {li.id: li.item_number for li in po.line_items}
    mr = (await db.execute(
        select(POMatchResult).options(selectinload(POMatchResult.line_matches))
        .where(POMatchResult.invoice_id == invoice.id, POMatchResult.po_id == po.id)
        .order_by(POMatchResult.created_at.desc(), POMatchResult.id.desc())
    )).scalars().first()
    pairs = {m.invoice_line_item_id: item_no[m.po_line_item_id]
             for m in (mr.line_matches if mr else [])
             if m.invoice_line_item_id and item_no.get(m.po_line_item_id) is not None}
    selected = set(json.loads(invoice.parking_line_item_ids)) if invoice.parking_line_item_ids else None
    single = po.line_items[0].item_number if len(po.line_items) == 1 else None
    routed, _ = route_invoice_lines(invoice.line_items, selected or None, pairs, single)
    billed: dict[int, float] = {}
    for li in invoice.line_items:
        if li.id in routed:
            billed[routed[li.id]] = billed.get(routed[li.id], 0.0) + float(li.quantity or 0)
    return billed


async def grs_on_other_invoices(db: AsyncSession, invoice: Invoice) -> set[str]:
    """GRs ticked on another live GOODS invoice of the same PO that is not posted yet
    (a posted one already reduces the GR's open quantity in SAP). A freight-only
    invoice (layout "delivery") bills no goods."""
    rows = (await db.execute(
        select(Invoice.parking_gr_refs).where(
            Invoice.matched_po_id == invoice.matched_po_id, Invoice.id != invoice.id,
            Invoice.is_deleted == 0, Invoice.parking_gr_refs.is_not(None),
            Invoice.status.notin_(("posted", "exception")),
            Invoice.sap_layout.is_distinct_from("delivery"))
    )).scalars().all()
    return {k for r in rows for k in json.loads(r)}


async def freight_on_other_invoices(db: AsyncSession, invoice: Invoice) -> dict[tuple, dict]:
    """{(po_item, cond_type, gr_key): {id, invoice_number}}: freight another live
    invoice of the same PO bills, posted ones included, because SAP's freight
    history does not say which GR an invoice covered. An invoice with goods and
    freight bills the freight of the GRs it ticked."""
    rows = (await db.execute(
        select(Invoice).where(
            Invoice.matched_po_id == invoice.matched_po_id, Invoice.id != invoice.id,
            Invoice.is_deleted == 0, Invoice.sap_delivery.is_not(None),
            Invoice.sap_layout.in_(("delivery", "both")), Invoice.status != "exception")
    )).scalars().all()
    out: dict[tuple, dict] = {}
    for inv in rows:
        goods = json.loads(inv.parking_gr_refs) if inv.parking_gr_refs and inv.sap_layout == "both" else []
        for c in json.loads(inv.sap_delivery):
            for k in (c.get("gr_keys") if inv.sap_layout == "delivery" else goods) or []:
                out[(c["po_item"], c["cond_type"], k)] = {"id": inv.id, "invoice_number": inv.invoice_number}
    return out


def _doc(number) -> str:
    return str(number or "").strip().lstrip("0")


def matching_grs(billed: dict[int, float], open_grs: list[dict], taken: set[str], own_doc: str | None,
                 receipts: list[dict] | None = None) -> list[str]:
    """gr_keys of every open GR of each billed PO item whose open quantities add up
    to the billed quantity, unless one of them is already used by another invoice
    (`taken` in VIM, or parked in SAP under a document other than `own_doc`).
    With `receipts` (the GRN summary) only the listed ones are candidates."""
    by_item: dict[int, list[dict]] = {}
    for g in open_grs:
        if receipts and not listed_numbers(receipts, g):
            continue
        by_item.setdefault(g["po_item"], []).append(g)

    def used(g):
        if g["gr_key"] in taken:
            return True
        return g["parked"] > 0 and any(_doc(d) != _doc(own_doc) for d in g["parked_docs"])

    keys: list[str] = []
    for item, qty in billed.items():
        grs = by_item.get(item, [])
        if not grs or qty <= 0 or any(used(g) for g in grs):
            continue
        if abs(round(sum(g["open_qty"] for g in grs), 3) - round(qty, 3)) <= 0.001:
            keys.extend(g["gr_key"] for g in grs)
    return keys


async def suggest_grs(db: AsyncSession, invoice: Invoice, po: PurchaseOrder, open_grs: list[dict]) -> list[str]:
    """What the card ticks. Nothing once the invoice is in SAP, unless SAP's
    workflow rejected it (then it is corrected and resubmitted)."""
    rejected = (invoice.sap_wf_status or "").upper() == "REJ" and invoice.sap_doc_status != "posted"
    if invoice.sap_document_number and not rejected:
        return []
    return matching_grs(await billed_by_po_item(db, invoice, po), open_grs,
                        await grs_on_other_invoices(db, invoice), invoice.sap_document_number,
                        json.loads(invoice.srn_list) if invoice.srn_list else None)
