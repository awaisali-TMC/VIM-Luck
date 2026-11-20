"""List a SAP table's columns from DD03L (read-only), and try reading a few rows.

Use it to confirm the workflow log tables before VIM reads them:

    backend/.venv/bin/python backend/sap_dd03l.py                     # ZMIR7_WF_LOG + ZMIR7_ERROR_LOG
    backend/.venv/bin/python backend/sap_dd03l.py ZMIR7_WF_LOG --rows 5
    backend/.venv/bin/python backend/sap_dd03l.py --find ZMIR7       # every ZMIR7* object + its kind

TABCLASS (DD02L): TRANSP = database table (readable); INTTAB = structure, which
RFC_READ_TABLE refuses with TABLE_WITHOUT_DATA; VIEW / POOL / CLUSTER = others.

Runs as the technical RFC user from backend/.env (SAP_USER), so it also shows
whether that user may read the table at all (RFC_READ_TABLE -> NOT_AUTHORIZED
means S_TABU_DIS / S_TABU_NAM for Basis). Nothing is written to SAP.
Compare the output with WF_LOG_FIELDS / ERROR_LOG_FIELDS in
app/services/sap_workflow.py.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings  # noqa: E402
from app.services.sap_connector import SAPConnector  # noqa: E402
from app.services.sap_po_service import _parse_delimited_rows  # noqa: E402
from app.services.sap_workflow import (ERROR_LOG_FIELDS, ERROR_LOG_TABLE,  # noqa: E402
                                       WF_LOG_FIELDS, WF_LOG_TABLE)

WF_TABLE = (settings.SAP_WF_LOG_TABLE or WF_LOG_TABLE).upper()
ERR_TABLE = (settings.SAP_WF_ERROR_TABLE or ERROR_LOG_TABLE).upper()
EXPECTED = {WF_TABLE: WF_LOG_FIELDS, ERR_TABLE: ERROR_LOG_FIELDS}


def read_table(sap, table, fields, where="", rows=0):
    res = sap.call(
        "RFC_READ_TABLE", QUERY_TABLE=table, DELIMITER="|", ROWCOUNT=rows,
        input_tables={"OPTIONS": [{"TEXT": where}] if where else [],
                      "FIELDS": [{"FIELDNAME": f} for f in fields]},
        tables=["DATA", "FIELDS"],
        table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
    )
    return _parse_delimited_rows(res.get("DATA", []), res.get("FIELDS", []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tables", nargs="*", default=[WF_TABLE, ERR_TABLE])
    ap.add_argument("--find", metavar="PREFIX",
                    help="list every DDIC table/structure whose name starts with PREFIX, with its TABCLASS")
    ap.add_argument("--rows", type=int, default=3, help="sample rows to read (0 = none)")
    ap.add_argument("--fm", metavar="FUNCTION",
                    help="print a function module's interface (FUPARAREF) and every structure's fields")
    args = ap.parse_args()

    sap = SAPConnector()
    sap.connect()
    try:
        if args.fm:
            fm = args.fm.upper()
            # PARAMTYPE: I import, E export, C changing, T tables, X exception
            params = read_table(sap, "FUPARAREF", ["PARAMETER", "PARAMTYPE", "STRUCTURE", "OPTIONAL", "PPOSITION"],
                                f"FUNCNAME = '{fm}' AND R3STATE = 'A'")
            if not params:
                print(f"  {fm}: not found (or not active) on this system")
                return
            kinds = {"I": "IMPORT", "E": "EXPORT", "C": "CHANGING", "T": "TABLES", "X": "EXCEPTION"}
            params.sort(key=lambda r: (r.get("PARAMTYPE", ""), r.get("PPOSITION", "")))
            print(f"\n=== {fm} interface ===")
            for p in params:
                print(f"  {kinds.get(p.get('PARAMTYPE', '').strip(), '?'):<9} {p.get('PARAMETER', '').strip():<28} "
                      f"{p.get('STRUCTURE', '').strip():<32} {'optional' if p.get('OPTIONAL', '').strip() else ''}")
            seen = set()
            for p in params:
                struct = p.get("STRUCTURE", "").strip()
                if not struct or "-" in struct or struct in seen or p.get("PARAMTYPE", "").strip() == "X":
                    continue          # a data element / field reference, not a structure
                seen.add(struct)
                cols = read_table(sap, "DD03L", ["FIELDNAME", "POSITION", "DATATYPE", "LENG"],
                                  f"TABNAME = '{struct}' AND AS4LOCAL = 'A'")
                if not cols:
                    continue
                cols.sort(key=lambda r: r.get("POSITION", ""))
                print(f"\n  --- {p.get('PARAMETER', '').strip()} : {struct} ---")
                for c in cols:
                    name = c.get("FIELDNAME", "").strip()
                    if not name.startswith("."):
                        print(f"    {name:<30} {c.get('DATATYPE', ''):<6} {c.get('LENG', '').lstrip('0')}")
            return
        if args.find:
            prefix = args.find.upper().rstrip("%*")
            print(f"\n=== DD02L: {prefix}* ===")
            objs = read_table(sap, "DD02L", ["TABNAME", "TABCLASS"],
                              f"TABNAME LIKE '{prefix}%' AND AS4LOCAL = 'A'")
            for o in sorted(objs, key=lambda r: r.get("TABNAME", "")):
                kind = o.get("TABCLASS", "").strip()
                note = {"TRANSP": "database table - VIM can read this",
                        "INTTAB": "structure - not readable"}.get(kind, "")
                print(f"  {o.get('TABNAME', '').strip():<30} {kind:<8} {note}")
            if not objs:
                print("  nothing found")
            return
        for table in [t.upper() for t in args.tables]:
            kind = read_table(sap, "DD02L", ["TABCLASS"], f"TABNAME = '{table}' AND AS4LOCAL = 'A'")
            kind = kind[0].get("TABCLASS", "").strip() if kind else "?"
            print(f"\n=== {table} (DD03L)  TABCLASS={kind}"
                  + ("  <- STRUCTURE, not a table: RFC_READ_TABLE cannot read it" if kind == "INTTAB" else "")
                  + " ===")
            try:
                cols = read_table(sap, "DD03L", ["FIELDNAME", "POSITION", "DATATYPE", "LENG"],
                                  f"TABNAME = '{table}' AND AS4LOCAL = 'A'")
            except Exception as exc:  # noqa: BLE001
                print(f"  DD03L read failed: {exc}")
                continue
            if not cols:
                print("  no such table (not active in DD03L)")
                continue
            cols.sort(key=lambda r: r.get("POSITION", ""))
            names = []
            for c in cols:
                name = c.get("FIELDNAME", "").strip()
                if name.startswith("."):
                    continue          # .INCLUDE rows
                names.append(name)
                print(f"  {c.get('POSITION', ''):>4}  {name:<30} {c.get('DATATYPE', ''):<6} {c.get('LENG', '').lstrip('0')}")
            want = EXPECTED.get(table)
            if want:
                missing = [v for v in want.values() if v not in names]
                print(f"  VIM reads: {list(want.values())}  ->  "
                      + ("all present" if not missing else f"MISSING in SAP: {missing}"))
            if args.rows:
                print(f"  --- first {args.rows} rows ---")
                try:
                    show = [n for n in names if n != "MANDT"][:8]
                    for r in read_table(sap, table, show, rows=args.rows):
                        print("  " + " | ".join(f"{k}={v.strip()}" for k, v in r.items()))
                except Exception as exc:  # noqa: BLE001
                    print(f"  read failed (authorization?): {exc}")
    finally:
        sap.disconnect()


if __name__ == "__main__":
    main()
