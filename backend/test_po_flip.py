"""
HTTP + DB integration test for the PO-flip API.

PO-flip is SUPPLIER-ONLY (see app/routers/po_flip.py): listing open POs and
flipping one require a supplier principal whose company matches the PO's
vendor. Creating/cancelling the PO is an internal action. So this test runs
as an internal admin for PO setup and as a seeded, verified supplier for the
flip itself — and asserts that an internal caller is refused.

Run from anywhere (the app and this script share the same ./invoices.db in
the current working directory):

    py -3 backend/test_po_flip.py
"""

import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402

_failures = []


def expect(label, cond):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}")
    if not cond:
        _failures.append(label)


def as_internal():
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin"
    )


def as_supplier(supplier_id):
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="supplier", id=supplier_id
    )


def seed_supplier(company_name):
    """Insert a verified supplier with no SAP vendor link, so PO ownership
    falls back to the lenient company-name match (same pattern as
    test_supplier_vendor_gate.py). Returns the new supplier id."""
    conn = sqlite3.connect(os.path.join(os.getcwd(), "invoices.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO supplier_users (name, company_name, mobile, status) VALUES (?,?,?,?)",
        ("Flip Test", company_name, f"03{uuid.uuid4().hex[:9]}", "verified"),
    )
    supplier_id = cur.lastrowid
    conn.commit()
    conn.close()
    return supplier_id


def _run(client):
    as_internal()
    po_number = f"FLIP-{uuid.uuid4().hex[:8]}"

    # 1) create an open PO with two lines
    r = client.post("/api/purchase-orders/", json={
        "po_number": po_number,
        "vendor_name": "AL-BADAR ENTERPRISES",
        "vendor_ntn": "6611174-8",
        "status": "open",
        "line_items": [
            {"description": "Khaka / stone dust", "quantity": 517.55, "unit": "ton", "unit_price": 390},
            {"description": "Loading charges", "quantity": 1, "unit": "job", "unit_price": 5000},
        ],
    })
    expect(f"create PO -> 201 (got {r.status_code})", r.status_code == 201)
    po_id = r.json()["id"]

    # 2) PO-flip is supplier-only: an internal caller is refused outright
    r = client.get("/api/po-flip/open-pos")
    expect(f"open-pos as internal -> 403 (got {r.status_code})", r.status_code == 403)

    # ...and the matching supplier sees the PO in their flippable list
    supplier_id = seed_supplier("AL-BADAR ENTERPRISES")
    as_supplier(supplier_id)
    r = client.get("/api/po-flip/open-pos")
    expect(f"open-pos as supplier -> 200 (got {r.status_code})", r.status_code == 200)
    pos = {p["po_number"]: p for p in r.json()} if r.status_code == 200 else {}
    expect("created PO is flippable", po_number in pos)
    expect("PO has 2 lines", len(pos.get(po_number, {}).get("line_items", [])) == 2)

    # 3) flip it with a partial-qty override on line 1. The supplier's own
    #    tax-invoice number is required (duplicate-checked per vendor).
    line1 = pos[po_number]["line_items"][0]
    r = client.post(f"/api/po-flip/{po_id}/create-invoice", json={
        "invoice_number": f"AB-{uuid.uuid4().hex[:6]}",
        "invoice_date": "2026-06-10",
        "line_overrides": [{"po_line_item_id": line1["id"], "quantity": 500}],
    })
    expect(f"flip -> 201 (got {r.status_code})", r.status_code == 201)
    body = r.json()
    # 500 * 390 + 1 * 5000 = 200,000; GST 18% = 36,000; total 236,000
    expect(f"subtotal = 200000 (got {body.get('subtotal_amount')})",
           body.get("subtotal_amount") == 200000.00)
    expect(f"gst = 36000 (got {body.get('gst_amount')})",
           body.get("gst_amount") == 36000.00)
    expect(f"total = 236000 (got {body.get('total_amount')})",
           body.get("total_amount") == 236000.00)
    expect("status = draft", body.get("status") == "draft")
    expect("line_count = 2", body.get("line_count") == 2)

    # 4) the draft invoice exists and carries the PO reference
    inv_id = body["invoice_id"]
    as_internal()
    r = client.get(f"/api/invoices/{inv_id}")
    expect(f"invoice fetch -> 200 (got {r.status_code})", r.status_code == 200)
    inv = r.json()
    expect("po_reference set", inv.get("po_reference") == po_number)
    expect("source_type = po_flip", inv.get("source_type") == "po_flip")

    # 4b) the match is recorded, so parking can route each line by it
    r = client.get(f"/api/po-matching/invoices/{inv_id}/matches")
    expect(f"match results fetch -> 200 (got {r.status_code})", r.status_code == 200)
    matches = r.json() if r.status_code == 200 else []
    lm = (matches[0].get("line_matches") if matches else None) or []
    expect("the flip invoice has a saved match", len(matches) == 1)
    expect("every invoice line is paired with its PO line",
           len(lm) == 2 and all(m.get("invoice_line_item_id") and m.get("po_line_item_id") for m in lm))

    # 5) flipping a cancelled PO is refused (cancel as internal, flip as supplier)
    client.patch(f"/api/purchase-orders/{po_id}/status", json={"status": "cancelled"})
    as_supplier(supplier_id)
    r = client.post(f"/api/po-flip/{po_id}/create-invoice", json={})
    expect(f"cancelled PO flip -> 400 (got {r.status_code})", r.status_code == 400)

    # 6) unknown PO -> 404
    r = client.post("/api/po-flip/999999/create-invoice", json={})
    expect(f"missing PO -> 404 (got {r.status_code})", r.status_code == 404)


if __name__ == "__main__":
    with TestClient(main.app) as client:
        _run(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL PO-FLIP TESTS PASSED")
    print("=" * 60)
