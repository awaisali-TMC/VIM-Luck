"""
SAP PO Fetch Service — fetch Purchase Orders from SAP via RFC.

Uses RFC_READ_TABLE to read EKKO (PO header) and EKPO (PO items),
then LFA1 (vendor master) for vendor names.
"""

import logging
import os
import re
from datetime import datetime

from app.services.sap_connector import SAPConnector

logger = logging.getLogger(__name__)


def _parse_delimited_rows(data_rows: list[dict], fields_info: list[dict], delimiter="|") -> list[dict]:
    """Parse RFC_READ_TABLE delimited output into a list of dicts."""
    field_names = [f.get("FIELDNAME", "").strip() for f in fields_info]
    result = []
    for row in data_rows:
        wa = row.get("WA", "")
        parts = wa.split(delimiter)
        record = {}
        for i, name in enumerate(field_names):
            record[name] = parts[i].strip() if i < len(parts) else ""
        result.append(record)
    return result


def _sap_date(raw: str) -> str | None:
    """Convert SAP date YYYYMMDD to ISO YYYY-MM-DD."""
    raw = raw.strip()
    if not raw or raw == "00000000":
        return None
    try:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    except Exception:
        return raw


def _safe_float(val: str) -> float | None:
    val = val.strip().replace(",", "")
    if not val or val == "0" or val == "0.000":
        return 0.0
    try:
        # SAP sometimes uses format like 1000.000- for negative
        if val.endswith("-"):
            return -float(val[:-1])
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_connector() -> SAPConnector:
    """Create a new SAP connector (adds DLL directory if needed)."""
    try:
        os.add_dll_directory(r"C:\nwrfcsdk\lib")
    except (OSError, AttributeError):
        pass
    return SAPConnector()


def fetch_po_list(max_rows: int = 100, company_code: str = None, vendor: str = None) -> list[dict]:
    """
    Fetch PO headers from SAP table EKKO.

    Returns list of dicts with: po_number, company_code, doc_type, vendor_number,
    po_date, currency, total_value.
    """
    sap = _get_connector()
    sap.connect()

    try:
        # Build WHERE clause
        where_parts = ["BSTYP = 'F'"]  # F = standard PO
        if company_code:
            where_parts.append(f"AND BUKRS = '{company_code}'")
        if vendor:
            where_parts.append(f"AND LIFNR = '{vendor.zfill(10)}'")

        options_rows = [{"TEXT": " ".join(where_parts)}]

        result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKKO",
            ROWCOUNT=str(max_rows),
            DELIMITER="|",
            input_tables={
                "OPTIONS": options_rows,
                "FIELDS": [
                    {"FIELDNAME": "EBELN"},   # PO number
                    {"FIELDNAME": "BUKRS"},   # Company code
                    {"FIELDNAME": "BSART"},   # Document type
                    {"FIELDNAME": "LIFNR"},   # Vendor number
                    {"FIELDNAME": "BEDAT"},   # PO date
                    {"FIELDNAME": "WAERS"},   # Currency
                    {"FIELDNAME": "RLWRT"},   # Total value
                    {"FIELDNAME": "LOEKZ"},   # Deletion flag
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )

        parsed = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))

        # Get vendor name + NTN in bulk
        vendor_numbers = list(set(r["LIFNR"] for r in parsed if r.get("LIFNR")))
        vendors = _fetch_vendor_master(sap, vendor_numbers) if vendor_numbers else {}

        pos = []
        for r in parsed:
            if r.get("LOEKZ", "").strip():  # skip deleted POs
                continue
            vendor_num = r.get("LIFNR", "")
            vendor = vendors.get(vendor_num) or {}
            pos.append({
                "po_number": r.get("EBELN", ""),
                "company_code": r.get("BUKRS", ""),
                "doc_type": r.get("BSART", ""),
                "vendor_number": vendor_num,
                "vendor_name": vendor.get("name", ""),
                "vendor_ntn": vendor.get("ntn", ""),
                "po_date": _sap_date(r.get("BEDAT", "")),
                "currency": r.get("WAERS", ""),
                "total_value": _safe_float(r.get("RLWRT", "0")),
            })

        logger.info(f"Fetched {len(pos)} POs from SAP")
        return pos

    finally:
        sap.disconnect()


def fetch_po_detail(po_number: str) -> dict | None:
    """
    Fetch a single PO with header + line items from SAP.

    Reads EKKO (header), EKPO (items), and LFA1 (vendor name + NTN).
    Returns dict with header fields + line_items list.
    """
    sap = _get_connector()
    sap.connect()

    try:
        po_num = po_number.strip().zfill(10)

        # Fetch header from EKKO
        header_result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKKO",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": f"EBELN = '{po_num}'"}],
                "FIELDS": [
                    {"FIELDNAME": "EBELN"},
                    {"FIELDNAME": "BUKRS"},
                    {"FIELDNAME": "BSART"},
                    {"FIELDNAME": "LIFNR"},
                    {"FIELDNAME": "BEDAT"},
                    {"FIELDNAME": "WAERS"},
                    {"FIELDNAME": "RLWRT"},
                    {"FIELDNAME": "EKGRP"},   # Purchasing group
                    {"FIELDNAME": "ZTERM"},    # Payment terms
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )

        headers = _parse_delimited_rows(
            header_result.get("DATA", []),
            header_result.get("FIELDS", []),
        )
        if not headers:
            return None

        h = headers[0]

        # Fetch line items from EKPO
        items_result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKPO",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": f"EBELN = '{po_num}' AND LOEKZ = ''"}],
                "FIELDS": [
                    {"FIELDNAME": "EBELN"},   # PO number
                    {"FIELDNAME": "EBELP"},   # PO item number
                    {"FIELDNAME": "TXZ01"},   # Short text / description
                    {"FIELDNAME": "MATNR"},   # Material number
                    {"FIELDNAME": "MENGE"},   # Quantity
                    {"FIELDNAME": "MEINS"},   # Order unit (OUn in ME23N)
                    {"FIELDNAME": "BPRME"},   # Order price unit (OPU in ME23N)
                    {"FIELDNAME": "NETPR"},   # Net price
                    {"FIELDNAME": "NETWR"},   # Net value
                    {"FIELDNAME": "WERKS"},   # Plant
                    {"FIELDNAME": "MATKL"},   # Material group
                    {"FIELDNAME": "PSTYP"},   # Item category (9 = service)
                    {"FIELDNAME": "WEBRE"},   # GR-based invoice verification flag
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )

        items_parsed = _parse_delimited_rows(
            items_result.get("DATA", []),
            items_result.get("FIELDS", []),
        )

        # Fetch vendor name + NTN
        vendor_num = h.get("LIFNR", "")
        vendors = _fetch_vendor_master(sap, [vendor_num]) if vendor_num else {}
        vendor = vendors.get(vendor_num) or {}
        vendor_name = vendor.get("name", "")
        vendor_ntn = vendor.get("ntn", "")

        # Build result
        line_items = []
        for item in items_parsed:
            line_items.append({
                "item_number": int(item.get("EBELP", "0") or "0"),
                "description": item.get("TXZ01", ""),
                "material_number": item.get("MATNR", ""),
                "quantity": _safe_float(item.get("MENGE", "0")),
                "unit": item.get("MEINS", ""),
                "price_unit": item.get("BPRME", "") or item.get("MEINS", ""),
                "unit_price": _safe_float(item.get("NETPR", "0")),
                "net_value": _safe_float(item.get("NETWR", "0")),
                "plant": item.get("WERKS", ""),
                "material_group": item.get("MATKL", ""),
                "item_category": item.get("PSTYP", ""),   # "9" = service item
                "is_service": item.get("PSTYP", "") == "9",
                "gr_based_iv": item.get("WEBRE", "") == "X",  # invoice must reference the GR
            })

        # RLWRT (total at release) is only filled for POs with a release
        # strategy — for ordinary POs it's 0, so fall back to the sum of the
        # item net values (EKPO NETWR).
        header_total = _safe_float(h.get("RLWRT", "0")) or 0
        if not header_total:
            header_total = round(sum((li["net_value"] or 0) for li in line_items), 2)

        po_detail = {
            "po_number": h.get("EBELN", ""),
            "company_code": h.get("BUKRS", ""),
            "doc_type": h.get("BSART", ""),
            "vendor_number": vendor_num,
            "vendor_name": vendor_name,
            "vendor_ntn": vendor_ntn,   # LFA1-STCD1
            "po_date": _sap_date(h.get("BEDAT", "")),
            "currency": h.get("WAERS", ""),
            "total_value": header_total,
            "purchasing_group": h.get("EKGRP", ""),
            "payment_terms": h.get("ZTERM", ""),
            "line_items": line_items,
            "source": "sap",
        }

        logger.info(f"Fetched PO {po_number} from SAP: {len(line_items)} line items")
        return po_detail

    finally:
        sap.disconnect()


def _fetch_vendor_master(sap: SAPConnector, vendor_numbers: list[str]) -> dict[str, dict]:
    """Fetch vendor name + tax number from LFA1. Returns {vendor_num: {name, ntn}}.

    The NTN (LFA1-STCD1) matters as much as the name: it is the cross-check
    against the NTN the extractor reads off the invoice PDF. If SAP's vendor
    master and the invoice disagree, either the invoice is from a different
    entity or the extraction is wrong — and neither can be spotted without this.
    """
    if not vendor_numbers:
        return {}

    # Build the WHERE across multiple OPTIONS rows. RFC_READ_TABLE concatenates
    # the rows, but each row's TEXT must stay within ~72 chars — a single long
    # "LIFNR = 'a' OR LIFNR = 'b' OR ..." string overflows that limit and fails
    # with SAPSQL_PARSE_ERROR. One vendor per row keeps every line short.
    terms = [v.strip() for v in vendor_numbers if v.strip()]
    if not terms:
        return {}
    options_rows = [
        {"TEXT": ("" if i == 0 else "OR ") + f"LIFNR = '{v}' "}
        for i, v in enumerate(terms)
    ]

    try:
        result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="LFA1",
            DELIMITER="|",
            input_tables={
                "OPTIONS": options_rows,
                "FIELDS": [
                    {"FIELDNAME": "LIFNR"},
                    {"FIELDNAME": "NAME1"},
                    {"FIELDNAME": "STCD1"},  # Tax number (NTN)
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )

        parsed = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))
        return {
            r["LIFNR"]: {
                "name": (r.get("NAME1") or "").strip(),
                "ntn": (r.get("STCD1") or "").strip(),
            }
            for r in parsed
        }

    except Exception as e:
        logger.warning(f"Vendor master lookup failed: {e}")
        return {}


def fetch_grn_for_po(po_number: str) -> list[dict]:
    """Fetch goods-receipt notes (GRNs) for a PO from SAP table EKBE (PO history).

    EKBE records every goods-movement against a PO line. We take the goods-receipt
    events (VGABE='1'), group them by material document (BELNR+GJAHR) — each
    material document is one GRN — and net the received quantity per PO item
    (debit SHKZG='S' adds, credit 'H' i.e. a reversal/return subtracts).

    Returns a list of:
        {grn_number, grn_year, grn_date, plant,
         line_items: [{po_item, material_number, received_quantity,
                       amount, movement_types}]}
    """
    sap = _get_connector()
    sap.connect()
    try:
        po_num = po_number.strip().zfill(10)
        # WHERE split across OPTIONS rows — RFC_READ_TABLE concatenates them and
        # each row's TEXT must stay within ~72 chars.
        result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKBE",
            ROWCOUNT="1000",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [
                    {"TEXT": f"EBELN = '{po_num}' "},
                    {"TEXT": "AND VGABE = '1' "},   # goods-receipt events only
                ],
                "FIELDS": [
                    {"FIELDNAME": "EBELP"},   # PO item
                    {"FIELDNAME": "GJAHR"},   # material doc year
                    {"FIELDNAME": "BELNR"},   # material doc number (= GRN)
                    {"FIELDNAME": "BWART"},   # movement type (101 GR, 102 reversal, …)
                    {"FIELDNAME": "BUDAT"},   # posting date
                    {"FIELDNAME": "MENGE"},   # quantity
                    {"FIELDNAME": "DMBTR"},   # amount in local currency
                    {"FIELDNAME": "WERKS"},   # plant
                    {"FIELDNAME": "MATNR"},   # material
                    {"FIELDNAME": "SHKZG"},   # debit/credit (S = receipt, H = reversal)
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )

        rows = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))

        grns: dict = {}
        for r in rows:
            belnr = r.get("BELNR", "").strip()
            if not belnr:
                continue
            gjahr = r.get("GJAHR", "").strip()
            key = (belnr, gjahr)
            sign = -1 if r.get("SHKZG", "").strip() == "H" else 1
            qty = (_safe_float(r.get("MENGE", "0")) or 0.0) * sign
            amt = (_safe_float(r.get("DMBTR", "0")) or 0.0) * sign
            try:
                item = int(r.get("EBELP", "0") or "0")
            except ValueError:
                item = 0

            grn = grns.setdefault(key, {
                "grn_number": belnr,
                "grn_year": gjahr,
                "grn_date": _sap_date(r.get("BUDAT", "")),
                "plant": r.get("WERKS", "").strip(),
                "_items": {},
            })
            li = grn["_items"].setdefault(item, {
                "po_item": item,
                "material_number": r.get("MATNR", "").strip(),
                "received_quantity": 0.0,
                "amount": 0.0,
                "_movements": set(),
            })
            li["received_quantity"] += qty
            li["amount"] += amt
            mvt = r.get("BWART", "").strip()
            if mvt:
                li["_movements"].add(mvt)

        out = []
        for g in grns.values():
            line_items = []
            for li in sorted(g["_items"].values(), key=lambda x: x["po_item"]):
                li["movement_types"] = sorted(li.pop("_movements"))
                li["received_quantity"] = round(li["received_quantity"], 3)
                li["amount"] = round(li["amount"], 2)
                line_items.append(li)
            out.append({
                "grn_number": g["grn_number"],
                "grn_year": g["grn_year"],
                "grn_date": g["grn_date"],
                "plant": g["plant"],
                "line_items": line_items,
            })

        out.sort(key=lambda x: (x.get("grn_date") or "", x.get("grn_number") or ""))
        logger.info(f"Fetched {len(out)} GRN(s) for PO {po_number} from SAP")
        return out

    finally:
        sap.disconnect()


def fetch_service_grn_refs(po_number: str) -> dict[int, dict]:
    """For each PO item, find the accepted Service Entry Sheet to invoice a
    SERVICE line against.

    A service PO item (EKPO-PSTYP='9') is confirmed by accepting a Service Entry
    Sheet in SAP (ML81N). Acceptance posts a goods-receipt material document
    (EKBE VGABE='1') whose LFBNR is the entry-sheet number. Invoicing the line
    against that sheet (SHEET_NO/SHEET_ITEM in the BAPI's ITEMDATA) carries the
    account assignment SAP needs — this is what clears error SE 509 "Account
    assignment for entry sheet missing" (referencing the GR material document
    directly via REF_DOC does NOT work).

    Net across debit (SHKZG='S') and credit (reversal 'H') movements, and return
    only PO items that still have an open (>0) received quantity.

    SHEET_ITEM defaults to "10" — OGDCL's service sheets carry a single accepted
    line per RO.

    Returns: { po_item(int): {sheet_no, sheet_item, gr_doc, quantity} }
    """
    sap = _get_connector()
    sap.connect()
    try:
        po_num = po_number.strip().zfill(10)
        result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKBE",
            ROWCOUNT="1000",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [
                    {"TEXT": f"EBELN = '{po_num}' "},
                    {"TEXT": "AND VGABE = '1' "},   # goods-receipt events only
                ],
                "FIELDS": [
                    {"FIELDNAME": "EBELP"},   # PO item
                    {"FIELDNAME": "GJAHR"},   # material doc year
                    {"FIELDNAME": "BELNR"},   # material doc number (the GR to reference)
                    {"FIELDNAME": "BUZEI"},   # material doc item
                    {"FIELDNAME": "MENGE"},   # quantity
                    {"FIELDNAME": "SHKZG"},   # debit/credit (S = receipt, H = reversal)
                    {"FIELDNAME": "BWART"},   # movement type (101/103 = GR, 105 = release)
                    {"FIELDNAME": "LFBNR"},   # ref document (= service entry sheet no.)
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={
                "DATA": ["WA"],
                "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
            },
        )
        rows = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))

        refs: dict[int, dict] = {}
        for r in rows:
            belnr = r.get("BELNR", "").strip()
            if not belnr:
                continue
            try:
                item = int(r.get("EBELP", "0") or "0")
            except ValueError:
                continue
            sign = -1 if r.get("SHKZG", "").strip() == "H" else 1
            qty = (_safe_float(r.get("MENGE", "0")) or 0.0) * sign
            sheet_no = r.get("LFBNR", "").strip()
            gjahr = r.get("GJAHR", "").strip()
            buzei = (r.get("BUZEI", "").strip() or "1")
            bwart = r.get("BWART", "").strip()
            # Only an actual goods-RECEIPT movement is a valid REF_DOC. In a
            # two-step GR the 103 (receipt into blocked stock) is the reference,
            # NOT the 105 (release to unrestricted) — SAP rejects the 105 with
            # "Enter a reference to a valid goods receipt". 101 is the one-step GR.
            is_gr_receipt = bwart in ("101", "103")
            ref = refs.setdefault(item, {
                # Service reference (SES): SHEET_NO from EKBE-LFBNR.
                "sheet_no": sheet_no,
                "sheet_item": "10",
                # Goods reference (GR-based IV): the receipt material document.
                "ref_doc": None,
                "ref_doc_year": None,
                "ref_doc_item": None,
                "quantity": 0.0,
            })
            # Pick the latest GR-receipt document as the goods reference.
            if is_gr_receipt and (ref["ref_doc"] is None or belnr > ref["ref_doc"]):
                ref["ref_doc"] = belnr
                ref["ref_doc_year"] = gjahr
                ref["ref_doc_item"] = buzei
            if sheet_no and not ref["sheet_no"]:
                ref["sheet_no"] = sheet_no
            ref["quantity"] += qty

        # Drop fully-reversed items (no open GR quantity to invoice against).
        open_refs = {k: v for k, v in refs.items() if round(v["quantity"], 3) > 0}
        logger.info(
            f"Fetched GR/sheet refs for PO {po_number}: "
            f"{ {k: (v['sheet_no'] or v['ref_doc']) for k, v in open_refs.items()} }"
        )
        return open_refs

    finally:
        sap.disconnect()


def fetch_open_grs(po_number: str) -> list[dict]:
    """The GR lines of a PO that can still be invoiced (see fetch_gr_overview)."""
    return fetch_gr_overview(po_number)["open"]


def fetch_gr_overview(po_number: str) -> dict:
    """Lucky Cement (observation F): the PO's goods-receipt lines, one entry per
    GR material-document line, so the user can choose which GRs an invoice
    parks against — and see why a list is empty.

    From EKBE: receipts (VGABE 1, BWART 101/103, SHKZG S) are the GR lines, and
    the documents an invoice references. Every other VGABE 1 row that points at
    one through LFGJA/LFBNR/LFPOS moves its quantity (S adds, H subtracts). That
    matters for a TWO-STEP receipt: the 103 (into blocked stock) carries no
    quantity of its own; the 105 releases do (Lucky PO 1010027884, 2026-11-24,
    where skipping them left every GR negative). Posted invoices (VGABE 2; H =
    credit memo) reduce the open quantity. Parked invoices (VGABE P) are only
    reported ("parked"): whether SAP always clears those rows is unconfirmed.

    Returns {"open": [...], "closed": [...], "rows": EKBE rows read,
    "unused": [{vgabe, bwart, shkzg, count}]}. A GR is {gr_key
    "YYYY/BELNR/BUZEI", gr_year, gr_doc, gr_item, po_item, posting_date,
    received, invoiced, open_qty, amount, open_amount, reason}, oldest first;
    "closed" = nothing left to invoice, with the reason. "unused" counts the
    EKBE rows that took no part (another movement type or event, or a reversal
    / invoice that names no GR above): numbers only, to spot a wrong filter.
    """
    sap = _get_connector()
    sap.connect()
    try:
        po_num = po_number.strip().zfill(10)
        result = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKBE",
            ROWCOUNT="5000",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": f"EBELN = '{po_num}' "}],
                "FIELDS": [{"FIELDNAME": f} for f in (
                    "EBELP", "GJAHR", "BELNR", "BUZEI", "VGABE", "BWART", "BUDAT",
                    "MENGE", "DMBTR", "SHKZG", "LFGJA", "LFBNR", "LFPOS")],
            },
            tables=["DATA", "FIELDS"],
            table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        )
        rows = _parse_delimited_rows(result.get("DATA", []), result.get("FIELDS", []))
    finally:
        sap.disconnect()

    def key(year, doc, item):
        return f"{(year or '').strip()}/{(doc or '').strip().zfill(10)}/{(item or '').strip().zfill(4)}"

    grs: dict[str, dict] = {}
    unused: dict[tuple, int] = {}

    def skip(r):
        k = tuple((r.get(f) or "").strip() for f in ("VGABE", "BWART", "SHKZG"))
        unused[k] = unused.get(k, 0) + 1

    others = []
    for r in rows:   # receipts first, so references below find their GR
        bwart = r.get("BWART", "").strip()
        if r.get("VGABE", "").strip() != "1" or r.get("SHKZG", "").strip() == "H" or bwart not in ("101", "103"):
            others.append(r)
            continue
        k = key(r.get("GJAHR"), r.get("BELNR"), r.get("BUZEI") or "1")
        g = grs.setdefault(k, {
            "gr_key": k, "gr_year": r.get("GJAHR", "").strip(), "gr_doc": r.get("BELNR", "").strip(),
            "gr_item": (r.get("BUZEI", "").strip() or "1"),
            "po_item": int(r.get("EBELP", "0") or "0"),
            "posting_date": r.get("BUDAT", "").strip(), "received": 0.0,
            "invoiced": 0.0, "parked": 0.0, "parked_docs": [], "amount": 0.0, "moves": [],
        })
        if bwart == "101":               # a 103 only counts through its 105 releases
            g["received"] += _safe_float(r.get("MENGE") or "") or 0.0
            g["amount"] += _safe_float(r.get("DMBTR") or "") or 0.0
    for r in others:
        vgabe, shkzg = r.get("VGABE", "").strip(), r.get("SHKZG", "").strip()
        g = grs.get(key(r.get("LFGJA"), r.get("LFBNR"), r.get("LFPOS") or "1"))
        if g is None or vgabe not in ("1", "2", "P"):
            skip(r)
            continue
        sign = -1 if shkzg == "H" else 1
        qty = (_safe_float(r.get("MENGE") or "") or 0.0) * sign
        if vgabe == "1":
            g["received"] += qty
            g["amount"] += (_safe_float(r.get("DMBTR") or "") or 0.0) * sign
            g["moves"].append({"key": key(r.get("GJAHR"), r.get("BELNR"), r.get("BUZEI") or "1"),
                               "doc": r.get("BELNR", "").strip(), "bwart": r.get("BWART", "").strip(), "qty": round(qty, 3)})
        elif vgabe == "2":
            g["invoiced"] += qty
        else:
            g["parked"] += qty
            g["parked_docs"].append(r.get("BELNR", "").strip())

    out, closed = [], []
    for g in grs.values():
        net = round(g["received"], 3)
        open_qty = round(net - g["invoiced"], 3)
        g["received"], g["invoiced"], g["parked"] = net, round(g["invoiced"], 3), round(g["parked"], 3)
        g["open_qty"] = max(open_qty, 0.0)
        g["open_amount"] = round(g["amount"] * (open_qty / net), 2) if net > 0 and open_qty > 0 else 0.0
        # The number Lucky calls the SRN: the 105 release of a two-step receipt.
        g["srn"] = [m["doc"] for m in g["moves"] if m["bwart"] == "105" and m["qty"] > 0] or [g["gr_doc"]]
        g["reason"] = None if open_qty > 0 else (
            "fully invoiced" if net > 0 else "reversed" if g["moves"] else "in blocked stock, not released (105)")
        (out if open_qty > 0 else closed).append(g)
    for lst in (out, closed):
        lst.sort(key=lambda g: (g["posting_date"], g["gr_key"]))
    logger.info("GRs for PO %s: %d EKBE rows, open %s, closed %s, unused (VGABE, BWART, SHKZG) %s",
                po_number, len(rows), [(g["gr_key"], g["open_qty"]) for g in out],
                [(g["gr_key"], g["reason"]) for g in closed], unused)
    return {"open": out, "closed": closed, "rows": len(rows),
            "unused": [{"vgabe": k[0], "bwart": k[1], "shkzg": k[2], "count": n}
                       for k, n in sorted(unused.items())]}


def fetch_vendor_wht(vendor_number: str, company_code: str) -> list[dict]:
    """Lucky Cement (observation G): the vendor's withholding-tax types and
    codes maintained in its BP for a company code (LFBW), with each code's rate
    from T059Z (LAND1 'PK': QSATZ = rate %, QPROZ = % of the base subject to
    it) and the name from Lucky's WHT list. Field names confirmed on AUP
    (sap_dd03l.py, 2026-11-24).

    Returns [{wht_type, wht_code, subject, name, rate, portion}].
    """
    from app.services.lucky_wht_codes import wht_code_info
    vendor = (vendor_number or "").strip()
    if vendor.isdigit():
        vendor = vendor.zfill(10)
    bukrs = (company_code or "").strip()
    if not vendor or not bukrs:
        return []
    sap = _get_connector()
    sap.connect()
    try:
        def read(table, opts, fields):
            res = sap.call(
                "RFC_READ_TABLE", QUERY_TABLE=table, ROWCOUNT="200", DELIMITER="|",
                input_tables={"OPTIONS": [{"TEXT": o} for o in opts],
                              "FIELDS": [{"FIELDNAME": f} for f in fields]},
                tables=["DATA", "FIELDS"],
                table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
            )
            return _parse_delimited_rows(res.get("DATA", []), res.get("FIELDS", []))

        rows = read("LFBW", [f"LIFNR = '{vendor}' ", f"AND BUKRS = '{bukrs}' "],
                    ["WITHT", "WT_WITHCD", "WT_SUBJCT"])
        out = []
        for r in rows:
            wtype, wcode = r.get("WITHT", "").strip(), r.get("WT_WITHCD", "").strip()
            if not wtype:
                continue
            info = wht_code_info(wtype, wcode)
            rate, portion = info["rate"], None
            if wcode:
                try:
                    t = read("T059Z", ["LAND1 = 'PK' ", f"AND WITHT = '{wtype}' ", f"AND WT_WITHCD = '{wcode}' "],
                             ["QSATZ", "QPROZ"])
                    if t:
                        rate = _safe_float(t[0].get("QSATZ") or "") if (t[0].get("QSATZ") or "").strip() else rate
                        portion = _safe_float(t[0].get("QPROZ") or "") if (t[0].get("QPROZ") or "").strip() else None
                except Exception:
                    logger.warning("T059Z read failed for %s/%s; using the code list's rate", wtype, wcode)
            out.append({"wht_type": wtype, "wht_code": wcode,
                        "subject": r.get("WT_SUBJCT", "").strip().upper() == "X",
                        "name": info["name"], "rate": rate, "portion": portion})
        logger.info("Vendor %s / %s WHT: %s", vendor, bukrs, [(w["wht_type"], w["wht_code"]) for w in out])
        return out
    finally:
        sap.disconnect()


def split_by_grs(goods_item: dict, grs: list[dict]) -> list[dict]:
    """One ITEMDATA row per selected GR for a PO item: each GR's open quantity,
    the invoice's unit price, and the GR as REF_DOC. Raises ValueError when the
    selected GRs' open quantity is not the quantity the invoice bills."""
    total = round(sum(g["open_qty"] for g in grs), 3)
    billed = round(float(goods_item.get("quantity") or 0), 3)
    if abs(total - billed) > 0.001:
        docs = ", ".join(g["gr_doc"] for g in grs)
        raise ValueError(
            f"PO item {goods_item['po_item']}: the selected goods receipts ({docs}) have "
            f"{total:g} open, but the invoice bills {billed:g}. Select GRs that add up to "
            f"the invoiced quantity, or correct the invoice quantity.")
    price = float(goods_item["amount"]) / billed if billed else 0.0
    rows, left = [], round(float(goods_item["amount"]), 2)
    for i, g in enumerate(grs):
        amount = left if i == len(grs) - 1 else round(g["open_qty"] * price, 2)
        left = round(left - amount, 2)
        rows.append({**goods_item, "quantity": g["open_qty"], "amount": amount,
                     "ref_doc": g["gr_doc"], "ref_doc_year": g["gr_year"], "ref_doc_item": g["gr_item"]})
    return rows


def fetch_delivery_costs(po_number: str, overview: dict | None = None) -> list[dict]:
    """Fetch invoiceable PLANNED delivery costs (freight, etc.) for a PO from
    SAP table EKBZ (delivery-cost PO history).

    Each delivery-cost condition (KSCHL, e.g. FRC1) accrues at goods receipt
    (VGABE='1'; SHKZG H = a reversal, which takes it back) and is consumed when
    invoiced (VGABE='2'; H = credit memo). Open = accrued - invoiced. VGABE='P'
    (parked) is only reported, as in fetch_gr_overview().

    Pass `overview` (fetch_gr_overview) to also split the accrual by goods
    receipt: a two-step receipt accrues on its 105 release, which belongs to the
    103. What can't be tied to a GR is counted in "unassigned".

    Returns a list of {po_item, cond_type, vendor, currency, amount, quantity
    (both still open), accrued, invoiced, parked, by_gr {gr_key: {amount,
    quantity}}, unassigned} (empty when no GR accrued any delivery cost).
    """
    doc_to_gr: dict[str, str] = {}
    for g in (overview or {}).get("open", []) + (overview or {}).get("closed", []):
        doc_to_gr[g["gr_key"]] = g["gr_key"]
        for m in g["moves"]:
            doc_to_gr[m["key"]] = g["gr_key"]
    by_doc: dict[str, set] = {}          # year/doc -> GRs, when the item number differs
    for k, gr in doc_to_gr.items():
        by_doc.setdefault(k.rsplit("/", 1)[0], set()).add(gr)

    sap = _get_connector()
    sap.connect()
    try:
        po_num = po_number.strip().zfill(10)
        fields = ["EBELP", "VGABE", "SHKZG", "GJAHR", "BELNR", "BUZEI", "KSCHL", "MENGE", "DMBTR", "WAERS"]

        def read(names):
            rows = sap.call(
                "RFC_READ_TABLE", QUERY_TABLE="EKBZ", ROWCOUNT="1000", DELIMITER="|",
                input_tables={"OPTIONS": [{"TEXT": f"EBELN = '{po_num}'"}],
                              "FIELDS": [{"FIELDNAME": n} for n in names]},
                tables=["DATA", "FIELDS"],
                table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
            )
            return _parse_delimited_rows(rows.get("DATA", []), rows.get("FIELDS", []))

        try:
            parsed = read(fields + ["LIFNR"])          # LIFNR = the freight vendor
        except Exception as exc:
            if "FIELD_NOT_VALID" not in str(exc):
                raise
            logger.warning("EKBZ-LIFNR is not readable; freight vendor unknown (%s)", exc)
            parsed = read(fields)

        agg: dict = {}
        for r in parsed:
            cond = r.get("KSCHL", "").strip()
            if not cond:
                continue
            try:
                item = int(r.get("EBELP", "0") or "0")
            except ValueError:
                item = 0
            vendor = r.get("LIFNR", "").strip()
            sign = -1 if r.get("SHKZG", "").strip() == "H" else 1
            amt = (_safe_float(r.get("DMBTR", "0")) or 0.0) * sign
            qty = (_safe_float(r.get("MENGE", "0")) or 0.0) * sign
            a = agg.setdefault((item, cond), {
                "po_item": item, "cond_type": cond, "vendor": "",
                "currency": r.get("WAERS", "").strip() or "PKR",
                "accrued": 0.0, "invoiced": 0.0, "parked": 0.0, "qty_in": 0.0, "qty_out": 0.0,
                "by_gr": {}, "unassigned": 0.0,
            })
            a["vendor"] = a["vendor"] or vendor
            vgabe = r.get("VGABE", "").strip()
            if vgabe == "1":        # goods receipt accrual
                a["accrued"] += amt
                a["qty_in"] += qty
                doc = f"{r.get('GJAHR', '').strip()}/{r.get('BELNR', '').strip().zfill(10)}"
                gr = doc_to_gr.get(f"{doc}/{(r.get('BUZEI', '').strip() or '1').zfill(4)}")
                if gr is None and len(by_doc.get(doc, ())) == 1:
                    gr = next(iter(by_doc[doc]))
                if gr is None:
                    a["unassigned"] += amt
                else:
                    g = a["by_gr"].setdefault(gr, {"amount": 0.0, "quantity": 0.0})
                    g["amount"] += amt
                    g["quantity"] += qty
            elif vgabe == "2":      # already invoiced
                a["invoiced"] += amt
                a["qty_out"] += qty
            elif vgabe == "P":
                a["parked"] += amt

        out = []
        for a in sorted(agg.values(), key=lambda x: (x["po_item"], x["cond_type"])):
            open_amt = round(a["accrued"] - a["invoiced"], 2)
            if open_amt <= 0:
                continue  # nothing left to invoice for this condition
            out.append({
                "po_item": a["po_item"], "cond_type": a["cond_type"], "vendor": a["vendor"],
                "currency": a["currency"], "amount": open_amt,
                "quantity": round(a["qty_in"] - a["qty_out"], 3),
                "accrued": round(a["accrued"], 2), "invoiced": round(a["invoiced"], 2),
                "parked": round(a["parked"], 2), "unassigned": round(a["unassigned"], 2),
                "by_gr": {k: {"amount": round(v["amount"], 2), "quantity": round(v["quantity"], 3)}
                          for k, v in a["by_gr"].items()},
            })
        logger.info("Delivery costs for PO %s: %d EKBZ rows, open %s", po_number, len(parsed),
                    [(c["po_item"], c["cond_type"], c["amount"], c["vendor"]) for c in out])
        return out

    finally:
        sap.disconnect()


def delivery_for_grs(cost: dict, gr_keys: list[str]) -> tuple[float, float]:
    """(amount, quantity) of a delivery cost to invoice: the ticked GRs' share, or
    everything still open when no GR is ticked. Raises ValueError when that can't
    be said for certain."""
    if not gr_keys:
        return cost["amount"], cost["quantity"]
    label = f"{cost['cond_type']} on PO item {cost['po_item']}"
    if abs(cost["unassigned"]) > 0.01:
        raise ValueError(f"{label}: SAP's delivery-cost history can't be tied to goods receipts "
                         f"({cost['unassigned']:,.2f} unassigned), so the ticked GRs' share is unknown. "
                         "Untick all GRs to take the whole open amount.")
    share = [cost["by_gr"][k] for k in gr_keys if k in cost["by_gr"]]
    amount = round(sum(x["amount"] for x in share), 2)
    if amount > cost["amount"] + 0.01:
        raise ValueError(f"{label}: the ticked GRs carry {amount:,.2f}, but only {cost['amount']:,.2f} is still "
                         "open (the rest is already invoiced).")
    return amount, round(sum(x["quantity"] for x in share), 3)


def fetch_tax_codes(company_code: str = "1100") -> dict:
    """Fetch SAP tax codes for a company code's country tax procedure.

    Resolves company (T001) → country → tax procedure (T005-KALSM) → tax codes
    (T007A) with English descriptions (T007S). Parses the % rate out of each
    description where present. Returns:
        {company_code, country, procedure, tax_codes: [{code, description,
         tax_type ("input"|"output"), rate}]}
    """
    sap = _get_connector()
    sap.connect()
    try:
        def read(table, opts, fields, rows="1000"):
            res = sap.call(
                "RFC_READ_TABLE", QUERY_TABLE=table, ROWCOUNT=rows, DELIMITER="|",
                input_tables={
                    "OPTIONS": [{"TEXT": o} for o in opts],
                    "FIELDS": [{"FIELDNAME": f} for f in fields],
                },
                tables=["DATA", "FIELDS"],
                table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
            )
            return _parse_delimited_rows(res.get("DATA", []), res.get("FIELDS", []))

        bukrs = company_code.strip()
        t001 = read("T001", [f"BUKRS = '{bukrs}' "], ["BUKRS", "LAND1"])
        land1 = t001[0]["LAND1"].strip() if t001 else ""
        kalsm = ""
        if land1:
            t005 = read("T005", [f"LAND1 = '{land1}' "], ["LAND1", "KALSM"])
            kalsm = t005[0]["KALSM"].strip() if t005 and t005[0].get("KALSM", "").strip() else ""

        opts = [f"KALSM = '{kalsm}' "] if kalsm else []
        codes = read("T007A", opts, ["MWSKZ", "MWART"])
        text_opts = (opts + ["AND SPRAS = 'E' "]) if kalsm else ["SPRAS = 'E' "]
        texts = read("T007S", text_opts, ["MWSKZ", "TEXT1"])
        desc = {t["MWSKZ"].strip(): t.get("TEXT1", "").strip() for t in texts}

        rate_re = re.compile(r"(\d+(?:\.\d+)?)\s*%")
        out, seen = [], set()
        for c in codes:
            mwskz = c["MWSKZ"].strip()
            if not mwskz or mwskz in seen:
                continue
            seen.add(mwskz)
            description = desc.get(mwskz, "")
            m = rate_re.search(description)
            mwart = c.get("MWART", "").strip()
            out.append({
                "code": mwskz,
                "description": description,
                "tax_type": {"V": "input", "A": "output"}.get(mwart, (mwart.lower() or "other")),
                "rate": float(m.group(1)) if m else None,
            })
        out.sort(key=lambda x: x["code"])
        logger.info(f"Fetched {len(out)} SAP tax codes (procedure {kalsm}) for company {bukrs}")
        return {"company_code": bukrs, "country": land1, "procedure": kalsm, "tax_codes": out}
    finally:
        sap.disconnect()


def lookup_vendor(ntn: str = "", name: str = "") -> dict:
    """Check whether a supplier is registered as a vendor in SAP (LFA1).

    Matches primarily on tax number (STCD1=NTN, STCD2=STRN, STCD3=CNIC), trying
    the value as-given and dash/space-stripped; falls back to an exact/prefix
    name match. Returns {registered, vendor_number, vendor_name, tax_number,
    matched_by, deleted}.
    """
    sap = _get_connector()
    sap.connect()
    try:
        FIELDS = ["LIFNR", "NAME1", "STCD1", "STCD2", "STCD3", "LOEVM"]

        def read(where_rows, rows="10"):
            r = sap.call(
                "RFC_READ_TABLE", QUERY_TABLE="LFA1", DELIMITER="|", ROWCOUNT=rows,
                input_tables={"OPTIONS": where_rows, "FIELDS": [{"FIELDNAME": f} for f in FIELDS]},
                tables=["DATA", "FIELDS"],
                table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
            )
            return _parse_delimited_rows(r.get("DATA", []), r.get("FIELDS", []))

        def result_from(rows, matched_by):
            v = rows[0]
            return {
                "registered": True,
                "vendor_number": v.get("LIFNR", "").strip(),
                "vendor_name": v.get("NAME1", "").strip(),
                "tax_number": v.get("STCD1", "").strip(),
                "matched_by": matched_by,
                "deleted": v.get("LOEVM", "").strip() == "X",
            }

        ntn = (ntn or "").strip()
        if ntn:
            candidates = list(dict.fromkeys([ntn, ntn.replace("-", "").replace(" ", "")]))
            conds = [f"{fld} = '{c}'" for c in candidates for fld in ("STCD1", "STCD2", "STCD3")]
            where_rows = [{"TEXT": ("" if i == 0 else "OR ") + cond + " "} for i, cond in enumerate(conds)]
            rows = read(where_rows)
            if rows:
                return result_from(rows, "ntn")

        nm = "".join(ch for ch in (name or "").upper() if ch.isalnum() or ch == " ").strip()
        if len(nm) >= 4:
            # Tiered prefixes: SAP NAME1 entries are often truncated (e.g.
            # "BENCHMARK TECHNOLOG"), so a long prefix can overshoot the stored
            # value. Try exact, then progressively shorter LIKE prefixes.
            rows = read([{"TEXT": f"NAME1 = '{nm[:35]}'"}])
            for cut in (20, 15, 12):
                if rows or len(nm) < cut:
                    break
                rows = read([{"TEXT": f"NAME1 LIKE '{nm[:cut]}%'"}])
            if rows:
                return result_from(rows, "name")

        return {"registered": False}
    finally:
        sap.disconnect()


def search_vendors(query: str, max_rows: int = 20) -> list[dict]:
    """Search the SAP vendor master (LFA1) for the admin onboarding picker.

    A digit query matches the vendor number (LIFNR); anything else does a
    case-insensitive contains-match on the name via MCOD1 (SAP's uppercase
    match-code field — NAME1 itself is stored mixed-case). Deleted vendors
    (LOEVM=X) are dropped.
    """
    q = (query or "").strip()
    if not q:
        return []
    sap = _get_connector()
    sap.connect()
    try:
        FIELDS = ["LIFNR", "NAME1", "ORT01", "STCD1", "LOEVM"]
        if q.replace("-", "").isdigit():
            where_rows = [{"TEXT": f"LIFNR = '{q.replace('-', '').zfill(10)}' "}]
        else:
            safe = "".join(ch for ch in q.upper() if ch.isalnum() or ch == " ")[:20]
            if len(safe) < 2:
                return []
            where_rows = [{"TEXT": f"MCOD1 LIKE '%{safe}%' "}]
        r = sap.call(
            "RFC_READ_TABLE", QUERY_TABLE="LFA1", DELIMITER="|", ROWCOUNT=str(max_rows),
            input_tables={"OPTIONS": where_rows, "FIELDS": [{"FIELDNAME": f} for f in FIELDS]},
            tables=["DATA", "FIELDS"],
            table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        )
        rows = _parse_delimited_rows(r.get("DATA", []), r.get("FIELDS", []))
        return [
            {
                "vendor_number": v["LIFNR"].strip(),
                "name": v.get("NAME1", "").strip(),
                "city": v.get("ORT01", "").strip(),
                "ntn": v.get("STCD1", "").strip(),
            }
            for v in rows
            if v.get("LIFNR", "").strip() and v.get("LOEVM", "").strip() != "X"
        ]
    finally:
        sap.disconnect()


def tax_rate_for_code(company_code: str, tax_code: str) -> float | None:
    """Return the % rate for a SAP tax code (e.g. 'AY' -> 19.5), or None if the
    code has no parseable rate. Used to derive tax when the invoice itself
    carries no tax amount."""
    if not tax_code:
        return None
    # Lucky Cement's official list first (no RFC); SAP only for a code not on it.
    from app.services.lucky_tax_codes import LUCKY_TAX_CODES
    for code, _desc, _kind, rate in LUCKY_TAX_CODES:
        if code == tax_code:
            return rate
    try:
        data = fetch_tax_codes(company_code)
    except Exception:
        logger.exception("Could not fetch tax codes to resolve rate for %s", tax_code)
        return None
    for c in data.get("tax_codes", []):
        if c.get("code") == tax_code:
            return c.get("rate")
    return None


def fetch_currencies(language: str = "E") -> list[dict]:
    """Fetch SAP currency codes with English names from TCURT (currency texts).

    Returns a list of {code, name} sorted by code.
    """
    sap = _get_connector()
    sap.connect()
    try:
        res = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="TCURT",
            ROWCOUNT="2000",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": f"SPRAS = '{language}'"}],
                "FIELDS": [
                    {"FIELDNAME": "WAERS"},   # currency key
                    {"FIELDNAME": "LTEXT"},   # long text (currency name)
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        )
        rows = _parse_delimited_rows(res.get("DATA", []), res.get("FIELDS", []))
        out = []
        for r in rows:
            code = r.get("WAERS", "").strip()
            if not code:
                continue
            out.append({"code": code, "name": r.get("LTEXT", "").strip()})
        out.sort(key=lambda x: x["code"])
        logger.info(f"Fetched {len(out)} SAP currencies from TCURT")
        return out
    finally:
        sap.disconnect()


def sync_po_to_db(po_data: dict, db_session) -> dict:
    """
    Convert SAP PO data dict into the einv PurchaseOrder format
    suitable for saving to the local database.
    """
    return {
        "po_number": po_data["po_number"],
        "vendor_name": po_data.get("vendor_name", ""),
        "vendor_ntn": po_data.get("vendor_ntn", ""),
        "company_code": (po_data.get("company_code") or "").strip() or None,
        "po_date": po_data.get("po_date", ""),
        "po_type": "local",
        "total_amount": po_data.get("total_value", 0),
        "currency": po_data.get("currency", "PKR"),
        "status": "open",
        "notes": f"Synced from SAP (Company: {po_data.get('company_code', '')}, Type: {po_data.get('doc_type', '')})",
        "source_type": "sap",
        "line_items": [
            {
                "item_number": li.get("item_number", 0),
                "description": li.get("description", ""),
                "quantity": li.get("quantity", 0),
                "unit": li.get("unit", ""),
                "price_unit": li.get("price_unit", ""),
                "unit_price": li.get("unit_price", 0),
                "amount": li.get("net_value", 0),
            }
            for li in po_data.get("line_items", [])
        ],
    }
