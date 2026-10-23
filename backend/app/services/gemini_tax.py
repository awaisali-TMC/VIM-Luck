import json
import logging
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

TAX_DETECTION_PROMPT = """You are a Pakistan tax specialist analyzing an invoice document.

Your task: Identify ALL specific tax types and their amounts from this invoice.

Pakistan tax types to look for:
- GST (General Sales Tax) - typically 18% on goods/services
- WHT (Withholding Tax) - varies by category (1%-15%)
- FED (Federal Excise Duty)
- SED (Special Excise Duty)
- PRA (Punjab Revenue Authority tax)
- SRB (Sindh Revenue Board tax)
- KPRA (KP Revenue Authority tax)
- BRA (Balochistan Revenue Authority tax)
- Customs Duty
- Any other taxes mentioned in the document

Context from prior extraction:
- Total tax amount: {total_tax_amount}
- Subtotal/Net amount: {net_amount}
- Total amount: {total_amount}

IMPORTANT RULES:
1. Only report taxes you can actually see or infer from the document.
2. If the document shows a single "Tax" line without specifying the type, try to infer from context (vendor type, invoice type, province).
3. The sum of detected tax amounts should ideally match the total tax amount.
4. Report rate as percentage if visible, otherwise null.

Respond ONLY with valid JSON in this exact format:
{{
  "detected_taxes": [
    {{
      "tax_type": "GST",
      "amount": 15000.00,
      "rate": 18.0,
      "description": "General Sales Tax on services"
    }}
  ],
  "tax_summary": "Brief description of tax analysis",
  "confidence": 0.85
}}

If no taxes are found, return:
{{
  "detected_taxes": [],
  "tax_summary": "No taxes detected on this document",
  "confidence": 0.95
}}
"""


def _get_client():
    """Create Gemini client using API key."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured in .env")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def detect_taxes(
    file_content: bytes,
    mime_type: str,
    total_tax_amount: str | None = None,
    net_amount: str | None = None,
    total_amount: str | None = None,
) -> dict:
    """
    Send document to Gemini 2.0 Flash for tax type detection.
    Returns dict with detected_taxes, tax_summary, gemini_confidence, gemini_processing_time_ms.
    """
    client = _get_client()

    prompt = TAX_DETECTION_PROMPT.format(
        total_tax_amount=total_tax_amount or "Not extracted",
        net_amount=net_amount or "Not extracted",
        total_amount=total_amount or "Not extracted",
    )

    start_time = time.time()

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=file_content, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Parse JSON response (strip markdown fences if present)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        detected_taxes = result.get("detected_taxes", [])
        for tax in detected_taxes:
            tax["amount"] = _safe_float(tax.get("amount"))
            tax["rate"] = _safe_float(tax.get("rate"))
            tax.setdefault("tax_type", "Unknown")
            tax.setdefault("description", "")

        return {
            "detected_taxes": detected_taxes,
            "tax_summary": result.get("tax_summary", ""),
            "gemini_confidence": result.get("confidence", 0.0),
            "gemini_processing_time_ms": processing_time_ms,
        }

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Gemini tax detection failed: {e}")
        return {
            "detected_taxes": [],
            "tax_summary": f"Tax detection failed: {str(e)}",
            "gemini_confidence": 0.0,
            "gemini_processing_time_ms": processing_time_ms,
        }


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
