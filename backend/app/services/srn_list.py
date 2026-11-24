"""Goods receipts (Lucky: SRNs) the client lists on a summary page attached to the
invoice, as read by the AI from the scanned PDF.

They only ever choose among the receipts SAP really has: a number SAP does not
know is reported, never sent, and the quantities are checked against SAP's.
"""
import re

MAX_RECEIPTS = 200


def _num(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


def clean_receipts(raw) -> list[dict]:
    """[{number, po_number, quantity, amount, freight}] from AI output or from the
    client. SAP material documents are 10 digits; anything else is dropped."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        number = re.sub(r"\D", "", str(r.get("number") or ""))
        if len(number) != 10:
            continue
        if number in seen:          # one row per PO item: its figures are not the document's
            first = next(x for x in out if x["number"] == number)
            for f in ("quantity", "amount", "freight"):
                if _num(r.get(f)) is not None and first[f] != _num(r.get(f)):
                    first[f] = None
            continue
        seen.add(number)
        po = re.sub(r"\D", "", str(r.get("po_number") or ""))
        out.append({"number": number, "po_number": po if len(po) == 10 else None,
                    "quantity": _num(r.get("quantity")), "amount": _num(r.get("amount")),
                    "freight": _num(r.get("freight"))})
        if len(out) >= MAX_RECEIPTS:
            break
    return out


def share_receipts(per_invoice: list[tuple[str | None, list[dict]]], whole_file: list[dict]) -> list[list[dict]]:
    """Receipts for each invoice split out of one file. The summary page ends up in
    only one of the parts, but it belongs to all of them (goods and freight): an
    invoice without its own list gets the file's, minus receipts of another PO."""
    union = {r["number"]: r for r in whole_file}
    for _po, own in per_invoice:
        for r in own:
            union.setdefault(r["number"], r)
    out = []
    for po_ref, own in per_invoice:
        if own:
            out.append(own)
            continue
        ref = re.sub(r"\D", "", po_ref or "")
        out.append([r for r in union.values()
                    if not (r["po_number"] and len(ref) == 10 and r["po_number"] != ref)])
    return out


def listed_numbers(receipts: list[dict], gr: dict) -> list[dict]:
    """The listed receipts that are this SAP goods receipt (103/101 or its 105s)."""
    docs = {str(d).lstrip("0") for d in [gr["gr_doc"], *gr.get("srn", [])]}
    return [r for r in receipts if r["number"].lstrip("0") in docs]


def check_receipts(receipts: list[dict], open_grs: list[dict], closed_grs: list[dict]) -> list[str]:
    """What does not agree between the summary page and SAP, in words."""
    problems = []
    for r in receipts:
        # A material document can hold several PO items.
        mine = [g for g in open_grs if listed_numbers([r], g)]
        shut = [g for g in closed_grs if listed_numbers([r], g)]
        if not mine and shut:
            problems.append(f"SRN {r['number']} is not open in SAP ({shut[0]['reason']}).")
        elif not mine:
            problems.append(f"SRN {r['number']} is not on this PO in SAP (misread, or another PO).")
        elif r["quantity"] is not None:
            got = [g["received"] for g in mine]
            if all(abs(r["quantity"] - q) > 0.01 for q in [*got, sum(got)]):
                problems.append(f"SRN {r['number']}: the summary says {r['quantity']:g}, SAP received "
                                f"{' + '.join(f'{q:g}' for q in got)}.")
        elif r["amount"] is not None:       # Lucky's SRN report has no quantity column
            got = [g["amount"] for g in mine]
            if all(abs(r["amount"] - a) > 1 for a in [*got, sum(got)]):
                problems.append(f"SRN {r['number']}: the summary says {r['amount']:,.2f}, SAP has "
                                f"{' + '.join(f'{a:,.2f}' for a in got)}.")
    return problems
