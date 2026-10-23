"""Test SAP PO fetch BAPIs to see what's available."""
import os
os.add_dll_directory(r"C:\nwrfcsdk\lib")

import sys
sys.path.insert(0, os.path.dirname(__file__))

from app.services.sap_connector import SAPConnector

sap = SAPConnector()
sap.connect()

# Test 1: BAPI_PO_GETITEMS — list POs
print("=" * 60)
print("TEST 1: BAPI_PO_GETITEMS (list POs)")
print("=" * 60)
try:
    result = sap.call(
        "BAPI_PO_GETITEMS",
        tables=["PO_ITEMS", "PO_ITEM_SCHEDULES", "RETURN"],
        table_fields={
            "PO_ITEMS": [
                "PO_NUMBER", "PO_ITEM", "DOC_TYPE", "DOC_DATE",
                "VENDOR", "VEND_NAME", "CREATED_BY",
                "SHORT_TEXT", "MATERIAL", "PLANT",
                "QUANTITY", "UNIT", "NET_PRICE", "NET_VALUE",
                "CURRENCY", "GR_IND", "IR_IND",
            ],
            "RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE"],
        },
    )
    items = result.get("PO_ITEMS", [])
    returns = result.get("RETURN", [])
    print(f"PO_ITEMS: {len(items)} rows")
    for item in items[:5]:
        print(f"  PO: {item.get('PO_NUMBER', '?')} | Item: {item.get('PO_ITEM', '?')} | "
              f"Vendor: {item.get('VEND_NAME', '?')} | Desc: {item.get('SHORT_TEXT', '?')} | "
              f"Qty: {item.get('QUANTITY', '?')} | Price: {item.get('NET_PRICE', '?')} {item.get('CURRENCY', '?')}")
    if items and len(items) > 5:
        print(f"  ... and {len(items) - 5} more")
    for r in returns:
        print(f"  RETURN: [{r.get('TYPE', '?')}] {r.get('MESSAGE', '?')}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 2: BAPI_PO_GETDETAIL1 — get specific PO detail (if we found POs above)
print("\n" + "=" * 60)
print("TEST 2: BAPI_PO_GETDETAIL1 (PO detail)")
print("=" * 60)
try:
    # Try with a PO number from test 1, or a sample
    po_number = ""
    if items:
        po_number = items[0].get("PO_NUMBER", "").strip()

    if po_number:
        print(f"Fetching details for PO: {po_number}")
        detail = sap.call(
            "BAPI_PO_GETDETAIL1",
            PURCHASEORDER=po_number,
            tables=["PO_ITEMS", "PO_ITEM_ACCOUNT_ASSIGNMENT", "RETURN"],
            table_fields={
                "PO_ITEMS": [
                    "PO_ITEM", "SHORT_TEXT", "MATERIAL", "PLANT",
                    "QUANTITY", "NET_PRICE", "NET_VALUE",
                    "PRICE_UNIT", "ORD_UNIT",
                ],
                "RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE"],
            },
            output_structures={
                "PO_HEADER": [
                    "PO_NUMBER", "DOC_TYPE", "DOC_DATE", "VENDOR",
                    "CURRENCY", "PMNTTRMS", "COMP_CODE",
                ],
            },
        )
        header = detail.get("PO_HEADER", {})
        print(f"  Header: PO={header.get('PO_NUMBER', '?')}, Vendor={header.get('VENDOR', '?')}, "
              f"Date={header.get('DOC_DATE', '?')}, Currency={header.get('CURRENCY', '?')}")
        for li in detail.get("PO_ITEMS", [])[:5]:
            print(f"  Line {li.get('PO_ITEM', '?')}: {li.get('SHORT_TEXT', '?')} | "
                  f"Qty: {li.get('QUANTITY', '?')} {li.get('ORD_UNIT', '?')} | "
                  f"Price: {li.get('NET_PRICE', '?')}")
        for r in detail.get("RETURN", []):
            print(f"  RETURN: [{r.get('TYPE', '?')}] {r.get('MESSAGE', '?')}")
    else:
        print("  No PO number found from Test 1, skipping")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 3: Get vendor details
print("\n" + "=" * 60)
print("TEST 3: RFC_READ_TABLE (PO headers from EKKO)")
print("=" * 60)
try:
    result = sap.call(
        "RFC_READ_TABLE",
        QUERY_TABLE="EKKO",
        ROWCOUNT="10",
        input_tables={
            "OPTIONS": [{"TEXT": "BSTYP = 'F'"}],
            "FIELDS": [
                {"FIELDNAME": "EBELN"},
                {"FIELDNAME": "BUKRS"},
                {"FIELDNAME": "BSART"},
                {"FIELDNAME": "LIFNR"},
                {"FIELDNAME": "BEDAT"},
                {"FIELDNAME": "WAERS"},
            ],
        },
        tables=["DATA", "FIELDS"],
        table_fields={
            "DATA": ["WA"],
            "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH", "TYPE", "FIELDTEXT"],
        },
    )
    fields_info = result.get("FIELDS", [])
    data_rows = result.get("DATA", [])
    print(f"  Fields: {[f.get('FIELDNAME', '') for f in fields_info]}")
    print(f"  Data rows: {len(data_rows)}")
    for row in data_rows[:10]:
        print(f"  {row.get('WA', '?')}")
except Exception as e:
    print(f"  FAILED: {e}")

sap.disconnect()
print("\nDone!")
