"""SAP parking workflow (Lucky Cement) — park + event in one LUW, status read-back.

What it proves, on the fixture SAP, offline (no SAP, no Gemini, no network):
- with SAP_WORKFLOW_ENABLED off, parking is exactly what it was (no event call);
- with it on, parking raises SAP_WAPI_CREATE_EVENT (ZMIR7_PARK, COMMIT_WORK ' ',
  OBJKEY = company code + document + year) before the single commit;
- a refused event (no event name configured, or no approval hierarchy for the
  initiator) rolls the park back: nothing is left parked in SAP or in VIM;
- the status read from ZMIR7_WF_LOG / ZMIR7_ERROR_LOG drives VIM: BLK in
  approval, APP + posted document → "posted", APP + error → stays parked with
  the error, REJ → stays parked and can be unparked; BLK can't be unparked.

Uses its own throwaway SQLite database, recreated on every run.

    py -3 backend/test_sap_workflow.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before app.config is imported (the engine is built at import time).
SCRATCH = os.path.join(tempfile.gettempdir(), "sap_workflow_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["GEMINI_API_KEY"] = ""

from app.config import settings  # noqa: E402

settings.DEBUG = True
settings.SAP_MODE = "fake"
settings.SAP_ENABLED = True
settings.SAP_FAKE_DB_PATH = ""
settings.SAP_WORKFLOW_ENABLED = False
settings.SAP_WF_EVENT = ""
settings.SAP_WF_RAISE_EVENT = True        # sections 2-5: VIM raises the event (old mode)
settings.SAP_WF_POLL_SECONDS = 0          # the test drives refreshes itself

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.models.internal_user import InternalUser  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402
from app.services import sap_connector_fake as fake  # noqa: E402
from app.services.sap_workflow import build_objkey  # noqa: E402

PO = "4500009001"          # company code 1100, goods receipt in place — parks cleanly
LINE = {"description": "Split AC Unit 1.5 Ton Inverter", "quantity": 20, "unit": "ST",
        "unit_price": 185000, "amount": 3700000}
_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


# ── spy on what reaches "SAP" ────────────────────────────────────────────────

_calls = []
_real_call = fake.SAPConnectorFake.call


def _spy(self, function_name, **kwargs):
    _calls.append((function_name, kwargs))
    return _real_call(self, function_name, **kwargs)


fake.SAPConnectorFake.call = _spy


def _names():
    return [n for n, _ in _calls]


def _rbkp_count():
    return fake._store().execute("SELECT count(*) AS n FROM RBKP").fetchone()["n"]


# ── helpers over HTTP ────────────────────────────────────────────────────────

_po_id = None


def _po(client):
    global _po_id
    if _po_id is None:
        r = client.post(f"/api/sap/pos/{PO}/sync")
        expect(f"sync PO {PO} -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])
        _po_id = r.json().get("po_id") or r.json().get("id")
    return _po_id


def _new_invoice(client, tick_grs=True):
    r = client.post("/api/invoices/save", json={
        "original_filename": "wf.pdf", "stored_filepath": "demo/wf", "mime_type": "application/pdf",
        "invoice_number": f"WF-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
        "currency": "PKR", "document_type": "invoice", "status": "validated",
        "source_type": "upload", "po_reference": PO, "supplier_ntn": "0912345-6",
        "subtotal_amount": 3700000, "tax_amount": 0, "total_amount": 3700000,
        "line_items": [dict(LINE)],
    })
    inv_id = r.json()["id"]
    m = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": _po(client)})
    expect(f"match invoice {inv_id} -> 200 (got {m.status_code})", m.status_code == 200, m.text[:160])
    if tick_grs:        # the 20 units came in two GRs; every test invoice bills both
        client.put(f"/api/invoices/{inv_id}/parking-grs",
                   json={"gr_keys": ["2026/5000009001/0001", "2026/5000009006/0001"]})
    return inv_id


def _park(client, inv_id):
    _calls.clear()
    return client.post(f"/api/sap/invoices/{inv_id}/post",
                       json={"mode": "park", "tax_code": "2I", "layout": "goods",
                             "posting_date": "20260312"})


def _detail(client, inv_id):
    return client.get(f"/api/invoices/{inv_id}").json()


def _refresh(client, inv_id):
    return client.post(f"/api/sap/invoices/{inv_id}/workflow/refresh")


# ── 1. OBJKEY ────────────────────────────────────────────────────────────────

def test_objkey():
    print("\nUNIT: OBJKEY = company code(4) + document(10) + year(4)")
    expect("the example from SAP's test data", build_objkey("1200", "5105660614", "2027") == "120051056606142027")
    expect("document number is zero-padded", build_objkey("1100", "5105001", "2026") == "110000051050012026")
    try:
        build_objkey("11", "5105000001", "2026")
        expect("a short company code is refused", False)
    except ValueError:
        expect("a short company code is refused", True)


# ── 2. Workflow off: unchanged ───────────────────────────────────────────────

def test_off(client):
    print("\nOFF: parking is unchanged when SAP_WORKFLOW_ENABLED is false")
    settings.SAP_WORKFLOW_ENABLED = False
    inv = _new_invoice(client)
    r = _park(client, inv)
    expect(f"park -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
    expect("no workflow event was raised", "SAP_WAPI_CREATE_EVENT" not in _names(), _names())
    d = _detail(client, inv)
    expect("invoice is parked", d["status"] == "parked", d["status"])
    expect("and carries no workflow key", not d.get("sap_wf_objkey"), d.get("sap_wf_objkey"))


# ── 3. Refused events roll the park back ─────────────────────────────────────

def test_refusals(client):
    print("\nREFUSED: no event name configured -> nothing is parked")
    settings.SAP_WORKFLOW_ENABLED = True
    settings.SAP_WF_EVENT = ""
    inv = _new_invoice(client)
    before = _rbkp_count()
    r = _park(client, inv)
    expect(f"park -> 422 (got {r.status_code})", r.status_code == 422, r.text[:200])
    expect("message names the missing event setting", "SAP_WF_EVENT" in r.text, r.text[:200])
    expect("the BAPI ran, then was rolled back",
           "BAPI_INCOMINGINVOICE_PARK" in _names() and "BAPI_TRANSACTION_ROLLBACK" in _names()
           and "BAPI_TRANSACTION_COMMIT" not in _names(), _names())
    expect("no document left in SAP (RBKP unchanged)", _rbkp_count() == before)
    d = _detail(client, inv)
    expect("invoice is not parked in VIM", d["status"] == "validated" and not d.get("sap_document_number"),
           (d["status"], d.get("sap_document_number")))

    print("\nREFUSED: no approval hierarchy for the initiator -> nothing is parked")
    settings.SAP_WF_EVENT = "PARKED"
    from app.services.sap_invoice_post import post_invoice_to_sap
    before = _rbkp_count()
    _calls.clear()
    res = post_invoice_to_sap(
        invoice_number=f"WF-{uuid.uuid4().hex[:6]}", invoice_date="2026-03-12", posting_date="2026-03-12",
        vendor_number="0002000101", company_code="1100", currency="PKR", gross_amount=3700000,
        tax_amount=0, po_number=PO, line_items=[{"po_item": 10, "amount": 3700000, "quantity": 20,
                                                 "po_unit": "ST"}],
        tax_code="2I", mode="park", workflow=True, initiator_sap_user="nohier")
    expect("park is reported as failed", res["success"] is False, res.get("message"))
    expect("with SAP's hierarchy message", "hierarchy" in res["message"].lower(), res["message"])
    expect("the event was raised as the VIM user's SAP id",
           any(n == "SAP_WAPI_CREATE_EVENT" and k.get("USER") == "NOHIER" for n, k in _calls))
    expect("and the park rolled back (RBKP unchanged)", _rbkp_count() == before)
    expect("no workflow row was left behind",
           fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG").fetchone()["n"] == 0)


# ── 4. The happy path and the outcomes ───────────────────────────────────────

def _park_with_workflow(client, label):
    settings.SAP_WORKFLOW_ENABLED = True
    settings.SAP_WF_EVENT = "PARKED"
    inv = _new_invoice(client)
    r = _park(client, inv)
    expect(f"{label}: park -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
    return inv, _detail(client, inv)


def test_flow(client):
    print("\nFLOW: park raises the event in the same LUW")
    inv, d = _park_with_workflow(client, "approve case")
    names = _names()
    expect("order: park, event, commit",
           [n for n in names if n in ("BAPI_INCOMINGINVOICE_PARK", "SAP_WAPI_CREATE_EVENT",
                                      "BAPI_TRANSACTION_COMMIT")]
           == ["BAPI_INCOMINGINVOICE_PARK", "SAP_WAPI_CREATE_EVENT", "BAPI_TRANSACTION_COMMIT"], names)
    ev = next(k for n, k in _calls if n == "SAP_WAPI_CREATE_EVENT")
    objkey = d.get("sap_wf_objkey") or ""
    expect("OBJKEY = 1100 + document + year",
           objkey == build_objkey("1100", d["sap_document_number"], d["sap_fiscal_year"]), objkey)
    expect("event: object ZMIR7_PARK, our OBJKEY, event name from settings",
           (ev["OBJECT_TYPE"], ev["OBJECT_KEY"], ev["EVENT"]) == ("ZMIR7_PARK", objkey, "PARKED"), ev)
    expect("event does NOT commit by itself", ev["COMMIT_WORK"] == "", ev["COMMIT_WORK"])
    rows = ev["input_tables"]["INPUT_CONTAINER"]
    expect("event sends INPUT_CONTAINER (AUP has no SIMPLE_CONTAINER)",
           "SIMPLE_CONTAINER" not in ev["input_tables"], list(ev["input_tables"]))
    expect("every row is SWR_CONT: exactly ELEMENT + VALUE (AUP refuses TAB_INDEX etc.)",
           all(set(r) == {"ELEMENT", "VALUE"} and r["ELEMENT"] for r in rows), rows)
    container = {r["ELEMENT"]: r["VALUE"] for r in rows}
    expect("container carries OBJKEY, D_NO, LEVEL, TOTALAPP, SCENARIO_CHAR, INIEMAIL",
           container.get("OBJKEY") == objkey and container.get("D_NO") == d["sap_document_number"].zfill(10)
           and {"LEVEL", "TOTALAPP", "SCENARIO_CHAR"} <= set(container)
           and container.get("INIEMAIL") == "purchaser@lucky.test", container)
    expect("without a personal SAP id, no USER is sent (TMC_VIM raises it)", "USER" not in ev, ev.get("USER"))

    r = _refresh(client, inv)
    expect(f"refresh -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
    expect("SAP says: in approval (BLK)", r.json().get("sap_wf_status") == "BLK", r.json())
    expect("label reads 'In SAP approval'", r.json().get("sap_wf_label") == "In SAP approval", r.json())

    u = client.post(f"/api/sap/invoices/{inv}/unpark")
    expect(f"unpark during approval -> 409 (got {u.status_code})", u.status_code == 409, u.text[:200])

    print("\nAPPROVED: SAP posts it, VIM follows")
    fake.decide_workflow(objkey, approve=True)
    r = _refresh(client, inv).json()
    expect("status APP with the posted document", r["sap_wf_status"] == "APP"
           and r["sap_wf_posted_doc"] == d["sap_document_number"], r)
    d2 = _detail(client, inv)
    expect("invoice is now POSTED in VIM", d2["status"] == "posted" and d2["sap_doc_status"] == "posted",
           (d2["status"], d2["sap_doc_status"]))

    print("\nAPPROVED BUT POSTING FAILED: stays parked, shows SAP's error")
    inv, d = _park_with_workflow(client, "posting-error case")
    fake.decide_workflow(d["sap_wf_objkey"], approve=True, error="Posting period 03 2026 is not open")
    r = _refresh(client, inv).json()
    expect("APP, no posted document, error text", r["sap_wf_status"] == "APP" and not r["sap_wf_posted_doc"]
           and "Posting period" in (r["sap_wf_message"] or ""), r)
    expect("invoice is still parked", r["status"] == "parked", r["status"])

    print("\nREJECTED: stays parked, can be unparked")
    inv, d = _park_with_workflow(client, "reject case")
    fake.decide_workflow(d["sap_wf_objkey"], approve=False)
    r = _refresh(client, inv).json()
    expect("REJ, 'Rejected in SAP'", r["sap_wf_status"] == "REJ" and r["sap_wf_label"] == "Rejected in SAP", r)
    expect("invoice is still parked", r["status"] == "parked", r["status"])
    u = client.post(f"/api/sap/invoices/{inv}/unpark")
    expect(f"unpark a rejected invoice -> 200 (got {u.status_code})", u.status_code == 200, u.text[:200])
    d3 = _detail(client, inv)
    expect("unparking clears the workflow fields", not d3.get("sap_wf_objkey") and not d3.get("sap_wf_status"),
           (d3.get("sap_wf_objkey"), d3.get("sap_wf_status")))

    r = _refresh(client, inv)
    expect(f"refresh without a workflow -> 409 (got {r.status_code})", r.status_code == 409, r.text[:160])


# ── 5. What the background poller picks up ───────────────────────────────────

def test_poller_selection(client):
    print("\nPOLLER: only workflows that can still change are re-read")
    import asyncio
    from app.database import async_session
    from app.services.sap_workflow import due_for_refresh, refresh_invoices

    # Invoices so far: 1 parked without workflow, 2 refused, 3 posted by SAP,
    # 4 approved but SAP's posting failed, 5 rejected then unparked.
    waiting, d = _park_with_workflow(client, "poller case")    # BLK, never read

    async def run():
        async with async_session() as db:
            due = {i.id for i in await due_for_refresh(db)}
            expect("a fresh workflow (never read) is due", waiting in due, due)
            expect("approved-but-not-posted (4) is due", 4 in due, due)
            expect("no workflow / refused / posted / unparked (1, 2, 3, 5) are not",
                   not ({1, 2, 3, 5} & due), due)
            fake.decide_workflow(d["sap_wf_objkey"], approve=True)
            rows = await due_for_refresh(db)
            await refresh_invoices(db, rows)            # what one poller round does
        async with async_session() as db:
            due = {i.id for i in await due_for_refresh(db)}
            expect("after a round, the now-posted invoice drops out", waiting not in due, due)

    asyncio.run(run())
    expect("and VIM shows it posted", _detail(client, waiting)["status"] == "posted",
           _detail(client, waiting)["status"])


def test_sap_raises(client):
    """Default on Lucky: SAP raises the event inside ZMIR7_PARK. VIM must not
    raise a second one (that started the workflow twice), but still tracks it."""
    print("\nSAP RAISES THE EVENT ITSELF (SAP_WF_RAISE_EVENT=false, the default)")
    settings.SAP_WORKFLOW_ENABLED = True
    settings.SAP_WF_RAISE_EVENT = False
    settings.SAP_WF_EVENT = ""                # not needed in this mode
    try:
        inv = _new_invoice(client)
        r = _park(client, inv)
        expect(f"park -> 200 without SAP_WF_EVENT (got {r.status_code})", r.status_code == 200, r.text[:200])
        names = _names()
        expect("VIM does NOT call SAP_WAPI_CREATE_EVENT (no second workflow)",
               "SAP_WAPI_CREATE_EVENT" not in names, names)
        expect("park then one commit",
               [n for n in names if n in ("BAPI_INCOMINGINVOICE_PARK", "BAPI_TRANSACTION_COMMIT")]
               == ["BAPI_INCOMINGINVOICE_PARK", "BAPI_TRANSACTION_COMMIT"], names)
        d = _detail(client, inv)
        objkey = d.get("sap_wf_objkey") or ""
        expect("OBJKEY still stored, so the status can be read",
               objkey == build_objkey("1100", d["sap_document_number"], d["sap_fiscal_year"]), objkey)
        rows = fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG WHERE OBJKEY = ?",
                                     (objkey,)).fetchone()["n"]
        expect("exactly one workflow for the document", rows == 1, rows)
        rr = _refresh(client, inv)
        expect("refresh reads SAP's workflow: BLK", rr.status_code == 200
               and rr.json().get("sap_wf_status") == "BLK", rr.text[:200])
        fake.decide_workflow(objkey, approve=True)
        expect("SAP approves and posts -> VIM shows posted",
               _refresh(client, inv).json().get("sap_wf_status") == "APP"
               and _detail(client, inv)["status"] == "posted", _detail(client, inv)["status"])

        print("\nSUBMIT DRY RUN while SAP raises the event: never reaches SAP")
        inv2 = _new_invoice(client)
        wf_before = fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG").fetchone()["n"]
        _calls.clear()
        v = client.post(f"/api/sap/invoices/{inv2}/post", json={"mode": "validate"})
        expect(f"validate -> 200 ok, marked skipped_sap (got {v.status_code})",
               v.status_code == 200 and v.json().get("ok") is True and v.json().get("skipped_sap") is True,
               v.text[:200])
        expect("no park BAPI called by the dry run", "BAPI_INCOMINGINVOICE_PARK" not in _names(), _names())
        wf_after = fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG").fetchone()["n"]
        expect("no stray workflow from the dry run", wf_after == wf_before, (wf_before, wf_after))
        settings.SAP_WF_DRY_RUN_SAFE = True
        _calls.clear()
        v = client.post(f"/api/sap/invoices/{inv2}/post", json={"mode": "validate"})
        expect("SAP_WF_DRY_RUN_SAFE=true: the SAP dry run runs again (park + rollback)",
               v.status_code == 200 and "skipped_sap" not in v.json()
               and "BAPI_INCOMINGINVOICE_PARK" in _names() and "BAPI_TRANSACTION_ROLLBACK" in _names(),
               (v.text[:200], _names()))
        hdr = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")["input_structures"]["HEADERDATA"]
        expect("dry run sends BKTXT = VALIDATE (ABAP raises no event for it)",
               hdr["HEADER_TXT"] == "VALIDATE", hdr["HEADER_TXT"])
        wf_dry = fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG").fetchone()["n"]
        expect("still no stray workflow after the SAP dry run", wf_dry == wf_before, (wf_before, wf_dry))
        _calls.clear()
        r2 = _park(client, inv2)
        hdr = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")["input_structures"]["HEADERDATA"]
        expect("the real park does not send VALIDATE", r2.status_code == 200 and hdr["HEADER_TXT"] != "VALIDATE",
               (r2.status_code, hdr["HEADER_TXT"]))
        wf_real = fake._store().execute("SELECT count(*) AS n FROM ZMIR7_WF_LOG").fetchone()["n"]
        expect("the real park starts exactly one workflow", wf_real == wf_before + 1, (wf_before, wf_real))
    finally:
        settings.SAP_WF_RAISE_EVENT = True
        settings.SAP_WF_DRY_RUN_SAFE = False


def test_resubmit(client):
    """A REJECTED parked invoice is changed in place (same document) and SAP
    restarts its workflow: REJ -> BLK. Anything not rejected can't be."""
    print("\nRESUBMIT A REJECTED INVOICE (BAPI_INCOMINGINVOICE_CHANGE)")
    settings.SAP_WORKFLOW_ENABLED = True
    settings.SAP_WF_RAISE_EVENT = False
    try:
        inv = _new_invoice(client)
        r = _park(client, inv)
        expect(f"park -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
        d = _detail(client, inv)
        doc, objkey = d["sap_document_number"], d["sap_wf_objkey"]

        _calls.clear()
        c = client.post(f"/api/sap/invoices/{inv}/post", json={"mode": "change", "tax_code": "2I"})
        expect(f"change while BLK -> 409 (got {c.status_code})", c.status_code == 409, c.text[:200])
        expect("...and nothing sent to SAP", "BAPI_INCOMINGINVOICE_CHANGE" not in _names(), _names())

        fake.decide_workflow(objkey, approve=False)
        expect("SAP rejected it", _refresh(client, inv).json().get("sap_wf_status") == "REJ")

        _calls.clear()
        c = client.post(f"/api/sap/invoices/{inv}/post", json={"mode": "change", "tax_code": "2I"})
        expect(f"change while REJ -> 200 (got {c.status_code})", c.status_code == 200, c.text[:300])
        names = _names()
        expect("change BAPI then one commit, no park, no event",
               "BAPI_INCOMINGINVOICE_CHANGE" in names and "BAPI_TRANSACTION_COMMIT" in names
               and "BAPI_INCOMINGINVOICE_PARK" not in names and "SAP_WAPI_CREATE_EVENT" not in names, names)
        kw = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_CHANGE")
        expect("same document and year", (kw["INVOICEDOCNUMBER"], kw["FISCALYEAR"]) == (doc.zfill(10), d["sap_fiscal_year"]),
               (kw["INVOICEDOCNUMBER"], kw["FISCALYEAR"]))
        hdr = kw["input_structures"]["HEADERDATA_CHANGE"]
        expect("header has no company code / doc type, and every field is flagged in CHANGEX",
               "COMP_CODE" not in hdr and "DOC_TYPE" not in hdr
               and set(kw["input_structures"]["HEADERDATA_CHANGEX"]) == set(hdr), hdr)
        expect("items and tax replaced (TABLE_CHANGE)",
               kw["input_structures"]["TABLE_CHANGE"] == {"ITEMDATA": "X", "TAXDATA": "X"})
        expect("BKTXT is not the dry-run marker", hdr.get("HEADER_TXT") != "VALIDATE", hdr.get("HEADER_TXT"))
        d2 = _detail(client, inv)
        expect("still parked, same document", d2["status"] == "parked" and d2["sap_document_number"] == doc,
               (d2["status"], d2["sap_document_number"]))
        expect("SAP's initial '0000' year is not stored; OBJKEY unchanged",
               d2["sap_fiscal_year"] == d["sap_fiscal_year"] and d2["sap_wf_objkey"] == objkey,
               (d2["sap_fiscal_year"], d2["sap_wf_objkey"], objkey))
        expect("SAP restarted the workflow: BLK", _refresh(client, inv).json().get("sap_wf_status") == "BLK")
    finally:
        settings.SAP_WF_RAISE_EVENT = True


def test_unit_from_po(client):
    """Observation B: an invoice line with no unit takes its PO line's unit at
    PO match; a unit the invoice printed is kept."""
    print("\nUNIT OF MEASURE FROM THE PO")
    for given, label in ((None, "no unit on the invoice -> PO's unit"), ("KG", "invoice unit KG is kept")):
        line = dict(LINE)
        line["unit"] = given
        r = client.post("/api/invoices/save", json={
            "original_filename": "uom.pdf", "stored_filepath": "demo/uom", "mime_type": "application/pdf",
            "invoice_number": f"UOM-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
            "currency": "PKR", "document_type": "invoice", "status": "validated",
            "source_type": "upload", "po_reference": PO, "supplier_ntn": "0912345-6",
            "subtotal_amount": 3700000, "tax_amount": 0, "total_amount": 3700000, "line_items": [line],
        })
        inv = r.json()["id"]
        m = client.post(f"/api/po-matching/invoices/{inv}/match", json={"po_id": _po(client)})
        unit = (_detail(client, inv)["line_items"][0].get("unit") or "")
        expect(f"{label} (got {unit!r})", m.status_code == 200 and unit == (given or "ST"), m.text[:150])

    import sqlite3
    db_path = settings.DATABASE_URL.split("///", 1)[-1]

    def sql(q, *a):
        with sqlite3.connect(db_path) as c:
            return c.execute(q, a).fetchall()

    def save(desc, qty, price):
        r = client.post("/api/invoices/save", json={
            "original_filename": "opu.pdf", "stored_filepath": "demo/opu", "mime_type": "application/pdf",
            "invoice_number": f"OPU-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
            "currency": "PKR", "document_type": "invoice", "status": "validated",
            "source_type": "upload", "po_reference": f"PO {PO}", "supplier_ntn": "0912345-6",
            "subtotal_amount": qty * price, "tax_amount": 0, "total_amount": qty * price,
            "line_items": [{"description": desc, "quantity": qty, "unit_price": price, "amount": qty * price}],
        })
        return r.json()["id"]

    def unit_of(inv):
        return _detail(client, inv)["line_items"][0].get("unit")

    po_id = _po(client)
    # A PO synced before price_unit existed: read from SAP at the next match.
    sql("UPDATE po_line_items SET price_unit = NULL WHERE po_id = ?", po_id)
    inv = save("Deep Freezer 500L", 5, 240000)
    client.post(f"/api/po-matching/invoices/{inv}/match", json={"po_id": po_id})
    expect(f"the unit is the OPU (EA), not the order unit (ST) (got {unit_of(inv)!r})", unit_of(inv) == "EA")
    expect("...and the PO line now has both units",
           sql("SELECT unit, price_unit FROM po_line_items WHERE po_id = ? AND item_number = 20", po_id) == [("ST", "EA")])
    # Matched before the unit was filled at match: shown from the pairing.
    sql("UPDATE invoice_line_items SET unit = NULL WHERE invoice_id = ?", inv)
    expect("matched earlier, unit never stored -> still shown from the PO", unit_of(inv) == "EA", unit_of(inv))
    # Not matched yet: the PO number on the invoice, only when its items share one unit.
    inv = save("Something else", 1, 100)
    expect("not matched, PO items differ in unit -> left empty", not unit_of(inv), unit_of(inv))
    sql("UPDATE po_line_items SET price_unit = 'ST' WHERE po_id = ? AND item_number = 20", po_id)
    expect("not matched, one unit on the whole PO -> shown", unit_of(inv) == "ST", unit_of(inv))
    sql("UPDATE po_line_items SET price_unit = 'EA' WHERE po_id = ? AND item_number = 20", po_id)


def test_gr_selection(client):
    """Observation F: list the PO's open GRs, tick some, park one ITEMDATA row
    per ticked GR (REF_DOC = that GR); a selection that doesn't add up refuses."""
    print("\nGR-WISE PARKING (select goods receipts)")
    settings.SAP_WORKFLOW_ENABLED = False
    inv = _new_invoice(client, tick_grs=False)   # PO 4500009001 item 10, 20 units
    import sqlite3
    db_path = settings.DATABASE_URL.split("///", 1)[-1]

    def sql(q, *a):
        with sqlite3.connect(db_path) as c:
            c.execute(q, a)

    sql("UPDATE invoices SET parking_gr_refs = NULL")      # the earlier tests' ticks
    r = client.get(f"/api/sap/invoices/{inv}/open-grs")
    grs = r.json().get("grs", [])
    item10 = [g for g in grs if g["po_item"] == 10]
    expect(f"open GRs listed (got {r.status_code}, {len(grs)})", r.status_code == 200 and len(item10) == 2,
           [(g["gr_key"], g["open_qty"]) for g in grs])
    expect("each GR has description/unit from the PO", all(g.get("unit") for g in item10), item10)

    def og(i):
        return client.get(f"/api/sap/invoices/{i}/open-grs").json()

    both = sorted(g["gr_key"] for g in item10)
    body = r.json()
    expect("12 + 8 = the 20 billed, nothing chosen yet -> both suggested, the other PO item not",
           body["chosen"] is False and sorted(body["suggested"]) == both, (body["chosen"], body["suggested"]))
    sql("UPDATE invoice_line_items SET quantity = 15 WHERE invoice_id = ?", inv)
    b = og(inv)
    expect("15 billed against 20 open -> nothing suggested, and why",
           b["suggested"] == [] and "add up to 20" in (b["why_not"] or "") and "bills 15" in b["why_not"], (b["suggested"], b["why_not"]))
    sql("UPDATE invoice_line_items SET quantity = 20 WHERE invoice_id = ?", inv)
    sql("UPDATE invoices SET parking_line_item_ids = '[999999]' WHERE id = ?", inv)
    expect("saved line ids that no longer exist are ignored", sorted(og(inv)["suggested"]) == both, og(inv))
    sql("UPDATE invoices SET parking_line_item_ids = NULL WHERE id = ?", inv)
    client.put(f"/api/invoices/{inv}/parking-grs", json={"gr_keys": []})
    expect("all unticked by the user -> remembered, not ticked again",
           og(inv)["chosen"] is True and og(inv)["selected"] == [], og(inv))
    expect("...stored as an empty selection", _detail(client, inv).get("parking_gr_refs") == [])
    inv2 = _new_invoice(client, tick_grs=False)
    client.put(f"/api/invoices/{inv2}/parking-grs", json={"gr_keys": both[:1]})
    b = og(inv)
    expect("a GR ticked on another open invoice -> not suggested, the invoice is named",
           b["suggested"] == [] and f"(#{inv2})" in (b["why_not"] or ""), (b["suggested"], b["why_not"]))
    client.delete(f"/api/invoices/{inv2}")
    expect("...and suggested again once that invoice is deleted", sorted(og(inv)["suggested"]) == both, og(inv)["suggested"])
    conn = fake._store()
    conn.execute("INSERT INTO EKBE (EBELN, EBELP, GJAHR, BELNR, BUZEI, VGABE, BWART, BUDAT, MENGE, DMBTR, SHKZG, LFGJA, LFBNR, LFPOS) "
                 "VALUES (?,'00010','2026','5100099999','0001','P','','20260301','8','1','S','2026','5000009006','0001')", (PO,))
    conn.commit()
    b = og(inv)
    expect("a GR with a parked SAP invoice -> not suggested, the document is named",
           b["suggested"] == [] and "5100099999" in (b["why_not"] or ""), (b["suggested"], b["why_not"]))
    conn.execute("DELETE FROM EKBE WHERE BELNR = '5100099999'")
    conn.commit()

    # Nothing ticked: 20 billed do not fit the latest GR (8 open).
    p = _park(client, inv)
    expect(f"user unticked all, bill is more than the latest GR -> refused (got {p.status_code})",
           p.status_code == 422 and "8 open" in p.text and "BAPI_INCOMINGINVOICE_PARK" not in _names(), p.text[:220])
    # Never opened in the browser (NULL): the park uses what the card would tick.
    auto = _new_invoice(client, tick_grs=False)
    p = _park(client, auto)
    expect(f"nobody chose -> parked on both GRs (got {p.status_code})", p.status_code == 200, p.text[:200])
    kw = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")
    expect("...one row per GR", sorted(x["REF_DOC"] for x in kw["input_tables"]["ITEMDATA"]) == ["5000009001", "5000009006"],
           kw["input_tables"]["ITEMDATA"])
    expect("...and remembered on the invoice", sorted(_detail(client, auto)["parking_gr_refs"]) == both,
           _detail(client, auto).get("parking_gr_refs"))
    late = _new_invoice(client, tick_grs=False)
    p = _park(client, late)
    expect(f"the same GRs for another invoice -> not taken silently, refused (got {p.status_code})",
           p.status_code == 422 and "Tick the goods receipts" in p.text, p.text[:200])
    # Rejected in SAP: the card may tick again, and the invoice's own parked rows don't block it.
    own = _detail(client, auto)["sap_document_number"]
    expect("in SAP and not rejected -> no suggestion", og(auto)["suggested"] == [], og(auto)["suggested"])
    sql("UPDATE invoices SET sap_wf_status = 'REJ', parking_gr_refs = NULL WHERE id = ?", auto)
    conn.execute("INSERT INTO EKBE (EBELN, EBELP, GJAHR, BELNR, BUZEI, VGABE, BWART, BUDAT, MENGE, DMBTR, SHKZG, LFGJA, LFBNR, LFPOS) "
                 "VALUES (?,'00010','2026',?,'0001','P','','20260301','20','1','S','2026','5000009006','0001')", (PO, own))
    conn.commit()
    expect("rejected -> suggested again, its own parked row ignored", sorted(og(auto)["suggested"]) == both, og(auto)["suggested"])
    expect("...but for another invoice that parked row blocks", og(late)["suggested"] == [], og(late)["suggested"])
    conn.execute("DELETE FROM EKBE WHERE BELNR = ? AND VGABE = 'P'", (own,))
    conn.commit()
    client.delete(f"/api/invoices/{late}")

    one = [item10[0]["gr_key"]]
    s = client.put(f"/api/invoices/{inv}/parking-grs", json={"gr_keys": one})
    expect("selection saved", s.status_code == 200 and _detail(client, inv).get("parking_gr_refs") == one,
           _detail(client, inv).get("parking_gr_refs"))
    p = _park(client, inv)
    expect(f"12 of 20 selected -> park refused with the reason (got {p.status_code})",
           p.status_code == 422 and "add up" in p.text, p.text[:200])
    expect("...and nothing parked", "BAPI_INCOMINGINVOICE_PARK" not in _names(), _names())

    both = [g["gr_key"] for g in item10]
    client.put(f"/api/invoices/{inv}/parking-grs", json={"gr_keys": both})
    p = _park(client, inv)
    expect(f"12 + 8 selected -> park 200 (got {p.status_code})", p.status_code == 200, p.text[:200])
    kw = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")
    rows = kw["input_tables"]["ITEMDATA"]
    got = sorted((r["REF_DOC"], r["QUANTITY"], r["ITEM_AMOUNT"]) for r in rows)
    expect("one ITEMDATA row per GR, own REF_DOC, quantity and amount",
           got == [("5000009001", "12.0", "2220000.0"), ("5000009006", "8.0", "1480000.0")], got)
    expect("in SAP -> no suggestion any more", og(inv)["suggested"] == [], og(inv)["suggested"])


def test_delivery_costs(client):
    """Planned delivery costs: explicit choice, own tax code, the ticked GRs' share,
    and never more than the vendor billed."""
    print("\nPLANNED DELIVERY COSTS (freight)")
    from app.services.sap_po_service import delivery_for_grs, fetch_delivery_costs, fetch_gr_overview
    settings.SAP_WORKFLOW_ENABLED = False

    def new(total, tax=0):
        r = client.post("/api/invoices/save", json={
            "original_filename": "fr.pdf", "stored_filepath": "demo/fr", "mime_type": "application/pdf",
            "invoice_number": f"FR-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
            "currency": "PKR", "document_type": "invoice", "status": "validated",
            "source_type": "upload", "po_reference": PO, "supplier_ntn": "0912345-6",
            "subtotal_amount": total - tax, "tax_amount": tax, "total_amount": total, "line_items": [dict(LINE)],
        })
        i = r.json()["id"]
        client.post(f"/api/po-matching/invoices/{i}/match", json={"po_id": _po(client)})
        client.put(f"/api/invoices/{i}", json={"sap_layout": "both"})
        client.put(f"/api/invoices/{i}/parking-grs",
                   json={"gr_keys": ["2026/5000009001/0001", "2026/5000009006/0001"]})
        return i

    def choose(i, code="I0"):
        return client.put(f"/api/invoices/{i}/delivery-costs",
                          json={"items": [{"po_item": 10, "cond_type": "FRA1", "tax_code": code}]})

    def park(i):
        _calls.clear()
        return client.post(f"/api/sap/invoices/{i}/post", json={"mode": "park", "tax_code": "2I", "layout": "both",
                                                               "posting_date": "20260312"})

    def sent():
        kw = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")
        rows = kw["input_tables"]["ITEMDATA"]
        return ([(r["COND_TYPE"], r["QUANTITY"], r["ITEM_AMOUNT"], r["TAX_CODE"]) for r in rows if r.get("COND_TYPE")],
                kw["input_tables"]["TAXDATA"], kw["input_structures"]["HEADERDATA"]["GROSS_AMOUNT"],
                {r["TAX_CODE"] for r in rows if not r.get("COND_TYPE")})

    inv = new(4391000, 666000)
    expect("layout saved", _detail(client, inv).get("sap_layout") == "both", _detail(client, inv).get("sap_layout"))
    p = park(inv)
    expect(f"nothing chosen -> refused (got {p.status_code})", p.status_code == 422 and "Choose" in p.text, p.text[:200])
    b = client.get(f"/api/sap/invoices/{inv}/delivery-costs").json()
    expect("the PO's freight is listed with vendor and amount",
           [(c["cond_type"], c["park_amount"], c["park_quantity"], c["other_vendor"]) for c in b["costs"]]
           == [("FRA1", 25000.0, 20.0, False)], b)
    r = choose(inv, "")
    expect(f"no tax code -> refused (got {r.status_code})", r.status_code == 400, r.text[:150])
    choose(inv)
    expect("choice saved", _detail(client, inv).get("sap_delivery")
           == [{"po_item": 10, "cond_type": "FRA1", "tax_code": "I0"}], _detail(client, inv).get("sap_delivery"))
    p = park(inv)
    expect(f"goods + 18% + freight 25,000 = billed -> park 200 (got {p.status_code})", p.status_code == 200, p.text[:200])
    fr, tax, gross, goods_codes = sent()
    expect("freight row with its own tax code", fr == [("FRA1", "20.0", "25000.0", "I0")] and goods_codes == {"2I"}, (fr, goods_codes))

    expect("18% goods + untaxed freight: one tax row, right total",
           tax == [{"TAX_CODE": "2I", "TAX_AMOUNT": "666000.0"}] and float(gross) == 4391000, (tax, gross))
    again = new(4391000, 666000)
    choose(again)
    p = park(again)
    expect(f"the same GRs' freight on a second invoice -> refused by name (got {p.status_code})",
           p.status_code == 422 and "already on invoice" in p.text, p.text[:200])
    client.delete(f"/api/invoices/{again}")

    import sqlite3
    db_path = settings.DATABASE_URL.split("///", 1)[-1]

    def forget():        # the earlier invoices' freight and GR choices
        with sqlite3.connect(db_path) as c:
            c.execute("UPDATE invoices SET sap_delivery = NULL, parking_gr_refs = NULL")
    forget()
    # Both taxed, different codes -> a TAXDATA row per code.
    inv = new(3700000 + 666000 + 25000 + 4250, 670250)
    choose(inv, "I2")
    p = park(inv)
    fr, tax, gross, _g = sent() if p.status_code == 200 else (None, None, None, None)
    expect("freight at 17%: its own TAXDATA row",
           p.status_code == 200 and tax == [{"TAX_CODE": "2I", "TAX_AMOUNT": "666000.0"},
                                            {"TAX_CODE": "I2", "TAX_AMOUNT": "4250.0"}], (p.text[:150], tax))

    forget()
    # The invoice bills goods only (Lucky's invoice 151): never park the freight on top.
    inv = new(4366000, 666000)
    choose(inv)
    p = park(inv)
    expect(f"freight not on the invoice -> refused with both totals (got {p.status_code})",
           p.status_code == 422 and "4,391,000.00" in p.text and "4,366,000.00" in p.text
           and "BAPI_INCOMINGINVOICE_PARK" not in _names(), p.text[:250])

    # Another vendor's freight, per-GR shares, reversals, invoiced and parked rows.
    conn = fake._store()
    conn.execute("UPDATE EKBZ SET LIFNR = '0002000102' WHERE EBELN = ?", (PO,))
    conn.commit()
    p = park(inv)
    expect(f"another vendor's freight -> refused (got {p.status_code})", p.status_code == 422 and "2000102" in p.text, p.text[:200])
    expect("...and flagged in the card",
           client.get(f"/api/sap/invoices/{inv}/delivery-costs").json()["costs"][0]["other_vendor"] is True)
    conn.execute("UPDATE EKBZ SET LIFNR = '0002000101' WHERE EBELN = ?", (PO,))
    conn.commit()
    client.put(f"/api/invoices/{inv}/parking-grs", json={"gr_keys": ["2026/5000009006/0001"]})
    c = client.get(f"/api/sap/invoices/{inv}/delivery-costs").json()["costs"][0]
    expect("only the ticked GR's freight", (c["park_amount"], c["park_quantity"]) == (10000.0, 8.0), c)
    conn.execute("INSERT INTO EKBZ (EBELN, EBELP, VGABE, SHKZG, GJAHR, BELNR, BUZEI, LIFNR, KSCHL, MENGE, DMBTR, WAERS) VALUES "
                 "(?,'00010','1','H','2026','5000009099','0001','','FRA1','8','10000','PKR')", (PO,))
    conn.commit()
    cost = fetch_delivery_costs(PO, fetch_gr_overview(PO))[0]
    expect("a reversal takes the freight back", cost["amount"] == 15000.0 and cost["quantity"] == 12.0, cost)
    try:
        delivery_for_grs(cost, ["2026/5000009001/0001"])
        expect("a reversal SAP ties to no known GR -> the ticked share is not guessed", False)
    except ValueError as exc:
        expect("a reversal SAP ties to no known GR -> the ticked share is not guessed", "unassigned" in str(exc), exc)
    conn.execute("DELETE FROM EKBZ WHERE BELNR = '5000009099'")
    conn.execute("INSERT INTO EKBZ (EBELN, EBELP, VGABE, SHKZG, GJAHR, BELNR, BUZEI, LIFNR, KSCHL, MENGE, DMBTR, WAERS) VALUES "
                 "(?,'00010','2','S','2026','5105000777','0001','','FRA1','12','15000','PKR')", (PO,))
    conn.commit()
    cost = fetch_delivery_costs(PO, fetch_gr_overview(PO))[0]
    expect("invoiced freight is no longer open", (cost["amount"], cost["quantity"]) == (10000.0, 8.0), cost)
    try:
        delivery_for_grs(cost, ["2026/5000009001/0001"])
        expect("more than still open -> refused", False)
    except ValueError as exc:
        expect("more than still open -> refused", "still" in str(exc), exc)
    conn.execute("DELETE FROM EKBZ WHERE BELNR = '5105000777'")
    # Two-step receipt: the 105 accrues the freight, it belongs to the 103.
    for doc, bw, ref in (("5000000200", "103", ""), ("5000000201", "105", "5000000200")):
        conn.execute("INSERT INTO EKBE (EBELN, EBELP, GJAHR, BELNR, BUZEI, VGABE, BWART, BUDAT, MENGE, DMBTR, SHKZG, LFGJA, LFBNR, LFPOS) "
                     "VALUES ('4588888888','00010','2026',?,'0001','1',?,'20260301',?,'1000','S',?,?,?)",
                     (doc, bw, "0" if bw == "103" else "57.52", "2026" if ref else "", ref, "0001" if ref else ""))
    conn.execute("INSERT INTO EKBZ (EBELN, EBELP, VGABE, SHKZG, GJAHR, BELNR, BUZEI, LIFNR, KSCHL, MENGE, DMBTR, WAERS) VALUES "
                 "('4588888888','00010','1','S','2026','5000000201','0001','','FRC1','57.52','287600','PKR')")
    conn.commit()
    cost = fetch_delivery_costs("4588888888", fetch_gr_overview("4588888888"))[0]
    expect("a 105's freight belongs to its 103", delivery_for_grs(cost, ["2026/5000000200/0001"]) == (287600.0, 57.52), cost)
    expect("...and its SRN is the 105, as in Lucky's SRN report",
           [g["srn"] for g in fetch_gr_overview("4588888888")["open"]] == [["5000000201"]])

    print("\nFREIGHT ON ITS OWN INVOICE (layout delivery)")
    forget()

    def freight(total, tax=0):
        r = client.post("/api/invoices/save", json={
            "original_filename": "fi.pdf", "stored_filepath": "demo/fi", "mime_type": "application/pdf",
            "invoice_number": f"FI-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
            "currency": "PKR", "document_type": "invoice", "status": "validated",
            "source_type": "upload", "po_reference": PO, "supplier_ntn": "0912345-6",
            "subtotal_amount": total - tax, "tax_amount": tax, "total_amount": total,
            "line_items": [{"description": "Freight", "quantity": 1, "unit_price": total - tax, "amount": total - tax}],
        })
        i = r.json()["id"]
        client.post(f"/api/po-matching/invoices/{i}/match", json={"po_id": _po(client)})
        client.put(f"/api/invoices/{i}", json={"sap_layout": "delivery"})
        return i

    def pick(i, keys, code="I0"):
        return client.put(f"/api/invoices/{i}/delivery-costs", json={"items": [
            {"po_item": 10, "cond_type": "FRA1", "tax_code": code, "gr_keys": keys}]})

    def parkd(i):
        _calls.clear()
        return client.post(f"/api/sap/invoices/{i}/post", json={"mode": "park", "tax_code": "2I", "layout": "delivery",
                                                               "posting_date": "20260312"})

    A, B = "2026/5000009001/0001", "2026/5000009006/0001"
    f1 = freight(15000)
    # Goods of both GRs are on a goods invoice; that says nothing about their freight.
    goods = _new_invoice(client)
    c = client.get(f"/api/sap/invoices/{f1}/delivery-costs").json()["costs"][0]
    expect("each SRN with its own freight, free although its goods are billed",
           [(g["gr_key"], g["amount"], g["srn"], g["taken_by"]) for g in c["grs"]]
           == [(A, 15000.0, ["5000009001"], None), (B, 10000.0, ["5000009006"], None)], c["grs"])
    pick(f1, [])
    p = parkd(f1)
    expect(f"no SRN ticked -> refused (got {p.status_code})", p.status_code == 422 and "Tick the SRNs" in p.text, p.text[:200])
    pick(f1, [A, B])
    p = parkd(f1)
    expect(f"25,000 ticked, 15,000 billed -> refused (got {p.status_code})",
           p.status_code == 422 and "25,000.00" in p.text and "15,000.00" in p.text, p.text[:200])
    pick(f1, [A], "I2")
    p = parkd(f1)
    expect(f"a tax the invoice does not carry -> refused (got {p.status_code})", p.status_code == 422 and "17,550.00" in p.text, p.text[:200])
    pick(f1, [A])
    p = parkd(f1)
    fr, tax, gross, goods_codes = sent() if p.status_code == 200 else (None,) * 4
    expect(f"only that SRN's freight, no goods rows, no tax row (got {p.status_code})",
           p.status_code == 200 and fr == [("FRA1", "12.0", "15000.0", "I0")] and goods_codes == set()
           and tax == [] and float(gross) == 15000, (p.text[:200], fr, tax, gross))
    f2 = freight(11700, 1700)
    c = client.get(f"/api/sap/invoices/{f2}/delivery-costs").json()["costs"][0]
    expect("the next freight invoice sees that SRN as taken",
           [(g["gr_key"], (g["taken_by"] or {}).get("id")) for g in c["grs"]] == [(A, f1), (B, None)], c["grs"])
    pick(f2, [A, B], "I2")
    p = parkd(f2)
    expect(f"...and cannot bill it again (got {p.status_code})", p.status_code == 422 and f"#{f1}" in p.text, p.text[:200])
    pick(f2, [B], "I2")
    p = parkd(f2)
    fr, tax, gross, _g = sent() if p.status_code == 200 else (None,) * 4
    expect(f"the other SRN's freight at 17% (got {p.status_code})",
           p.status_code == 200 and tax == [{"TAX_CODE": "I2", "TAX_AMOUNT": "1700.0"}] and float(gross) == 11700,
           (p.text[:200], tax, gross))
    # Freight billed by a transporter (another SAP vendor), or by the PO's vendor.
    def header():
        return next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")["input_structures"]["HEADERDATA"]

    forget()
    f4 = freight(15000)
    pick(f4, [A])
    p = parkd(f4)
    expect(f"the PO's own vendor: no invoicing party sent (got {p.status_code})",
           p.status_code == 200 and "DIFF_INV" not in header(), p.text[:200])
    forget()
    f5 = freight(15000)
    client.put(f"/api/invoices/{f5}", json={"supplier_ntn": "0456789", "supplier_name": "Bestway Cement Ltd"})
    pick(f5, [A])
    b = client.get(f"/api/sap/invoices/{f5}/delivery-costs").json()
    expect("the transporter is found by NTN (stored with a check digit) and shown as different",
           (b["party"] or {}).get("vendor_number") == "0002000102" and b["party"]["different"] is True
           and b["costs"][0]["other_vendor"] is False, (b["party"], b["party_problem"]))
    w = client.get(f"/api/sap/invoices/{f5}/wht").json()
    expect("its WHT card reads the transporter's BP", w["vendor_number"] == "0002000102", w)
    p = parkd(f5)
    expect(f"parked with the transporter as invoicing party (got {p.status_code})",
           p.status_code == 200 and header().get("DIFF_INV") == "0002000102", p.text[:200])
    expect("...and remembered as the invoice's vendor", _detail(client, f5)["sap_vendor_number"] == "0002000102")
    forget()
    conn.execute("UPDATE EKBZ SET LIFNR = '0002000103' WHERE EBELN = ?", (PO,))
    conn.commit()
    f6 = freight(15000)
    client.put(f"/api/invoices/{f6}", json={"supplier_ntn": "0456789-1"})
    pick(f6, [A])
    p = parkd(f6)
    expect(f"SAP names another freight vendor -> refused (got {p.status_code})", p.status_code == 422 and "2000103" in p.text, p.text[:200])
    client.put(f"/api/invoices/{f6}", json={"supplier_ntn": "1234567-8"})
    p = parkd(f6)
    expect(f"the freight vendor SAP names -> parked for it (got {p.status_code})",
           p.status_code == 200 and header().get("DIFF_INV") == "0002000103", p.text[:200])
    conn.execute("UPDATE EKBZ SET LIFNR = '0002000101' WHERE EBELN = ?", (PO,))
    conn.commit()
    forget()
    f7 = freight(15000)
    pick(f7, [A])
    for ntn, why in (("9999999-9", "No SAP vendor"), ("", "no vendor NTN")):
        client.put(f"/api/invoices/{f7}", json={"supplier_ntn": ntn})
        p = parkd(f7)
        expect(f"NTN {ntn!r} -> refused, never paid to the PO's vendor (got {p.status_code})",
               p.status_code == 422 and why in p.text, p.text[:200])
    conn.execute("INSERT INTO LFA1 (LIFNR, NAME1, MCOD1, ORT01, STCD1, STCD2, STCD3, LOEVM, SPERR) VALUES "
                 "('0002000199','Bestway Branch','BESTWAY BRANCH','Karachi','0456789-1','','','','')")
    conn.execute("INSERT INTO LFB1 (LIFNR, BUKRS, AKONT, ZTERM, LOEVM, SPERR) VALUES ('0002000199','1100','','','','')")
    conn.commit()
    client.put(f"/api/invoices/{f7}", json={"supplier_ntn": "0456789-1"})
    p = parkd(f7)
    expect(f"two vendors with that NTN -> refused, both named (got {p.status_code})",
           p.status_code == 422 and "2000102" in p.text and "2000199" in p.text, p.text[:200])
    conn.execute("DELETE FROM LFB1 WHERE LIFNR = '0002000199'")
    conn.commit()
    p = parkd(f7)
    expect(f"only one of them is in the company code -> that one (got {p.status_code})",
           p.status_code == 200 and header().get("DIFF_INV") == "0002000102", p.text[:200])
    conn.execute("DELETE FROM LFA1 WHERE LIFNR = '0002000199'")
    conn.commit()
    forget()
    f3 = freight(5000)
    client.put(f"/api/invoices/{f3}/parking-grs", json={"gr_keys": [A, B]})
    client.delete(f"/api/invoices/{goods}")
    g2 = _new_invoice(client, tick_grs=False)
    expect("a freight-only invoice does not use up the goods of its GRs",
           sorted(client.get(f"/api/sap/invoices/{g2}/open-grs").json()["suggested"]) == [A, B])


def test_gr_overview():
    """Why a GR list is empty: closed GRs carry a reason, other EKBE rows are counted."""
    print("\nGR OVERVIEW (why nothing is open)")
    from app.services.sap_po_service import fetch_gr_overview, fetch_open_grs
    conn = fake._store()

    def row(doc, vgabe, bwart, qty, shkzg="S", ref="", item="0001"):
        conn.execute("INSERT INTO EKBE (EBELN, EBELP, GJAHR, BELNR, BUZEI, VGABE, BWART, BUDAT, MENGE, DMBTR, SHKZG, "
                     "LFGJA, LFBNR, LFPOS) VALUES ('4599999999','00010','2026',?,?,?,?,'20260301',?,'1000',?,?,?,?)",
                     (doc, item, vgabe, bwart, str(qty), shkzg, "2026" if ref else "", ref, "0001" if ref else ""))

    expect("no history -> 0 rows", fetch_gr_overview("4599999999")["rows"] == 0)
    row("5000000091", "1", "101", 10)
    row("5100000091", "2", "", 10, ref="5000000091")          # fully invoiced
    row("5000000092", "1", "101", 5)
    row("5000000093", "1", "102", 5, "H", ref="5000000092")   # reversed
    row("5000000094", "1", "105", 7)                          # not a receipt movement
    row("5100000095", "P", "", 4, ref="5000000091")           # another event
    row("5000000096", "1", "101", 8)
    row("5100000096", "2", "", 3, ref="5000000096")           # partly invoiced
    conn.commit()
    ov = fetch_gr_overview("4599999999")
    expect("closed GRs carry the reason", {g["gr_doc"]: g["reason"] for g in ov["closed"]}
           == {"5000000091": "fully invoiced", "5000000092": "reversed"}, ov["closed"])
    expect("partly invoiced stays open with the rest", [(g["gr_doc"], g["open_qty"]) for g in ov["open"]]
           == [("5000000096", 5.0)], ov["open"])
    expect("other rows are counted, not hidden", {(u["vgabe"], u["bwart"]): u["count"] for u in ov["unused"]}
           == {("1", "105"): 1}, ov["unused"])
    expect("a parked invoice is reported on its GR, not subtracted",
           [(g["parked"], g["parked_docs"]) for g in ov["closed"] if g["gr_doc"] == "5000000091"] == [(4.0, ["5100000095"])],
           ov["closed"])
    # Two-step receipt, as on Lucky's PO 1010027884: 103 without quantity, 105 releases.
    row("5000000100", "1", "103", 0)
    row("5000000101", "1", "105", 57.52, ref="5000000100")
    row("5000000102", "1", "106", 57.52, "H", ref="5000000100")
    row("5000000103", "1", "105", 57.52, ref="5000000100")      # released again
    row("5000000104", "1", "103", 0)
    row("5000000105", "1", "105", 58.96, ref="5000000104")
    row("5000000106", "1", "106", 58.96, "H", ref="5000000104")  # released, then reversed
    row("5000000107", "1", "103", 0)                             # never released
    conn.commit()
    ov = fetch_gr_overview("4599999999")
    two = {g["gr_doc"]: g for g in ov["open"] + ov["closed"]}
    expect("105 releases count for their 103 (the reference document)",
           two["5000000100"]["open_qty"] == 57.52, two["5000000100"])
    expect("released then reversed -> closed, reversed", two["5000000104"]["reason"] == "reversed", two["5000000104"])
    expect("never released -> says so", "blocked stock" in (two["5000000107"]["reason"] or ""), two["5000000107"])
    expect("open list is the same one the park uses", fetch_open_grs("4599999999") == ov["open"])
    conn.execute("DELETE FROM EKBE WHERE EBELN = '4599999999'")
    conn.commit()


def test_wht(client):
    """Observation G: the vendor's WHT from its BP (LFBW + T059Z rate) is shown;
    parking sends WITHTAXDATA only when the invoice overrides it."""
    print("\nWITHHOLDING TAX (vendor BP -> invoice -> park)")
    settings.SAP_WORKFLOW_ENABLED = False
    inv = _new_invoice(client)              # PO 4500009001 -> vendor 0002000101, company 1100
    r = client.get(f"/api/sap/invoices/{inv}/wht")
    body = r.json()
    got = sorted((w["wht_type"], w["wht_code"], w["rate"], w["subject"]) for w in body.get("vendor_wht", []))
    expect(f"vendor WHT read from SAP (got {r.status_code})",
           r.status_code == 200 and got == [("K1", "K1", 80.0, True), ("VG", "VG", 4.0, True), ("VN", "VN", 8.0, True)],
           (got, body.get("message")))
    expect("types the vendor is not subject to are left out",
           [w["wht_type"] for w in body.get("not_subject", [])] == ["PA"], body.get("not_subject"))
    k1 = next((w for w in body.get("vendor_wht", []) if w["wht_type"] == "K1"), {})
    expect("a sales-tax WHT is estimated on the sales tax, not the net (tax is 0 here)",
           k1.get("base_kind") == "sales_tax" and k1.get("estimate") == 0, k1)
    from app.services.lucky_wht_codes import PK_WHT_CODES, wht_base_kind
    kinds = {c: wht_base_kind(n) for _t, c, n, _r in PK_WHT_CODES}
    expect("base read from the name: S.Tax / supply / income tax / unclear",
           {c: kinds[c] for c in ("V7", "K1", "V1", "W1", "V8", "V3", "VI", "PL", "K5")}
           == {"V7": "sales_tax", "K1": "sales_tax", "V1": "sales_tax", "W1": "sales_tax", "V8": "sales_tax",
               "V3": "net", "VI": "net", "PL": None, "K5": None}, kinds)
    vg = next((w for w in body.get("vendor_wht", []) if w["wht_type"] == "VG"), {})
    expect("named from Lucky's WHT list, with an estimate", "goods" in (vg.get("name") or "").lower()
           and vg.get("estimate") == round(3700000 * 0.04, 2), vg)

    p = _park(client, inv)
    kw = next(k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK")
    expect("no override -> no WITHTAXDATA (SAP uses the BP)", p.status_code == 200
           and "WITHTAXDATA" not in kw["input_tables"], list(kw["input_tables"]))

    inv2 = _new_invoice(client)
    s = client.put(f"/api/invoices/{inv2}/wht", json={"items": [{"wht_type": "vh", "wht_code": "vh"}]})
    expect("override saved (upper-cased)", s.status_code == 200
           and _detail(client, inv2).get("sap_wht") == [{"wht_type": "VH", "wht_code": "VH"}],
           _detail(client, inv2).get("sap_wht"))
    w = client.get(f"/api/sap/invoices/{inv2}/wht").json()
    expect("a type outside the BP is flagged", w["override"][0].get("in_bp") is False, w["override"])
    p = _park(client, inv2)
    expect(f"a type outside the BP -> park refused, by name (got {p.status_code})",
           p.status_code == 422 and "VH" in p.text, p.text[:200])
    expect("...and nothing parked", "BAPI_INCOMINGINVOICE_PARK" not in _names(), _names())
    client.put(f"/api/invoices/{inv2}/wht", json={"items": [{"wht_type": "PA", "wht_code": "PA"}]})
    p = _park(client, inv2)
    expect(f"in the BP but not subject -> refused too (got {p.status_code})", p.status_code == 422 and "PA" in p.text, p.text[:150])
    client.put(f"/api/invoices/{inv2}/wht", json={"items": [{"wht_type": "VN", "wht_code": "VN"}]})
    p = _park(client, inv2)
    kw = next((k for n, k in _calls if n == "BAPI_INCOMINGINVOICE_PARK"), {"input_tables": {}})
    expect("one of the BP's own types -> WITHTAXDATA sent", p.status_code == 200
           and kw["input_tables"].get("WITHTAXDATA") == [{"WI_TAX_TYPE": "VN", "WI_TAX_CODE": "VN"}],
           (p.text[:150], kw["input_tables"].get("WITHTAXDATA")))


def test_t100_text():
    """A ZMIR7_ERROR_LOG row with only a message code is shown with its T100 text."""
    print("\nERROR LOG WITH A CODE ONLY -> T100 TEXT")
    from app.services.sap_workflow import read_workflow_status
    key = "1200510566999920" + "27"
    conn = fake._store()
    fake.wf_log_step(conn, key, "REJ")
    conn.execute("INSERT INTO ZMIR7_ERROR_LOG (SR_NO, BELNR, GJAHR, TYPE, ID, ZNUMBER, ZMESSAGE, "
                 "ZMESSAGE_V1, ZMESSAGE_V2, CDATE, CTIME) VALUES (900, ?, ?, 'E', 'ZVIMDEMO', '001', '', "
                 "'5105669999', '1,000.00', '20261120', '120000')", (key[4:14], key[14:18]))
    conn.commit()
    info = read_workflow_status(fake.SAPConnectorFake(), [key])[key]
    expect("status REJ", info["status"] == "REJ", info)
    expect("T100 text with variables filled in",
           info["error"] == "ZVIMDEMO 1: Document 5105669999 could not be posted: amount 1,000.00 does not match",
           info["error"])
    conn.execute("UPDATE ZMIR7_ERROR_LOG SET ID = 'ZNOSUCH' WHERE SR_NO = 900")
    conn.commit()
    info = read_workflow_status(fake.SAPConnectorFake(), [key])[key]
    expect("unknown message -> code and variables", info["error"] == "ZNOSUCH 1: 5105669999 1,000.00", info["error"])
    # Leave the store as found: later sections count ZMIR7 rows.
    conn.execute("DELETE FROM ZMIR7_WF_LOG WHERE OBJKEY = ?", (key,))
    conn.execute("DELETE FROM ZMIR7_ERROR_LOG WHERE SR_NO = 900")
    conn.commit()


if __name__ == "__main__":
    test_objkey()
    test_t100_text()

    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin")
    main.app.dependency_overrides[get_current_internal_user] = lambda: InternalUser(
        id=1, email="purchaser@lucky.test", display_name="Purchaser",
        password_hash="x", role="ap_operator", is_active=1)

    with TestClient(main.app) as client:
        test_off(client)
        test_refusals(client)
        test_flow(client)
        test_poller_selection(client)
        test_sap_raises(client)
        test_resubmit(client)
        test_unit_from_po(client)
        test_gr_selection(client)
        test_delivery_costs(client)
        test_gr_overview()
        test_wht(client)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL SAP WORKFLOW TESTS PASSED")
    print("=" * 60)
