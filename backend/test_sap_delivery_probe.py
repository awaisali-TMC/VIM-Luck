"""
READ-ONLY SAP probe: inspect how planned delivery costs are stored for a PO.

Run from a freshly-opened terminal (so C:\\nwrfcsdk\\lib is on PATH):

    py -3 backend/test_sap_delivery_probe.py
    py -3 backend/test_sap_delivery_probe.py 4500047473 4500047474

Reads (nothing is written to SAP):
  EKKO  — PO header (KNUMV = condition doc, vendor, currency)
  EKPO  — PO items (material, qty, net price)
  EKBZ  — delivery-cost PO history (condition type KSCHL + GR-accrued amount)
  PRCD_ELEMENTS / KONV — the planned condition rate on the PO
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services.sap_po_service import _get_connector, _parse_delimited_rows  # noqa: E402


def read_table(sap, table, where_rows, fields, rowcount="500"):
    try:
        res = sap.call(
            "RFC_READ_TABLE",
            QUERY_TABLE=table,
            ROWCOUNT=rowcount,
            DELIMITER="|",
            input_tables={
                "OPTIONS": [{"TEXT": t} for t in where_rows],
                "FIELDS": [{"FIELDNAME": f} for f in fields],
            },
            tables=["DATA", "FIELDS"],
            table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
        )
        return _parse_delimited_rows(res.get("DATA", []), res.get("FIELDS", []))
    except Exception as e:
        print(f"    !! read {table} failed: {e}")
        return []


def dump(rows, fields):
    if not rows:
        print("    (no rows)")
        return
    for r in rows:
        print("    " + " | ".join(f"{f}={r.get(f, '').strip()}" for f in fields))


def probe(sap, po):
    po_num = po.strip().zfill(10)
    print(f"\n{'='*70}\nPO {po}  (padded {po_num})\n{'='*70}")

    print("\n[EKKO header]")
    ekko = read_table(sap, "EKKO", [f"EBELN = '{po_num}'"],
                      ["EBELN", "BUKRS", "LIFNR", "WAERS", "KNUMV"])
    dump(ekko, ["EBELN", "BUKRS", "LIFNR", "WAERS", "KNUMV"])
    knumv = ekko[0].get("KNUMV", "").strip() if ekko else ""

    print("\n[EKPO items]")
    ekpo = read_table(sap, "EKPO", [f"EBELN = '{po_num}' "],
                      ["EBELP", "MATNR", "TXZ01", "MENGE", "MEINS", "NETPR", "NETWR"])
    dump(ekpo, ["EBELP", "MATNR", "TXZ01", "MENGE", "MEINS", "NETPR", "NETWR"])

    print("\n[EKBZ delivery-cost history]  VGABE 1=GR 2=invoice")
    ekbz = read_table(sap, "EKBZ", [f"EBELN = '{po_num}'"],
                      ["EBELP", "VGABE", "BEWTP", "KSCHL", "LIFNR", "MENGE", "DMBTR", "WRBTR", "SHKZG", "WAERS"])
    dump(ekbz, ["EBELP", "VGABE", "BEWTP", "KSCHL", "LIFNR", "MENGE", "DMBTR", "WRBTR", "SHKZG", "WAERS"])

    if knumv:
        print(f"\n[PRCD_ELEMENTS conditions]  KNUMV={knumv}")
        pe = read_table(sap, "PRCD_ELEMENTS", [f"KNUMV = '{knumv}'"],
                        ["KPOSN", "STUNR", "KSCHL", "KBETR", "KWERT", "KNTYP", "KOAID", "WAERS"])
        if not pe:
            print("    (PRCD_ELEMENTS empty/failed — trying KONV)")
            pe = read_table(sap, "KONV", [f"KNUMV = '{knumv}'"],
                            ["KPOSN", "STUNR", "KSCHL", "KBETR", "KWERT", "KNTYP", "KOAID", "WAERS"])
        dump(pe, ["KPOSN", "STUNR", "KSCHL", "KBETR", "KWERT", "KNTYP", "KOAID", "WAERS"])


if __name__ == "__main__":
    pos = sys.argv[1:] or ["4500047473", "4500047474"]
    sap = _get_connector()
    sap.connect()
    try:
        for po in pos:
            probe(sap, po)
    finally:
        sap.disconnect()
    print("\nDone (read-only).")
