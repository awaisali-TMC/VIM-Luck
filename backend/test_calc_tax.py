"""MIR7 "Calculate Tax" (client 2026-11-27): park with CALC_TAX_IND = X, no TAXDATA.

Covers:
  - post_invoice_to_sap(calc_tax=True): HEADERDATA-CALC_TAX_IND = 'X' and an
    empty TAXDATA (SAP refuses both together with M8 738); the park succeeds
  - calc_tax=False (default): CALC_TAX_IND blank and the invoice's tax in TAXDATA
  - API: PUT /api/invoices/{id} {"sap_calc_tax": true} is stored and returned by
    the detail, default False

Offline (fake SAP, no Gemini). Own throwaway SQLite database.

    py -3 backend/test_calc_tax.py
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCRATCH = os.path.join(tempfile.gettempdir(), "calc_tax_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_ENABLED"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["SAP_FAKE_DB_PATH"] = ""
os.environ["GEMINI_API_KEY"] = ""

from app.config import settings  # noqa: E402

assert SCRATCH in settings.DATABASE_URL, "DATABASE_URL is not the scratch DB; .env won"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services import sap_connector_fake as fk  # noqa: E402
from app.services.sap_invoice_post import post_invoice_to_sap  # noqa: E402

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


_sent = []
_orig = fk.SAPConnectorFake.call


def _spy(self, fn, *a, **kw):
    if fn.startswith("BAPI_INCOMINGINVOICE_"):
        _sent.append((fn, kw))
    return _orig(self, fn, *a, **kw)


fk.SAPConnectorFake.call = _spy

PARK = dict(
    invoice_date="2026-11-19", posting_date="2026-11-19",
    vendor_number="0002000101", company_code="1100", currency="PKR",
    po_number="4500009001",
    line_items=[{"po_item": "00010", "amount": 100000.0, "quantity": 20, "po_unit": "EA"}],
    tax_code="2I", header_text="calc-tax-test", mode="park",
)


def park(calc):
    _sent.clear()
    r = post_invoice_to_sap(invoice_number=f"CT-{uuid.uuid4().hex[:6]}", gross_amount=118000.0,
                            tax_amount=18000.0, calc_tax=calc, **PARK)
    fn, kw = next(((f, k) for f, k in _sent if f == "BAPI_INCOMINGINVOICE_PARK"), (None, {}))
    return r, kw.get("input_structures", {}).get("HEADERDATA", {}), kw.get("input_tables", {}).get("TAXDATA")


def test_bapi():
    print("\nBAPI: what reaches SAP")
    r, head, tax = park(True)
    expect("calc tax: CALC_TAX_IND = X", head.get("CALC_TAX_IND") == "X", head.get("CALC_TAX_IND"))
    expect("calc tax: no TAXDATA rows", tax == [], tax)
    expect("calc tax: park succeeds", r.get("success") is True, r.get("message"))
    r, head, tax = park(False)
    expect("manual tax: CALC_TAX_IND blank", head.get("CALC_TAX_IND") == "", head.get("CALC_TAX_IND"))
    expect("manual tax: invoice tax in TAXDATA",
           tax == [{"TAX_CODE": "2I", "TAX_AMOUNT": "18000.0"}], tax)


def test_api(client):
    print("\nAPI: the invoice option")
    r = client.post("/api/invoices/save", json={
        "original_filename": "ct.pdf", "stored_filepath": "unsaved", "mime_type": "application/pdf",
        "invoice_number": f"CT-{uuid.uuid4().hex[:6]}", "supplier_name": "Vendor", "total_amount": 118000,
        "status": "pending_processing", "line_items": []})
    inv = r.json()["id"]
    expect("default off", client.get(f"/api/invoices/{inv}").json().get("sap_calc_tax") is False)
    r = client.put(f"/api/invoices/{inv}", json={"sap_calc_tax": True})
    expect(f"PUT stores it (got {r.status_code})", r.status_code == 200, r.text[:200])
    expect("detail returns it", client.get(f"/api/invoices/{inv}").json().get("sap_calc_tax") is True)


if __name__ == "__main__":
    test_bapi()
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(kind="internal", id=1, role="admin")
    with TestClient(main.app) as client:
        test_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL CALCULATE TAX TESTS PASSED")
    print("=" * 60)
