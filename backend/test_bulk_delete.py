"""Bulk delete of invoices (Inbox "Delete selected"), offline, own throwaway DB.

- plain invoices are soft-deleted;
- an invoice parked in SAP is skipped unless vim_only=true;
- vim_only=true is admin-only (403 for anyone else) and removes it from VIM
  only: the SAP document number stays on the row, nothing is sent to SAP.

    py -3 backend/test_bulk_delete.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCRATCH = os.path.join(tempfile.gettempdir(), "bulk_delete_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if extra is not None and not cond else ""))
    if not cond:
        _failures.append(label)


def as_role(role):
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(kind="internal", id=1, role=role)


def new_invoice(client, n):
    r = client.post("/api/invoices/save", json={
        "original_filename": f"b{n}.pdf", "stored_filepath": f"demo/b{n}", "mime_type": "application/pdf",
        "invoice_number": f"BULK-{n}", "invoice_date": "2026-11-20", "currency": "PKR",
        "document_type": "invoice", "status": "validated", "source_type": "upload",
        "subtotal_amount": 100, "tax_amount": 0, "total_amount": 100, "line_items": [],
    })
    return r.json()["id"]


def mark_parked(inv_id):
    import asyncio
    from sqlalchemy import update
    from app.database import async_session
    from app.models.invoice import Invoice

    async def run():
        async with async_session() as db:
            await db.execute(update(Invoice).where(Invoice.id == inv_id).values(
                status="parked", sap_document_number="5105660685", sap_fiscal_year="2027",
                sap_doc_status="parked", sap_wf_status="BLK"))
            await db.commit()
    asyncio.run(run())


if __name__ == "__main__":
    as_role("admin")
    with TestClient(main.app) as client:
        a, b, parked = new_invoice(client, 1), new_invoice(client, 2), new_invoice(client, 3)
        mark_parked(parked)

        print("NORMAL DELETE")
        r = client.post("/api/invoices/bulk-delete", json={"ids": [a, b, parked, 99999]})
        body = r.json()
        expect("200", r.status_code == 200, r.text[:200])
        expect("plain invoices deleted", sorted(body["deleted"]) == sorted([a, b]), body)
        reasons = {s["id"]: s["reason"] for s in body["skipped"]}
        expect("parked one skipped, with its SAP document", "5105660685" in reasons.get(parked, ""), reasons)
        expect("unknown id skipped", reasons.get(99999) == "not found", reasons)
        ids = [i["id"] for i in client.get("/api/invoices/").json()["invoices"]]
        expect("deleted ones gone from the list, parked one still there", a not in ids and parked in ids, ids)

        print("\nVIM-ONLY, NOT ADMIN")
        as_role("ap_operator")
        r = client.post("/api/invoices/bulk-delete", json={"ids": [parked], "vim_only": True})
        expect(f"403 (got {r.status_code})", r.status_code == 403, r.text[:200])

        print("\nVIM-ONLY, ADMIN")
        as_role("admin")
        r = client.post("/api/invoices/bulk-delete", json={"ids": [parked], "vim_only": True})
        expect("parked invoice removed from VIM", r.status_code == 200 and r.json()["deleted"] == [parked], r.text[:200])
        ids = [i["id"] for i in client.get("/api/invoices/").json()["invoices"]]
        expect("no longer listed", parked not in ids, ids)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL BULK DELETE TESTS PASSED")
