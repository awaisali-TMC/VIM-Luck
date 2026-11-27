"""MIR7 reference document category 2 (Delivery Note) / 4 (Service Entry Sheet).

Covers:
  - find_grs_by_reference on the fake SAP: a delivery note (EKBE-XBLNR) finds its
    PO and GR; an entry sheet (EKBE-LFBNR) finds its service PO and GR; the GR
    keys are the Goods Receipts card's keys; unknown numbers find nothing; bad
    category / empty number are refused
  - API GET /api/sap/reference-lookup: the PO is synced into VIM (po_id), 404 for
    an unknown number, 400 for a bad category

Offline (fake SAP, no Gemini). Own throwaway SQLite database.

    py -3 backend/test_reference_lookup.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

SCRATCH = os.path.join(tempfile.gettempdir(), "reference_lookup_test.db")
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
from app.services.sap_po_service import fetch_gr_overview, find_grs_by_reference  # noqa: E402

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def test_service():
    print("\nFAKE SAP: find_grs_by_reference")
    dn = find_grs_by_reference("delivery_note", "dn-2026-00417")
    expect("delivery note -> its PO", dn["po_numbers"] == ["4500009001"], dn)
    # GR 5000009001 received two PO items, so the note covers both of its lines.
    expect("delivery note -> every line of its GR",
           dn["gr_keys"] == ["2026/5000009001/0001", "2026/5000009001/0002"], dn)
    ov = fetch_gr_overview("4500009001")
    card_keys = {g["gr_key"] for g in ov["open"] + ov["closed"]}
    expect("each GR carries its PO item", [g["po_item"] for g in dn["grs"]] == [10, 20], dn["grs"])
    expect("GR key is the Goods Receipts card's key", set(dn["gr_keys"]) <= card_keys, card_keys)

    ses = find_grs_by_reference("service_entry_sheet", "1000009001")
    expect("entry sheet -> its service PO", ses["po_numbers"] == ["4700009001"], ses)
    expect("entry sheet -> its GR", ses["gr_keys"] == ["2026/5000009002/0001"], ses)

    none = find_grs_by_reference("delivery_note", "NO-SUCH-NOTE")
    expect("unknown delivery note -> nothing", none["po_numbers"] == [] and none["gr_keys"] == [], none)
    for cat, num in (("bill_of_lading", "X"), ("delivery_note", "  ")):
        try:
            find_grs_by_reference(cat, num)
            expect(f"refused: {cat!r} / {num!r}", False)
        except ValueError:
            expect(f"refused: {cat!r} / {num!r}", True)


def test_api(client):
    print("\nAPI: GET /api/sap/reference-lookup")
    r = client.get("/api/sap/reference-lookup", params={"category": "delivery_note", "number": "DN-2026-00418"})
    d = r.json() if r.status_code == 200 else {}
    expect(f"delivery note -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
    expect("... PO synced into VIM (po_id)", bool(d.get("po_id")) and d.get("po_number") == "4500009001", d)
    expect("... the second GR", d.get("gr_keys") == ["2026/5000009006/0001"], d.get("gr_keys"))
    r2 = client.get("/api/sap/reference-lookup", params={"category": "delivery_note", "number": "DN-2026-00417"})
    expect("same PO again -> same po_id, not re-created",
           r2.status_code == 200 and r2.json().get("po_id") == d.get("po_id"), r2.text[:200])
    r = client.get("/api/sap/reference-lookup", params={"category": "service_entry_sheet", "number": "1000009001"})
    expect(f"entry sheet -> 200 (got {r.status_code})",
           r.status_code == 200 and r.json().get("po_number") == "4700009001", r.text[:200])
    r = client.get("/api/sap/reference-lookup", params={"category": "delivery_note", "number": "NOPE"})
    expect(f"unknown number -> 404 (got {r.status_code})", r.status_code == 404, r.text[:200])
    r = client.get("/api/sap/reference-lookup", params={"category": "supplier", "number": "1"})
    expect(f"bad category -> 400 (got {r.status_code})", r.status_code == 400, r.text[:200])


if __name__ == "__main__":
    test_service()
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(kind="internal", id=1, role="admin")
    with TestClient(main.app) as client:
        test_api(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL REFERENCE LOOKUP TESTS PASSED")
    print("=" * 60)
