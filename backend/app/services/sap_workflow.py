"""SAP parking workflow (Lucky Cement) — raise the event, read the outcome.

Flow agreed with Lucky Cement's SAP team (emails of 2026-11-16 and
MIR7_Parking_Workflow.md):

1. VIM parks the invoice with BAPI_INCOMINGINVOICE_PARK  (no commit yet)
2. VIM raises the workflow event with SAP_WAPI_CREATE_EVENT, COMMIT_WORK=' '
3. Only if both succeeded: BAPI_TRANSACTION_COMMIT — otherwise ROLLBACK, so the
   invoice is NOT parked. SAP's rule is "no parked invoice without a workflow";
   the event needs the document number, which only exists after the park call,
   so the two steps share one LUW instead of running in the order "event, park".
4. WS90000096 routes the approvals (the approvers come from SAP's employee
   hierarchy) and, on approval, SAP posts the invoice itself.
5. VIM reads the outcome by OBJKEY from ZMIR7_WF_LOG / ZMIR7_ERROR_LOG with the
   standard RFC_READ_TABLE.

ASSUMED, NOT YET CONFIRMED BY SAP — check against DD03L on the target system
before relying on it (RFC_READ_TABLE on DD03L is read-only):
- the column names in WF_LOG_FIELDS / ERROR_LOG_FIELDS below,
- the container element names (taken from SAP's test data in the md),
- the event name (settings.SAP_WF_EVENT, deliberately without a default).
The fixture SAP (sap_fixtures/schema.sql) uses the same names, so a mismatch
on a real system fails loudly in RFC_READ_TABLE rather than reading nothing.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger(__name__)

WF_LOG_TABLE = "ZMIR7_WF_LOG"
ERROR_LOG_TABLE = "ZMIR7_ERROR_LOG"

# Logical name → SAP column. Change the right-hand side once DD03L is read.
WF_LOG_FIELDS = {"objkey": "OBJKEY", "status": "STATUS", "posted_doc": "POSTED_DOC"}
ERROR_LOG_FIELDS = {"objkey": "OBJKEY", "type": "TYPE", "message": "MESSAGE"}

# ZMIR7_WF_LOG-STATUS values (Naila's meeting notes).
WF_INIT = "INIT"   # document saved, workflow NOT initiated
WF_BLK = "BLK"     # workflow in process
WF_APP = "APP"     # approved — SAP posts the invoice
WF_REJ = "REJ"     # rejected
WF_LABELS = {
    WF_INIT: "Workflow not started",
    WF_BLK: "In SAP approval",
    WF_APP: "Approved in SAP",
    WF_REJ: "Rejected in SAP",
}
# Statuses that can still change, so the poller keeps reading them.
OPEN_STATUSES = (None, "", WF_INIT, WF_BLK)


def build_objkey(company_code: str, doc_number: str, fiscal_year: str) -> str:
    """Company code (4) + document number (10, zero-padded) + fiscal year (4) = 18."""
    cc = (company_code or "").strip()
    doc = (doc_number or "").strip().zfill(10)
    fy = (fiscal_year or "").strip()
    if len(cc) != 4 or len(doc) != 10 or len(fy) != 4:
        raise ValueError(f"Cannot build OBJKEY from company code {cc!r}, document {doc!r}, year {fy!r}")
    return f"{cc}{doc}{fy}"


def raise_parking_event(sap, objkey: str, doc_number: str,
                        initiator_sap_user: str = "", initiator_email: str = "") -> dict:
    """Raise the workflow event on an OPEN connection, without committing.

    The caller owns the LUW: it commits after a success and rolls back after a
    failure. Returns {ok, event_id, message, messages}.
    """
    event = (settings.SAP_WF_EVENT or "").strip()
    if not event:
        return {"ok": False, "event_id": "", "messages": [],
                "message": "SAP workflow is on but SAP_WF_EVENT is not set — the event name "
                           "is still awaited from the SAP ABAP team. The invoice was not parked."}

    container = [
        {"ELEMENT": "OBJKEY", "VALUE": objkey},
        {"ELEMENT": "D_NO", "VALUE": (doc_number or "").strip().zfill(10)},
        {"ELEMENT": "LEVEL", "VALUE": settings.SAP_WF_LEVEL},
        {"ELEMENT": "TOTALAPP", "VALUE": settings.SAP_WF_TOTAL_APPROVALS},
        {"ELEMENT": "SCENARIO_CHAR", "VALUE": settings.SAP_WF_SCENARIO},
    ]
    if initiator_email:
        container.append({"ELEMENT": "INIEMAIL", "VALUE": initiator_email})
    # ZWF_LOGIN carries the initiator's SAP user id. The workflow reads this to
    # resolve the approver from the Approval Matrix; without it the agent comes
    # out as 00000000 (nobody). Element name confirmed with Lucky Cement's SAP
    # team (2026-11-17). SAP user ids are upper-case.
    if initiator_sap_user:
        container.append({"ELEMENT": "ZWF_LOGIN", "VALUE": initiator_sap_user.strip().upper()})

    kwargs = dict(
        OBJECT_TYPE=settings.SAP_WF_OBJECT_TYPE,
        OBJECT_KEY=objkey,
        EVENT=event,
        COMMIT_WORK="",          # the caller commits park + event together
        input_tables={"INPUT_CONTAINER": container},
        tables=["MESSAGE_LINES"],
        output_params=["RETURN_CODE", "EVENT_ID"],
    )
    # Technical-user model: TMC_VIM raises the event on behalf of the VIM user,
    # whose SAP id becomes the event creator (and so the workflow initiator).
    if initiator_sap_user:
        kwargs["USER"] = initiator_sap_user.strip().upper()

    result = sap.call("SAP_WAPI_CREATE_EVENT", **kwargs)
    rc = (result.get("RETURN_CODE") or "").strip()
    lines = result.get("MESSAGE_LINES") or []
    texts = [(r.get("LINE") or "").strip() for r in lines if (r.get("LINE") or "").strip()]
    ok = rc in ("", "0")
    if ok:
        logger.info("SAP workflow event %s.%s raised for %s (event id %s)",
                    settings.SAP_WF_OBJECT_TYPE, event, objkey, result.get("EVENT_ID"))
    else:
        logger.error("SAP workflow event failed for %s: rc=%s %s", objkey, rc, texts)
    return {
        "ok": ok,
        "event_id": (result.get("EVENT_ID") or "").strip(),
        "messages": lines,
        "message": ("; ".join(texts) if texts else
                    f"SAP_WAPI_CREATE_EVENT returned code {rc}") if not ok else "Workflow started",
    }


def _read(sap, table: str, fields: dict, objkeys: list[str]) -> list[dict]:
    """RFC_READ_TABLE for a list of OBJKEYs, returned with LOGICAL field names."""
    if not objkeys:
        return []
    key_col = fields["objkey"]
    # One OR-ed predicate, one ≤72-char OPTIONS row per key (RFC_READ_TABLE's
    # row width); the trailing space keeps the concatenation valid.
    options = []
    for i, k in enumerate(objkeys):
        options.append({"TEXT": f"{'OR ' if i else ''}{key_col} = '{k}' "})
    from app.services.sap_po_service import _parse_delimited_rows
    result = sap.call(
        "RFC_READ_TABLE",
        QUERY_TABLE=table,
        DELIMITER="|",
        input_tables={"OPTIONS": options,
                      "FIELDS": [{"FIELDNAME": c} for c in fields.values()]},
        tables=["DATA", "FIELDS"],
        table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
    )
    rows = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))
    back = {sap_col: logical for logical, sap_col in fields.items()}
    return [{back.get(k, k): v for k, v in r.items()} for r in rows]


def read_workflow_status(sap, objkeys: list[str]) -> dict[str, dict]:
    """OBJKEY → {status, label, posted_doc, error}. Keys with no WF_LOG row are
    absent from the result (the workflow has not written anything yet)."""
    objkeys = [k for k in dict.fromkeys(objkeys) if k]
    out: dict[str, dict] = {}
    for row in _read(sap, WF_LOG_TABLE, WF_LOG_FIELDS, objkeys):
        status = (row.get("status") or "").strip().upper()
        out[row["objkey"]] = {
            "status": status,
            "label": WF_LABELS.get(status, status or "Unknown"),
            "posted_doc": (row.get("posted_doc") or "").strip(),
            "error": "",
        }
    # The last row per key decides (the table has no timestamp we rely on, so
    # this trusts SAP's row order): an E row sets the error, an S row clears it.
    for row in _read(sap, ERROR_LOG_TABLE, ERROR_LOG_FIELDS, objkeys):
        entry = out.setdefault(row["objkey"], {"status": "", "label": "No workflow record",
                                               "posted_doc": "", "error": ""})
        kind = (row.get("type") or "").strip().upper()
        if kind == "E":
            entry["error"] = (row.get("message") or "").strip() or "SAP posting error"
        elif kind == "S":
            entry["error"] = ""
    return out


# ── Applying the outcome to VIM invoices ────────────────────────────────────

def _read_statuses_blocking(objkeys: list[str]) -> dict[str, dict]:
    """One SAP connection (the global technical user), both log tables."""
    from app.services.sap_invoice_post import _get_connector
    sap = _get_connector()
    sap.connect()
    try:
        return read_workflow_status(sap, objkeys)
    finally:
        sap.disconnect()


def apply_status(invoice, info: dict | None, now: datetime) -> bool:
    """Copy one ZMIR7 status onto an invoice. Returns True if anything changed.

    APP with a posted document number → the invoice is POSTED (SAP posted it).
    APP without one yet → still parked; SAP has approved but not finished posting.
    REJ stays "parked" in VIM (the SAP document still exists, parked) and is
    shown as rejected; a user unparks it from VIM or handles it in SAP.
    """
    before = (invoice.sap_wf_status, invoice.sap_wf_posted_doc, invoice.sap_wf_message,
              invoice.status, invoice.sap_doc_status)
    invoice.sap_wf_checked_at = now
    if info:
        invoice.sap_wf_status = info["status"] or invoice.sap_wf_status or ""
        invoice.sap_wf_posted_doc = info["posted_doc"] or invoice.sap_wf_posted_doc
        invoice.sap_wf_message = (info["error"] or None) and info["error"][:500]
        if info["status"] == WF_APP and info["posted_doc"] and invoice.status == "parked":
            invoice.status = "posted"
            invoice.sap_doc_status = "posted"
    after = (invoice.sap_wf_status, invoice.sap_wf_posted_doc, invoice.sap_wf_message,
             invoice.status, invoice.sap_doc_status)
    return before != after


async def refresh_invoices(db, invoices: list) -> dict[int, dict]:
    """Read SAP for these invoices and update them. Commits. Returns id → info."""
    keyed = [inv for inv in invoices if inv.sap_wf_objkey]
    if not keyed:
        return {}
    statuses = await asyncio.to_thread(_read_statuses_blocking,
                                       [inv.sap_wf_objkey for inv in keyed])
    now = datetime.now(timezone.utc)
    changed = 0
    for inv in keyed:
        if apply_status(inv, statuses.get(inv.sap_wf_objkey), now):
            changed += 1
            logger.info("Invoice %s SAP workflow → %s (posted doc %s)%s", inv.id,
                        inv.sap_wf_status or "—", inv.sap_wf_posted_doc or "—",
                        f", error: {inv.sap_wf_message}" if inv.sap_wf_message else "")
    await db.commit()
    return {inv.id: statuses.get(inv.sap_wf_objkey) or {} for inv in keyed}


# ── Background poller (wired into main.lifespan) ────────────────────────────

_poll_task: asyncio.Task | None = None


async def due_for_refresh(db, limit: int = 200) -> list:
    """Parked invoices whose SAP workflow can still change: not read yet, INIT,
    BLK, or approved without a posted document yet. REJ and posted are final."""
    from sqlalchemy import and_, or_, select
    from app.models.invoice import Invoice

    return (await db.execute(
        select(Invoice).where(
            Invoice.is_deleted == 0,
            Invoice.status == "parked",
            Invoice.sap_wf_objkey.is_not(None),
            or_(Invoice.sap_wf_status.is_(None),
                Invoice.sap_wf_status.in_(["", WF_INIT, WF_BLK]),
                and_(Invoice.sap_wf_status == WF_APP, Invoice.sap_wf_posted_doc.is_(None))),
        ).order_by(Invoice.id).limit(limit)
    )).scalars().all()


async def _poll_loop():
    from app.database import async_session

    while True:
        await asyncio.sleep(settings.SAP_WF_POLL_SECONDS)
        try:
            async with async_session() as db:
                rows = await due_for_refresh(db)
                if rows:
                    await refresh_invoices(db, rows)
        except asyncio.CancelledError:
            raise
        except Exception:
            # SAP down, SAProuter timeout, wrong field names… — log and retry next round.
            logger.exception("SAP workflow status poll failed; retrying in %ss",
                             settings.SAP_WF_POLL_SECONDS)


def start_workflow_poller():
    global _poll_task
    if not (settings.SAP_ENABLED and settings.SAP_WORKFLOW_ENABLED
            and settings.SAP_WF_POLL_SECONDS > 0):
        return
    _poll_task = asyncio.create_task(_poll_loop())
    logger.info("SAP workflow status poller started (every %ss)", settings.SAP_WF_POLL_SECONDS)


async def stop_workflow_poller():
    global _poll_task
    if _poll_task:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
        _poll_task = None
