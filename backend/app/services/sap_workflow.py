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

# Logical name → SAP column. ZMIR7_WF_LOG is confirmed on AUP (RFC_READ_TABLE
# FIELDS, 2026-11-20): one row per workflow step, ITEM counting up; there is no
# posted-document column, because APP means SAP approved AND posted the invoice,
# which keeps its parked number (BELNR).
WF_LOG_FIELDS = {"objkey": "OBJKEY", "item": "ITEM", "status": "WF_STATUS",
                 "belnr": "BELNR", "erdat": "ERDAT", "erzet": "ERZET"}
# ZMIR7_ERROR_LOG, also confirmed on AUP (2026-11-20): it has NO OBJKEY — rows
# are keyed by document number + fiscal year (no company code). TYPE is
# S/E/W/I/A, ZMESSAGE the text (CHAR 220), CDATE/CTIME (CHAR) when it was
# logged. The newest row per document decides; Z_FROM is not used.
ERROR_LOG_FIELDS = {"belnr": "BELNR", "gjahr": "GJAHR", "type": "TYPE",
                    "message": "ZMESSAGE", "cdate": "CDATE", "ctime": "CTIME",
                    # used when ZMESSAGE is empty (seen on AUP for a rejection)
                    "msg_id": "ID", "msg_no": "ZNUMBER", "v1": "ZMESSAGE_V1",
                    "v2": "ZMESSAGE_V2", "v3": "ZMESSAGE_V3", "v4": "ZMESSAGE_V4"}

# ZMIR7_WF_LOG-WF_STATUS values (Lucky ABAP team, 2026-11-20). CHAR 3, so
# "INIT" may be stored as "INI"; both are read as WF_INIT.
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


def _container_row(element: str, value) -> dict:
    """One INPUT_CONTAINER row of SAP_WAPI_CREATE_EVENT. On AUP the table is
    typed SWR_CONT, whose only fields are ELEMENT (CHAR 32) and VALUE (CHAR 255):
    PyRFC refuses any other (TAB_INDEX / ELEMLENGTH / TYPE belong to the old
    SWCONT and were rejected, "field 'TAB_INDEX' not found", 2026-11-19)."""
    return {"ELEMENT": element.upper()[:32], "VALUE": str(value if value is not None else "")[:255]}


def raise_parking_event(sap, objkey: str, doc_number: str,
                        initiator_sap_user: str = "", initiator_email: str = "",
                        initiator_sap_pwd: str = "") -> dict:
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
    # The MIR7 workflow (exit ZXM08U30 / ZWF_LOGIN) authenticates the initiator
    # from the container: USERI = SAP user id, PWDI = that user's SAP password.
    # Both come from the logged-in VIM user (Admin -> Users). Without them the
    # approver resolves to 00000000 (nobody). Element names confirmed with Lucky
    # Cement's SAP team (2026-11-17). SAP user ids are upper-case.
    if initiator_sap_user:
        # The approver hierarchy matches USERI against the 8-digit personnel
        # number (PERNR, e.g. 00004007), so zero-pad a numeric id; leave an
        # alphanumeric SAP user id as-is. Confirmed with Lucky Cement's SAP team
        # (2026-11-17): "4007" resolved to nobody, "00004007" resolves correctly.
        _uid = initiator_sap_user.strip()
        container.append({"ELEMENT": "USERI", "VALUE": _uid.zfill(8) if _uid.isdigit() else _uid.upper()})
    if initiator_sap_pwd:
        container.append({"ELEMENT": "PWDI", "VALUE": initiator_sap_pwd})

    kwargs = dict(
        OBJECT_TYPE=settings.SAP_WF_OBJECT_TYPE,
        OBJECT_KEY=objkey,
        EVENT=event,
        COMMIT_WORK="",          # the caller commits park + event together
        # INPUT_CONTAINER, typed SWR_CONT (ELEMENT + VALUE) on AUP — the live
        # interface (2026-11-19, LAN box): TABLES INPUT_CONTAINER, MESSAGE_LINES,
        # MESSAGE_STRUCT. There is no SIMPLE_CONTAINER, and the rows take no
        # SWCONT fields (TAB_INDEX etc.); PyRFC refuses both. Commit 9aecc4b used
        # SIMPLE_CONTAINER, which only "worked" on Windows because the ctypes
        # path silently ignores an unknown table or field.
        input_tables={"INPUT_CONTAINER": [_container_row(r["ELEMENT"], r["VALUE"]) for r in container]},
        tables=["MESSAGE_LINES"],
        output_params=["RETURN_CODE", "EVENT_ID"],
    )
    # Technical-user model: TMC_VIM raises the event on behalf of the VIM user,
    # whose SAP id becomes the event creator (and so the workflow initiator).
    if initiator_sap_user:
        kwargs["USER"] = initiator_sap_user.strip().upper()

    # Diagnostic: exactly what VIM sends to SAP. PWDI (the initiator's SAP
    # password) is masked — never log it. Logged at WARNING on purpose so it
    # shows at the LAN box's default log level without --log-level info; revert
    # to debug/remove once the flow is verified.
    safe_container = {
        r["ELEMENT"]: ("***" if r["ELEMENT"] == "PWDI" else r["VALUE"]) for r in container
    }
    logger.warning(
        "[wf-diag] SAP_WAPI_CREATE_EVENT %s.%s objkey=%s USER=%s container=%s",
        settings.SAP_WF_OBJECT_TYPE, event, objkey, kwargs.get("USER", "(none)"),
        safe_container,
    )

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


def _message_text(row: dict) -> str:
    """ZMESSAGE, or, when SAP left it empty, "<class> <number>: <v1> <v2> <v3> <v4>"."""
    text = (row.get("message") or "").strip()
    if text:
        return text
    vars_ = " ".join(v for v in (row.get(k, "").strip() for k in ("v1", "v2", "v3", "v4")) if v)
    head = " ".join(p for p in (row.get("msg_id", "").strip(), row.get("msg_no", "").strip().lstrip("0")) if p)
    text = ": ".join(p for p in (head, vars_) if p)
    return text or "SAP logged an error without a message text"


def _read_error_log(sap, objkeys: list[str]) -> list[dict]:
    """ZMIR7_ERROR_LOG rows for these OBJKEYs, matched by BELNR + GJAHR (the
    table has no OBJKEY). Each row gets the "objkey" it belongs to."""
    by_doc = {(k[4:14], k[14:18]): k for k in objkeys if len(k) >= 18}
    if not by_doc:
        return []
    f = ERROR_LOG_FIELDS
    # One <=72-char OPTIONS row per document, OR-ed together.
    options = [{"TEXT": f"{'OR ' if i else ''}( {f['belnr']} = '{doc}' AND {f['gjahr']} = '{year}' ) "}
               for i, (doc, year) in enumerate(by_doc)]
    from app.services.sap_po_service import _parse_delimited_rows
    result = sap.call(
        "RFC_READ_TABLE",
        QUERY_TABLE=settings.SAP_WF_ERROR_TABLE or ERROR_LOG_TABLE,
        DELIMITER="|",
        input_tables={"OPTIONS": options,
                      "FIELDS": [{"FIELDNAME": c} for c in f.values()]},
        tables=["DATA", "FIELDS"],
        table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
    )
    back = {sap_col: logical for logical, sap_col in f.items()}
    rows = []
    for r in _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", [])):
        row = {back.get(k, k): (v or "").strip() for k, v in r.items()}
        row["objkey"] = by_doc.get((row.get("belnr", "").zfill(10), row.get("gjahr", "")), "")
        if row["objkey"]:
            rows.append(row)
    return rows


def read_workflow_status(sap, objkeys: list[str]) -> dict[str, dict]:
    """OBJKEY → {status, label, posted_doc, error}. Keys with no WF_LOG row are
    absent from the result (the workflow has not written anything yet)."""
    objkeys = [k for k in dict.fromkeys(objkeys) if k]
    out: dict[str, dict] = {}
    # Several rows per key (one per step): the newest step decides.
    latest: dict[str, dict] = {}
    for row in _read(sap, settings.SAP_WF_LOG_TABLE or WF_LOG_TABLE, WF_LOG_FIELDS, objkeys):
        key = (row.get("objkey") or "").strip()
        order = tuple((row.get(f) or "").strip() for f in ("erdat", "erzet", "item"))
        if key and (key not in latest or order >= latest[key]["_order"]):
            latest[key] = {**row, "_order": order}
    for key, row in latest.items():
        status = (row.get("status") or "").strip().upper()
        if status == "INI":
            status = WF_INIT
        out[key] = {
            "status": status,
            "label": WF_LABELS.get(status, status or "Unknown"),
            # APP = approved and posted by SAP, under the same document number.
            "posted_doc": ((row.get("belnr") or "").strip() or key[4:14]) if status == WF_APP else "",
            "error": "",
        }
    # The last row per key decides (the table has no timestamp we rely on, so
    # this trusts SAP's row order): an E row sets the error, an S row clears it.
    # If the error log can't be read, keep the workflow status rather than
    # failing the whole refresh.
    try:
        err_rows = _read_error_log(sap, objkeys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s not read: %s", settings.SAP_WF_ERROR_TABLE or ERROR_LOG_TABLE, exc)
        err_rows = []
    # Newest message per document decides (CDATE + CTIME; ties keep SAP's order).
    newest: dict[str, dict] = {}
    for row in err_rows:
        order = (row.get("cdate", ""), row.get("ctime", ""))
        if row["objkey"] not in newest or order >= newest[row["objkey"]]["_order"]:
            newest[row["objkey"]] = {**row, "_order": order}
    for key, row in newest.items():
        entry = out.setdefault(key, {"status": "", "label": "No workflow record",
                                     "posted_doc": "", "error": ""})
        kind = (row.get("type") or "").upper()
        if kind in ("E", "A"):
            entry["error"] = _message_text(row)
        elif kind == "S":
            entry["error"] = ""
    # APP normally means posted, but a posting error logged after it means SAP
    # approved and could not post: keep it parked and show the error.
    for entry in out.values():
        if entry["error"]:
            entry["posted_doc"] = ""
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
