"""
PO ↔ Invoice deterministic matching engine.

Supports 2-way (PO ↔ Invoice) and 3-way (PO ↔ GRN/SES ↔ Invoice) matching
with configurable tolerances for quantity and price differences.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Tokenize a description into lowercase words for similarity comparison."""
    if not text:
        return set()
    # Remove punctuation, split into words, lowercase
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if len(w) > 1}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _pct_diff(actual: float, reference: float) -> float:
    """Percentage difference: (actual - reference) / reference * 100."""
    if reference == 0:
        return 100.0 if actual != 0 else 0.0
    return ((actual - reference) / abs(reference)) * 100.0


def _closeness(a: float, b: float) -> Optional[float]:
    """1.0 when equal, trending to 0 as they diverge. None if either is
    missing/zero (so the caller can ignore an unavailable signal)."""
    if a and b and a > 0 and b > 0:
        return 1.0 - min(abs(a - b) / max(a, b), 1.0)
    return None


def _pair_score(inv_li: dict, po_li: dict) -> tuple[float, float]:
    """Composite match score for one invoice line vs one PO line.

    Vendors name products with their own codes (e.g. "CM001-DeFOAMER") while
    the PO carries generic descriptions ("LIQUID 'CMT DEFOAMER"), so word
    overlap alone misses obviously-matching lines. We therefore combine
    description similarity with quantity/price/amount closeness — a line whose
    numbers line up (same qty x price = amount) is a strong match regardless of
    naming. Returns (composite_score, description_similarity)."""
    desc_sim = _jaccard_similarity(
        _tokenize(inv_li.get("description", "")),
        _tokenize(po_li.get("description", "")),
    )
    qty_c = _closeness(float(inv_li.get("quantity", 0) or 0), float(po_li.get("quantity", 0) or 0))
    price_c = _closeness(float(inv_li.get("unit_price", 0) or 0), float(po_li.get("unit_price", 0) or 0))
    amt_c = _closeness(float(inv_li.get("amount", 0) or 0), float(po_li.get("amount", 0) or 0))

    # Weighted mean of the numeric signals that are actually available.
    parts = [(qty_c, 0.4), (price_c, 0.4), (amt_c, 0.2)]
    avail = [(v, w) for v, w in parts if v is not None]
    numeric = (sum(v * w for v, w in avail) / sum(w for _, w in avail)) if avail else 0.0

    score = 0.35 * desc_sim + 0.65 * numeric
    return score, desc_sim


def match_invoice_to_po(
    invoice_line_items: list[dict],
    po_line_items: list[dict],
    grn_data: Optional[list[dict]] = None,
    ses_data: Optional[list[dict]] = None,
    quantity_tolerance_pct: float = 5.0,
    price_tolerance_pct: float = 2.0,
    match_type: str = "2-way",
) -> dict:
    """
    Match invoice line items against PO line items.

    Parameters
    ----------
    invoice_line_items : list[dict]
        Each: {id, description, quantity, unit_price, amount}
    po_line_items : list[dict]
        Each: {id, item_number, description, quantity, unit_price, amount}
    grn_data : list[dict] | None
        Aggregated GRN data: [{po_line_item_id, total_received_qty}]
    ses_data : list[dict] | None
        Aggregated SES data: [{po_line_item_id, total_completed_qty}]
    quantity_tolerance_pct : float
        Allowed quantity difference percentage (default 5%)
    price_tolerance_pct : float
        Allowed price difference percentage (default 2%)
    match_type : str
        "2-way" (PO ↔ Invoice) or "3-way" (PO ↔ GRN/SES ↔ Invoice)

    Returns
    -------
    dict with match_status, overall_score, line_matches, etc.
    """
    if not invoice_line_items or not po_line_items:
        return {
            "match_status": "unmatched",
            "match_type": match_type,
            "overall_score": 0.0,
            "total_amount_diff": None,
            "total_amount_diff_pct": None,
            "line_matches": [],
        }

    # Build GRN/SES lookup: po_line_item_id → total received/completed
    grn_lookup = {}
    if grn_data:
        for g in grn_data:
            pid = g["po_line_item_id"]
            grn_lookup[pid] = grn_lookup.get(pid, 0) + g.get("total_received_qty", 0)

    ses_lookup = {}
    if ses_data:
        for s in ses_data:
            pid = s["po_line_item_id"]
            ses_lookup[pid] = ses_lookup.get(pid, 0) + s.get("total_completed_qty", 0)

    # Tokenize PO line descriptions for similarity matching
    po_tokens = [(po_li, _tokenize(po_li.get("description", ""))) for po_li in po_line_items]

    # Track which PO lines have been matched (prevent double-matching)
    matched_po_ids = set()

    line_matches = []
    matched_count = 0
    full_match_count = 0
    partial_match_count = 0
    mismatch_count = 0

    # ── Step 1: Pair each invoice line to the best PO line ──────

    for inv_li in invoice_line_items:
        inv_qty = float(inv_li.get("quantity", 0) or 0)
        inv_price = float(inv_li.get("unit_price", 0) or 0)
        inv_amount = float(inv_li.get("amount", 0) or 0)

        best_po = None
        best_score = -1.0
        best_desc = 0.0

        for po_li, _po_tok in po_tokens:
            if po_li["id"] in matched_po_ids:
                continue

            score, desc_sim = _pair_score(inv_li, po_li)

            # Accept a pairing when the numbers line up well (composite score)
            # OR the descriptions clearly match — either is enough to pair the
            # lines; tolerance checks below then decide full/partial/mismatch.
            if (score >= 0.45 or desc_sim >= 0.35) and score > best_score:
                best_score = score
                best_desc = desc_sim
                best_po = po_li

        if best_po is None:
            # Unmatched invoice line
            line_matches.append({
                "invoice_line_item_id": inv_li["id"],
                "po_line_item_id": None,
                "match_status": "unmatched",
                "quantity_match": 0,
                "price_match": 0,
                "quantity_diff": None,
                "quantity_diff_pct": None,
                "price_diff": None,
                "price_diff_pct": None,
                "grn_received_qty": None,
                "ses_completed_qty": None,
                "reasoning": "No matching PO line item found",
            })
            continue

        matched_po_ids.add(best_po["id"])
        matched_count += 1

        po_qty = float(best_po.get("quantity", 0) or 0)
        po_price = float(best_po.get("unit_price", 0) or 0)

        # ── Step 2: Tolerance check ─────────────────────────

        qty_diff = inv_qty - po_qty
        qty_diff_pct = _pct_diff(inv_qty, po_qty)
        qty_within = abs(qty_diff_pct) <= quantity_tolerance_pct

        price_diff = inv_price - po_price
        price_diff_pct = _pct_diff(inv_price, po_price)
        price_within = abs(price_diff_pct) <= price_tolerance_pct

        # ── Step 3: 3-way check (GRN/SES) ──────────────────

        grn_qty = grn_lookup.get(best_po["id"])
        ses_qty = ses_lookup.get(best_po["id"])
        three_way_ok = True

        if match_type == "3-way":
            received_qty = (grn_qty or 0) + (ses_qty or 0)
            if received_qty > 0:
                # Invoice qty should be <= received qty
                if inv_qty > received_qty * (1 + quantity_tolerance_pct / 100):
                    three_way_ok = False
            else:
                # No GRN/SES data — can't do 3-way
                three_way_ok = False

        # ── Step 4: Determine line status ───────────────────

        if qty_within and price_within and three_way_ok:
            line_status = "full_match"
            full_match_count += 1
        elif (qty_within or price_within) and three_way_ok:
            line_status = "partial_match"
            partial_match_count += 1
        else:
            line_status = "mismatch"
            mismatch_count += 1

        # Build reasoning
        reasons = []
        inv_desc_short = (inv_li.get("description", "") or "")[:40]
        po_desc_short = (best_po.get("description", "") or "")[:40]
        reasons.append(f"Desc: '{inv_desc_short}' ~ '{po_desc_short}' (name~{best_desc:.2f}, match score {best_score:.2f})")
        reasons.append(f"Qty: {inv_qty} vs {po_qty} ({qty_diff_pct:+.1f}%) {'OK' if qty_within else 'OVER'}")
        reasons.append(f"Price: {inv_price} vs {po_price} ({price_diff_pct:+.1f}%) {'OK' if price_within else 'OVER'}")
        if match_type == "3-way":
            total_rcvd = (grn_qty or 0) + (ses_qty or 0)
            reasons.append(f"3-way: received={total_rcvd} {'OK' if three_way_ok else 'FAIL'}")

        line_matches.append({
            "invoice_line_item_id": inv_li["id"],
            "po_line_item_id": best_po["id"],
            "match_status": line_status,
            "quantity_match": 1 if qty_within else 0,
            "price_match": 1 if price_within else 0,
            "quantity_diff": round(qty_diff, 4),
            "quantity_diff_pct": round(qty_diff_pct, 2),
            "price_diff": round(price_diff, 4),
            "price_diff_pct": round(price_diff_pct, 2),
            "grn_received_qty": grn_qty,
            "ses_completed_qty": ses_qty,
            "reasoning": ". ".join(reasons),
        })

    # Add unmatched PO lines (PO lines with no invoice line paired)
    for po_li, _ in po_tokens:
        if po_li["id"] not in matched_po_ids:
            line_matches.append({
                "invoice_line_item_id": None,
                "po_line_item_id": po_li["id"],
                "match_status": "unmatched",
                "quantity_match": 0,
                "price_match": 0,
                "quantity_diff": None,
                "quantity_diff_pct": None,
                "price_diff": None,
                "price_diff_pct": None,
                "grn_received_qty": grn_lookup.get(po_li["id"]),
                "ses_completed_qty": ses_lookup.get(po_li["id"]),
                "reasoning": "PO line not matched to any invoice line",
            })

    # ── Step 5: Overall status ──────────────────────────────

    total_lines = len(invoice_line_items)
    if total_lines == 0:
        overall_status = "unmatched"
        overall_score = 0.0
    elif full_match_count == total_lines:
        overall_status = "full_match"
        overall_score = 1.0
    elif matched_count == 0:
        overall_status = "unmatched"
        overall_score = 0.0
    elif mismatch_count > 0:
        overall_status = "mismatch"
        overall_score = full_match_count / total_lines
    else:
        overall_status = "partial_match"
        overall_score = (full_match_count + partial_match_count * 0.5) / total_lines

    # Total amount comparison
    inv_total = sum(float(li.get("amount", 0) or 0) for li in invoice_line_items)
    po_total = sum(float(li.get("amount", 0) or 0) for li in po_line_items)
    total_diff = inv_total - po_total
    total_diff_pct = _pct_diff(inv_total, po_total) if po_total else None

    return {
        "match_status": overall_status,
        "match_type": match_type,
        "overall_score": round(overall_score, 4),
        "total_amount_diff": round(total_diff, 2),
        "total_amount_diff_pct": round(total_diff_pct, 2) if total_diff_pct is not None else None,
        "line_matches": line_matches,
    }
