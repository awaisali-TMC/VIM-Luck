"""
Gemini-powered line item extraction service.

Used when Document AI fails to properly extract line items (missing descriptions,
wrong groupings, etc.). Sends the invoice image/PDF directly to Gemini vision
which can understand the visual layout of any invoice format.
"""

import json
import logging
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


LINE_ITEM_EXTRACTION_PROMPT = """You are an accounts payable specialist extracting line items from an invoice.

Carefully read the invoice and extract EVERY billable line item, service, or product listed.

RULES:
1. Extract each distinct service/product/charge as a separate line item.
2. Do NOT include tax rows (GST, WHT, Sales Tax, Advance Tax, Excise Duty) as line items — those are taxes, not services.
3. Do NOT include summary rows (Subtotal, Grand Total, Amount Due) as line items.
4. For utility bills: extract the actual services (e.g. "CONNECT 1024.30M Internet Package", "TV Service", "Phone Line").
5. For multi-section bills: extract each section's services separately.
6. If a line item has no quantity shown, use null. If no unit price shown but amount is visible, use null for unit_price.
7. Remove any currency symbols from numeric fields — return plain numbers only.
8. description must never be null or empty — always provide a meaningful name.

Respond ONLY with valid JSON:
{
  "line_items": [
    {
      "description": "CONNECT 1024.30M Internet Package",
      "quantity": 1,
      "unit": "Month",
      "unit_price": 7000.00,
      "amount": 7000.00
    }
  ],
  "confidence": 0.92,
  "notes": "Brief note about extraction (optional)"
}

If no billable line items found (only taxes/totals), return:
{
  "line_items": [],
  "confidence": 0.95,
  "notes": "No billable line items found"
}
"""


def _get_client():
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured in .env")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def extract_line_items(file_content: bytes, mime_type: str) -> dict:
    """
    Use Gemini vision to extract line items from an invoice document.

    Returns dict with:
      - line_items: list of {description, quantity, unit, unit_price, amount}
      - confidence: float 0-1
      - processing_time_ms: int
    """
    client = _get_client()
    start_time = time.time()

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=file_content, mime_type=mime_type),
                LINE_ITEM_EXTRACTION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        line_items = result.get("line_items", [])
        cleaned = []
        for li in line_items:
            description = li.get("description", "").strip()
            if not description:
                continue
            cleaned.append({
                "description": description,
                "quantity": _safe_float(li.get("quantity")),
                "unit": li.get("unit") or None,
                "unit_price": _safe_float(li.get("unit_price")),
                "amount": _safe_float(li.get("amount")),
                # confidence fields — Gemini-extracted items get uniform confidence
                "description_confidence": round(result.get("confidence", 0.85) * 100, 1),
                "quantity_confidence": None,
                "unit_price_confidence": None,
                "amount_confidence": None,
            })

        return {
            "line_items": cleaned,
            "confidence": result.get("confidence", 0.85),
            "processing_time_ms": processing_time_ms,
        }

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Gemini line item extraction failed: {e}")
        return {
            "line_items": [],
            "confidence": 0.0,
            "processing_time_ms": processing_time_ms,
        }


def needs_gemini_line_items(doc_ai_line_items: list[dict]) -> bool:
    """
    Return True if Document AI line items are poor quality and Gemini should be used.
    Conditions:
      - No line items extracted at all, OR
      - More than half the items have no description
    """
    if not doc_ai_line_items:
        return True
    missing_desc = sum(1 for li in doc_ai_line_items if not li.get("description"))
    return missing_desc > len(doc_ai_line_items) / 2
