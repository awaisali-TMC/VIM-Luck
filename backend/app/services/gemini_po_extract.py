"""
Gemini-powered Purchase Order extraction service.

Given a PO file (PDF/image/Excel), extracts structured PO data
including header fields and line items using Gemini (model: settings.GEMINI_MODEL).
"""

import json
import logging
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


PO_EXTRACT_PROMPT = """You are a procurement specialist extracting Purchase Order data from the attached document.

Extract the following information:
- po_number: The purchase order number
- vendor_name: Supplier/vendor name
- vendor_ntn: Vendor NTN / tax registration number (if present)
- po_date: PO date (in the format shown in the document)
- po_type: "local" (domestic), "foreign" (import), or "contract" (service contract)
- total_amount: Total PO amount (numeric only, no currency symbols)
- currency: Currency code (PKR, USD, EUR, etc.)
- notes: Any special instructions or notes

For each line item, extract:
- item_number: Sequential line number
- description: Item description
- quantity: Ordered quantity (numeric)
- unit: Unit of measure (e.g., Each, BBL, KG, Nos, Lot)
- unit_price: Unit price (numeric)
- amount: Line total (numeric, should be quantity × unit_price)

Respond ONLY with valid JSON in this exact format:
{
  "po_number": "...",
  "vendor_name": "...",
  "vendor_ntn": "...",
  "po_date": "...",
  "po_type": "local",
  "total_amount": 0.0,
  "currency": "PKR",
  "notes": "",
  "line_items": [
    {
      "item_number": 1,
      "description": "...",
      "quantity": 0.0,
      "unit": "Each",
      "unit_price": 0.0,
      "amount": 0.0
    }
  ]
}

If a field is not found in the document, use null for strings and 0 for numbers.
Ensure all numeric values are numbers, not strings."""


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def extract_po_from_file(file_content: bytes, mime_type: str) -> dict:
    """Extract PO data from uploaded file using Gemini (settings.GEMINI_MODEL)."""
    start = time.time()
    client = _get_client()

    # For Excel files, convert to text first and send as plain string
    if "spreadsheet" in mime_type or "excel" in mime_type:
        text_content = _excel_to_text(file_content)
        contents = [
            f"Extract Purchase Order data from this spreadsheet content:\n\n{text_content}\n\n{PO_EXTRACT_PROMPT}"
        ]
    else:
        # PDF or image — send as inline bytes + plain text prompt
        contents = [
            types.Part.from_bytes(data=file_content, mime_type=mime_type),
            PO_EXTRACT_PROMPT,
        ]

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    elapsed_ms = int((time.time() - start) * 1000)

    # Strip markdown fences if present (matching pattern from gemini_tax.py)
    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse Gemini PO extraction response: {raw_text[:500]}")
        raise ValueError("Failed to parse PO extraction result from Gemini")

    result["processing_time_ms"] = elapsed_ms
    logger.info(
        f"PO extraction complete: {result.get('po_number', 'unknown')} "
        f"with {len(result.get('line_items', []))} line items in {elapsed_ms}ms"
    )
    return result


def _excel_to_text(file_content: bytes) -> str:
    """Convert Excel file bytes to text representation."""
    try:
        import io
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        lines = []
        for ws in wb.worksheets:
            lines.append(f"=== Sheet: {ws.title} ===")
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(c) if c is not None else "" for c in row]
                lines.append(" | ".join(row_vals))
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Excel parsing failed, sending raw: {e}")
        return f"[Excel file, {len(file_content)} bytes — could not parse]"
