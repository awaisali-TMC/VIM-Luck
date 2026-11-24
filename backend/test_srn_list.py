"""GRN summary attached to the invoice: the SRNs the AI reads from it decide which
goods receipts are ticked — checked against SAP, never trusted blindly.

Offline: Gemini is stubbed (how well it reads a real scan is NOT tested here), fake
SAP (PO 4500009001 item 10: GR 5000009001 = 12, GR 5000009006 = 8), own throwaway DB.

    py -3 backend/test_srn_list.py
"""

import io
import json
import os
import sys
import tempfile
import types as pytypes
import uuid

sys.path.insert(0, os.path.dirname(__file__))

SCRATCH = os.path.join(tempfile.gettempdir(), "srn_list_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
UPLOADS = tempfile.mkdtemp(prefix="srn_list_uploads_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["GEMINI_API_KEY"] = ""
os.environ["UPLOAD_DIR"] = UPLOADS

from app.config import settings  # noqa: E402

settings.DEBUG = True
settings.SAP_MODE = "fake"
settings.SAP_ENABLED = True
settings.SAP_FAKE_DB_PATH = ""
settings.SAP_WORKFLOW_ENABLED = False

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
import app.routers.invoices as inv_router  # noqa: E402
import app.services.gemini_extract as gx  # noqa: E402
from app.models.internal_user import InternalUser  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402
from app.services.srn_list import check_receipts, clean_receipts, share_receipts  # noqa: E402

PO = "4500009001"
A, B = "2026/5000009001/0001", "2026/5000009006/0001"
_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def rec(number, **kw):
    return {"number": number, "po_number": None, "quantity": None, "amount": None, "freight": None, **kw}


def test_units():
    print("\nUNIT: cleaning, sharing, checking")
    got = clean_receipts([{"number": "50 0202 9076", "quantity": "57.52", "amount": "34,512.00", "po_number": "1010027885"},
                          {"number": "5002029076"}, {"number": "500202907"}, {"number": None}, "x",
                          {"number": 5002029077, "quantity": "n/a"}])
    expect("10-digit numbers only, no duplicates, amounts as numbers",
           [(r["number"], r["quantity"], r["amount"], r["po_number"]) for r in got]
           == [("5002029076", 57.52, 34512.0, "1010027885"), ("5002029077", None, None, None)], got)
    expect("nonsense from the client is ignored", clean_receipts("abc") == [] and clean_receipts(None) == [])
    r1, r2 = rec("5002029076", po_number="1010027885"), rec("5002029099", po_number="1010099999")
    expect("the summary in the freight part also goes to the goods invoice",
           share_receipts([("1010027885", []), ("1010027885", [r1])], []) == [[r1], [r1]])
    expect("an invoice of another PO does not get it",
           share_receipts([("1010099999", []), ("1010027885", [r1])], [r2]) == [[r2], [r1]])
    gr = {"gr_doc": "5002029070", "srn": ["5002029076"], "received": 57.52, "amount": 34512.0, "reason": None}
    closed = {"gr_doc": "5002029071", "srn": ["5002029077"], "received": 58.96, "reason": "fully invoiced"}
    p = check_receipts([rec("5002029076", quantity=57.52), rec("5002029077"), rec("5002029999")], [gr], [closed])
    expect("closed and unknown SRNs are named; a matching one is not a problem",
           len(p) == 2 and "5002029077" in p[0] and "fully invoiced" in p[0] and "5002029999" in p[1], p)
    expect("a different quantity is named", "says 60" in check_receipts([rec("5002029076", quantity=60.0)], [gr], [])[0])
    expect("no quantity on the report: the amount is checked",
           check_receipts([rec("5002029076", amount=34512.0)], [gr], []) == []
           and "35,512.00" in check_receipts([rec("5002029076", amount=35512.0)], [gr], [])[0])
    two = [{"gr_doc": "5002029080", "srn": ["5002029080"], "received": q, "reason": None} for q in (12.0, 5.0)]
    expect("a document with two PO items: either quantity or the total is right",
           [check_receipts([rec("5002029080", quantity=q)], two, []) == [] for q in (12.0, 5.0, 17.0, 13.0)] == [True, True, True, False])
    expect("the same SRN on two rows keeps no quantity",
           clean_receipts([rec("5002029080", quantity=12), rec("5002029080", quantity=5)])[0]["quantity"] is None)
    expect("the 103 number is accepted too", check_receipts([rec("5002029070")], [gr], []) == [])

    print("\nUNIT: page ranges")
    pg = lambda n, num, starts, t="invoice": {"page": n, "invoice_number": num, "starts_new_invoice": starts, "page_type": t}  # noqa: E731
    expect("goods, freight, summary -> two invoices, the summary with the last",
           gx.ranges_from_pages([pg(1, "151", True), pg(2, "F-9", True), pg(3, None, True, "receipt_list")], 3) == [[1, 1], [2, 3]])
    expect("a summary in front joins the first invoice",
           gx.ranges_from_pages([pg(1, None, True, "receipt_list"), pg(2, "151", True), pg(3, "F-9", True)], 3) == [[1, 2], [3, 3]])
    expect("as before without a summary",
           gx.ranges_from_pages([{"page": 1, "invoice_number": "1", "starts_new_invoice": True},
                                 {"page": 2, "invoice_number": "1", "starts_new_invoice": True},
                                 {"page": 3, "invoice_number": "2", "starts_new_invoice": True}], 3) == [[1, 2], [3, 3]])


def test_extract():
    print("\nEXTRACTION (Gemini stubbed)")
    reply = {"fields": {"invoice_id": "151", "total_amount": 100}, "line_items": [],
             "goods_receipts": [{"number": "5002029076", "quantity": 57.52}, {"number": "12"}]}
    fake = pytypes.SimpleNamespace(models=pytypes.SimpleNamespace(
        generate_content=lambda **k: pytypes.SimpleNamespace(text=json.dumps(reply))))
    real = gx._get_client
    gx._get_client = lambda: fake
    try:
        got = gx.extract_invoice(b"x", "application/pdf")["goods_receipts"]
        expect("SRNs come through cleaned", [r["number"] for r in got] == ["5002029076"], got)
        reply.pop("goods_receipts")
        expect("no summary -> empty list", gx.extract_invoice(b"x", "application/pdf")["goods_receipts"] == [])
    finally:
        gx._get_client = real


_po_id = None


def _po(client):
    global _po_id
    if _po_id is None:
        r = client.post(f"/api/sap/pos/{PO}/sync")
        _po_id = r.json().get("po_id") or r.json().get("id")
    return _po_id


def save(client, po_id, qty, receipts, desc="Split AC Unit 1.5 Ton Inverter", price=185000):
    total = qty * price
    r = client.post("/api/invoices/save", json={
        "original_filename": "s.pdf", "stored_filepath": "demo/s", "mime_type": "application/pdf",
        "invoice_number": f"SRN-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
        "currency": "PKR", "document_type": "invoice", "status": "validated", "source_type": "upload",
        "po_reference": PO, "supplier_ntn": "0912345-6", "subtotal_amount": total, "tax_amount": 0,
        "total_amount": total, "goods_receipts": receipts,
        "line_items": [{"description": desc, "quantity": qty, "unit": "ST", "unit_price": price, "amount": total}],
    })
    i = r.json()["id"]
    m = client.post(f"/api/po-matching/invoices/{i}/match", json={"po_id": po_id})
    expect(f"save and match (got {r.status_code}/{m.status_code})", r.status_code == 200 and m.status_code == 200, m.text[:150])
    return i


def test_suggestion(client):
    print("\nTHE SUMMARY CHOOSES THE GOODS RECEIPTS")
    po_id = _po(client)
    og = lambda i: client.get(f"/api/sap/invoices/{i}/open-grs").json()  # noqa: E731
    inv = save(client, po_id, 12, [{"number": "5000009001", "quantity": 12}])
    d = client.get(f"/api/invoices/{inv}").json()
    expect("stored on the invoice", [r["number"] for r in d["srn_list"] or []] == ["5000009001"], d.get("srn_list"))
    b = og(inv)
    expect("12 billed of 20 open: the listed GR is ticked (the total alone could not say)",
           b["suggested"] == [A] and b["srn_count"] == 1 and b["srn_problems"] == [], (b["suggested"], b["srn_problems"]))
    expect("the listed GR is marked", [g["gr_key"] for g in b["grs"] if g["listed"] and g["po_item"] == 10] == [A])
    r = client.post(f"/api/sap/invoices/{inv}/post", json={"mode": "park", "tax_code": "I1", "layout": "goods", "posting_date": "20260312"})
    expect(f"parked without opening the card (got {r.status_code})", r.status_code == 200, r.text[:200])
    expect("...on that GR", client.get(f"/api/invoices/{inv}").json()["parking_gr_refs"] == [A])
    client.post(f"/api/sap/invoices/{inv}/unpark", json={})
    r = client.delete(f"/api/invoices/{inv}")
    expect(f"unparked and deleted (got {r.status_code})", r.status_code == 200, r.text[:150])

    inv = save(client, po_id, 20, [{"number": "5000009001", "quantity": 13}, {"number": "5000000000"}])
    b = og(inv)
    expect("listed GRs do not add up to the bill -> nothing ticked, although all open GRs would", b["suggested"] == [], b["suggested"])
    expect("the differences are named", len(b["srn_problems"]) == 2 and "13" in b["srn_problems"][0]
           and "5000000000" in b["srn_problems"][1], b["srn_problems"])
    client.delete(f"/api/invoices/{inv}")
    inv = save(client, po_id, 20, None)
    expect("no summary -> as before, all open GRs", sorted(og(inv)["suggested"]) == [A, B])
    client.delete(f"/api/invoices/{inv}")

    inv = save(client, po_id, 20, [{"number": "5009999999"}])
    b = og(inv)
    expect("a summary that names no receipt of SAP -> works as without one, but says so",
           sorted(b["suggested"]) == [A, B] and len(b["srn_problems"]) == 1, (b["suggested"], b["srn_problems"]))
    client.delete(f"/api/invoices/{inv}")

    f = save(client, po_id, 1, [{"number": "5000009006"}], desc="Freight", price=10000)
    client.put(f"/api/invoices/{f}", json={"sap_layout": "delivery"})
    c = client.get(f"/api/sap/invoices/{f}/delivery-costs").json()["costs"][0]
    expect("freight invoice: the listed SRN is marked", [(g["gr_key"], g["listed"]) for g in c["grs"]] == [(A, False), (B, True)], c["grs"])
    expect("...and suggested", c["suggested"] == [B] and "GRN summary" in c["suggested_from"], (c["suggested"], c["suggested_from"]))
    client.delete(f"/api/invoices/{f}")


def freight_costs(client, i):
    return client.get(f"/api/sap/invoices/{i}/delivery-costs").json()["costs"][0]


def test_different_times(client):
    print("\nGOODS, FREIGHT AND SUMMARY AT DIFFERENT TIMES")
    po_id = _po(client)
    og = lambda i: client.get(f"/api/sap/invoices/{i}/open-grs").json()  # noqa: E731

    def freight(net):
        i = save(client, po_id, 1, None, desc="Freight", price=net)
        client.put(f"/api/invoices/{i}", json={"sap_layout": "delivery"})
        return i

    f = freight(15000)
    c = freight_costs(client, f)
    expect("freight first, nothing else known -> every open SRN, as before", c["suggested"] == [A, B], c["suggested"])
    goods = save(client, po_id, 12, None)
    expect("goods of 12 out of 20, no summary -> left to the user", og(goods)["suggested"] == [], og(goods)["suggested"])
    client.put(f"/api/invoices/{f}/delivery-costs", json={"items": [
        {"po_item": 10, "cond_type": "FRA1", "tax_code": "I0", "gr_keys": [A]}]})
    expect("the freight invoice's SRNs tell which goods they are", og(goods)["suggested"] == [A], og(goods)["suggested"])
    client.put(f"/api/invoices/{f}/delivery-costs", json={"items": []})
    client.put(f"/api/invoices/{goods}/parking-grs", json={"gr_keys": [A]})
    c = freight_costs(client, f)
    expect("goods invoice ticked: the freight of the same SRNs equals this invoice",
           c["suggested"] == [A] and "invoice SRN-" in c["suggested_from"], (c["suggested"], c["suggested_from"]))
    f2 = freight(10000)
    c = freight_costs(client, f2)
    expect("a freight invoice those goods don't explain -> every open SRN, as before", c["suggested"] == [A, B], c["suggested"])
    client.delete(f"/api/invoices/{f2}")
    client.delete(f"/api/invoices/{f}")
    client.put(f"/api/invoices/{goods}/parking-grs", json={"gr_keys": []})

    print("\nA SUMMARY ATTACHED LATER (Gemini stubbed)")
    real = gx.extract_receipts
    pdf = b"%PDF-1.4\n%stub\n"

    def attach(i, found, doc_type="goods_receipt"):
        def fake(*a, **k):
            if isinstance(found, Exception):
                raise found
            return clean_receipts(found)
        gx.extract_receipts = fake
        try:
            return client.post(f"/api/invoices/{i}/attachments", data={"document_type": doc_type},
                               files={"file": ("srn.pdf", pdf, "application/pdf")})
        finally:
            gx.extract_receipts = real

    def srns(i):
        return [r["number"] for r in client.get(f"/api/invoices/{i}").json()["srn_list"] or []]

    r = attach(goods, [{"number": "5000009001", "quantity": 12}], doc_type="other")
    expect(f"another document type is not read (got {r.status_code})", r.status_code == 201 and srns(goods) == [])
    r = attach(goods, RuntimeError("AI down"))
    expect(f"AI failure: the file is kept, the message says so (got {r.status_code})",
           r.status_code == 201 and "could not be read" in r.json()["srn_message"] and srns(goods) == [], r.text[:200])
    r = attach(goods, [])
    expect("nothing found: kept, said so", r.status_code == 201 and "No SRN" in r.json()["srn_message"], r.text[:200])
    r = attach(goods, [{"number": "5000009001", "quantity": 12}])
    expect("SRNs read and stored", "1 SRN(s)" in r.json()["srn_message"] and srns(goods) == ["5000009001"], r.text[:200])
    b = og(goods)
    expect("...the user's empty choice stays, the summary's SRNs are offered",
           b["chosen"] is True and b["selected"] == [] and b["suggested"] == [A], (b["chosen"], b["suggested"]))
    attach(goods, [{"number": "5000009001", "quantity": 12}, {"number": "5000009006"}])
    expect("a second file adds, without doubles", sorted(srns(goods)) == ["5000009001", "5000009006"], srns(goods))
    f = freight(25000)
    c = freight_costs(client, f)
    expect("the freight invoice uses the summary that came with the goods invoice",
           c["suggested"] == [A, B] and "GRN summary of invoice" in c["suggested_from"], (c["suggested"], c["suggested_from"]))
    r = client.delete(f"/api/invoices/{goods}/srn-list")
    expect(f"the SRNs can be removed again (got {r.status_code})", r.status_code == 200 and srns(goods) == [])


def test_upload(client):
    print("\nONE PDF: goods invoice + freight invoice + GRN summary (Gemini stubbed)")
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    receipts = clean_receipts([{"number": "5000009001", "po_number": PO, "quantity": 12}])

    def result(number, total, rcpts, multi=False):
        fields = [{"label": k, "value": str(v), "field_name": k, "confidence": 95.0} for k, v in
                  (("invoice_id", number), ("purchase_order", PO), ("total_amount", total), ("net_amount", total))]
        return {"fields": fields, "line_items": [], "overall_confidence": 95.0, "document_type": "Tax Invoice", "page_count": 1,
                "processing_time_ms": 1, "warnings": [], "detected_taxes": [], "multiple_invoices": multi, "invoice_count": 2 if multi else 1,
                "goods_receipts": rcpts}

    calls = [result("151", 2220000, [], multi=True), result("151", 2220000, []), result("F-9", 15000, receipts)]
    real = (inv_router.extract_invoice, gx.segment_invoice_pages)
    inv_router.extract_invoice = lambda *a, **k: calls.pop(0)
    gx.segment_invoice_pages = lambda *a, **k: [[1, 1], [2, 3]]
    try:
        r = client.post("/api/invoices/upload", files={"file": ("bundle.pdf", buf.getvalue(), "application/pdf")})
    finally:
        inv_router.extract_invoice, gx.segment_invoice_pages = real
    body = r.json()
    expect(f"two drafts (got {r.status_code})", r.status_code == 200 and body.get("invoice_count") == 2, r.text[:200])
    got = {}
    for x in body.get("invoices", []):
        d = client.get(f"/api/invoices/{x['id']}").json()
        got[d["invoice_number"]] = [s["number"] for s in d["srn_list"] or []]
    expect("both carry the summary's SRN", got == {"151": ["5000009001"], "F-9": ["5000009001"]}, got)


if __name__ == "__main__":
    test_units()
    test_extract()
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(kind="internal", id=1, role="admin")
    main.app.dependency_overrides[get_current_internal_user] = lambda: InternalUser(
        id=1, email="admin@tmcltd.com", display_name="Test Admin", password_hash="x", role="admin", is_active=1)
    with TestClient(main.app) as client:
        test_suggestion(client)
        test_different_times(client)
        test_upload(client)
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL SRN LIST TESTS PASSED")
    print("=" * 60)
