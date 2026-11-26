"""MIR7 / FV60: the SAP transaction chosen on the upload screen.

MIR7 = invoice with a PO (the existing flow). FV60 = invoice without a PO: it is
recorded only, so PO matching and the SAP park route refuse it.

Covers:
  - norm_sap_transaction: FV60 kept, anything else (empty, junk, lower case) -> MIR7
  - _extraction_to_draft (batch / split drafts) stores the chosen transaction
  - API /save: FV60 stored and returned; missing -> MIR7; a SUPPLIER's save is
    always MIR7 whatever it sends
  - list endpoint returns it
  - PO match (POST /api/po-matching/invoices/{id}/match) refuses FV60 with 422
  - SAP park route (POST /api/sap/invoices/{id}/post) refuses FV60 with 422

Offline: no Gemini, no SAP. Uses its own throwaway SQLite database, recreated on
every run.

    py -3 backend/test_sap_transaction.py
"""
import os
import sys
import tempfile
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before app.config is imported (environment beats backend/.env).
SCRATCH = os.path.join(tempfile.gettempdir(), "sap_transaction_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""

from app.config import settings  # noqa: E402

assert SCRATCH in settings.DATABASE_URL, "DATABASE_URL is not the scratch DB; .env won"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.routers.invoices import _extraction_to_draft, norm_sap_transaction  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402

_failures = []

ADMIN = Principal(kind="internal", id=1, role="admin")
SUPPLIER = Principal(kind="supplier", id=99, role="supplier")


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def as_principal(p):
    main.app.dependency_overrides[get_current_principal] = lambda: p


def test_unit():
    print("\nUNIT: normalisation and batch drafts")
    expect("FV60 kept", norm_sap_transaction("FV60") == "FV60")
    expect("lower case fv60 kept", norm_sap_transaction(" fv60 ") == "FV60")
    expect("MIR7 kept", norm_sap_transaction("MIR7") == "MIR7")
    expect("empty -> MIR7", norm_sap_transaction(None) == "MIR7" and norm_sap_transaction("") == "MIR7")
    expect("junk -> MIR7", norm_sap_transaction("FB60") == "MIR7")

    result = {"fields": [{"field_name": "invoice_id", "value": "INV-1", "confidence": 99}], "line_items": []}
    d_default = _extraction_to_draft(result, "a.pdf", "unsaved", "application/pdf", 10)
    d_fv60 = _extraction_to_draft(result, "a.pdf", "unsaved", "application/pdf", 10, sap_transaction="FV60")
    expect("batch draft defaults to MIR7", d_default.sap_transaction == "MIR7", d_default.sap_transaction)
    expect("batch draft carries FV60", d_fv60.sap_transaction == "FV60", d_fv60.sap_transaction)


def save(client, sap_transaction):
    body = {
        "original_filename": "inv.pdf", "stored_filepath": "unsaved", "mime_type": "application/pdf",
        "invoice_number": f"TX-{uuid.uuid4().hex[:6]}", "supplier_name": "Vendor Co",
        "total_amount": 1000, "status": "pending_processing", "line_items": [],
    }
    if sap_transaction is not None:
        body["sap_transaction"] = sap_transaction
    r = client.post("/api/invoices/save", json=body)
    assert r.status_code == 200, f"save failed: {r.status_code} {r.text}"
    return r.json()["id"]


def detail(client, inv_id):
    as_principal(ADMIN)
    r = client.get(f"/api/invoices/{inv_id}")
    assert r.status_code == 200, r.text
    return r.json()


def test_api(client):
    print("\nAPI: save and read back")
    as_principal(ADMIN)
    fv = save(client, "FV60")
    mir = save(client, None)
    expect("FV60 is stored", detail(client, fv).get("sap_transaction") == "FV60", detail(client, fv).get("sap_transaction"))
    expect("not sent -> MIR7", detail(client, mir).get("sap_transaction") == "MIR7", detail(client, mir).get("sap_transaction"))

    as_principal(SUPPLIER)
    sup = save(client, "FV60")
    expect("a supplier's save is always MIR7", detail(client, sup).get("sap_transaction") == "MIR7",
           detail(client, sup).get("sap_transaction"))

    as_principal(ADMIN)
    rows = client.get("/api/invoices/?limit=100").json()["invoices"]
    by_id = {r["id"]: r for r in rows}
    expect("list returns FV60", by_id.get(fv, {}).get("sap_transaction") == "FV60", by_id.get(fv))

    print("\nAPI: FV60 is not matched to a PO or parked")
    r = client.post(f"/api/po-matching/invoices/{fv}/match", json={"po_id": 1, "match_type": "2-way"})
    expect(f"PO match refused with 422 (got {r.status_code})", r.status_code == 422 and "FV60" in r.text, r.text[:200])

    main.app.dependency_overrides[get_current_internal_user] = lambda: SimpleNamespace(
        id=1, role="admin", email="admin@example.com", name="Admin", sap_username=None)
    for mode in ("validate", "park"):
        r = client.post(f"/api/sap/invoices/{fv}/post", json={"mode": mode})
        expect(f"SAP {mode} refused with 422 (got {r.status_code})", r.status_code == 422 and "FV60" in r.text,
               r.text[:200])
    r = client.post(f"/api/sap/invoices/{mir}/post", json={"mode": "validate"})
    expect(f"a MIR7 invoice is not refused for being FV60 (got {r.status_code})", "FV60" not in r.text, r.text[:200])


if __name__ == "__main__":
    test_unit()
    as_principal(ADMIN)
    with TestClient(main.app) as client:
        test_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL SAP TRANSACTION TESTS PASSED")
    print("=" * 60)
