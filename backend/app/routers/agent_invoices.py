"""REST endpoint that drives the ADK invoice-processing agent.

  POST /api/agent/invoices/process       — upload PDF, agent runs full pipeline
  POST /api/agent/invoices/process-path  — process a file already on disk
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.config import settings
from app.agents.invoice_agent import root_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/invoices", tags=["agent"])

UPLOAD_DIR = Path(settings.UPLOAD_DIR if hasattr(settings, "UPLOAD_DIR") else "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _run_agent(file_path: str, mime_type: str) -> dict:
    """Drive the agent for a single invoice file and return the structured result."""
    runner = InMemoryRunner(agent=root_agent, app_name="einv-agent")
    user_id = "api"
    session = await runner.session_service.create_session(
        app_name="einv-agent", user_id=user_id
    )

    user_message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text=(
                    f"Process the invoice at file_path={file_path!r} "
                    f"(mime_type={mime_type!r}). Run the full pipeline and "
                    "return the structured JSON decision as instructed."
                )
            )
        ],
    )

    # Collect everything the agent does so the API caller can see tool traces.
    tool_calls: list[dict] = []
    final_text = ""

    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=user_message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call:
                    tool_calls.append({
                        "tool": part.function_call.name,
                        "args": dict(part.function_call.args or {}),
                    })
                elif part.function_response:
                    if tool_calls and "result" not in tool_calls[-1]:
                        # Compact the tool result for response
                        tool_calls[-1]["result"] = part.function_response.response
                elif part.text:
                    if event.is_final_response():
                        final_text = part.text

    # Try to extract the JSON decision from the final text.
    decision_obj: dict | None = None
    if final_text:
        m = re.search(r"\{[\s\S]*\}", final_text)
        if m:
            try:
                decision_obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

    return {
        "decision": decision_obj or {"raw": final_text},
        "tool_calls": tool_calls,
    }


@router.post("/process")
async def process_invoice_with_agent(file: UploadFile = File(...)):
    """Upload an invoice PDF/image — the ADK agent runs the full pipeline."""
    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = UPLOAD_DIR / stored_name
    content = await file.read()
    stored_path.write_bytes(content)

    mime_type = file.content_type or "application/pdf"
    try:
        return await _run_agent(str(stored_path), mime_type)
    except Exception:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail="Agent run failed — see server logs.")


@router.post("/process-path")
async def process_invoice_by_path(
    file_path: str = Form(...),
    mime_type: str = Form("application/pdf"),
):
    """DEV ONLY: run the agent against a file already on the server's disk.

    Disabled outside DEBUG — accepting arbitrary server paths from a client is
    a local-file-disclosure vector and exists purely for local testing.
    """
    from app.config import settings
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        return await _run_agent(file_path, mime_type)
    except Exception:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail="Agent run failed — see server logs.")


@router.get("/health")
async def agent_health():
    """Quick check that the agent module loaded and a model is configured."""
    return {
        "ok": True,
        "agent_name": root_agent.name,
        "model": str(root_agent.model),
        "tools": [t.__name__ if hasattr(t, "__name__") else str(t) for t in root_agent.tools],
    }
