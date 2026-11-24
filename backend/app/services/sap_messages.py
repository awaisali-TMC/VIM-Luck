"""SAP's own messages, kept on the invoice and shown as SAP sends them.

Every answer SAP gives to a park, resubmit, post, dry run or unpark (BAPI RETURN:
errors, warnings, information), a failed RFC call, a missing approval hierarchy and
the workflow's ZMIR7_ERROR_LOG. VIM's own checks are not SAP messages and stay
where they were. Stored as invoices.sap_messages, newest run first:
[{at, action, document, messages: [{type, id, number, text}]}]
"""
import json
from datetime import datetime, timezone

MAX_RUNS = 12
MAX_MESSAGES = 60
WORKFLOW = "workflow"


def clean_message(row: dict) -> dict:
    """One BAPIRET2-like row (any case) as {type, id, number, text}."""
    def get(name):
        return str(row.get(name) or "").strip()

    mtype, mid, number = get("TYPE").upper()[:1] or "I", get("ID"), get("NUMBER")
    text = get("MESSAGE")
    if not text:
        shown = " ".join(v for v in (get("MESSAGE_V1"), get("MESSAGE_V2"), get("MESSAGE_V3"), get("MESSAGE_V4")) if v)
        text = shown or "SAP sent no message text"
    # M8 417 "Document deleted" comes as E but confirms the unpark.
    if mid == "M8" and number == "417":
        mtype = "S"
    return {"type": mtype, "id": mid, "number": number, "text": text[:400]}


def load(invoice) -> list[dict]:
    try:
        runs = json.loads(invoice.sap_messages) if invoice.sap_messages else []
    except (TypeError, ValueError):
        return []
    return runs if isinstance(runs, list) else []


def _store(invoice, runs: list[dict]) -> None:
    invoice.sap_messages = json.dumps(runs[:MAX_RUNS]) if runs else None


def record(invoice, action: str, rows: list[dict] | None, summary: str = "", ok: bool = True) -> None:
    """Add one run. `summary` is used when SAP returned no message at all."""
    messages, seen = [], set()
    for row in rows or []:
        m = clean_message(row)
        key = (m["type"], m["id"], m["number"], m["text"])
        if key not in seen:
            seen.add(key)
            messages.append(m)
    if not messages and summary:
        messages = [{"type": "S" if ok else "E", "id": "", "number": "", "text": summary[:400]}]
    if not messages:
        return
    run = {"at": datetime.now(timezone.utc).isoformat(), "action": action,
           "document": invoice.sap_document_number or "", "messages": messages[:MAX_MESSAGES]}
    _store(invoice, [run] + load(invoice))


def record_workflow_log(invoice, log: list[dict]) -> None:
    """The workflow's log (ZMIR7_ERROR_LOG) is read whole on every refresh, so it
    replaces the previous copy for this document instead of adding to it."""
    doc = invoice.sap_document_number or ""
    runs = load(invoice)
    mine = [r for r in runs if r.get("action") == WORKFLOW and r.get("document") == doc]
    if not log or (mine and mine[0]["messages"] == log[:MAX_MESSAGES]):
        return                              # nothing new (an empty read keeps the last log)
    others = [r for r in runs if r not in mine]
    run = {"at": datetime.now(timezone.utc).isoformat(), "action": WORKFLOW, "document": doc,
           "messages": log[:MAX_MESSAGES]}
    _store(invoice, [run] + others)
