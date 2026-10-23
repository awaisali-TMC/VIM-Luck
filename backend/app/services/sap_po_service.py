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
                    {"FIELDNAME": "MEINS"},   # Unit of measure
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


def fetch_delivery_costs(po_number: str) -> list[dict]:
    """Fetch invoiceable PLANNED delivery costs (freight, etc.) for a PO from
    SAP table EKBZ (delivery-cost PO history).

    Each delivery-cost condition (KSCHL, e.g. ZFRT) accrues at goods receipt
    (VGABE='1') and is consumed when invoiced (VGABE='2'). The open, still-
    invoiceable amount per (PO item, condition) is GR-accrued − already-invoiced.

    Returns a list of:
        {po_item, cond_type, amount, quantity, currency}
    (empty when the PO has no GR-accrued delivery costs yet).
    """
    sap = _get_connector()
    sap.connect()
    try:
        po_num = po_number.strip().zfill(10)
        rows = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE="EKBZ",
            ROWCOUNT="1000",
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": f"EBELN = '{po_num}'"}],
                "FIELDS": [
                    {"FIELDNAME": "EBELP"},   # PO item
                    {"FIELDNAME": "VGABE"},   # 1=GR, 2=invoice
                    {"FIELDNAME": "KSCHL"},   # condition type (e.g. ZFRT)
                    {"FIELDNAME": "MENGE"},   # quantity
                    {"FIELDNAME": "DMBTR"},   # amount (local currency)
                    {"FIELDNAME": "WAERS"},   # currency
                ],
            },
            tables=["DATA", "FIELDS"],
            table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        )
        parsed = _parse_delimited_rows(rows.get("DATA", []), rows.get("FIELDS", []))

        agg: dict = {}
        for r in parsed:
            cond = r.get("KSCHL", "").strip()
            if not cond:
                continue
            try:
                item = int(r.get("EBELP", "0") or "0")
            except ValueError:
                item = 0
            vgabe = r.get("VGABE", "").strip()
            amt = _safe_float(r.get("DMBTR", "0")) or 0.0
            qty = _safe_float(r.get("MENGE", "0")) or 0.0
            key = (item, cond)
            a = agg.setdefault(key, {
                "po_item": item, "cond_type": cond,
                "gr_amount": 0.0, "inv_amount": 0.0, "quantity": 0.0,
                "currency": r.get("WAERS", "").strip() or "PKR",
            })
            if vgabe == "1":        # goods receipt accrual
                a["gr_amount"] += amt
                a["quantity"] += qty
            elif vgabe == "2":      # already invoiced
                a["inv_amount"] += amt

        out = []
        for a in sorted(agg.values(), key=lambda x: (x["po_item"], x["cond_type"])):
            open_amt = round(a["gr_amount"] - a["inv_amount"], 2)
            if open_amt <= 0:
                continue  # nothing left to invoice for this condition
            out.append({
                "po_item": a["po_item"],
                "cond_type": a["cond_type"],
                "amount": open_amt,
                "quantity": round(a["quantity"], 3),
                "currency": a["currency"],
            })
        logger.info(f"Fetched {len(out)} delivery-cost condition(s) for PO {po_number} from SAP")
        return out

    finally:
        sap.disconnect()


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
                "unit_price": li.get("unit_price", 0),
                "amount": li.get("net_value", 0),
            }
            for li in po_data.get("line_items", [])
        ],
    }
