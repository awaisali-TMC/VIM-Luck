"""Fake SAP connector — contract, fixtures and the demo path. Fully offline.

The fake stands in for a real SAP system, so what matters is that it honours the
same contract the real connector does. A fake that is merely *convenient* would
let bugs through locally and fail in production, which is the opposite of useful.

    DEBUG=true SAP_MODE=fake py -3 backend/test_sap_fake.py

Both env vars are required: the module refuses to import without DEBUG, and
sap_connector.py only swaps the class in when SAP_MODE=fake.
"""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SAP_MODE", "fake")

from app.config import settings  # noqa: E402

settings.DEBUG = True
settings.SAP_MODE = "fake"
settings.SAP_ENABLED = True
# Stay hermetic: a developer with SAP_FAKE_DB_PATH set in .env must not have this
# suite parking documents into the database they are demoing from.
settings.SAP_FAKE_DB_PATH = ""

from app.services.sap_connector import SAPConnector  # noqa: E402
import app.services.sap_po_service as po_svc  # noqa: E402

_failures = []

PO_GOODS = "4500009001"
PO_SERVICE = "4700009001"
PO_BLOCKED = "4500009002"
PO_SERVICE_2 = "4700009002"       # second service PO, entry sheet 1000009002 accepted
PO_PARTIAL = "4500009004"         # 30 laptops ordered, 18 received
PO_SERVICE_NO_SES = "4700009003"  # service PO, no entry sheet ever accepted
PO_PACKAGING = "4500009005"       # three items, fully received: the line-routing demo

FIXTURE_PO_COUNT = 8  # EKKO rows in sap_fixtures/data.sql


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def _read(sap, table, options, fields, rowcount=None):
    """The exact call shape every RFC_READ_TABLE caller in the app uses."""
    kwargs = {}
    if rowcount is not None:
        kwargs["ROWCOUNT"] = rowcount
    return sap.call(
        "RFC_READ_TABLE", QUERY_TABLE=table, DELIMITER="|",
        input_tables={"OPTIONS": [{"TEXT": t} for t in options],
                      "FIELDS": [{"FIELDNAME": f} for f in fields]},
        tables=["DATA", "FIELDS"],
        table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        **kwargs,
    )


# ── 1. The response contract ─────────────────────────────────────────────────

def test_contract():
    print("\nCONTRACT: what the real connector guarantees")
    sap = SAPConnector()
    sap.connect()

    expect("the fake is installed under the real name", SAPConnector.__name__ == "SAPConnectorFake")
    expect("ping works without an SDK", sap.ping() is True)
    expect("system info identifies itself as fake", sap.get_system_info().get("RFCSYSID") == "FAK",
           sap.get_system_info())

    fields = ["EBELN", "BUKRS", "BSART", "LIFNR", "BEDAT", "WAERS"]
    res = _read(sap, "EKKO", ["BSTYP = 'F'"], fields)

    # FIELDS is echoed back in input order — _parse_delimited_rows positionally
    # zips it against WA, so any reordering silently mislabels every column.
    echoed = [f["FIELDNAME"] for f in res["FIELDS"]]
    expect("FIELDS is echoed back in the requested order", echoed == fields, echoed)

    wa = res["DATA"][0]["WA"].split("|")
    expect("WA column count matches FIELDS", len(wa) == len(fields), wa)

    parsed = po_svc._parse_delimited_rows(res["DATA"], res["FIELDS"])
    expect("the app's own parser round-trips it", parsed[0]["EBELN"] == PO_GOODS, parsed[0])

    # Zero-padded keys must stay strings — TEXT affinity, not INTEGER.
    expect("zero-padded LIFNR survives as a string",
           parsed[0]["LIFNR"] == "0002000101", parsed[0].get("LIFNR"))

    # Only what was asked for comes back.
    only_data = sap.call("RFC_READ_TABLE", QUERY_TABLE="EKKO", DELIMITER="|",
                         input_tables={"OPTIONS": [], "FIELDS": [{"FIELDNAME": "EBELN"}]},
                         tables=["DATA"], table_fields={"DATA": ["WA"]})
    expect("unrequested tables are absent from the result", set(only_data) == {"DATA"}, sorted(only_data))

    # An unknown table must shout, not return []. A silent empty table is
    # indistinguishable from "SAP has no such row" and costs an afternoon.
    try:
        _read(sap, "ZZ_NOT_A_TABLE", [], ["FOO"])
        expect("unknown table raises", False, "no exception")
    except RuntimeError as e:
        expect("unknown table raises rather than returning []", "fixture" in str(e).lower(), str(e)[:90])

    try:
        _read(sap, "EKKO", [], ["NOT_A_COLUMN"])
        expect("unknown column raises", False, "no exception")
    except RuntimeError as e:
        expect("unknown column raises", "no such column" in str(e).lower(), str(e)[:90])

    # An unimplemented function must look like SAP's own failure, because
    # routers/sap.py sniffs for "GetFunctionDesc" to pick a fallback BAPI.
    try:
        sap.call("BAPI_SOMETHING_UNIMPLEMENTED")
        expect("unknown BAPI raises", False, "no exception")
    except RuntimeError as e:
        expect("unknown BAPI raises a GetFunctionDesc error", "GetFunctionDesc" in str(e), str(e)[:90])

    sap.disconnect()


# ── 2. The WHERE clause ──────────────────────────────────────────────────────

def test_where():
    print("\nWHERE: the clause the app builds must mean what it means in SAP")
    sap = SAPConnector()
    sap.connect()

    def count(table, options, fields, rowcount=None):
        return len(_read(sap, table, options, fields, rowcount)["DATA"])

    expect("AND across two OPTIONS rows",
           count("EKPO", [f"EBELN = '{PO_GOODS}' ", "AND LOEKZ = '' "], ["EBELN", "EBELP"]) == 2)

    # OPTIONS rows concatenate with NO separator — the trailing spaces are baked
    # into each row on purpose. Joining with anything else corrupts the clause.
    expect("OR across rows, prefix style the app uses",
           count("LFA1", ["LIFNR = '0002000101' ", "OR LIFNR = '0002000102' "], ["LIFNR", "NAME1"]) == 2)

    expect("LIKE with a trailing %",
           count("LFA1", ["MCOD1 LIKE 'HAIER%'"], ["LIFNR", "NAME1"]) == 1)

    # SAP dates are YYYYMMDD strings, so range comparisons are string comparisons.
    expect("date range >= and <=",
           count("EKKO", ["BEDAT >= '20260301' ", "AND BEDAT <= '20260331' "], ["EBELN", "BEDAT"]) == 2)

    expect("empty OPTIONS returns everything", count("T001", [], ["BUKRS"]) == 1)
    expect("ROWCOUNT caps the result", count("EKKO", [], ["EBELN"], rowcount="2") == 2)
    expect("absent ROWCOUNT does not cap", count("EKKO", [], ["EBELN"]) == FIXTURE_PO_COUNT)

    sap.disconnect()


# ── 3. Invoice BAPIs ─────────────────────────────────────────────────────────

def _park(sap, po_number, po_item="00010", amount="3700000", post=False):
    name = "BAPI_INCOMINGINVOICE_CREATE1" if post else "BAPI_INCOMINGINVOICE_PARK"
    return sap.call(
        name,
        input_structures={"HEADERDATA": {
            "INVOICE_IND": "X", "DOC_TYPE": "RE", "DOC_DATE": "20260312",
            "PSTNG_DATE": "20260312", "COMP_CODE": "1100", "CURRENCY": "PKR",
            "GROSS_AMOUNT": amount, "REF_DOC_NO": "INV-9001",
        }},
        input_tables={"ITEMDATA": [{
            "INVOICE_DOC_ITEM": "000001", "PO_NUMBER": po_number, "PO_ITEM": po_item,
            "TAX_CODE": "I1", "ITEM_AMOUNT": amount, "QUANTITY": "20", "PO_UNIT": "ST",
        }], "TAXDATA": []},
        tables=["RETURN"],
        table_fields={"RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE", "MESSAGE_V1", "MESSAGE_V2"]},
        output_params=["INVOICEDOCNUMBER", "FISCALYEAR"],
    )


def _rbkp(sap, doc):
    return _read(sap, "RBKP", [f"BELNR = '{doc}'"], ["BELNR", "GJAHR", "RBSTAT"])["DATA"]


def test_invoice_bapis():
    print("\nBAPI: park, validate, post, delete")
    sap = SAPConnector()
    sap.connect()

    res = _park(sap, PO_GOODS)
    doc = res.get("INVOICEDOCNUMBER", "").strip()
    errors = [m for m in res["RETURN"] if m.get("TYPE", "").strip() in ("E", "A")]
    expect("park returns a document number", doc.startswith("510"), doc)
    expect("park reports no errors", errors == [], errors)
    expect("fiscal year comes back", res.get("FISCALYEAR") == "2026", res.get("FISCALYEAR"))

    # Scalars must be str — sap_invoice_post.py does .strip() with no `or ""`.
    expect("INVOICEDOCNUMBER is a string, never None", isinstance(res.get("INVOICEDOCNUMBER"), str))

    sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
    expect("committed park is visible in RBKP", len(_rbkp(sap, doc)) == 1)
    expect("parked documents carry RBSTAT 'A'", _rbkp(sap, doc)[0]["WA"].split("|")[2] == "A",
           _rbkp(sap, doc))

    # mode="validate" is park-then-rollback, and must leave nothing behind.
    res2 = _park(sap, PO_GOODS)
    doc2 = res2.get("INVOICEDOCNUMBER", "").strip()
    sap.call("BAPI_TRANSACTION_ROLLBACK")
    expect("rolled-back park leaves no RBKP row", len(_rbkp(sap, doc2)) == 0, doc2)
    expect("a rolled-back document number is not reused", doc2 != doc)

    # The scripted failure — the part of the demo that shows error handling.
    res3 = _park(sap, PO_BLOCKED)
    errs3 = [m for m in res3["RETURN"] if m.get("TYPE", "").strip() in ("E", "A")]
    expect("blocked-vendor PO is refused", len(errs3) == 1, res3["RETURN"])
    expect("the refusal is readable", "blocked" in errs3[0]["MESSAGE"].lower(), errs3[0]["MESSAGE"])
    expect("a refused park returns no document number",
           res3.get("INVOICEDOCNUMBER", "") == "", res3.get("INVOICEDOCNUMBER"))

    # An item that does not exist on the PO must be refused, not accepted.
    res4 = _park(sap, PO_GOODS, po_item="00090")
    errs4 = [m for m in res4["RETURN"] if m.get("TYPE", "").strip() in ("E", "A")]
    expect("unknown PO item is refused", len(errs4) == 1, res4["RETURN"])

    # SAP reports a successful reversal as an ERROR row; the app filters M8/417
    # back out. Returning a cheerful "S" here would be read as a FAILURE.
    res5 = sap.call("BAPI_INCOMINGINVOICE_DELETE", INVOICEDOCNUMBER=doc, FISCALYEAR="2026",
                    tables=["RETURN"], table_fields={"RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE"]})
    row = res5["RETURN"][0]
    expect("delete reports success as M8/417",
           (row["TYPE"], row["ID"], row["NUMBER"]) == ("E", "M8", "417"), row)
    real_errors = [m for m in res5["RETURN"]
                   if m.get("TYPE", "").strip() in ("E", "A")
                   and not (m.get("ID", "").strip() == "M8" and m.get("NUMBER", "").strip() == "417")]
    expect("the app's own filter reads that as success", real_errors == [], real_errors)

    sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
    expect("deleted document is gone from RBKP", len(_rbkp(sap, doc)) == 0)

    sap.disconnect()


# ── 4. The demo path, through the real service layer ─────────────────────────

def test_services():
    print("\nSERVICES: the app's own code paths, unmodified")

    pos = po_svc.fetch_po_list(max_rows=50)
    expect("PO list returns the fixtures", len(pos) == FIXTURE_PO_COUNT, len(pos))
    by_po = {p["po_number"]: p for p in pos}
    expect("PO list carries the vendor NTN",
           by_po[PO_GOODS].get("vendor_ntn") == "0912345-6", by_po.get(PO_GOODS))

    detail = po_svc.fetch_po_detail(PO_GOODS)
    expect("PO detail resolves the vendor name",
           detail["vendor_name"] == "Haier Pakistan (Pvt) Ltd", detail.get("vendor_name"))

    # LFA1-STCD1 was always fetched and then discarded, so this was permanently
    # "" — which silently disabled the cross-check between SAP's vendor master
    # and the NTN the extractor reads off the invoice.
    expect("PO detail carries the vendor NTN from LFA1-STCD1",
           detail["vendor_ntn"] == "0912345-6", detail.get("vendor_ntn"))
    expect("and it survives the conversion to local PO format",
           po_svc.sync_po_to_db(detail, None)["vendor_ntn"] == "0912345-6",
           po_svc.sync_po_to_db(detail, None).get("vendor_ntn"))
    expect("PO detail returns both line items", len(detail["line_items"]) == 2)
    expect("goods item is not flagged as a service", detail["line_items"][0]["is_service"] is False)

    svc_detail = po_svc.fetch_po_detail(PO_SERVICE)
    expect("service PO item is flagged as a service",
           svc_detail["line_items"][0]["is_service"] is True, svc_detail["line_items"][0])

    grns = po_svc.fetch_grn_for_po(PO_GOODS)
    expect("GRN is found for the goods PO", len(grns) == 1, grns)
    expect("GRN nets the received quantity",
           grns[0]["line_items"][0]["received_quantity"] == 20.0, grns[0]["line_items"][0])

    partial = po_svc.fetch_grn_for_po(PO_PARTIAL)
    expect("partial PO: only 18 of 30 are received",
           len(partial) == 1 and partial[0]["line_items"][0]["received_quantity"] == 18.0, partial)

    # Service lines are invoiced against the accepted entry sheet (EKBE-LFBNR),
    # which is what the park path reads through fetch_service_grn_refs.
    svc2 = po_svc.fetch_po_detail(PO_SERVICE_2)
    expect("second service PO item is flagged as a service",
           svc2["line_items"][0]["is_service"] is True, svc2["line_items"][0])
    refs = po_svc.fetch_service_grn_refs(PO_SERVICE_2)
    expect("second service PO carries entry sheet 1000009002",
           refs.get(10, {}).get("sheet_no") == "1000009002", refs)
    expect("a service PO with no accepted entry sheet has no reference",
           po_svc.fetch_service_grn_refs(PO_SERVICE_NO_SES) == {},
           po_svc.fetch_service_grn_refs(PO_SERVICE_NO_SES))

    costs = po_svc.fetch_delivery_costs(PO_GOODS)
    expect("delivery costs are found", len(costs) == 1 and costs[0]["cond_type"] == "FRA1", costs)

    taxes = po_svc.fetch_tax_codes("1100")
    expect("tax codes come from the fixture, not the static fallback",
           taxes.get("procedure") == "TAXPK", taxes.get("procedure"))
    expect("tax code rates are parsed", any(t["rate"] == 18.0 for t in taxes["tax_codes"]),
           taxes.get("tax_codes"))

    currencies = po_svc.fetch_currencies()
    expect("currencies come from TCURT", len(currencies) == 6, len(currencies))

    vendor = po_svc.lookup_vendor(ntn="0912345-6")
    expect("vendor lookup by NTN resolves", vendor.get("vendor_number") == "0002000101", vendor)



# ── 5. The demo, over HTTP, exactly as the UI drives it ──────────────────────

def _invoice_payload(po_number, lines, number_prefix="DEMO"):
    subtotal = sum(l["amount"] for l in lines)
    return {
        "original_filename": f"invoice_{po_number}.pdf",
        "stored_filepath": f"demo/{po_number}", "mime_type": "application/pdf",
        "invoice_number": f"{number_prefix}-{uuid.uuid4().hex[:6].upper()}",
        "invoice_date": "2026-03-12", "currency": "PKR",
        "document_type": "invoice", "status": "validated", "source_type": "upload",
        "po_reference": po_number,
        "subtotal_amount": subtotal, "tax_amount": 0, "total_amount": subtotal,
        "line_items": lines,
    }


def _local_po_id(client, po_number):
    """The local PurchaseOrder row for a SAP PO, syncing it if it isn't there yet.

    These scripts share ./invoices.db, so on a second run the PO already exists
    and /sync answers 409. That is correct behaviour, not a failure — look the
    existing row up instead of treating a re-run as broken.
    """
    r = client.post(f"/api/sap/pos/{po_number}/sync")
    if r.status_code == 200:
        body = r.json() or {}
        return body.get("po_id") or body.get("id") or (body.get("po") or {}).get("id")
    if r.status_code != 409:
        expect(f"sync PO {po_number} -> 200 or 409 (got {r.status_code})", False, r.text[:160])
        return None
    found = client.get("/api/purchase-orders/search", params={"q": po_number})
    if found.status_code == 200:
        for row in (found.json() if isinstance(found.json(), list) else found.json().get("pos", [])):
            if row.get("po_number") == po_number:
                return row.get("id")
    listing = client.get("/api/purchase-orders/", params={"limit": 200}).json()
    for row in listing.get("purchase_orders", listing.get("pos", [])):
        if row.get("po_number") == po_number:
            return row.get("id")
    return None


def _park_via_api(client, po_number, lines, expect_ok=True, label=""):
    """Sync the PO, save an invoice against it, match, park. What the UI does."""
    po_id = _local_po_id(client, po_number)
    expect(f"{label}PO {po_number} is available locally", po_id is not None)

    inv = client.post("/api/invoices/save", json=_invoice_payload(po_number, lines)).json()
    inv_id = inv["id"]

    r = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": po_id})
    expect(f"{label}match invoice to PO -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])

    r = client.post(f"/api/sap/invoices/{inv_id}/post",
                    json={"mode": "park", "tax_code": "I1", "layout": "goods",
                          "posting_date": "20260312"})
    return inv_id, r


def test_end_to_end(client):
    print("\nEND TO END: upload -> match -> park, over HTTP")

    # The happy path: quantities and amounts agree with the PO.
    inv_id, r = _park_via_api(client, PO_GOODS, [
        {"description": "Split AC Unit 1.5 Ton Inverter", "quantity": 20, "unit": "ST",
         "unit_price": 185000, "amount": 3700000},
        {"description": "Deep Freezer 500L", "quantity": 5, "unit": "ST",
         "unit_price": 240000, "amount": 1200000},
    ])
    expect(f"park -> 200 (got {r.status_code})", r.status_code == 200, r.text[:300])
    body = r.json() if r.status_code == 200 else {}
    doc = body.get("sap_document_number") or body.get("document_number") or ""
    expect("SAP returned a document number", str(doc).startswith("510"), body)

    detail = client.get(f"/api/invoices/{inv_id}").json()
    expect("invoice is now parked", detail["status"] == "parked", detail.get("status"))
    expect("the document number is persisted on the invoice",
           detail.get("sap_document_number") == str(doc), detail.get("sap_document_number"))

    # Parking twice must be refused, not silently duplicated in SAP.
    again = client.post(f"/api/sap/invoices/{inv_id}/post", json={"mode": "park"})
    expect(f"a second park is refused (got {again.status_code})",
           again.status_code >= 400, again.text[:160])
    expect("and says the invoice is already parked", "parked" in again.text.lower(), again.text[:160])

    # Two distinct failure modes, and both are worth showing in a demo.
    #
    # 1. SAP refuses it. The request is well-formed, reaches the BAPI, and comes
    #    back with a RETURN row of TYPE 'E'.
    _, bad = _park_via_api(client, PO_BLOCKED, [
        {"description": "Industrial Solvent Drums 200L", "quantity": 100, "unit": "EA",
         "unit_price": 3500, "amount": 350000},
    ], label="blocked vendor: ")
    expect(f"blocked vendor is refused, not parked (got {bad.status_code})",
           bad.status_code >= 400, bad.text[:200])
    expect("the SAP message reaches the user verbatim",
           "blocked for posting" in bad.text.lower(), bad.text[:240])

    # 2. The app refuses it first. PO 4500009003 is under GR-based invoice
    #    verification (WEBRE='X') with no goods receipt, so nothing is ever sent.
    _, early = _park_via_api(client, "4500009003", [
        {"description": "OPC Cement 50kg Bags", "quantity": 2000, "unit": "BAG",
         "unit_price": 950, "amount": 1900000},
    ], label="no GR: ")
    expect(f"a PO awaiting its goods receipt is stopped locally (got {early.status_code})",
           early.status_code >= 400, early.text[:200])
    expect("and the reason names the missing goods receipt",
           "goods receipt" in early.text.lower(), early.text[:240])

    # A second service PO: the park must travel with its entry sheet and land.
    _, svc = _park_via_api(client, PO_SERVICE_2, [
        {"description": "IT Support & Maintenance - Q1 2026", "quantity": 1, "unit": "AU",
         "unit_price": 540000, "amount": 540000},
    ], label="2nd service PO: ")
    expect(f"second service PO parks (got {svc.status_code})", svc.status_code == 200, svc.text[:300])

    # The service twin of the no-GR case: never confirmed, so never sent.
    _, no_ses = _park_via_api(client, PO_SERVICE_NO_SES, [
        {"description": "Security Guard Services - March 2026", "quantity": 1, "unit": "AU",
         "unit_price": 480000, "amount": 480000},
    ], label="no SES: ")
    expect(f"a service PO without an entry sheet is stopped locally (got {no_ses.status_code})",
           no_ses.status_code >= 400, no_ses.text[:200])
    expect("and the reason names the missing entry sheet",
           "service entry sheet" in no_ses.text.lower(), no_ses.text[:240])


def _three_way(client, po_number, lines, label):
    """Import the PO's receipts, save an invoice, and run a 3-way match on it."""
    po_id = _local_po_id(client, po_number)
    r = client.post(f"/api/sap/pos/{po_number}/grn/sync")
    expect(f"{label}receipts import -> 200 (got {r.status_code})", r.status_code == 200, r.text[:200])
    inv_id = client.post("/api/invoices/save", json=_invoice_payload(po_number, lines)).json()["id"]
    m = client.post(f"/api/po-matching/invoices/{inv_id}/match",
                    json={"po_id": po_id, "match_type": "3-way"})
    expect(f"{label}3-way match -> 200 (got {m.status_code})", m.status_code == 200, m.text[:200])
    return inv_id, (m.json() if m.status_code == 200 else {})


def test_partial_delivery(client):
    print("\nPARTIAL DELIVERY: 30 ordered, 18 received")
    laptop = {"description": "Laptop Core i7 16GB 512GB SSD", "unit": "ST", "unit_price": 250000}

    # Billing for all 30 when only 18 arrived: the 3-way match must say no.
    _, over = _three_way(client, PO_PARTIAL, [{**laptop, "quantity": 30, "amount": 7500000}],
                         "over-billed: ")
    expect("billing 30 against 18 received is a mismatch",
           over.get("match_status") == "mismatch", over.get("match_status"))
    line = (over.get("line_matches") or [{}])[0]
    expect("the match line shows 18 received",
           line.get("grn_received_qty") == 18.0, line.get("grn_received_qty"))

    # Billing exactly what arrived: short of the PO, but every unit is received.
    inv_id, ok = _three_way(client, PO_PARTIAL, [{**laptop, "quantity": 18, "amount": 4500000}],
                            "billed as received: ")
    expect("billing the 18 received is a partial match, not a mismatch",
           ok.get("match_status") == "partial_match", ok.get("match_status"))
    r = client.post(f"/api/sap/invoices/{inv_id}/post",
                    json={"mode": "park", "tax_code": "I1", "layout": "goods",
                          "posting_date": "20260318"})
    expect(f"and it parks (got {r.status_code})", r.status_code == 200, r.text[:300])


# ── 5b. Which invoice lines can be parked ────────────────────────────────────
# A parked invoice line must sit on a PO item: the BAPI payload has no other row
# type. So a selected line with no PO item (typically freight the PO does not
# carry) is refused by name, instead of being guessed onto another PO item by
# position or silently left out of a document that then totals less than the
# invoice.

_PKG_LINES = [
    {"description": "Aluminium Foil Roll 20 Micron", "quantity": 400, "unit": "ST",
     "unit_price": 2250, "amount": 900000},
    {"description": "PVC Blister Film Roll 250mm", "quantity": 300, "unit": "ST",
     "unit_price": 2200, "amount": 660000},
    {"description": "Corrugated Carton 5-Ply", "quantity": 5000, "unit": "EA",
     "unit_price": 120, "amount": 600000},
]
_FREIGHT_LINE = {"description": "Freight and delivery charges", "quantity": 1, "unit": "AU",
                 "unit_price": 25000, "amount": 25000}


class _CallSpy:
    """Wraps a connector and records every BAPI call, so a test can inspect the payload."""

    def __init__(self, inner, log):
        self._inner, self._log = inner, log

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def call(self, name, *args, **kwargs):
        self._log.append((name, kwargs))
        return self._inner.call(name, *args, **kwargs)


def _with_spy(fn):
    import app.services.sap_invoice_post as post_mod
    calls = []
    real = post_mod._get_connector
    post_mod._get_connector = lambda: _CallSpy(real(), calls)
    try:
        return fn(), calls
    finally:
        post_mod._get_connector = real


def _invoice_bapi(calls):
    """(HEADERDATA, ITEMDATA rows) of the last invoice BAPI call, or (None, None)."""
    for name, kw in reversed(calls):
        if name.startswith("BAPI_INCOMINGINVOICE"):
            return kw["input_structures"]["HEADERDATA"], kw["input_tables"]["ITEMDATA"]
    return None, None


def _save_and_match(client, po_number, lines):
    po_id = _local_po_id(client, po_number)
    inv_id = client.post("/api/invoices/save", json=_invoice_payload(po_number, lines)).json()["id"]
    m = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": po_id})
    expect(f"match invoice {inv_id} to PO {po_number} -> 200 (got {m.status_code})",
           m.status_code == 200, m.text[:200])
    detail = client.get(f"/api/invoices/{inv_id}").json()
    return inv_id, [li["id"] for li in detail["line_items"]]


def _send(client, inv_id, mode="park", line_item_ids=None, layout="goods"):
    body = {"mode": mode, "tax_code": "I1", "layout": layout, "posting_date": "20260330"}
    if line_item_ids is not None:
        body["line_item_ids"] = line_item_ids
    return client.post(f"/api/sap/invoices/{inv_id}/post", json=body)


def test_route_helpers():
    print("\nROUTING HELPERS: pure rules, no HTTP")
    from app.services.invoice_line_rules import route_invoice_lines, unrouted_lines_message

    class L:
        def __init__(self, i, d, a):
            self.id, self.description, self.amount = i, d, a

    lines = [L(1, "Foil", 900000), L(2, "Freight", 25000), L(3, "Carton", 600000)]

    routed, unrouted = route_invoice_lines(lines, None, {1: 10, 3: 30}, None)
    expect("matched lines route to their PO item", routed == {1: 10, 3: 30}, routed)
    expect("a line with no match and no single item is unrouted, with its screen position",
           [(u["line_item_id"], u["position"]) for u in unrouted] == [(2, 2)], unrouted)

    routed, unrouted = route_invoice_lines(lines, {1, 3}, {1: 10, 3: 30}, None)
    expect("an unselected line is not reported", unrouted == [] and routed == {1: 10, 3: 30})

    routed, unrouted = route_invoice_lines(lines, None, {}, 10)
    expect("a PO with a single item takes every line", unrouted == [] and set(routed.values()) == {10})

    routed, unrouted = route_invoice_lines(lines, None, {}, None)
    expect("with no match and several PO items nothing is guessed by position",
           routed == {} and len(unrouted) == 3, (routed, unrouted))

    msg = unrouted_lines_message([{"line_item_id": 2, "position": 2, "description": "Freight",
                                   "amount": 25000.0}], "4500009005")
    expect("the message names the line, its amount and the PO",
           'line 2 "Freight" (25,000.00)' in msg and "4500009005" in msg, msg)
    expect("and tells the user how to fix it", "Uncheck or delete" in msg, msg)
    missing = unrouted_lines_message([], "4500009005", matching_missing=True)
    expect("no match at all points at PO matching", "Run PO matching" in missing, missing)


def test_line_routing(client):
    print("\nLINE ROUTING: select all, but a line with no PO item cannot be parked")

    # 1. Every line on the PO: all three are selected by default and it parks.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, _PKG_LINES)
    (r, calls) = _with_spy(lambda: _send(client, inv_id))
    expect(f"a clean three-line invoice parks (got {r.status_code})", r.status_code == 200, r.text[:300])
    _, items = _invoice_bapi(calls)
    expect("all three PO items are in the document", sorted(i["PO_ITEM"] for i in items) == ["00010", "00020", "00030"],
           items)

    # 2. The same invoice plus freight the PO does not carry.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, _PKG_LINES + [_FREIGHT_LINE])
    r = _send(client, inv_id)
    expect(f"park with an unroutable freight line is refused (got {r.status_code})", r.status_code == 422, r.text[:300])
    detail = r.json().get("detail", "") if r.status_code == 422 else ""
    expect("the refusal names the line and its position", 'line 4 "Freight and delivery charges"' in detail, detail)
    expect("it names the PO and says what to do", PO_PACKAGING in detail and "Uncheck or delete" in detail, detail)
    r = _send(client, inv_id, mode="validate")
    expect(f"the dry run refuses it the same way (got {r.status_code})", r.status_code == 422, r.text[:200])
    after = client.get(f"/api/invoices/{inv_id}").json()
    expect("the invoice was not parked", not after.get("sap_document_number"), after.get("sap_document_number"))

    # 3. Unchecking the freight line parks the rest as a partial park.
    (r, calls) = _with_spy(lambda: _send(client, inv_id, line_item_ids=ids[:3]))
    expect(f"parking only the three PO lines works (got {r.status_code})", r.status_code == 200, r.text[:300])
    header, items = _invoice_bapi(calls)
    expect("no unplanned delivery cost is sent",
           header is not None and "DEL_COSTS" not in header and "DEL_COSTS_TAXC" not in header, header)
    expect("gross is the selected net plus 18% tax (2,160,000 + 388,800)",
           header is not None and float(header["GROSS_AMOUNT"]) == 2548800.0, header)

    # 4. A freight line first in the list must not be folded onto item 10 by position.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, [_FREIGHT_LINE] + _PKG_LINES)
    r = _send(client, inv_id)
    expect(f"freight listed first is refused, not folded onto the first PO item (got {r.status_code})",
           r.status_code == 422, r.text[:300])
    detail = r.json().get("detail", "") if r.status_code == 422 else ""
    expect("and it is reported as line 1", 'line 1 "Freight and delivery charges"' in detail, detail)

    # 5. The selection saved at submit is honoured when the request carries none.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, _PKG_LINES + [_FREIGHT_LINE])
    s = client.put(f"/api/invoices/{inv_id}/parking-selection", json={"line_item_ids": ids[:3]})
    expect(f"the selection saves (got {s.status_code})", s.status_code == 200, s.text[:160])
    r = _send(client, inv_id)
    expect(f"a saved selection of the three PO lines parks (got {r.status_code})", r.status_code == 200, r.text[:300])

    # 6. A saved empty selection means 'nothing was saved', i.e. all lines.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, _PKG_LINES)
    client.put(f"/api/invoices/{inv_id}/parking-selection", json={"line_item_ids": []})
    r = _send(client, inv_id)
    expect(f"a saved empty selection parks every line (got {r.status_code})", r.status_code == 200, r.text[:300])

    # 7. A PO with one item still takes every invoice line.
    (inv_id, ids) = _save_and_match(client, PO_SERVICE_2, [
        {"description": "IT Support - Q1 2026, part A", "quantity": 1, "unit": "AU",
         "unit_price": 300000, "amount": 300000},
        {"description": "IT Support - Q1 2026, part B", "quantity": 1, "unit": "AU",
         "unit_price": 240000, "amount": 240000},
    ])
    (r, calls) = _with_spy(lambda: _send(client, inv_id))
    expect(f"two lines on a one-item service PO park (got {r.status_code})", r.status_code == 200, r.text[:300])
    _, items = _invoice_bapi(calls)
    expect("as a single document item", items is not None and len(items) == 1, items)

    # 8. Nothing selected is its own message.
    inv_id, ids = _save_and_match(client, PO_PACKAGING, _PKG_LINES)
    r = _send(client, inv_id, line_item_ids=[])
    expect(f"no lines selected is refused (got {r.status_code})", r.status_code == 400, r.text[:200])
    expect("and says so", "No line items are selected" in r.text, r.text[:200])

    # 9. A goods line whose text merely says "DELIVERY INFO" is an ordinary line:
    #    matched to its PO item, not treated as freight, and parked with the rest.
    noted = dict(_PKG_LINES[0],
                 description="Aluminium Foil Roll 20 Micron - DELIVERY INFO: DN-2026-00533, Weight 412 KG")
    inv_id, ids = _save_and_match(client, PO_PACKAGING, [noted] + _PKG_LINES[1:])
    (r, calls) = _with_spy(lambda: _send(client, inv_id))
    expect(f"a goods line that mentions DELIVERY INFO parks with the rest (got {r.status_code})",
           r.status_code == 200, r.text[:300])
    header, items = _invoice_bapi(calls)
    expect("all three PO items are in the document and no delivery cost is sent",
           items is not None and len(items) == 3 and "DEL_COSTS" not in header, (header, items))


# ── 6. The file-backed store ─────────────────────────────────────────────────

def test_file_backed_store():
    print("\nSTORE: SAP_FAKE_DB_PATH makes the fixtures inspectable")
    import sqlite3 as _sqlite3
    import tempfile
    from app.services import sap_connector_fake as fake

    tmp = Path(tempfile.mkdtemp()) / "nested" / "sap_fake.db"
    fake.reset_store()
    settings.SAP_FAKE_DB_PATH = str(tmp)
    try:
        sap = SAPConnector()
        sap.connect()
        expect("a path creates the file, parent dirs and all", tmp.exists(), tmp)

        res = _park(sap, PO_GOODS)
        doc = res.get("INVOICEDOCNUMBER", "").strip()
        sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
        sap.disconnect()

        # The point of the whole feature: read it from OUTSIDE the app's
        # connection, the way a DB browser would, while the app is still up.
        with _sqlite3.connect(f"file:{tmp}?mode=ro", uri=True) as ext:
            rows = ext.execute("SELECT BELNR, RBSTAT FROM RBKP WHERE BELNR = ?", (doc,)).fetchall()
        expect("a parked document is visible to an outside reader", rows == [(doc, "A")], rows)

        # And it survives a restart — which the in-memory store cannot do.
        fake.reset_store()
        sap2 = SAPConnector()
        sap2.connect()
        still = _rbkp(sap2, doc)
        expect("it is still there after the store is reopened", len(still) == 1, still)
        expect("reopening does NOT re-seed over existing data",
               len(_read(sap2, "EKKO", [], ["EBELN"])["DATA"]) == FIXTURE_PO_COUNT,
               "fixtures were seeded twice")
        sap2.disconnect()
    finally:
        settings.SAP_FAKE_DB_PATH = ""
        fake.reset_store()

    # Back to the default: in memory, nothing written to disk.
    sap3 = SAPConnector()
    sap3.connect()
    expect("with the setting empty, the store is in memory again",
           len(_rbkp(sap3, doc)) == 0, "the file-backed document leaked into memory mode")
    sap3.disconnect()


# ── 7. The production gate ───────────────────────────────────────────────────

def test_production_gate():
    print("\nGATE: the fake must be unable to load in production")
    import importlib
    import app.services.sap_connector_fake as fake

    settings.DEBUG = False
    try:
        importlib.reload(fake)
        expect("importing with DEBUG=False raises", False, "it imported cleanly")
    except RuntimeError as e:
        expect("importing with DEBUG=False raises", "DEBUG=False" in str(e), str(e)[:90])
    finally:
        settings.DEBUG = True
        importlib.reload(fake)


if __name__ == "__main__":
    test_contract()
    test_where()
    test_invoice_bapis()
    test_services()
    test_route_helpers()
    test_file_backed_store()

    from fastapi.testclient import TestClient
    import app.main as main
    from app.security import get_current_principal, get_current_internal_user, Principal
    from app.models.internal_user import InternalUser

    # Two overrides, because parking is gated differently from the rest: the
    # shared endpoints take get_current_principal, but /api/sap/invoices/{id}/post
    # checks user.role against SAP_PARK_ROLES and so needs a real InternalUser.
    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin")
    main.app.dependency_overrides[get_current_internal_user] = lambda: InternalUser(
        id=1, email="admin@tmcltd.com", display_name="Demo Admin",
        password_hash="x", role="admin", is_active=1)

    with TestClient(main.app) as client:
        test_end_to_end(client)
        test_partial_delivery(client)
        test_line_routing(client)

    test_production_gate()

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL FAKE SAP TESTS PASSED")
    print("=" * 60)
