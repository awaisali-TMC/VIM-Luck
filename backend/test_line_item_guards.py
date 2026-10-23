"""
Line-item guards — a line billing an amount with no quantity must not reach SAP.

Covers the three guards added alongside the frontend fix in LineItemsTable.jsx:

  1. services/invoice_line_rules.find_zero_quantity_goods  (pure, no SAP/HTTP)
  2. PATCH /api/invoices/{id}/line-items/{lid}  — explicit null refused
  3. PUT   /api/invoices/{id}                   — explicit null refused per line

Offline: no SAP, no Gemini. Writes rows to ./invoices.db like the other
integration scripts.

    py -3 backend/test_line_item_guards.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services.invoice_line_rules import (  # noqa: E402
    find_zero_quantity_goods,
    zero_quantity_message,
)

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def as_internal():
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin"
    )


def _payload(**overrides):
    base = {
        "original_filename": "guard.pdf", "stored_filepath": "guard", "mime_type": "application/pdf",
        "invoice_number": f"GRD-{uuid.uuid4().hex[:8]}", "invoice_date": "2026-09-01", "currency": "PKR",
        "supplier_name": "Karachi Office Supplies", "document_type": "invoice",
        "subtotal_amount": 1250, "tax_amount": 0, "total_amount": 1250,
        "status": "pending_processing", "source_type": "upload",
        "line_items": [{"description": "Trading goods", "quantity": 50, "unit": "ST",
                        "unit_price": 25, "amount": 1250}],
    }
    base.update(overrides)
    return base


# ── 1. Pure rule ─────────────────────────────────────────────────────────────

def test_rule_unit():
    print("\nUNIT: find_zero_quantity_goods")

    # amount billed, quantity missing -> flagged
    out = find_zero_quantity_goods({10: {"amount": 1250.0, "quantity": None}}, set())
    expect("null quantity with an amount is flagged", len(out) == 1, out)

    # amount billed, quantity zero -> flagged (this is the `or 0` case)
    out = find_zero_quantity_goods({10: {"amount": 1250.0, "quantity": 0.0}}, set())
    expect("zero quantity with an amount is flagged", len(out) == 1, out)

    # healthy line -> clean
    out = find_zero_quantity_goods({10: {"amount": 1250.0, "quantity": 50.0}}, set())
    expect("quantity present -> not flagged", out == [], out)

    # empty line is not an error
    out = find_zero_quantity_goods({10: {"amount": 0.0, "quantity": 0.0}}, set())
    expect("zero amount and zero quantity -> not flagged", out == [], out)

    # SERVICE items are value-based: SAP rejects QUANTITY on them
    out = find_zero_quantity_goods({10: {"amount": 1250.0, "quantity": 0.0}}, {10})
    expect("service item is exempt", out == [], out)

    # mixed: only the goods item is reported
    out = find_zero_quantity_goods(
        {10: {"amount": 1250.0, "quantity": 0.0}, 20: {"amount": 900.0, "quantity": 0.0}},
        {20},
    )
    expect("mixed goods/service -> only goods flagged", [o["po_item"] for o in out] == [10], out)

    # the message names the invoice line, not just the PO item
    out = find_zero_quantity_goods(
        {10: {"amount": 1250.0, "quantity": None}}, set(), {10: [33]}
    )
    msg = zero_quantity_message(out)
    expect("message names the offending line item id", "33" in msg, msg)
    expect("message is actionable", "quantity" in msg.lower(), msg)


# ── 2 & 3. API guards ────────────────────────────────────────────────────────

def _run_api(client):
    as_internal()

    print("\nAPI: PATCH /line-items/{id}")
    inv = client.post("/api/invoices/save", json=_payload()).json()
    inv_id, line_id = inv["id"], inv["line_items"][0]["id"]

    r = client.patch(f"/api/invoices/{inv_id}/line-items/{line_id}", json={"quantity": None})
    expect(f"explicit null quantity -> 400 (got {r.status_code})", r.status_code == 400, r.text[:160])

    r = client.patch(f"/api/invoices/{inv_id}/line-items/{line_id}", json={"unit_price": None})
    expect(f"explicit null unit_price -> 400 (got {r.status_code})", r.status_code == 400, r.text[:160])

    # The regression that matters: an OMITTED field is a normal partial update
    # and must still work. Confusing "unset" with "null" breaks every edit.
    r = client.patch(f"/api/invoices/{inv_id}/line-items/{line_id}", json={"description": "Renamed"})
    expect(f"omitting quantity -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])

    r = client.patch(f"/api/invoices/{inv_id}/line-items/{line_id}", json={"quantity": 4, "unit_price": 25})
    expect(f"valid numbers -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])
    expect("amount recomputed to 100", r.json()["line_item"]["amount"] == 100, r.json()["line_item"])

    # a text field may still be cleared
    r = client.patch(f"/api/invoices/{inv_id}/line-items/{line_id}", json={"unit": None})
    expect(f"null unit (text) still allowed -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])

    print("\nAPI: PUT /invoices/{id} (whole-invoice line replacement)")
    inv2 = client.post("/api/invoices/save", json=_payload()).json()
    inv2_id = inv2["id"]

    bad = {"line_items": [{"description": "Trading goods", "quantity": None,
                           "unit": "ST", "unit_price": 25, "amount": 1250}]}
    r = client.put(f"/api/invoices/{inv2_id}", json=bad)
    expect(f"PUT with a null quantity -> 400 (got {r.status_code})", r.status_code == 400, r.text[:160])
    expect("PUT error names the line", "Line 1" in r.text, r.text[:160])

    # the invoice must be untouched — the guard runs before any delete
    still = client.get(f"/api/invoices/{inv2_id}").json()
    expect("rejected PUT left the existing lines intact", len(still["line_items"]) == 1, still["line_items"])

    good = {"line_items": [{"description": "Trading goods", "quantity": 10,
                            "unit": "ST", "unit_price": 25, "amount": 250}]}
    r = client.put(f"/api/invoices/{inv2_id}", json=good)
    expect(f"PUT with valid lines -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])


if __name__ == "__main__":
    test_rule_unit()
    with TestClient(main.app) as client:
        _run_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL LINE-ITEM GUARD TESTS PASSED")
    print("=" * 60)
