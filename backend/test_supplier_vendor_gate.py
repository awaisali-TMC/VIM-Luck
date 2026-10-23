"""
HTTP + DB integration test for the supplier vendor-name gate.

A supplier may only invoice as their own registered company. A confident
mismatch between the document's extracted vendor name and the registered
company records a warning on the invoice (surfaced to AP on the detail page)
but must NOT change its status — Exception is reserved for approvers
explicitly flagging an invoice.

Run with the venv python:

    backend/venv/Scripts/python.exe backend/test_supplier_vendor_gate.py
"""

import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.routers.invoices import _supplier_name_matches  # noqa: E402

_failures = []


def expect(label, cond):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}")
    if not cond:
        _failures.append(label)


def _save_payload(supplier_name, status="pending_processing"):
    return {
        "original_filename": "test.pdf",
        "stored_filepath": "test",
        "mime_type": "application/pdf",
        "invoice_number": f"VG-{uuid.uuid4().hex[:8]}",
        "supplier_name": supplier_name,
        "total_amount": 1000,
        "status": status,
        "source_type": "supplier",
        "line_items": [],
    }


def test_matcher_unit():
    print("\nUNIT: lenient company-name matcher")
    expect("exact match", _supplier_name_matches("Al-Badar Enterprises", "AL-BADAR ENTERPRISES"))
    expect("legal-form variant matches",
           _supplier_name_matches("Al-Badar", "AL-BADAR ENTERPRISES (Pvt) Ltd"))
    expect("different company rejected",
           not _supplier_name_matches("Damco Pakistan Pvt ltd", "Al-Badar Enterprises"))
    expect("empty extracted counts as match", _supplier_name_matches("", "Al-Badar"))


def _run(client, supplier_id, company):
    # gate fires: different company -> warning recorded, status UNCHANGED
    r = client.post("/api/invoices/save", json=_save_payload("Damco Pakistan Pvt ltd"))
    expect(f"mismatch save -> 200 (got {r.status_code})", r.status_code == 200)
    body = r.json()
    expect("mismatch keeps submitted status", body.get("status") == "pending_processing")
    inv_id = body["id"]
    r = client.get(f"/api/invoices/{inv_id}")
    warns = r.json().get("warnings") or []
    expect("mismatch warning recorded",
           any("does not match the registered supplier" in w for w in warns))

    # gate passes: own company name (with legal-form noise) keeps requested status
    r = client.post("/api/invoices/save", json=_save_payload(f"{company} (Pvt) Ltd"))
    expect("own-name save keeps status",
           r.json().get("status") == "pending_processing")

    # draft saves are warned but not forced to exception
    r = client.post("/api/invoices/save", json=_save_payload("Damco Pakistan Pvt ltd", status="draft"))
    expect("mismatched draft stays draft", r.json().get("status") == "draft")


if __name__ == "__main__":
    test_matcher_unit()

    print("\nAPI: supplier saves through the gate")
    with TestClient(main.app) as client:
        # Ensure a supplier row exists, then authenticate as that supplier.
        db_path = os.path.join(os.getcwd(), "invoices.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        mobile = f"03{uuid.uuid4().hex[:9]}"
        cur.execute(
            "INSERT INTO supplier_users (name, company_name, mobile, status) VALUES (?,?,?,?)",
            ("Gate Test", "Al-Badar Enterprises", mobile, "verified"),
        )
        supplier_id = cur.lastrowid
        conn.commit()
        conn.close()

        main.app.dependency_overrides[get_current_principal] = (
            lambda: Principal(kind="supplier", id=supplier_id)
        )
        _run(client, supplier_id, "Al-Badar Enterprises")

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL VENDOR-GATE TESTS PASSED")
    print("=" * 60)
