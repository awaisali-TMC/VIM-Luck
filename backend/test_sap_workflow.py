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


def _new_invoice(client):
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


def test_gr_selection(client):
    """Observation F: list the PO's open GRs, tick some, park one ITEMDATA row
    per ticked GR (REF_DOC = that GR); a selection that doesn't add up refuses."""
    print("\nGR-WISE PARKING (select goods receipts)")
    settings.SAP_WORKFLOW_ENABLED = False
    inv = _new_invoice(client)              # PO 4500009001 item 10, 20 units
    r = client.get(f"/api/sap/invoices/{inv}/open-grs")
    grs = r.json().get("grs", [])
    item10 = [g for g in grs if g["po_item"] == 10]
    expect(f"open GRs listed (got {r.status_code}, {len(grs)})", r.status_code == 200 and len(item10) == 2,
           [(g["gr_key"], g["open_qty"]) for g in grs])
    expect("each GR has description/unit from the PO", all(g.get("unit") for g in item10), item10)

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
        test_gr_overview()
        test_wht(client)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL SAP WORKFLOW TESTS PASSED")
    print("=" * 60)
