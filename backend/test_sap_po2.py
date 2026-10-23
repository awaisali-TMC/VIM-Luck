"""Test SAP PO fetch — get all POs and their line items."""
import os
os.add_dll_directory(r"C:\nwrfcsdk\lib")

import sys
sys.path.insert(0, os.path.dirname(__file__))

from app.services.sap_connector import SAPConnector

sap = SAPConnector()
sap.connect()

# Step 1: Get all PO headers from EKKO
print("Fetching PO headers from EKKO...")
result = sap.call(
    "RFC_READ_TABLE",
    QUERY_TABLE="EKKO",
    ROWCOUNT="50",
    DELIMITER="|",
    input_tables={
        "OPTIONS": [{"TEXT": "BSTYP = 'F'"}],
        "FIELDS": [
            {"FIELDNAME": "EBELN"},   # PO number
            {"FIELDNAME": "BUKRS"},   # Company code
            {"FIELDNAME": "BSART"},   # Doc type
            {"FIELDNAME": "LIFNR"},   # Vendor number
            {"FIELDNAME": "BEDAT"},   # PO date
            {"FIELDNAME": "WAERS"},   # Currency
            {"FIELDNAME": "RLWRT"},   # Total value
        ],
    },
    tables=["DATA", "FIELDS"],
    table_fields={
        "DATA": ["WA"],
        "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"],
    },
)

fields_info = result.get("FIELDS", [])
data_rows = result.get("DATA", [])
print(f"Found {len(data_rows)} POs")
print(f"Fields: {[f.get('FIELDNAME') for f in fields_info]}")

# Parse the delimited data
po_numbers = []
for row in data_rows:
    wa = row.get("WA", "")
    parts = wa.split("|")
    if len(parts) >= 6:
        po_num = parts[0].strip()
        po_numbers.append(po_num)
        print(f"  PO: {po_num} | Company: {parts[1].strip()} | Type: {parts[2].strip()} | "
              f"Vendor: {parts[3].strip()} | Date: {parts[4].strip()} | Currency: {parts[5].strip()}")

# Step 2: Get detail for first PO using BAPI_PO_GETDETAIL1
if po_numbers:
    po = po_numbers[0]
    print(f"\n{'='*60}")
    print(f"Fetching details for PO: {po}")
    print(f"{'='*60}")

    detail = sap.call(
        "BAPI_PO_GETDETAIL1",
        PURCHASEORDER=po,
        tables=["PO_ITEMS", "RETURN"],
        table_fields={
            "PO_ITEMS": [
                "PO_ITEM", "SHORT_TEXT", "MATERIAL", "PLANT",
                "QUANTITY", "NET_PRICE", "NET_VALUE",
                "PRICE_UNIT", "ORD_UNIT", "TAX_CODE",
            ],
            "RETURN": ["TYPE", "MESSAGE"],
        },
        output_structures={
            "PO_HEADER": [
                "PO_NUMBER", "DOC_TYPE", "DOC_DATE", "VENDOR",
                "CURRENCY", "PMNTTRMS", "COMP_CODE",
            ],
        },
    )

    header = detail.get("PO_HEADER", {})
    print(f"  Header: PO={header.get('PO_NUMBER')} | Vendor={header.get('VENDOR')} | "
          f"Date={header.get('DOC_DATE')} | Currency={header.get('CURRENCY')} | "
          f"Company={header.get('COMP_CODE')}")

    items = detail.get("PO_ITEMS", [])
    print(f"  Line items: {len(items)}")
    for li in items:
        print(f"    #{li.get('PO_ITEM')} | {li.get('SHORT_TEXT')} | "
              f"Qty: {li.get('QUANTITY')} {li.get('ORD_UNIT')} | "
              f"Price: {li.get('NET_PRICE')} | Value: {li.get('NET_VALUE')}")

    for r in detail.get("RETURN", []):
        if r.get("MESSAGE", "").strip():
            print(f"  RETURN: [{r.get('TYPE')}] {r.get('MESSAGE')}")

# Step 3: Get vendor name using BAPI
if po_numbers:
    vendor_num = ""
    for row in data_rows:
        wa = row.get("WA", "")
        parts = wa.split("|")
        if len(parts) >= 4:
            vendor_num = parts[3].strip()
            break

    if vendor_num:
        print(f"\n{'='*60}")
        print(f"Fetching vendor name for: {vendor_num}")
        print(f"{'='*60}")
        try:
            vresult = sap.call(
                "RFC_READ_TABLE",
                QUERY_TABLE="LFA1",
                DELIMITER="|",
                input_tables={
                    "OPTIONS": [{"TEXT": f"LIFNR = '{vendor_num}'"}],
                    "FIELDS": [
                        {"FIELDNAME": "LIFNR"},
                        {"FIELDNAME": "NAME1"},
                        {"FIELDNAME": "NAME2"},
                        {"FIELDNAME": "STCD1"},  # Tax number
                        {"FIELDNAME": "LAND1"},  # Country
                    ],
                },
                tables=["DATA"],
                table_fields={"DATA": ["WA"]},
            )
            for vrow in vresult.get("DATA", []):
                print(f"  Vendor: {vrow.get('WA', '')}")
        except Exception as e:
            print(f"  Vendor lookup failed: {e}")

sap.disconnect()
print("\nDone!")
