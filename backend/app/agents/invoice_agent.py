"""ADK LlmAgent that orchestrates invoice processing.

Equivalent of `google/adk-samples/invoice-processing` adapted to use einv's
existing extraction + matching services. Exposed through the FastAPI router
``app.routers.agent_invoices`` (REST) and also runnable via ``adk web`` for
interactive testing.

Run interactively (from backend/):
    set GOOGLE_API_KEY=...    # PowerShell: $env:GOOGLE_API_KEY="..."
    adk web app/agents
"""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.genai import types

from app.config import settings
from app.agents.prompts import INVOICE_AGENT_INSTRUCTION
from app.agents.tools import (
    extract_invoice,
    validate_totals,
    find_duplicate_invoices,
    match_to_purchase_order,
    persist_invoice,
)

# ADK's default Gemini client reads GOOGLE_API_KEY (not GEMINI_API_KEY).
# Bridge it from settings if not already present in env.
if settings.GEMINI_API_KEY and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY

# Force the AI Studio (Gemini API) backend instead of Vertex AI. Vertex AI's
# function-calling schema is stricter and rejects some auto-generated fields
# (e.g. "additional_properties"). Direct Gemini API works fine.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")


root_agent = LlmAgent(
    name="invoice_processor",
    model=settings.GEMINI_MODEL,
    description=(
        "Accounts payable agent that extracts, validates, deduplicates, and PO-matches "
        "vendor invoices, then decides ACCEPT / FLAG / REJECT."
    ),
    instruction=INVOICE_AGENT_INSTRUCTION,
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
    tools=[
        extract_invoice,
        validate_totals,
        find_duplicate_invoices,
        match_to_purchase_order,
        persist_invoice,
    ],
)
