"""Browse the fake SAP database — the fixture equivalent of SAP's SE16.

Read-only, and needs nothing installed: Python ships with sqlite3, and the
Windows sqlite3.exe CLI usually is not present.

    py -3 backend/sap_se16.py                     list tables with row counts
    py -3 backend/sap_se16.py RBKP                every parked/posted document
    py -3 backend/sap_se16.py EKPO -w "EBELN = '4500009001'"
    py -3 backend/sap_se16.py EKKO --csv pos.csv  open it in Excel

The database only exists when the app runs with SAP_FAKE_DB_PATH set; leave that
empty and the fixtures live in memory, invisible from outside the process.

Opened with mode=ro, so this cannot change what the app is serving — safe to run
against a live demo, including mid-demo.
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# What each table is, so a reader who does not speak SAP can still navigate.
GLOSS = {
    "EKKO": "PO header", "EKPO": "PO line items", "EKBE": "PO history (goods receipts)",
    "EKBZ": "PO delivery costs", "LFA1": "Vendor master (general)",
    "LFB1": "Vendor master (per company code)", "RBKP": "Invoice header — PARKED/POSTED DOCUMENTS",
    "MKPF": "Material document header", "MSEG": "Material document items",
    "ESSR": "Service entry sheets", "T001": "Company codes", "T005": "Countries",
    "T007A": "Tax codes", "T007S": "Tax code texts", "TCURT": "Currency texts",
    "SKA1": "G/L accounts (chart)", "SKB1": "G/L accounts (company code)",
    "SKAT": "G/L account texts", "Z_COUNTER": "Fake bookkeeping (next document number)",
}

RBSTAT = {"A": "parked", "5": "posted"}


def _db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        from app.config import settings
        configured = (settings.SAP_FAKE_DB_PATH or "").strip()
    except Exception:
        configured = ""
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).parent / "sap_fake.db").resolve()


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(
            f"No fake SAP database at {path}.\n\n"
            "It is only written when the backend runs with SAP_FAKE_DB_PATH set:\n"
            "    SAP_ENABLED=true SAP_MODE=fake DEBUG=true SAP_FAKE_DB_PATH=sap_fake.db \\\n"
            "        py -3 -m uvicorn app.main:app --port 8000\n"
            "With that setting empty the fixtures stay in memory and cannot be read\n"
            "from outside the running process."
        )
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn) -> list[str]:
    return [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]


def list_tables(conn, path):
    print(f"\n  {path}\n")
    print(f"  {'TABLE':<12} {'ROWS':>6}   WHAT IT HOLDS")
    print(f"  {'-' * 12} {'-' * 6}   {'-' * 44}")
    for t in _tables(conn):
        n = conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
        mark = " *" if (t == "RBKP" and n) else ""
        print(f"  {t:<12} {n:>6}   {GLOSS.get(t, '')}{mark}")
    parked = conn.execute("SELECT count(*) AS n FROM RBKP").fetchone()["n"]
    print(f"\n  {parked} document(s) currently in SAP."
          f"{'  Run: py -3 sap_se16.py RBKP' if parked else ''}\n")


def dump(conn, table: str, where: str | None, limit: int, csv_out: str | None):
    known = {t.upper(): t for t in _tables(conn)}
    if table.upper() not in known:
        sys.exit(f"No table {table!r}. Available: {', '.join(sorted(known))}")
    table = known[table.upper()]

    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if limit:
        sql += f" LIMIT {limit}"
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error as e:
        sys.exit(f"Query failed: {e}\n  {sql}")

    if not rows:
        print(f"\n  {table}: no rows" + (f" matching {where}" if where else "") + "\n")
        return

    cols = rows[0].keys()

    if csv_out:
        with open(csv_out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows([tuple(r) for r in rows])
        print(f"\n  {len(rows)} row(s) from {table} -> {Path(csv_out).resolve()}")
        print("  utf-8-sig, so Excel opens it with the right encoding.\n")
        return

    widths = {c: max(len(c), *(len(str(r[c] if r[c] is not None else "")) for r in rows))
              for c in cols}
    print(f"\n  {table} — {GLOSS.get(table, '')}" + (f"   WHERE {where}" if where else ""))
    print("  " + "  ".join(c.ljust(widths[c]) for c in cols))
    print("  " + "  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  " + "  ".join(str(r[c] if r[c] is not None else "").ljust(widths[c]) for c in cols))

    if table == "RBKP":
        print()
        for r in rows:
            state = RBSTAT.get(r["RBSTAT"], r["RBSTAT"])
            print(f"    document {r['BELNR']} / {r['GJAHR']} is {state}")
    print(f"\n  {len(rows)} row(s)\n")


def main():
    ap = argparse.ArgumentParser(description="Read-only browser for the fake SAP database.")
    ap.add_argument("table", nargs="?", help="table to dump; omit to list all tables")
    ap.add_argument("-w", "--where", help="SQL WHERE clause, e.g. \"EBELN = '4500009001'\"")
    ap.add_argument("-n", "--limit", type=int, default=200, help="max rows (default 200)")
    ap.add_argument("--csv", help="write to this CSV file instead of printing (for Excel)")
    ap.add_argument("--db", help="path to the database (default: SAP_FAKE_DB_PATH)")
    args = ap.parse_args()

    path = _db_path(args.db)
    conn = _connect(path)
    if args.table:
        dump(conn, args.table, args.where, args.limit, args.csv)
    else:
        list_tables(conn, path)


if __name__ == "__main__":
    main()
