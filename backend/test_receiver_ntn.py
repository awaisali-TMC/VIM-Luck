"""Receiver NTN: read from the invoice when it is printed, stored, shown, editable.

It is capture-only: never compared with the buyer's own NTN, never flagged or
warned on.

Covers:
  - extraction: the prompt asks for receiver_tax_id and it has a label; no
    attention flag is ever raised for it, whatever its value
  - _extraction_to_draft (batch-upload drafts): maps receiver_tax_id and adds no
    warning of its own
  - API: /save stores it; a missing value stays empty; the detail response
    returns it; PUT edits it; no warning is saved for it

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

from app.config import settings  # noqa: E402

assert SCRATCH in settings.DATABASE_URL, "DATABASE_URL is not the scratch DB; .env won"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.routers.invoices import _extraction_to_draft  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services.gemini_extract import EXTRACTION_PROMPT, FIELD_LABELS, _detect_attention_flags  # noqa: E402

NTN = "4455667-1"   # invented

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def test_extraction():
    print("\nUNIT: extraction")
    expect("prompt asks for receiver_tax_id", "receiver_tax_id" in EXTRACTION_PROMPT)
    expect("prompt says to leave it empty when not printed", "null when the invoice does not print it" in EXTRACTION_PROMPT)
    expect("receiver_tax_id has a label", FIELD_LABELS.get("receiver_tax_id") == "Receiver NTN")

    def receiver_flags(receiver):
        fm = {"invoice_id": "INV-1", "supplier_name": "Vendor", "supplier_tax_id": "1234567-8",
              "total_amount": 100, "currency": "PKR", "receiver_tax_id": receiver}
        return [f for f in _detect_attention_flags(fm, [], [], 99.0)
                if "receiver" in (f.get("title", "") + f.get("message", "")).lower()
                or "addressed" in f.get("title", "").lower()]

    expect("no attention flag for any receiver NTN", receiver_flags(NTN) == [], receiver_flags(NTN))
    expect("no attention flag when it is missing", receiver_flags(None) == [])

    result = {"fields": [{"field_name": "invoice_id", "value": "INV-9", "confidence": 99},
                         {"field_name": "receiver_tax_id", "value": NTN, "confidence": 99}],
              "line_items": [], "warnings": ["existing warning"]}
    draft = _extraction_to_draft(result, "a.pdf", "unsaved", "application/pdf", 10)
    expect("batch draft carries the receiver NTN", draft.receiver_ntn == NTN, draft.receiver_ntn)
    expect("batch draft keeps only the extraction's own warnings",
           draft.warnings == '["existing warning"]', draft.warnings)


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
    inv = save(client, NTN)
    expect("detail returns the receiver NTN", inv.get("receiver_ntn") == NTN, inv.get("receiver_ntn"))
    expect("no warning is saved for it", not inv.get("warnings"), inv.get("warnings"))

    empty = save(client, None)
    expect("not on the invoice -> stays empty", empty.get("receiver_ntn") is None, empty.get("receiver_ntn"))

    r = client.put(f"/api/invoices/{empty['id']}", json={"receiver_ntn": "0712345-6"})
    expect(f"PUT edits the receiver NTN (got {r.status_code})",
           r.status_code == 200 and r.json().get("receiver_ntn") == "0712345-6", r.text[:200])


if __name__ == "__main__":
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
