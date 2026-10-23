"""
Gemini-powered product/account matching service.

Given extracted invoice line items and a list of products from the database,
asks Gemini to find the best matching product for each line item.
"""

import json
import logging
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


PRODUCT_MATCH_PROMPT = """You are an accounts payable specialist matching invoice line items to a company's product/service catalog.

For each invoice line item below, find the BEST matching product from the catalog.
Consider:
- Semantic similarity (e.g., "internet 50 mb" matches "Internet Service - 50 Mbps")
- Category relevance (e.g., "bandwidth" relates to IT & Telecom)
- Partial matches (e.g., "CFS charges" matches "CFS Receiving Charge")
- Abbreviations and synonyms (e.g., "A/C service" matches "AC Maintenance Service")

LINE ITEMS FROM INVOICE:
{line_items_json}

PRODUCT CATALOG (code | name | category):
{catalog_text}

IMPORTANT RULES:
1. Match each line item to exactly ONE product from the catalog.
2. If no good match exists, use the closest reasonable match with low confidence.
3. Confidence should be 0.0-1.0 (1.0 = exact match, 0.5 = partial, below 0.3 = poor guess).
4. The "reasoning" field should briefly explain WHY you matched them.

Respond ONLY with valid JSON:
{{
  "matches": [
    {{
      "line_item_index": 0,
      "product_code": "IT-003",
      "confidence": 0.92,
      "reasoning": "Invoice says internet 50 mb which matches Internet Service - 50 Mbps"
    }}
  ]
}}
"""


def _get_client():
    """Create Gemini client using API key."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured in .env")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def match_products(line_items: list[dict], products: list[dict]) -> dict:
    """
    Use Gemini to match invoice line items to products from the catalog.

    Args:
        line_items: List of dicts with at least 'description', optionally 'quantity', 'unit_price', 'amount'
        products: List of dicts with 'code', 'name', 'category'

    Returns:
        dict with 'matches' list and 'processing_time_ms'
    """
    if not line_items:
        return {"matches": [], "processing_time_ms": 0}

    client = _get_client()

    # Build line items text
    li_for_prompt = []
    for i, li in enumerate(line_items):
        li_for_prompt.append({
            "index": i,
            "description": li.get("description", ""),
            "quantity": li.get("quantity"),
            "unit_price": li.get("unit_price"),
            "amount": li.get("amount"),
        })

    # Build catalog text (compact format to fit token limits)
    catalog_lines = []
    for p in products:
        catalog_lines.append(f"{p['code']} | {p['name']} | {p['category']}")
    catalog_text = "\n".join(catalog_lines)

    prompt = PRODUCT_MATCH_PROMPT.format(
        line_items_json=json.dumps(li_for_prompt, indent=2),
        catalog_text=catalog_text,
    )

    start_time = time.time()

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        # Parse response
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        matches = result.get("matches", [])

        # Validate and clean up matches
        product_map = {p["code"]: p for p in products}
        cleaned = []
        for m in matches:
            code = m.get("product_code", "")
            if code in product_map:
                cleaned.append({
                    "line_item_index": m.get("line_item_index", 0),
                    "product_code": code,
                    "product_name": product_map[code]["name"],
                    "product_category": product_map[code]["category"],
                    "confidence": min(1.0, max(0.0, float(m.get("confidence", 0)))),
                    "reasoning": m.get("reasoning", ""),
                })

        return {
            "matches": cleaned,
            "processing_time_ms": processing_time_ms,
        }

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Gemini product matching failed: {e}")
        return {
            "matches": [],
            "processing_time_ms": processing_time_ms,
        }
