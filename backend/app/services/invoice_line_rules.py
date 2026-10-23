"""PO lane — line-level checks on the items about to be sent to SAP.

Pure functions: every input is passed in, nothing is fetched here, so the rules
are unit-testable on a machine with no SAP SDK. The router decides what to load
and what status code to raise.

Why this exists: a line item whose quantity is NULL (see the frontend guard in
LineItemsTable.jsx, and the API guards in routers/invoices.py) used to reach the
BAPI as a quantity of ZERO, because the value is defaulted twice on the way:

    routers/sap.py            float(inv_line.quantity or 0)      None -> 0
    services/sap_invoice_post  str(li.get("quantity", 0))        missing -> 0

The result is a well-formed invoice line billing a real amount for zero units.
SAP would most likely reject it, but the app should not be building it.
"""

from typing import Iterable, Optional


def find_zero_quantity_goods(
    agg_rows: dict,
    service_po_items: Iterable,
    line_ids_by_po_item: Optional[dict] = None,
) -> list[dict]:
    """PO items billing a non-zero amount with no usable quantity.

    agg_rows             {po_item: {"amount": float, "quantity": float, ...}} —
                         the aggregation built in routers/sap.py.
    service_po_items     PO items confirmed via a Service Entry Sheet. EXEMPT:
                         service lines are value-based and SAP rejects QUANTITY
                         on them ("Quantities and units of measure … not
                         permitted" — see sap_invoice_post.py:195).
    line_ids_by_po_item  optional {po_item: [invoice_line_id, ...]} so the caller
                         can tell the user which line to fix, not just which PO
                         item.

    Returns one dict per offending PO item; empty list means nothing to report.
    A zero amount is NOT an offence — an empty line is not the same as a broken
    one.
    """
    services = set(service_po_items or ())
    offenders = []

    for po_item, row in sorted((agg_rows or {}).items()):
        if po_item in services:
            continue
        amount = row.get("amount")
        quantity = row.get("quantity")
        if not amount:                       # 0, 0.0 or None — nothing billed
            continue
        if quantity is None or float(quantity) <= 0:
            offenders.append({
                "po_item": po_item,
                "amount": float(amount),
                "quantity": quantity,
                "line_item_ids": sorted((line_ids_by_po_item or {}).get(po_item, [])),
            })

    return offenders


def zero_quantity_message(offenders: list[dict]) -> str:
    """A one-line, fixable description of what `find_zero_quantity_goods` found."""
    parts = []
    for o in offenders:
        ids = o.get("line_item_ids") or []
        where = f"line item{'s' if len(ids) > 1 else ''} {', '.join(str(i) for i in ids)}" if ids \
            else f"PO item {o['po_item']}"
        parts.append(f"{where} bills {o['amount']} with no quantity")
    return (
        "Cannot send to SAP: " + "; ".join(parts) +
        ". Set a quantity on each line, or remove the line."
    )


def route_invoice_lines(
    lines: Iterable,
    selected_ids: Optional[set],
    inv_to_po_item: dict,
    single_po_item,
):
    """Decide which PO item each selected invoice line is parked against.

    lines            the invoice's line items, in screen order (objects with
                     .id, .description and .amount).
    selected_ids     ids chosen for parking; None means every line.
    inv_to_po_item   {invoice_line_id: po_item} from the saved PO match.
    single_po_item   the item number when the PO has exactly one line, else None.

    A line is routed by (1) its saved match, else (2) the PO's only item. Nothing
    else: a line is never guessed onto another PO item by position, because that
    can park it against an item a matched line already covers, or against the
    wrong item entirely. The park payload has no row type for a line without a PO
    item (the Non-PO lane is gone), so such a line is reported, not dropped.

    Returns (routed, unrouted): routed is {invoice_line_id: po_item}; unrouted is
    one dict per selected line with no PO item, with its 1-based screen position.
    """
    routed: dict = {}
    unrouted: list[dict] = []
    for position, line in enumerate(lines, start=1):
        if selected_ids is not None and line.id not in selected_ids:
            continue
        po_item = inv_to_po_item.get(line.id)
        if po_item is None:
            po_item = single_po_item
        if po_item is None:
            unrouted.append({
                "line_item_id": line.id,
                "position": position,
                "description": (getattr(line, "description", None) or "").strip(),
                "amount": float(getattr(line, "amount", None) or 0),
            })
        else:
            routed[line.id] = po_item
    return routed, unrouted


def unrouted_lines_message(unrouted: list[dict], po_number: str, matching_missing: bool = False) -> str:
    """A fixable, one-paragraph description of what `route_invoice_lines` refused."""
    if matching_missing:
        return (
            f"Cannot send to SAP: the invoice lines have not been matched to the items of "
            f"PO {po_number}. Run PO matching, then try again."
        )
    shown = []
    for u in unrouted[:5]:
        desc = u["description"]
        if len(desc) > 60:
            desc = desc[:57] + "..."
        label = f'line {u["position"]} "{desc}"' if desc else f'line {u["position"]}'
        shown.append(f'{label} ({u["amount"]:,.2f})')
    more = f" and {len(unrouted) - 5} more" if len(unrouted) > 5 else ""
    verb = "is" if len(unrouted) == 1 and not more else "are"
    return (
        f"Cannot send to SAP: {'; '.join(shown)}{more} {verb} not on PO {po_number}. "
        "Lines are never guessed onto another PO item or dropped. "
        "Uncheck or delete the line, then try again."
    )
