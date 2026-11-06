"""Receiver NTN: captured from the invoice, stored, editable, and checked against
the buyer's own NTN (BUYER_NTN).

Covers:
  - fbr_verification.ntn_base / receiver_ntn_problem: with and without the check
    digit, several buyer NTNs, silent without BUYER_NTN or without a receiver NTN
  - extraction: the prompt asks for receiver_tax_id, it has a label, and a
    mismatch raises a "Not addressed to us" attention flag on the review screen
  - _extraction_to_draft (batch-upload drafts): maps receiver_tax_id and adds
    the warning
  - API: /save stores it and adds the warning on a mismatch only; the detail
    response returns it; PUT edits it

Offline: no Gemini, no SAP. Uses its own throwaway SQLite database, recreated on
every run.

    py -3 backend/test_receiver_ntn.py
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before app.config is imported (environment beats backend/.env).
SCRATCH = os.path.join(tempfile.gettempdir(), "receiver_ntn_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["EMAIL_NOTIFICATIONS_ENABLED"] = "false"
os.environ["BUYER_NAME"] = "Lucky Cement Limited"
os.environ["BUYER_NTN"] = ""   # set per check below

from app.config import settings  # noqa: E402

assert SCRATCH in settings.DATABASE_URL, "DATABASE_URL is not the scratch DB; .env won"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.routers.invoices import _extraction_to_draft  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services.fbr_verification import ntn_base, receiver_ntn_problem  # noqa: E402
from app.services.gemini_extract import EXTRACTION_PROMPT, FIELD_LABELS, _detect_attention_flags  # noqa: E402

OURS = "0712345-6"     # invented buyer NTN for the test
OTHER = "4455667-1"    # someone else's

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def test_rule():
    print("\nUNIT: the buyer-NTN check")
    expect("check digit is ignored", ntn_base("0712345-6") == ntn_base("0712345") == ntn_base("712345"))
    expect("a 13-digit CNIC compares in full", ntn_base("35202-1234567-1") != ntn_base("35202-1234567-9"))

    settings.BUYER_NTN = ""
    expect("no BUYER_NTN configured -> silent", receiver_ntn_problem(OTHER) is None)

    settings.BUYER_NTN = OURS
    expect("our NTN -> fine", receiver_ntn_problem(OURS) is None)
    expect("our NTN without the check digit -> fine", receiver_ntn_problem("0712345") is None)
    expect("no receiver NTN on the invoice -> silent", receiver_ntn_problem(None) is None and receiver_ntn_problem("  ") is None)
    msg = receiver_ntn_problem(OTHER)
    expect("someone else's NTN -> warning", bool(msg))
    expect("... naming both NTNs and the buyer",
           bool(msg) and OTHER in msg and OURS in msg and "Lucky Cement Limited" in msg, msg)

    settings.BUYER_NTN = f"1111111-1, {OURS}"
    expect("several buyer NTNs: any one matches", receiver_ntn_problem("0712345-6") is None)
    settings.BUYER_NTN = OURS


def test_extraction():
    print("\nUNIT: extraction")
    expect("prompt asks for receiver_tax_id", "receiver_tax_id" in EXTRACTION_PROMPT)
    expect("receiver_tax_id has a label", FIELD_LABELS.get("receiver_tax_id") == "Receiver NTN")

    def flags(receiver):
        fm = {"invoice_id": "INV-1", "supplier_name": "Vendor", "supplier_tax_id": "1234567-8",
              "total_amount": 100, "currency": "PKR", "receiver_tax_id": receiver}
        return [f for f in _detect_attention_flags(fm, [], [], 99.0) if f["title"] == "Not addressed to us"]

    got = flags(OTHER)
    expect("mismatch -> 'Not addressed to us' flag on the review screen", len(got) == 1, got)
    expect("... high severity", bool(got) and got[0]["severity"] == "high")
    expect("our NTN -> no flag", flags(OURS) == [])
    expect("no receiver NTN -> no flag", flags(None) == [])

    result = {"fields": [{"field_name": "invoice_id", "value": "INV-9", "confidence": 99},
                         {"field_name": "receiver_tax_id", "value": OTHER, "confidence": 99}],
              "line_items": [], "warnings": ["existing warning"]}
    draft = _extraction_to_draft(result, "a.pdf", "unsaved", "application/pdf", 10)
    expect("batch draft carries the receiver NTN", draft.receiver_ntn == OTHER, draft.receiver_ntn)
    expect("batch draft gets the warning (and keeps existing ones)",
           draft.warnings and "existing warning" in draft.warnings and OTHER in draft.warnings, draft.warnings)


def save(client, receiver_ntn):
    r = client.post("/api/invoices/save", json={
        "original_filename": "inv.pdf", "stored_filepath": "unsaved", "mime_type": "application/pdf",
        "invoice_number": f"RN-{uuid.uuid4().hex[:6]}", "supplier_name": "Vendor Co",
        "receiver_name": "Lucky Cement Limited", "receiver_ntn": receiver_ntn,
        "total_amount": 1000, "status": "pending_processing", "line_items": [],
    })
    assert r.status_code == 200, f"save failed: {r.status_code} {r.text}"
    # /save answers with a summary; read back what was stored via the detail.
    d = client.get(f"/api/invoices/{r.json()['id']}")
    assert d.status_code == 200, d.text
    return d.json()


def test_api(client):
    print("\nAPI: save, read back, edit")
    settings.BUYER_NTN = OURS
    inv = save(client, OURS)
    expect("detail returns the receiver NTN", inv.get("receiver_ntn") == OURS, inv.get("receiver_ntn"))
    expect("our NTN -> no warning", not any(OURS in w for w in (inv.get("warnings") or [])), inv.get("warnings"))

    bad = save(client, OTHER)
    expect("someone else's NTN -> warning saved on the invoice",
           any("not Lucky Cement Limited's NTN" in w for w in (bad.get("warnings") or [])), bad.get("warnings"))

    none = save(client, None)
    expect("no receiver NTN -> stored empty, no warning",
           none.get("receiver_ntn") is None and not none.get("warnings"), (none.get("receiver_ntn"), none.get("warnings")))

    r = client.put(f"/api/invoices/{none['id']}", json={"receiver_ntn": "0712345"})
    expect(f"PUT edits the receiver NTN (got {r.status_code})",
           r.status_code == 200 and r.json().get("receiver_ntn") == "0712345", r.text[:200])

    settings.BUYER_NTN = ""
    quiet = save(client, OTHER)
    expect("BUYER_NTN not configured -> captured but not flagged",
           quiet.get("receiver_ntn") == OTHER and not quiet.get("warnings"), quiet.get("warnings"))


if __name__ == "__main__":
    test_rule()
    test_extraction()
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(kind="internal", id=1, role="admin")
    with TestClient(main.app) as client:
        test_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL RECEIVER NTN TESTS PASSED")
    print("=" * 60)
