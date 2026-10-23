"""
Unified Gemini extraction service.

Replaces the 3-step pipeline (Document AI → Gemini tax → Gemini line items)
with a single Gemini call (model: settings.GEMINI_MODEL) that extracts fields, line items, and taxes
all at once from the invoice image/PDF.
"""

import json
import logging
import re
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_LABELS = {
    "invoice_statement": "Invoice Statement",
    "invoice_receipt": "Invoice / Receipt",
    "invoice": "Tax Invoice",
    "credit_note": "Credit Note",
    "debit_note": "Debit Note",
    "purchase_order": "Purchase Order",
    "remittance_advice": "Remittance Advice",
    "utility_bill": "Utility Bill",
    "statement": "Statement",
    "expense_report": "Expense Report",
    "receipt": "Receipt",
}

EXTRACTION_PROMPT = """You are an expert accounts payable specialist. Extract ALL information from this invoice document in a single pass.

## FIELDS TO EXTRACT
Extract these header fields. Use null if not found:
- invoice_id: Invoice number / reference
- invoice_date: Invoice date (return as-is from document)
- due_date: Payment due date (return as-is from document)
- supplier_name: Vendor / supplier name
- supplier_address: Vendor address
- supplier_tax_id: Vendor NTN / tax registration number
- receiver_name: Buyer / receiver name
- receiver_address: Buyer address
- total_amount: Grand total / amount due
- net_amount: Subtotal before tax
- total_tax_amount: Total tax amount
- currency: Currency code (PKR, USD, EUR, etc.) — default "PKR" if not shown
- purchase_order: PO reference number
- remit_to_address: Bank details / IBAN
- invoice_type: One of: invoice, credit_note, debit_note, purchase_order, utility_bill, receipt, expense_report, statement, remittance_advice, invoice_statement, invoice_receipt

## LINE ITEMS
Extract EVERY billable line item / service / product:
- Do NOT include tax rows (GST, WHT, Sales Tax, etc.)
- Do NOT include summary rows (Subtotal, Grand Total)
- description must never be empty
- Remove currency symbols from numbers

## TAX DETECTION (Pakistan-specific)
Identify ALL tax types and amounts:
- GST (General Sales Tax) — typically 18%
- WHT (Withholding Tax) — varies 1%-15%
- FED (Federal Excise Duty)
- SED (Special Excise Duty)
- PRA (Punjab Revenue Authority)
- SRB (Sindh Revenue Board)
- KPRA (KP Revenue Authority)
- BRA (Balochistan Revenue Authority)
- Customs Duty
- Any other taxes visible

## ATTENTION FLAGS (anomalies / inconsistencies)
Inspect the document carefully and report ANYTHING that a human reviewer should double-check.
Be specific and quote the values you saw. Look for:
- CURRENCY INCONSISTENCY: amounts shown in one currency but labelled another, or more than one
  currency on the same invoice (e.g. line amounts in USD but column header / subtotal says PKR,
  or a "USD x.xx @ rate" conversion line). This is HIGH severity.
- REVISED / DUPLICATE / DRAFT markings: words like "REVISED", "v2/v3", "COPY", "DUPLICATE",
  "PROFORMA", "DRAFT", "carbon copy".
- TAX JURISDICTION MISMATCH: provincial sales tax billed for the wrong province (e.g. SRB/Sindh
  tax on a Punjab supply), or both FBR + provincial GST on the same line.
- UNREGISTERED / NON-FILER vendor, missing NTN/STRN, or "kacha bill" / informal receipt.
- HANDWRITTEN or low-legibility document, or values that look uncertain.
- MISSING or unclear critical fields (invoice number, date, total, supplier).
- MATH that does not add up (line items vs subtotal vs total vs taxes).

For each issue add one object to "attention_flags" with:
  severity: "high" | "medium" | "low"
  category: "currency" | "document" | "tax" | "missing_field" | "math" | "confidence"
  title: short label (e.g. "Currency mismatch")
  message: one clear sentence explaining what to check, quoting the values you saw.
If nothing is wrong, return an empty list.

## MULTIPLE-INVOICE CHECK
This system processes ONE invoice per upload. Decide whether this file contains more than one
DISTINCT invoice — i.e. separate invoices with different invoice numbers / separate invoice
headers (a single invoice that simply spans multiple pages is NOT multiple invoices). Report:
- invoice_count: number of distinct invoices you can identify (1 for a normal single invoice)
- multiple_invoices: true only when invoice_count is 2 or more
- invoice_page_ranges: when multiple_invoices is true, the 1-based page span of EACH distinct
  invoice as [start_page, end_page] pairs in document order, e.g. [[1,2],[3,3],[4,6]]. Every
  page belongs to exactly one range. Omit (or []) for a single invoice.
If multiple invoices are present, still extract the FIRST invoice's fields/line items as usual.

Respond ONLY with valid JSON:
{
  "fields": {
    "invoice_id": "INV-001",
    "invoice_date": "2026-01-15",
    "due_date": "2026-02-15",
    "supplier_name": "Vendor Co",
    "supplier_address": "123 Street",
    "supplier_tax_id": "1234567-8",
    "receiver_name": "Buyer Co",
    "receiver_address": "456 Avenue",
    "total_amount": 118000.00,
    "net_amount": 100000.00,
    "total_tax_amount": 18000.00,
    "currency": "PKR",
    "purchase_order": "PO-001",
    "remit_to_address": "IBAN PK36...",
    "invoice_type": "invoice"
  },
  "line_items": [
    {
      "description": "Consulting Services",
      "quantity": 1,
      "unit": "Month",
      "unit_price": 100000.00,
      "amount": 100000.00
    }
  ],
  "detected_taxes": [
    {
      "tax_type": "GST",
      "amount": 18000.00,
      "rate": 18.0,
      "description": "General Sales Tax on services"
    }
  ],
  "tax_summary": "GST at 18% applied on consulting services",
  "tax_confidence": 0.90,
  "overall_confidence": 0.92,
  "page_count": 1,
  "invoice_count": 1,
  "multiple_invoices": false,
  "invoice_page_ranges": [],
  "attention_flags": [
    {
      "severity": "high",
      "category": "currency",
      "title": "Currency mismatch",
      "message": "Amount column header says PKR but line values appear in USD with a 'USD 22,507 @ 281.4' conversion — verify the currency and exchange rate."
    }
  ]
}
"""

FIELD_LABELS = {
    "invoice_id": "Invoice #",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "supplier_name": "Vendor Name",
    "supplier_address": "Vendor Address",
    "receiver_name": "Receiver Name",
    "receiver_address": "Receiver Address",
    "total_amount": "Total Amount",
    "net_amount": "Subtotal",
    "total_tax_amount": "Tax Amount",
    "currency": "Currency",
    "purchase_order": "PO Reference",
    "remit_to_address": "Bank / IBAN",
    "invoice_type": "Document Type",
    "supplier_tax_id": "Vendor NTN",
}

CONFIDENCE_THRESHOLD_HIGH = 95.0
CONFIDENCE_THRESHOLD_MEDIUM = 85.0


def _get_client():
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured in .env")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _strip_code_fence(text: str) -> str:
    """Remove a ```json ... ``` (or bare ```) wrapper if present."""
    text = text.strip()
    if text.startswith("```"):
        # drop the opening fence line, then the trailing fence
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _extract_json_span(text: str) -> str:
    """Return the substring from the first '{' to its matching '}'.

    Guards against leading/trailing prose Gemini sometimes adds despite the
    JSON mime-type request. Respects strings and escapes so braces inside
    string values don't confuse the matcher.
    """
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    # Unbalanced (likely truncated) — return from first brace onward
    return text[start:]


def _repair_json(text: str) -> str:
    """Best-effort repairs for common LLM JSON defects."""
    # Remove // and /* */ comments
    text = re.sub(r"//[^\n\r]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Remove trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    # Collapse Python-style None/True/False if they slip in
    text = re.sub(r"\bNone\b", "null", text)
    text = re.sub(r"\bTrue\b", "true", text)
    text = re.sub(r"\bFalse\b", "false", text)
    return text


def _parse_json_lenient(raw: str) -> dict:
    """Parse Gemini output into a dict, applying escalating repair strategies.

    Raises json.JSONDecodeError only if every strategy fails.
    """
    text = _strip_code_fence(raw)

    # 1. Straight parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Isolate the JSON object span, then parse
    span = _extract_json_span(text)
    try:
        return json.loads(span)
    except json.JSONDecodeError:
        pass

    # 3. Apply repairs to the span and parse
    repaired = _repair_json(span)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # 4. As a last resort, close an unbalanced/truncated object
    closed = repaired.rstrip().rstrip(",")
    open_braces = closed.count("{") - closed.count("}")
    open_brackets = closed.count("[") - closed.count("]")
    if open_brackets > 0:
        closed += "]" * open_brackets
    if open_braces > 0:
        closed += "}" * open_braces
    return json.loads(closed)  # let it raise if still broken


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        cleaned = (
            str(value)
            .replace(",", "")
            .replace("PKR", "")
            .replace("Rs", "")
            .replace("Rs.", "")
            .strip()
        )
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _friendly_doc_type(raw: str | None) -> str:
    if not raw:
        return "Tax Invoice"
    return DOCUMENT_TYPE_LABELS.get(raw.strip().lower(), raw.replace("_", " ").title())


# Markers that indicate a non-final / informal / duplicate document
_DOC_MARKERS = [
    ("revised", "Revised document", "Invoice is marked as revised/amended — confirm it supersedes any earlier version on file."),
    ("proforma", "Proforma invoice", "This is a proforma/preliminary invoice, not a final tax invoice."),
    ("duplicate", "Duplicate copy", "Document is marked as a duplicate copy."),
    ("carbon copy", "Carbon copy", "Document is a carbon copy of a receipt — verify the original."),
    ("draft", "Draft document", "Document is marked as a draft."),
    ("kacha", "Informal bill", "Informal 'kacha' bill — no formal tax document; verify vendor and amounts manually."),
]


def _detect_attention_flags(
    field_map: dict,
    line_items: list[dict],
    detected_taxes: list[dict],
    conf_percent: float,
) -> list[dict]:
    """Deterministic anomaly checks that complement Gemini's document-level flags.

    Returns a list of {severity, category, title, message} dicts.
    """
    flags: list[dict] = []

    # --- Missing critical fields ---
    if not field_map.get("invoice_id"):
        flags.append({
            "severity": "high", "category": "missing_field",
            "title": "Missing invoice number",
            "message": "No invoice number was detected — required before posting.",
        })
    if _safe_float(field_map.get("total_amount")) is None:
        flags.append({
            "severity": "high", "category": "missing_field",
            "title": "Missing total amount",
            "message": "No grand total could be read from the document.",
        })
    if not field_map.get("supplier_name"):
        flags.append({
            "severity": "medium", "category": "missing_field",
            "title": "Missing supplier name",
            "message": "Vendor / supplier name was not detected.",
        })
    if not field_map.get("supplier_tax_id"):
        flags.append({
            "severity": "low", "category": "tax",
            "title": "No vendor NTN",
            "message": "No vendor NTN/STRN found — verify FBR registration and filer status.",
        })

    # --- Foreign currency ---
    currency = (field_map.get("currency") or "PKR").strip().upper()
    if currency and currency != "PKR":
        flags.append({
            "severity": "medium", "category": "currency",
            "title": f"Foreign currency ({currency})",
            "message": f"Invoice is denominated in {currency} — confirm the exchange rate and PKR conversion before posting.",
        })

    # --- Math: line items should sum to the subtotal ---
    net = _safe_float(field_map.get("net_amount"))
    li_sum = sum((li.get("amount") or 0) for li in line_items) if line_items else 0
    if net is not None and line_items and li_sum > 0:
        if abs(li_sum - net) > max(1.0, abs(net) * 0.01):
            flags.append({
                "severity": "medium", "category": "math",
                "title": "Line items don't match subtotal",
                "message": "Sum of line item amounts does not equal the stated subtotal.",
                "detail": f"Line items sum to {li_sum:,.2f} but subtotal reads {net:,.2f}.",
            })

    # --- Negative or zero total ---
    total = _safe_float(field_map.get("total_amount"))
    if total is not None and total <= 0:
        flags.append({
            "severity": "high", "category": "math",
            "title": "Non-positive total",
            "message": f"Total amount is {total:,.2f} — verify this is correct (credit note?).",
        })

    # --- Document markers (revised / proforma / duplicate / kacha …) ---
    haystack = " ".join(
        str(field_map.get(k) or "") for k in ("invoice_id", "invoice_type")
    ).lower()
    for needle, title, msg in _DOC_MARKERS:
        if needle in haystack:
            flags.append({
                "severity": "medium", "category": "document",
                "title": title, "message": msg,
            })

    # --- Low confidence ---
    if conf_percent < 90.0:
        flags.append({
            "severity": "medium" if conf_percent < 80.0 else "low",
            "category": "confidence",
            "title": "Low OCR confidence",
            "message": f"Extraction confidence is {conf_percent}% — review all fields against the document.",
        })

    return flags


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _merge_attention_flags(gemini_flags: list, rule_flags: list[dict]) -> list[dict]:
    """Combine Gemini-detected and rule-based flags, de-duplicating by title and
    sorting high→low severity."""
    merged: list[dict] = []
    seen: set[str] = set()

    def _add(f: dict):
        title = str(f.get("title") or "").strip()
        sev = str(f.get("severity") or "medium").strip().lower()
        if sev not in _SEVERITY_RANK:
            sev = "medium"
        key = title.lower()
        if not title or key in seen:
            return
        seen.add(key)
        merged.append({
            "severity": sev,
            "category": str(f.get("category") or "document").strip().lower(),
            "title": title,
            "message": str(f.get("message") or "").strip(),
            "detail": f.get("detail"),
        })

    # Gemini flags first (it sees the raw document), then deterministic rules
    for f in (gemini_flags or []):
        if isinstance(f, dict):
            _add(f)
    for f in rule_flags:
        _add(f)

    merged.sort(key=lambda f: _SEVERITY_RANK.get(f["severity"], 1))
    return merged


SEGMENTATION_PROMPT = """You are segmenting a scanned document that contains MULTIPLE separate
invoices. Your ONLY task is to map every page to the invoice it belongs to.

For EACH page of the document (in order, 1-based), report:
- page: the page number
- invoice_number: the invoice number/reference visible on or governing this page (null if none visible)
- starts_new_invoice: true if a NEW invoice STARTS on this page (a fresh invoice header — new
  invoice number, vendor letterhead restarting, new "Invoice #"). false if this page CONTINUES
  the previous page's invoice (continuation of a line-items table, totals page, terms page,
  annexure, or any page without its own new invoice header).

Rules:
- Page 1 always has starts_new_invoice = true.
- An invoice may span 1, 2, 3, 5 or more pages — a continuation page shows running line items,
  carried-forward totals, or no new header. Do NOT mark continuations as new invoices.
- If a page shows the SAME invoice number as the previous page, it is a continuation.
- When unsure whether a page starts a new invoice, prefer false (continuation).

Respond ONLY with valid JSON:
{"page_count": 4, "pages": [
  {"page": 1, "invoice_number": "INV-001", "starts_new_invoice": true},
  {"page": 2, "invoice_number": "INV-001", "starts_new_invoice": false},
  {"page": 3, "invoice_number": "INV-002", "starts_new_invoice": true},
  {"page": 4, "invoice_number": "INV-003", "starts_new_invoice": true}
]}"""


def segment_invoice_pages(file_content: bytes, mime_type: str, total_pages: int) -> list[list[int]]:
    """Dedicated segmentation pass: map every page to an invoice and derive
    [start, end] page ranges deterministically. Much more reliable for large
    multi-invoice files than boundary-guessing inside the main extraction.

    Returns validated, gap-free ranges covering pages 1..total_pages; a single
    full-document range on any failure (caller treats that as 'cannot split')."""
    client = _get_client()

    def _call():
        return client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=file_content, mime_type=mime_type),
                SEGMENTATION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

    try:
        response = _call()
        try:
            result = _parse_json_lenient((response.text or "").strip())
        except json.JSONDecodeError:
            response = _call()
            result = _parse_json_lenient((response.text or "").strip())
        pages = sorted(
            (p for p in result.get("pages", []) if isinstance(p.get("page"), int)),
            key=lambda p: p["page"],
        )
        if not pages:
            return [[1, total_pages]]

        # Assemble ranges: new range on starts_new_invoice, else continuation.
        # Also treat a page repeating the previous invoice_number as continuation
        # even if the model flagged it as a start (number wins over the flag).
        ranges: list[list[int]] = []
        prev_num = None
        for p in pages:
            page_no = min(max(1, p["page"]), total_pages)
            num = (str(p.get("invoice_number")).strip() or None) if p.get("invoice_number") else None
            starts = bool(p.get("starts_new_invoice"))
            if num and prev_num and num == prev_num:
                starts = False
            if not ranges or (starts and page_no > ranges[-1][1]):
                ranges.append([page_no, page_no])
            else:
                ranges[-1][1] = max(ranges[-1][1], page_no)
            prev_num = num or prev_num

        # Repair: full coverage 1..total_pages, contiguous, no overlaps.
        ranges[0][0] = 1
        for i in range(1, len(ranges)):
            ranges[i][0] = ranges[i - 1][1] + 1   # close any gap to previous
            if ranges[i][1] < ranges[i][0]:
                ranges[i][1] = ranges[i][0]
        ranges[-1][1] = total_pages
        ranges = [r for r in ranges if r[0] <= r[1] and r[0] <= total_pages]
        logger.info(f"Segmentation: {total_pages} pages -> ranges {ranges}")
        return ranges if ranges else [[1, total_pages]]
    except Exception:
        logger.exception("Invoice segmentation failed; treating file as unsplittable")
        return [[1, total_pages]]


def extract_invoice(file_content: bytes, mime_type: str) -> dict:
    """
    Single Gemini call to extract all invoice data: fields, line items, and taxes.

    Returns dict matching the structure expected by the upload endpoint.
    """
    client = _get_client()
    start_time = time.time()

    def _call_gemini():
        return client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=file_content, mime_type=mime_type),
                EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

    try:
        response = _call_gemini()
        raw_text = (response.text or "").strip()

        # Parse with escalating repair strategies; if the model produced
        # unrecoverable JSON, retry the call once before giving up.
        try:
            result = _parse_json_lenient(raw_text)
        except json.JSONDecodeError as parse_err:
            logger.warning(
                f"Gemini returned malformed JSON, retrying once: {parse_err}"
            )
            response = _call_gemini()
            raw_text = (response.text or "").strip()
            result = _parse_json_lenient(raw_text)

        processing_time_ms = int((time.time() - start_time) * 1000)

        # --- Parse fields ---
        raw_fields = result.get("fields", {})
        overall_conf = result.get("overall_confidence", 0.85)
        conf_percent = round(overall_conf * 100, 1)

        fields = []
        warnings = []
        for field_name, label in FIELD_LABELS.items():
            value = raw_fields.get(field_name)
            if value is None or value == "":
                continue
            display_value = str(value)
            if field_name == "invoice_type":
                display_value = _friendly_doc_type(display_value)
            fields.append({
                "label": label,
                "value": display_value,
                "field_name": field_name,
                "confidence": conf_percent,
            })

        # Warn if confidence is low
        if conf_percent < CONFIDENCE_THRESHOLD_MEDIUM:
            warnings.append(
                f"Overall extraction confidence is low ({conf_percent}%) — manual verification recommended"
            )
        elif conf_percent < CONFIDENCE_THRESHOLD_HIGH:
            warnings.append(
                f"Overall extraction confidence is moderate ({conf_percent}%) — consider reviewing"
            )

        # Fix: if total_tax_amount == total_amount, likely misread — zero it out
        field_map = {f["field_name"]: f["value"] for f in fields}
        try:
            tax_val = float(str(field_map.get("total_tax_amount", "0")).replace(",", ""))
            total_val = float(str(field_map.get("total_amount", "0")).replace(",", ""))
            if tax_val > 0 and tax_val == total_val:
                for f in fields:
                    if f["field_name"] == "total_tax_amount":
                        f["value"] = "0"
                        break
        except (ValueError, TypeError):
            pass

        document_type = _friendly_doc_type(raw_fields.get("invoice_type"))
        page_count = result.get("page_count", 1)

        # --- Parse line items ---
        raw_line_items = result.get("line_items", [])
        line_items = []
        for li in raw_line_items:
            description = (li.get("description") or "").strip()
            if not description:
                continue
            line_items.append({
                "description": description,
                "quantity": _safe_float(li.get("quantity")),
                "unit": li.get("unit") or None,
                "unit_price": _safe_float(li.get("unit_price")),
                "amount": _safe_float(li.get("amount")),
                "description_confidence": conf_percent,
                "quantity_confidence": None,
                "unit_price_confidence": None,
                "amount_confidence": None,
            })

        # --- Parse taxes ---
        raw_taxes = result.get("detected_taxes", [])
        detected_taxes = []
        for tax in raw_taxes:
            detected_taxes.append({
                "tax_type": tax.get("tax_type", "Unknown"),
                "amount": _safe_float(tax.get("amount")),
                "rate": _safe_float(tax.get("rate")),
                "description": tax.get("description", ""),
            })

        tax_summary = result.get("tax_summary", "")
        tax_confidence = result.get("tax_confidence", overall_conf)

        # --- Attention flags: merge Gemini's document-level findings with
        #     deterministic rule checks (math, currency, missing fields, …) ---
        rule_flags = _detect_attention_flags(
            field_map, line_items, detected_taxes, conf_percent
        )
        attention_flags = _merge_attention_flags(
            result.get("attention_flags", []), rule_flags
        )

        return {
            "fields": fields,
            "line_items": line_items,
            "overall_confidence": conf_percent,
            "document_type": document_type,
            "page_count": page_count,
            "processing_time_ms": processing_time_ms,
            "warnings": warnings,
            "raw_document_ai": None,
            "detected_taxes": detected_taxes,
            "tax_summary": tax_summary,
            "gemini_confidence": tax_confidence,
            "gemini_processing_time_ms": processing_time_ms,
            "line_items_source": "gemini",
            "attention_flags": attention_flags,
            "multiple_invoices": bool(result.get("multiple_invoices")),
            "invoice_count": int(result.get("invoice_count") or 1),
            "invoice_page_ranges": result.get("invoice_page_ranges") or [],
        }

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Gemini extraction failed: {e}", exc_info=True)
        raise RuntimeError(f"Gemini extraction failed: {e}")
