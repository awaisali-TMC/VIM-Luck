"""Function tools the invoice agent can call.

Each tool wraps an existing einv service so the agent reuses the same
extraction/matching logic the REST API uses today. Tools must:

  * Have type hints + Google-style docstrings — ADK introspects these
    to build the function-calling schema.
  * Return JSON-serialisable dicts.
  * Be either sync or async (`asyncio` works in ADK 1.31).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import select

from app.database import async_session
from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder, POLineItem
from app.services.gemini_extract import extract_invoice as _extract_invoice_service
from app.services.duplicate_detection import check_duplicates as _check_duplicates_service
from app.services.po_matching_engine import match_invoice_to_po as _match_engine

logger = logging.getLogger(__name__)


# ── Tool 1: extraction ────────────────────────────────────────────────────────


async def extract_invoice(file_path: str, mime_type: str = "application/pdf") -> dict:
    """Extract structured fields, line items and detected taxes from an invoice file.

    Wraps the existing Gemini extraction service. The file must already be on
    disk — usually saved by the upload router into ``uploads/``.

    Args:
        file_path: Absolute or relative path to the invoice file.
        mime_type: MIME type, typically ``application/pdf`` or ``image/png``.

    Returns:
        Dict with keys:
          ``fields`` (list of {field_name, value, confidence}),
          ``line_items`` (list of {description, quantity, unit_price, amount}),
          ``detected_taxes`` (list of {type, rate, amount}),
          ``overall_confidence`` (0–100),
          ``document_type`` (e.g. "Tax Invoice"),
          ``warnings`` (list of strings),
          ``processing_time_ms``.
    """
    try:
        with open(file_path, "rb") as f:
            content = f.read()
        result = _extract_invoice_service(content, mime_type)
        return {"ok": True, **result}
    except FileNotFoundError:
        return {"ok": False, "error": f"file not found: {file_path}"}
    except Exception as exc:
        logger.exception("extract_invoice tool failed")
        return {"ok": False, "error": str(exc)}


# ── Tool 2: total validation ──────────────────────────────────────────────────


def validate_totals(
    line_items_json: str,
    total_amount: float,
    tax_amount: float = 0.0,
    tolerance_pct: float = 1.0,
) -> dict:
    """Sanity-check that line item amounts sum to the invoice total.

    Args:
        line_items_json: JSON string of the line items array (each with "amount").
        total_amount: Reported invoice grand total.
        tax_amount: Reported total tax amount (subtracted before comparison).
        tolerance_pct: Allowed mismatch as a percentage of total_amount.

    Returns:
        ``{"ok": True/False, "computed_subtotal": float, "expected_subtotal":
        float, "diff": float, "within_tolerance": bool}``.
    """
    try:
        line_items = json.loads(line_items_json) if line_items_json else []
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid line_items_json"}
    computed = sum(float(li.get("amount") or 0) for li in line_items or [])
    expected = float(total_amount or 0) - float(tax_amount or 0)
    diff = computed - expected
    threshold = abs(float(total_amount or 0)) * (tolerance_pct / 100.0)
    return {
        "ok": True,
        "computed_subtotal": round(computed, 2),
        "expected_subtotal": round(expected, 2),
        "diff": round(diff, 2),
        "within_tolerance": abs(diff) <= max(threshold, 0.5),
        "tolerance_pct": tolerance_pct,
    }


# ── Tool 3: duplicate detection ───────────────────────────────────────────────


async def find_duplicate_invoices(
    invoice_number: Optional[str] = None,
    supplier_name: Optional[str] = None,
    supplier_ntn: Optional[str] = None,
    total_amount: Optional[float] = None,
    invoice_date: Optional[str] = None,
) -> dict:
    """Search the local database for possible duplicate invoices.

    Uses three strategies in order:
      1. Exact: same invoice_number + supplier_ntn.
      2. Fuzzy: same supplier + close amount + close dates.
      3. Hash: same amount + date + supplier name.

    Args:
        invoice_number: Vendor's invoice reference.
        supplier_name: Supplier name as extracted.
        supplier_ntn: Supplier tax registration number.
        total_amount: Invoice grand total.
        invoice_date: Invoice date as ISO string (YYYY-MM-DD).

    Returns:
        ``{"ok": True, "match_count": int, "matches": [{id, invoice_number,
        match_type, similarity, ...}]}``.
    """
    async with async_session() as db:
        result = await _check_duplicates_service(
            db,
            invoice_number=invoice_number,
            supplier_ntn=supplier_ntn,
            supplier_name=supplier_name,
            total_amount=total_amount,
            invoice_date=invoice_date,
        )
    matches = result.get("duplicates", []) if isinstance(result, dict) else []
    return {
        "ok": True,
        "match_count": len(matches),
        "matches": matches[:5],  # cap to keep agent context small
    }


# ── Tool 4: PO matching ───────────────────────────────────────────────────────


async def match_to_purchase_order(
    po_reference: Optional[str] = None,
    supplier_name: Optional[str] = None,
    invoice_line_items_json: Optional[str] = None,
) -> dict:
    """Find a matching Purchase Order in the local DB and run line-item match.

    Args:
        po_reference: PO number extracted from the invoice (preferred lookup key).
        supplier_name: Fallback — match by exact supplier name if PO ref absent.
        invoice_line_items_json: JSON string of [{description, quantity,
            unit_price, amount}, ...].

    Returns:
        ``{"ok": True, "po_id": int|None, "po_number": str|None,
        "vendor_name": str|None, "match_summary": {matched, partial, unmatched,
        match_score}}`` — or ``{"ok": False, "reason": "..."}`` if no PO found.
    """
    if not po_reference and not supplier_name:
        return {"ok": False, "reason": "no PO reference and no supplier_name provided"}

    async with async_session() as db:
        po = None
        if po_reference:
            res = await db.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.po_number == po_reference.strip()
                )
            )
            po = res.scalar_one_or_none()

        if po is None and supplier_name:
            res = await db.execute(
                select(PurchaseOrder)
                .where(PurchaseOrder.vendor_name.ilike(f"%{supplier_name.strip()}%"))
                .order_by(PurchaseOrder.po_date.desc())
                .limit(1)
            )
            po = res.scalar_one_or_none()

        if po is None:
            return {"ok": False, "reason": f"no PO found for ref={po_reference!r}"}

        li_res = await db.execute(
            select(POLineItem).where(POLineItem.po_id == po.id)
        )
        po_line_items = [
            {
                "id": li.id,
                "item_number": li.item_number,
                "description": li.description,
                "quantity": float(li.quantity or 0),
                "unit_price": float(li.unit_price or 0),
                "amount": float(li.amount or 0),
            }
            for li in li_res.scalars().all()
        ]

    try:
        inv_li = json.loads(invoice_line_items_json) if invoice_line_items_json else []
    except json.JSONDecodeError:
        inv_li = []
    # Synthesise IDs / numeric fields the matching engine requires
    for idx, li in enumerate(inv_li):
        li.setdefault("id", idx + 1)
        for k in ("quantity", "unit_price", "amount"):
            try:
                li[k] = float(li.get(k) or 0)
            except (ValueError, TypeError):
                li[k] = 0.0
    match = _match_engine(
        invoice_line_items=inv_li,
        po_line_items=po_line_items,
        match_type="2-way",
    )
    return {
        "ok": True,
        "po_id": po.id,
        "po_number": po.po_number,
        "vendor_name": po.vendor_name,
        "po_total": float(po.total_amount or 0),
        "po_currency": po.currency,
        "match_summary": {
            "matched": len(match.get("matched", [])),
            "partial": len(match.get("partial", [])),
            "unmatched": len(match.get("unmatched", [])),
            "match_score": match.get("match_score"),
        },
    }


# ── Tool 5: persist (optional — used after agent decides ACCEPT) ──────────────


async def persist_invoice(
    extracted_json: str,
    file_path: str,
    decision: str,
) -> dict:
    """Save the extracted invoice + agent decision into the local DB.

    Only call this after the agent has decided ACCEPT or FLAG. Sets the
    invoice ``status`` to ``validated`` (ACCEPT) or ``pending_approval`` (FLAG).

    Args:
        extracted_json: JSON string of the dict returned by ``extract_invoice``.
        file_path: Path of the original uploaded file.
        decision: "ACCEPT" or "FLAG".

    Returns:
        ``{"ok": True, "invoice_id": int}``.
    """
    try:
        extracted = json.loads(extracted_json)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid extracted_json"}
    fields = {f["field_name"]: f["value"] for f in extracted.get("fields", [])}

    def _safe_float(v):
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    status = "validated" if decision == "ACCEPT" else "pending_approval"

    async with async_session() as db:
        invoice = Invoice(
            original_filename=file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            stored_filepath=file_path,
            invoice_number=fields.get("invoice_id"),
            invoice_date=fields.get("invoice_date"),
            due_date=fields.get("due_date"),
            currency=fields.get("currency") or "PKR",
            supplier_name=fields.get("supplier_name"),
            supplier_address=fields.get("supplier_address"),
            supplier_ntn=fields.get("supplier_tax_id"),
            receiver_name=fields.get("receiver_name"),
            receiver_address=fields.get("receiver_address"),
            total_amount=_safe_float(fields.get("total_amount")),
            subtotal_amount=_safe_float(fields.get("net_amount")),
            tax_amount=_safe_float(fields.get("total_tax_amount")),
            po_reference=fields.get("purchase_order"),
            overall_confidence=extracted.get("overall_confidence"),
            status=status,
            document_type=extracted.get("document_type"),
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)
        return {"ok": True, "invoice_id": invoice.id, "status": status}
