"""Invoice vendor NTN vs the SAP PO vendor's tax numbers (client request 2026-11-26).

A mismatch is reported on the invoice detail (vendor_ntn_check) and never blocks.

Covers:
  - compare(): NTN with / without check digit, letter NTNs, CNIC in full, a
    labelled NTN inside a bundled field, mismatch, unknown when a side is empty
  - fake SAP: _fetch_vendor_master returns STCD1..3 as tax_numbers; a PO's
    detail carries them
  - API: GET /api/invoices/{id} returns match / mismatch for a matched PO; an
    older PO without stored tax numbers is read from SAP once (backfill) and
    stored; no check when not matched; suppliers do not get it; the check does
    not block validating the invoice

Offline (fake SAP, no Gemini). Own throwaway SQLite database.

    py -3 backend/test_vendor_ntn_check.py
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

SCRATCH = os.path.join(tempfile.gettempdir(), "vendor_ntn_check_test.db")
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
from sqlalchemy import select  # noqa: E402

import app.main as main  # noqa: E402
from app.database import async_session  # noqa: E402
from app.models.invoice import Invoice  # noqa: E402
from app.models.purchase_order import PurchaseOrder  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services import sap_po_service  # noqa: E402
from app.services.ntn_check import compare  # noqa: E402

_failures = []
ADMIN = Principal(kind="internal", id=1, role="admin")
SUPPLIER = Principal(kind="supplier", id=77, role="supplier")


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def test_compare():
    print("\nUNIT: compare")
    expect("same NTN", compare("1234567-8", ["1234567-8"]) == "match")
    expect("NTN without check digit", compare("1234567", ["1234567-8"]) == "match")
    expect("letter NTN", compare("H914032-1", ["H9140321"]) == "match")
    expect("CNIC dashed vs plain", compare("42201-1234567-1", ["", "", "4220112345671"]) == "match")
    expect("labelled NTN in a bundled field",
           compare("STRN # 3277876177886, NTN # 5433744-3", ["5433744-3", "3277876177886"]) == "match")
    expect("different NTN", compare("7654321-0", ["1234567-8"]) == "mismatch")
    expect("short / mistyped NTN is a mismatch", compare("13288", ["1328862-8"]) == "mismatch")
    expect("the right NTN for that vendor matches", compare("1328862-8", ["1328862-8"]) == "match")
    expect("CNIC vs other CNIC", compare("4220112345671", ["4220112345672"]) == "mismatch")
    expect("no invoice NTN -> unknown", compare("", ["1234567-8"]) == "unknown")
    expect("no SAP tax number -> unknown", compare("1234567-8", []) == "unknown")


def test_fake_sap():
    print("\nFAKE SAP: vendor tax numbers")
    sap = sap_po_service._get_connector()
    sap.connect()
    try:
        v = sap_po_service._fetch_vendor_master(sap, ["0002000101"]).get("0002000101", {})
    finally:
        sap.disconnect()
    expect("tax_numbers from LFA1", v.get("tax_numbers") == ["0912345-6"], v)
    expect("ntn = STCD1", v.get("ntn") == "0912345-6", v)
    d = sap_po_service.fetch_po_detail("4500009001")
    expect("PO detail carries vendor_tax_numbers", d.get("vendor_tax_numbers") == ["0912345-6"], d.get("vendor_tax_numbers"))


async def _seed():
    async with async_session() as db:
        new_po = PurchaseOrder(po_number="4500009001", vendor_name="Haier Pakistan (Pvt) Ltd",
                               sap_vendor_number="0002000101", vendor_ntn="0912345-6",
                               vendor_tax_numbers=json.dumps(["0912345-6"]), source_type="sap",
                               currency="PKR", status="open", po_type="local")
        old_po = PurchaseOrder(po_number="4500009005", vendor_name="Haier Pakistan (Pvt) Ltd",
                               sap_vendor_number="0002000101", vendor_ntn="", vendor_tax_numbers=None,
                               source_type="sap", currency="PKR", status="open", po_type="local")
        db.add_all([new_po, old_po])
        await db.flush()

        def inv(num, ntn, po):
            return Invoice(original_filename="a.pdf", stored_filepath="unsaved", mime_type="application/pdf",
                           invoice_number=num, supplier_name="Haier", supplier_ntn=ntn, total_amount=100,
                           invoice_date="2026-11-20", currency="PKR", status="pending_processing",
                           matched_po_id=po.id if po else None, supplier_id=None)
        rows = [inv("N-OK", "0912345", new_po), inv("N-BAD", "7654321-0", new_po),
                inv("N-OLD", "0912345-6", old_po), inv("N-NONE", "0912345-6", None),
                inv("N-FREIGHT", "7654321-0", new_po)]
        rows[-1].sap_layout = "delivery"   # a transporter's own freight invoice
        db.add_all(rows)
        await db.commit()
        return {r.invoice_number: r.id for r in rows}, old_po.id


async def _old_po_numbers(po_id):
    async with async_session() as db:
        po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one()
        return po.vendor_tax_numbers


def test_api(client):
    print("\nAPI: invoice detail")
    ids, old_po_id = asyncio.run(_seed())
    main.app.dependency_overrides[get_current_principal] = lambda: ADMIN

    def check(name):
        r = client.get(f"/api/invoices/{ids[name]}")
        assert r.status_code == 200, r.text
        return r.json().get("vendor_ntn_check")

    ok = check("N-OK")
    expect("same NTN -> match", ok and ok["status"] == "match", ok)
    bad = check("N-BAD")
    expect("different NTN -> mismatch", bad and bad["status"] == "mismatch", bad)
    expect("mismatch names the SAP numbers and vendor",
           bad and bad["sap_tax_numbers"] == ["0912345-6"] and bad["vendor_number"] == "0002000101", bad)
    old = check("N-OLD")
    expect("older PO: read from SAP -> match", old and old["status"] == "match", old)
    expect("older PO: tax numbers stored", asyncio.run(_old_po_numbers(old_po_id)) == json.dumps(["0912345-6"]))
    expect("not matched -> no check", check("N-NONE") is None)
    expect("freight-only invoice (transporter) -> PO vendor not compared",
           check("N-FREIGHT") is None)

    r = client.patch(f"/api/invoices/{ids['N-BAD']}/status", json={"status": "validated"})
    expect(f"a mismatch does not block Validate (got {r.status_code})", r.status_code == 200, r.text[:200])

    # Client 2026-11-27: a mismatch is never parked and goes to Exception.
    from types import SimpleNamespace
    from app.security import get_current_internal_user
    main.app.dependency_overrides[get_current_internal_user] = lambda: SimpleNamespace(
        id=1, role="admin", email="admin@example.com", name="Admin", sap_username=None, sap_password_enc=None)
    r = client.post(f"/api/sap/invoices/{ids['N-BAD']}/post", json={"mode": "validate"})
    expect(f"mismatch: SAP park/dry run refused with 422 (got {r.status_code})",
           r.status_code == 422 and "does not match SAP" in r.text, r.text[:200])
    d = client.get(f"/api/invoices/{ids['N-BAD']}").json()
    expect("... and the invoice is moved to Exception", d["status"] == "exception", d["status"])
    expect("... with the reason in its warnings", any("does not match SAP" in w for w in (d.get("warnings") or [])),
           d.get("warnings"))
    r = client.post(f"/api/sap/invoices/{ids['N-OK']}/post", json={"mode": "validate"})
    expect(f"a matching NTN is not refused for its NTN (got {r.status_code})", "does not match SAP" not in r.text,
           r.text[:200])

    ok = client.get(f"/api/invoices/{ids['N-OK']}").json()
    expect("Vendor Code = the matched PO's SAP vendor", ok.get("vendor_code") == "0002000101", ok.get("vendor_code"))
    expect("not matched -> no Vendor Code", client.get(f"/api/invoices/{ids['N-NONE']}").json().get("vendor_code") is None)

    main.app.dependency_overrides[get_current_principal] = lambda: SUPPLIER
    r = client.get(f"/api/invoices/{ids['N-BAD']}")
    expect("suppliers do not get the check",
           r.status_code != 200 or r.json().get("vendor_ntn_check") is None, r.text[:200])
    main.app.dependency_overrides[get_current_principal] = lambda: ADMIN


if __name__ == "__main__":
    test_compare()
    test_fake_sap()
    main.app.dependency_overrides[get_current_principal] = lambda: ADMIN
    with TestClient(main.app) as client:
        test_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL VENDOR NTN CHECK TESTS PASSED")
    print("=" * 60)
