"""Duplicate invoice check — the blocking key: Reference, PO, NTN, Vendor, Company Code.

An invoice is a duplicate of an EARLIER live invoice with the same key, and is
refused at submit-for-approval, at every SAP park mode (including the
submit-time dry run) and on forward status changes. See
services/duplicate_detection.py.

Offline: fake SAP (fixture PO 4500009001 — company code 1100, vendor
0002000101), no Gemini, no network. Uses its own throwaway SQLite database,
recreated on every run, so the synced PO always carries its company code.

    py -3 backend/test_duplicate_check.py
"""

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before app.config is imported (the engine is built at import time).
SCRATCH = os.path.join(tempfile.gettempdir(), "duplicate_check_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GCP_CREDENTIALS_JSON"] = ""

from app.config import settings  # noqa: E402

settings.DEBUG = True
settings.SAP_MODE = "fake"
settings.SAP_ENABLED = True
settings.SAP_FAKE_DB_PATH = ""

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.models.internal_user import InternalUser  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402
from app.services.duplicate_detection import compare_keys, _norm_ntn  # noqa: E402

PO = "4500009001"
OTHER_PO = "4500009005"
NTN = "0912345-6"
LINE = {"description": "Split AC Unit 1.5 Ton Inverter", "quantity": 20, "unit": "ST",
        "unit_price": 185000, "amount": 3700000}

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


# ── 1. Pure rule ─────────────────────────────────────────────────────────────

def _key(**kw):
    base = {"reference": "inv-1", "po": "4500009001", "ntn": "0912345",
            "vendor": "2000101", "company_code": "1100"}
    base.update(kw)
    return base


def test_rule_unit():
    print("\nUNIT: compare_keys / NTN normalisation")
    expect("all five equal -> duplicate",
           compare_keys(_key(), _key()) == ["reference", "po", "ntn", "vendor", "company_code"])
    expect("different reference -> not a duplicate", compare_keys(_key(), _key(reference="inv-2")) is None)
    expect("different PO -> not a duplicate", compare_keys(_key(), _key(po="4500009002")) is None)
    expect("different NTN -> not a duplicate", compare_keys(_key(), _key(ntn="1111111")) is None)
    expect("different vendor -> not a duplicate", compare_keys(_key(), _key(vendor="2000102")) is None)
    expect("different company code -> not a duplicate", compare_keys(_key(), _key(company_code="1200")) is None)
    expect("NTN missing on one side -> compared on the rest",
           compare_keys(_key(), _key(ntn="")) == ["reference", "po", "vendor", "company_code"])
    expect("no PO on this invoice -> cannot be judged", compare_keys(_key(po=""), _key(po="")) is None)
    expect("NTN with and without check digit are the same NTN", _norm_ntn("5433744-3") == _norm_ntn("5433744"))
    expect("short NTN is zero-padded", _norm_ntn("912345") == _norm_ntn("0912345-6"))
    expect("13-digit CNIC compares in full",
           _norm_ntn("35202-1234567-1") != _norm_ntn("35202-1234567-9"))


# ── 2. Over HTTP, as the UI drives it ────────────────────────────────────────

def _po_id(client, po_number):
    r = client.post(f"/api/sap/pos/{po_number}/sync")
    expect(f"sync PO {po_number} from fake SAP -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])
    body = r.json() or {}
    return body.get("po_id") or body.get("id") or (body.get("po") or {}).get("id")


def _save(client, invoice_number, ntn=NTN, po_reference=PO):
    payload = {
        "original_filename": "dup.pdf", "stored_filepath": "dup", "mime_type": "application/pdf",
        "invoice_number": invoice_number, "invoice_date": "2026-03-12", "currency": "PKR",
        "supplier_name": "Haier Pakistan (Pvt) Ltd", "supplier_ntn": ntn,
        "document_type": "invoice", "status": "validated", "source_type": "upload",
        "po_reference": po_reference,
        "subtotal_amount": 3700000, "tax_amount": 0, "total_amount": 3700000,
        "line_items": [dict(LINE)],
    }
    r = client.post("/api/invoices/save", json=payload)
    expect(f"save {invoice_number!r} -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])
    return r.json()["id"]


def _match(client, inv_id, po_id):
    r = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": po_id})
    expect(f"match invoice {inv_id} -> 200 (got {r.status_code})", r.status_code == 200, r.text[:160])


def _dups(client, inv_id):
    return client.get(f"/api/invoices/{inv_id}/duplicates").json()


def _is_dup_block(r):
    return r.status_code == 409 and "Duplicate invoice" in r.text


def test_api(client):
    po_id = _po_id(client, PO)
    other_po_id = _po_id(client, OTHER_PO)
    ref = f"DUP-{uuid.uuid4().hex[:6].upper()}"

    print("\nAPI: the original and a re-send")
    a = _save(client, ref)
    _match(client, a, po_id)
    # same reference in another case with stray spaces, NTN without its check digit
    b = _save(client, f"  {ref.lower()} ", ntn="0912345")
    _match(client, b, po_id)

    d = _dups(client, b)
    expect("re-send is flagged as a duplicate", d.get("is_duplicate") is True, d)
    first = (d.get("duplicate_matches") or [{}])[0]
    expect("it points at the original", first.get("id") == a, first)
    expect("matched on all five fields (company code from the synced PO)",
           first.get("matched_on") == ["Reference", "PO", "NTN", "Vendor", "Company Code"], first.get("matched_on"))
    expect("the original is not listed again as a softer warning",
           a not in [m["id"] for m in d.get("exact_matches", []) + d.get("probable_matches", [])
                     + d.get("possible_matches", [])])

    print("\nAPI: the re-send is blocked everywhere")
    r = client.post(f"/api/approvals/invoice/{b}/initiate")
    expect(f"submit for approval -> 409 duplicate (got {r.status_code})", _is_dup_block(r), r.text[:200])
    r = client.post(f"/api/sap/invoices/{b}/post", json={"mode": "validate"})
    expect(f"SAP dry run -> 409 duplicate (got {r.status_code})", _is_dup_block(r), r.text[:200])
    r = client.post(f"/api/sap/invoices/{b}/post", json={"mode": "park"})
    expect(f"SAP park -> 409 duplicate (got {r.status_code})", _is_dup_block(r), r.text[:200])
    r = client.patch(f"/api/invoices/{b}/status", json={"status": "posted"})
    expect(f"status -> posted -> 409 duplicate (got {r.status_code})", _is_dup_block(r), r.text[:200])
    still = client.get(f"/api/invoices/{b}").json()
    expect("the refused invoice is unchanged", still["status"] == "validated" and not still.get("sap_document_number"),
           (still["status"], still.get("sap_document_number")))

    print("\nAPI: the original is never blocked by a later copy")
    expect("original is not a duplicate", _dups(client, a).get("is_duplicate") is False)
    r = client.post(f"/api/sap/invoices/{a}/post", json={"mode": "validate"})
    expect(f"original's SAP dry run is not refused as a duplicate (got {r.status_code})",
           not _is_dup_block(r), r.text[:200])

    print("\nAPI: what is NOT a duplicate")
    c = _save(client, ref, ntn="1111111-1")
    _match(client, c, po_id)
    expect("different NTN -> not a duplicate", _dups(client, c).get("is_duplicate") is False)
    e = _save(client, f"{ref}-X")
    _match(client, e, po_id)
    expect("different reference -> not a duplicate", _dups(client, e).get("is_duplicate") is False)
    g = _save(client, ref, po_reference=OTHER_PO)
    _match(client, g, other_po_id)
    expect("different PO -> not a duplicate", _dups(client, g).get("is_duplicate") is False)
    r = client.post(f"/api/approvals/invoice/{c}/initiate")
    expect(f"non-duplicate submit is not refused as a duplicate (got {r.status_code})",
           not _is_dup_block(r), r.text[:200])

    print("\nAPI: missing data does not let a duplicate through")
    n = _save(client, ref, ntn=None)
    _match(client, n, po_id)
    d = _dups(client, n)
    expect("no NTN -> still a duplicate", d.get("is_duplicate") is True, d)
    expect("... compared on the other four",
           (d.get("duplicate_matches") or [{}])[0].get("matched_on") == ["Reference", "PO", "Vendor", "Company Code"],
           (d.get("duplicate_matches") or [{}])[0].get("matched_on"))
    u = _save(client, ref, po_reference=f"00{PO}")  # never matched; PO only printed on the invoice
    d = _dups(client, u)
    expect("unmatched invoice is caught through its printed PO reference", d.get("is_duplicate") is True, d)

    print("\nAPI: retiring the original releases the copy")
    r = client.patch(f"/api/invoices/{a}/status", json={"status": "exception"})
    expect(f"original -> exception (got {r.status_code})", r.status_code == 200, r.text[:160])
    expect("re-send is no longer a duplicate", _dups(client, b).get("is_duplicate") is False)


if __name__ == "__main__":
    test_rule_unit()

    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin")
    main.app.dependency_overrides[get_current_internal_user] = lambda: InternalUser(
        id=1, email="admin@tmcltd.com", display_name="Test Admin",
        password_hash="x", role="admin", is_active=1)

    with TestClient(main.app) as client:
        test_api(client)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL DUPLICATE CHECK TESTS PASSED")
    print("=" * 60)
