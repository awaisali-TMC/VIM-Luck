"""
PO-lane regression baseline — run BEFORE and AFTER any change that could touch
the existing PO invoice flow (e.g. the Non-PO work). It drives the real code
path end to end against a real SAP PO:

    sync PO from SAP -> save invoice -> 2-way match -> validated
    -> POST /api/sap/invoices/{id}/post  mode=validate   (dry run)

`validate` calls BAPI_INCOMINGINVOICE_PARK and then BAPI_TRANSACTION_ROLLBACK,
so NOTHING is persisted in SAP. Locally it leaves a synced PO and one invoice
row in ./invoices.db, like the other integration scripts.

Needs live SAP: set SAP_PASSWD (and SAP_* if not defaults) in the environment,
e.g. from the sap-passwd secret. Optional:
    REG_PO              SAP PO to use (default 4500000378)
    REG_TRANSCRIPT_OUT  path to write the normalized transcript JSON

    py -3 backend/test_po_regression.py
"""

import json
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.models.internal_user import InternalUser  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402

PO_NUMBER = os.environ.get("REG_PO", "4500000378").strip()
POSTING_DATE = "2025-05-20"  # inside SAP DEV's open period (see sap_invoice_post.py)

_failures = []
_transcript = {"po": PO_NUMBER, "steps": []}


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}")
    _transcript["steps"].append({"label": label, "ok": bool(cond), **({"detail": extra} if extra else {})})
    if not cond:
        _failures.append(label)


def as_internal_admin():
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin"
    )
    # The park endpoint depends on get_current_internal_user and checks .role.
    main.app.dependency_overrides[get_current_internal_user] = lambda: InternalUser(
        id=1, email="regression@test", display_name="Regression", password_hash="x",
        role="admin", is_active=1,
    )


def local_po(po_number):
    conn = sqlite3.connect(os.path.join(os.getcwd(), "invoices.db"))
    row = conn.execute(
        "SELECT id, vendor_name FROM purchase_orders WHERE po_number = ?", (po_number,)
    ).fetchone()
    unit = None
    if row:
        u = conn.execute(
            "SELECT unit FROM po_line_items WHERE po_id = ? ORDER BY item_number LIMIT 1", (row[0],)
        ).fetchone()
        unit = u[0] if u else None
    conn.close()
    return (row[0], row[1], unit) if row else (None, None, None)


def _run(client):
    as_internal_admin()

    # 1) the PO exists locally (synced from SAP; 409 = already there)
    r = client.post(f"/api/sap/pos/{PO_NUMBER}/sync")
    expect(f"sync PO {PO_NUMBER} -> 200/409 (got {r.status_code})", r.status_code in (200, 409))
    po_id, vendor_name, unit = local_po(PO_NUMBER)
    expect(f"PO is in local DB (id={po_id}, vendor={vendor_name!r})", po_id is not None)
    if po_id is None:
        return

    # 2) an invoice against it — one line, no tax (I0)
    inv_no = f"REG-{uuid.uuid4().hex[:8]}"
    r = client.post("/api/invoices/save", json={
        "original_filename": "regression.pdf", "stored_filepath": "regression", "mime_type": "application/pdf",
        "invoice_number": inv_no, "invoice_date": POSTING_DATE, "currency": "PKR",
        "supplier_name": vendor_name, "po_reference": PO_NUMBER,
        "subtotal_amount": 1000, "tax_amount": 0, "total_amount": 1000,
        "status": "pending_processing", "source_type": "upload",
        "line_items": [{"description": "Regression line", "quantity": 1, "unit": unit or "EA",
                        "unit_price": 1000, "amount": 1000}],
    })
    expect(f"save invoice -> 200 (got {r.status_code})", r.status_code == 200)
    inv_id = r.json()["id"]

    r = client.put(f"/api/invoices/{inv_id}", json={
        "sap_tax_code": "I0", "sap_layout": "goods", "sap_currency": "PKR",
        "sap_posting_date": POSTING_DATE, "sap_baseline_date": POSTING_DATE,
        "sap_header_text": f"einv-{inv_no}", "sap_item_text": inv_no,
    })
    expect(f"set SAP parking fields -> 200 (got {r.status_code})", r.status_code == 200)

    # 3) 2-way match to the PO (sets matched_po_id — the park prerequisite)
    r = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": po_id, "match_type": "2-way"})
    expect(f"2-way match -> 200 (got {r.status_code})", r.status_code == 200,
           extra=(r.json().get("match_status") if r.status_code == 200 else r.text[:200]))

    # 4) validated
    r = client.patch(f"/api/invoices/{inv_id}/status", json={"status": "validated"})
    expect(f"status -> validated (got {r.status_code})", r.status_code == 200)

    # 5) THE BASELINE: the existing PO park endpoint in validate (dry-run) mode
    r = client.post(f"/api/sap/invoices/{inv_id}/post", json={"mode": "validate"})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text[:300]}
    msgs = [
        {k: (m.get(k) or "").strip() for k in ("TYPE", "ID", "NUMBER", "MESSAGE")}
        for m in (body.get("sap_return") or (body.get("detail") or {}).get("sap_return", []) if isinstance(body.get("detail"), dict) else body.get("sap_return") or [])
    ]
    _transcript["validate"] = {"http": r.status_code, "ok": body.get("ok"), "message": body.get("message"), "sap_return": msgs}
    print(f"     HTTP {r.status_code} | ok={body.get('ok')} | {body.get('message')}")
    for m in msgs:
        print(f"     [{m['TYPE']}] {m['ID']}{m['NUMBER']}: {m['MESSAGE'][:100]}")
    expect("validate dry-run -> HTTP 200", r.status_code == 200)
    expect("validate dry-run -> ok=True (SAP accepted the PO invoice)", body.get("ok") is True)

    # 6) a dry run must not persist anything
    r = client.get(f"/api/invoices/{inv_id}")
    inv = r.json()
    expect("status still 'validated' after dry run", inv.get("status") == "validated")
    expect("no SAP document number stamped by dry run", not inv.get("sap_document_number"))


if __name__ == "__main__":
    with TestClient(main.app) as client:
        _run(client)
    out = os.environ.get("REG_TRANSCRIPT_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(_transcript, f, indent=2)
        print(f"\ntranscript -> {out}")
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: PO-LANE BASELINE PASSED")
    print("=" * 60)
