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
    # Like the invoice page, ignore saved line ids that no longer exist (lines are
    # recreated by a full edit); none left = every line.
    selected = set(json.loads(invoice.parking_line_item_ids)) if invoice.parking_line_item_ids else set()
    selected &= {li.id for li in invoice.line_items}
    single = po.line_items[0].item_number if len(po.line_items) == 1 else None
    routed, _ = route_invoice_lines(invoice.line_items, selected or None, pairs, single)
    billed: dict[int, float] = {}
    for li in invoice.line_items:
        if li.id in routed:
            billed[routed[li.id]] = billed.get(routed[li.id], 0.0) + float(li.quantity or 0)
    return billed


async def grs_on_other_invoices(db: AsyncSession, invoice: Invoice) -> dict[str, str]:
    """{gr_key: "151 (#57)"}: GRs ticked on another live GOODS invoice of the same PO that is not posted yet
    (a posted one already reduces the GR's open quantity in SAP). A freight-only
    invoice (layout "delivery") bills no goods."""
    rows = (await db.execute(
        select(Invoice.id, Invoice.invoice_number, Invoice.parking_gr_refs).where(
            Invoice.matched_po_id == invoice.matched_po_id, Invoice.id != invoice.id,
            Invoice.is_deleted == 0, Invoice.parking_gr_refs.is_not(None),
            Invoice.status.notin_(("posted", "exception")),
            Invoice.sap_layout.is_distinct_from("delivery"))
    )).all()
    return {k: f"{number or ''} (#{i})".strip() for i, number, refs in rows for k in json.loads(refs)}


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


def matching_grs(billed: dict[int, float], open_grs: list[dict], taken: dict[str, str], own_doc: str | None,
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


def _net(invoice: Invoice) -> float:
    return float(invoice.subtotal_amount or 0) or max(float(invoice.total_amount or 0) - float(invoice.tax_amount or 0), 0.0)


async def sibling_choices(db: AsyncSession, invoice: Invoice) -> list[dict]:
    """What the PO's other live invoices say about goods receipts, oldest first: the
    goods invoice, the freight invoice and the GRN summary need not arrive together.
    [{invoice_number, keys (ticked), receipts (GRN summary)}]"""
    rows = (await db.execute(
        select(Invoice).where(
            Invoice.matched_po_id == invoice.matched_po_id, Invoice.id != invoice.id,
            Invoice.is_deleted == 0, Invoice.status != "exception").order_by(Invoice.id)
    )).scalars().all()
    out = []
    for inv in rows:
        if inv.sap_layout == "delivery":
            keys = {k for c in (json.loads(inv.sap_delivery) if inv.sap_delivery else []) for k in c.get("gr_keys") or []}
        else:
            keys = set(json.loads(inv.parking_gr_refs)) if inv.parking_gr_refs else set()
        receipts = json.loads(inv.srn_list) if inv.srn_list else []
        if keys or receipts:
            out.append({"invoice_number": inv.invoice_number or f"#{inv.id}", "keys": keys, "receipts": receipts})
    return out


async def choose_grs(db: AsyncSession, invoice: Invoice, billed: dict[int, float], open_grs: list[dict]) -> list[str]:
    """The goods receipts of a goods invoice: its own GRN summary; else all open ones;
    else those another invoice of the PO (its freight invoice, or the one the summary
    came with) names. Always only when they add up to the bill and are not used."""
    taken = await grs_on_other_invoices(db, invoice)
    own = json.loads(invoice.srn_list) if invoice.srn_list else None
    # The summary is optional help: one that names no open GR at all (misread,
    # wrong file) is as good as none. One that does, but disagrees, is the user's call.
    if own and not any(listed_numbers(own, g) for g in open_grs):
        own = None
    keys = matching_grs(billed, open_grs, taken, invoice.sap_document_number, own)
    if keys or own:
        return keys
    for sib in await sibling_choices(db, invoice):
        for subset in ([g for g in open_grs if g["gr_key"] in sib["keys"]],
                       [g for g in open_grs if listed_numbers(sib["receipts"], g)]):
            if subset and (keys := matching_grs(billed, subset, taken, invoice.sap_document_number)):
                return keys
    return []


async def why_not_suggested(db: AsyncSession, invoice: Invoice, po: PurchaseOrder, open_grs: list[dict]) -> str | None:
    """In words, why the card ticks nothing for an invoice it could still change."""
    if not open_grs:
        return None
    billed = await billed_by_po_item(db, invoice, po)
    if not billed:
        return "no invoice line selected for parking is matched to a PO item."
    taken = await grs_on_other_invoices(db, invoice)
    own = json.loads(invoice.srn_list) if invoice.srn_list else []
    listed = [g for g in open_grs if listed_numbers(own, g)]
    why = []
    for item, qty in billed.items():
        grs = [g for g in (listed or open_grs) if g["po_item"] == item]
        what = "the SRNs of the GRN summary" if listed else "the open receipts"
        if not grs:
            why.append(f"PO item {item} has no open receipt{' on the GRN summary' if listed else ''}.")
            continue
        others = sorted({taken[g["gr_key"]] for g in grs if g["gr_key"] in taken})
        docs = sorted({d for g in grs if g["parked"] > 0 for d in g["parked_docs"]
                       if _doc(d) != _doc(invoice.sap_document_number)})
        total = round(sum(g["open_qty"] for g in grs), 3)
        if others:
            why.append(f"PO item {item}: receipts are ticked on invoice {', '.join(others)}.")
        elif docs:
            why.append(f"PO item {item}: receipts are on parked SAP document {', '.join(docs)}.")
        elif abs(total - round(qty, 3)) > 0.001:
            why.append(f"PO item {item}: {what} add up to {total:g}, the invoice bills {qty:g}.")
    return " ".join(why) or None


async def suggest_grs(db: AsyncSession, invoice: Invoice, po: PurchaseOrder, open_grs: list[dict]) -> list[str]:
    """What the card ticks. Nothing once the invoice is in SAP, unless SAP's
    workflow rejected it (then it is corrected and resubmitted)."""
    rejected = (invoice.sap_wf_status or "").upper() == "REJ" and invoice.sap_doc_status != "posted"
    if invoice.sap_document_number and not rejected:
        return []
    return await choose_grs(db, invoice, await billed_by_po_item(db, invoice, po), open_grs)


def suggest_freight(invoice: Invoice, cost_grs: list[dict], siblings: list[dict]) -> tuple[list[str], str | None]:
    """(gr_keys, where from) for a freight-only invoice. cost_grs: the condition's
    GRs with {gr_key, amount, listed, taken_by, gr}. Its own GRN summary decides;
    otherwise the set whose freight equals the invoice (the GRs of the PO's goods
    invoices, or a summary that came with another invoice); else every free GR."""
    free = [g for g in cost_grs if not g["taken_by"]]
    listed = [g["gr_key"] for g in free if g["listed"]]
    if listed:
        return listed, "the attached GRN summary"
    net = _net(invoice)

    def equals(grs):
        return bool(grs) and net > 0 and abs(sum(g["amount"] for g in grs) - net) <= 1

    for sib in siblings:
        mine = [g for g in free if g["gr_key"] in sib["keys"]]
        if equals(mine):
            return [g["gr_key"] for g in mine], f"invoice {sib['invoice_number']}"
        mine = [g for g in free if listed_numbers(sib["receipts"], g["gr"])]
        if equals(mine):
            return [g["gr_key"] for g in mine], f"the GRN summary of invoice {sib['invoice_number']}"
    return [g["gr_key"] for g in free], "all open freight"      # as without a summary
