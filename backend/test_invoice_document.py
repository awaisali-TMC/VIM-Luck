"""Original invoice document: view / download, and who may fetch what.

Covers GET /api/invoices/{id}/document and the `document_available` flag on the
invoice detail response:
  - staff can view (inline) and download (attachment) the uploaded file
  - a supplier reaches only their own invoices' files (404 otherwise)
  - stored_filepath is client-supplied on /save, so traversal, absolute paths,
    placeholders ("po-flip") and missing files must all give 404, never a file
  - the served type comes from the file's bytes, not the claimed mime_type

Offline: no SAP, no Gemini. Uses its own throwaway SQLite database and upload
folder (both in the temp dir), so backend/invoices.db and backend/uploads are
never touched.

    py -3 backend/test_invoice_document.py
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(__file__))

# Must be set before app.config is imported (the DB engine is built at import
# time, and environment variables beat backend/.env).
SCRATCH = tempfile.mkdtemp(prefix="invoice_document_test_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(SCRATCH, 'test.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(SCRATCH, "uploads")
os.environ["DEBUG"] = "true"
os.environ["SAP_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GCP_CREDENTIALS_JSON"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.config import settings  # noqa: E402
from app.security import get_current_principal, Principal  # noqa: E402
from app.services.file_storage import save_uploaded_file, resolve_stored_file  # noqa: E402

assert settings.UPLOAD_DIR.startswith(SCRATCH), "UPLOAD_DIR is not the scratch folder; .env won"
assert SCRATCH in settings.DATABASE_URL, "DATABASE_URL is not the scratch DB; .env won"

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
HTML = b"<html><script>alert(1)</script></html>"

STAFF = Principal(kind="internal", id=1, role="ap_manager")
SUPPLIER_A = Principal(kind="supplier", id=501)
SUPPLIER_B = Principal(kind="supplier", id=502)

_failures = []
_as = {"p": STAFF}


def expect(label, cond):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}")
    if not cond:
        _failures.append(label)


def save(client, who, stored_filepath, filename="invoice.pdf", mime="application/pdf"):
    """Create an invoice through the real /save endpoint, as `who`."""
    _as["p"] = who
    r = client.post("/api/invoices/save", json={
        "original_filename": filename,
        "stored_filepath": stored_filepath,
        "mime_type": mime,
        "invoice_number": f"DOC-{uuid.uuid4().hex[:8]}",
        "supplier_name": "",
        "total_amount": 1000,
        "status": "draft",
        "line_items": [],
    })
    assert r.status_code == 200, f"save failed: {r.status_code} {r.text}"
    return r.json()["id"]


def fetch(client, who, inv_id, download=False):
    _as["p"] = who
    return client.get(f"/api/invoices/{inv_id}/document", params={"download": "true"} if download else None)


def available(client, who, inv_id):
    _as["p"] = who
    r = client.get(f"/api/invoices/{inv_id}")
    return r.status_code, (r.json().get("document_available") if r.status_code == 200 else None)


if __name__ == "__main__":
    main.app.dependency_overrides[get_current_principal] = lambda: _as["p"]
    with TestClient(main.app) as client:
        pdf_path = save_uploaded_file(PDF, "Vendor Invoice 0417.pdf")
        png_path = save_uploaded_file(PNG, "scan.png")
        html_path = save_uploaded_file(HTML, "evil.pdf")  # HTML bytes behind a .pdf name

        print("\nSTAFF: view and download the uploaded file")
        inv = save(client, STAFF, pdf_path, filename="Vendor Invoice 0417.pdf")
        expect("detail reports document_available=True", available(client, STAFF, inv) == (200, True))
        r = fetch(client, STAFF, inv)
        expect(f"view -> 200 (got {r.status_code})", r.status_code == 200)
        expect("view body is the uploaded file", r.content == PDF)
        expect("view is application/pdf", r.headers.get("content-type") == "application/pdf")
        expect("view is inline", r.headers.get("content-disposition", "").startswith("inline"))
        expect("nosniff header set", r.headers.get("x-content-type-options") == "nosniff")
        expect("not cached", "no-store" in r.headers.get("cache-control", ""))
        r = fetch(client, STAFF, inv, download=True)
        cd = r.headers.get("content-disposition", "")
        expect(f"download -> 200 (got {r.status_code})", r.status_code == 200)
        expect("download is an attachment", cd.startswith("attachment"))
        # Names that need quoting go out RFC 5987-encoded (filename*=utf-8''...).
        expect("download keeps the original file name", "Vendor%20Invoice%200417.pdf" in cd)

        inv_png = save(client, STAFF, png_path, filename="scan", mime="image/png")
        r = fetch(client, STAFF, inv_png, download=True)
        expect("image served as image/png", r.headers.get("content-type") == "image/png")
        expect("name without extension gets the real one", "scan.png" in r.headers.get("content-disposition", ""))

        print("\nSUPPLIERS: only their own invoices")
        own = save(client, SUPPLIER_A, pdf_path)
        expect("supplier A views own invoice -> 200", fetch(client, SUPPLIER_A, own).status_code == 200)
        expect("supplier B, A's invoice -> 404", fetch(client, SUPPLIER_B, own).status_code == 404)
        expect("supplier B, A's invoice detail -> 404", available(client, SUPPLIER_B, own)[0] == 404)
        expect("supplier A, a staff invoice -> 404", fetch(client, SUPPLIER_A, inv).status_code == 404)
        expect("staff views supplier A's invoice -> 200", fetch(client, STAFF, own).status_code == 200)

        print("\nCLIENT-SUPPLIED PATHS: nothing outside the upload folder")
        secret = os.path.join(SCRATCH, "secret.txt")
        with open(secret, "w") as f:
            f.write("DATABASE_URL=postgresql://user:pw@host/db")
        rel = os.path.relpath(secret, settings.UPLOAD_DIR)
        attempts = {
            "absolute path": secret,
            "../ traversal": rel,
            "../ traversal, backslashes": rel.replace("/", "\\"),
            "traversal ending in a valid-looking name": os.path.join(settings.UPLOAD_DIR, "..", "secret.txt"),
            "the database file": os.path.join(SCRATCH, "test.db"),
            "/proc/self/environ": "/proc/self/environ",
            "po-flip placeholder": "po-flip",
            "valid name, file missing": os.path.join(settings.UPLOAD_DIR, uuid.uuid4().hex + ".pdf"),
        }
        # /save itself rejects an empty path (NOT NULL), so check the helper directly.
        expect("empty stored path resolves to nothing",
               resolve_stored_file("") is None and resolve_stored_file(None) is None)
        bad_ids = []
        for label, stored in attempts.items():
            bad = save(client, SUPPLIER_A, stored)
            bad_ids.append(bad)
            r = fetch(client, SUPPLIER_A, bad)
            expect(f"{label} -> 404 (got {r.status_code})", r.status_code == 404)
            expect(f"{label} -> document_available=False", available(client, SUPPLIER_A, bad) == (200, False))
        expect("404 says the document is unavailable",
               "not available" in fetch(client, SUPPLIER_A, bad).json().get("detail", ""))

        print("\nLIST: per-row document_available (Invoice Inbox View/Download)")
        def listed(who):
            _as["p"] = who
            r = client.get("/api/invoices/", params={"limit": 100})
            return r.status_code, {row["id"]: row for row in r.json().get("invoices", [])}
        st, staff_rows = listed(STAFF)
        expect(f"staff list -> 200 (got {st})", st == 200)
        expect("staff list: PDF row available", staff_rows.get(inv, {}).get("document_available") is True)
        expect("staff list: image row available", staff_rows.get(inv_png, {}).get("document_available") is True)
        st, a_rows = listed(SUPPLIER_A)
        expect("supplier list: own row available", a_rows.get(own, {}).get("document_available") is True)
        expect("supplier list: every bad-path row unavailable",
               all(a_rows.get(i, {}).get("document_available") is False for i in bad_ids))
        expect("supplier list: no staff invoices", inv not in a_rows and inv_png not in a_rows)
        _, b_rows = listed(SUPPLIER_B)
        expect("supplier B list: none of supplier A's rows", own not in b_rows and not set(bad_ids) & set(b_rows))

        print("\nTYPE COMES FROM THE BYTES, NOT THE CLAIM")
        spoof = save(client, STAFF, html_path, filename="evil.pdf", mime="text/html")
        r = fetch(client, STAFF, spoof)
        expect("HTML bytes are not served as HTML", "html" not in r.headers.get("content-type", ""))
        expect("unknown bytes go out as octet-stream", r.headers.get("content-type") == "application/octet-stream")
        expect("unknown bytes are never inline", r.headers.get("content-disposition", "").startswith("attachment"))

        print("\nAUTH: the route needs a session")
        main.app.dependency_overrides.clear()
        r = client.get(f"/api/invoices/{inv}/document")
        expect(f"no token -> 401 (got {r.status_code})", r.status_code == 401)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} INVOICE DOCUMENT TEST(S) FAILED")
        for f in _failures:
            print(f"  - {f}")
        print("=" * 60)
        sys.exit(1)
    print("RESULT: ALL INVOICE DOCUMENT TESTS PASSED")
    print("=" * 60)
