"""
Importer for FBR's Active Taxpayer List into the app's `atl_taxpayers` table.

Handles FBR's published Excel files (downloaded from fbr.gov.pk → Online
Services), which come as multi-sheet workbooks (Part1, Part2, … — Excel caps a
sheet at ~1.05M rows, so the list is split):
  - ATL_IT.xlsx  columns: SR_NO, NTN, NAME, BUSINESS_NAME          (income tax)
  - ATL_ST.xlsx  columns: SR, NTN, CNIC, NAME, BUSINESSNAME        (sales tax)
Also accepts a CSV/TSV with an `ntn` column, or an SQLite `active_taxpayers` db.

Being ON the ATL means the taxpayer is an ACTIVE filer, so every imported row
is stored with filing_status = "Active". The table is REPLACED for the given
list_type on each run (fresh snapshot).

Usage:
    py -3 import_atl.py ATL_IT.xlsx --type IT
    py -3 import_atl.py ATL_ST.xlsx --type ST

Target DB = the app's DATABASE_URL (SQLite locally; Cloud SQL Postgres in cloud
via cloud-sql-proxy + DATABASE_URL env).
"""
import asyncio
import csv
import os
import re
import sqlite3
import sys

from sqlalchemy import delete, insert

from app.database import async_session, engine, Base
from app.models.atl_taxpayer import AtlTaxpayer

BATCH = 5000


def _norm(v):
    return re.sub(r"[\s\-/]", "", str(v or "").strip())


def _col(header, *names):
    """Find a column index by any of the candidate names (case-insensitive)."""
    low = [str(h or "").strip().lower() for h in header]
    for n in names:
        if n.lower() in low:
            return low.index(n.lower())
    return None


def _rows_from_xlsx(path, list_type):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    for sheet in wb.sheetnames:
        ws = wb[sheet]
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            continue
        i_ntn = _col(header, "ntn", "registration no", "reg_no")
        i_name = _col(header, "name")
        i_biz = _col(header, "business_name", "businessname")
        i_cnic = _col(header, "cnic")
        for r in it:
            if i_ntn is None or i_ntn >= len(r):
                continue
            disp = str(r[i_ntn]).strip() if r[i_ntn] is not None else ""
            if not disp:
                continue
            yield {
                "ntn": _norm(disp), "ntn_display": disp,
                "cnic": _norm(r[i_cnic]) if (i_cnic is not None and i_cnic < len(r) and r[i_cnic]) else None,
                "name": (str(r[i_name]).strip() if i_name is not None and i_name < len(r) and r[i_name] else None),
                "business_name": (str(r[i_biz]).strip() if i_biz is not None and i_biz < len(r) and r[i_biz] else None),
                "filing_status": "Active", "list_type": list_type,
                "status_date": None, "last_updated": None,
            }
    wb.close()


def _rows_from_csv(path, list_type):
    delim = "\t" if path.lower().endswith((".tsv", ".txt")) else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        i_ntn = _col(header, "ntn"); i_name = _col(header, "name")
        i_biz = _col(header, "business_name", "businessname"); i_cnic = _col(header, "cnic")
        if i_ntn is None:
            raise SystemExit(f"CSV has no NTN column. Header: {header}")
        for r in reader:
            disp = r[i_ntn].strip() if i_ntn < len(r) else ""
            if not disp:
                continue
            yield {
                "ntn": _norm(disp), "ntn_display": disp,
                "cnic": _norm(r[i_cnic]) if (i_cnic is not None and i_cnic < len(r) and r[i_cnic]) else None,
                "name": r[i_name].strip() if i_name is not None and i_name < len(r) else None,
                "business_name": r[i_biz].strip() if i_biz is not None and i_biz < len(r) else None,
                "filing_status": "Active", "list_type": list_type,
                "status_date": None, "last_updated": None,
            }


async def main(source, list_type):
    if not os.path.exists(source):
        raise SystemExit(f"Source not found: {source}")
    if source.lower().endswith((".xlsx", ".xlsm")):
        src = _rows_from_xlsx(source, list_type)
    else:
        src = _rows_from_csv(source, list_type)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Replace just this list_type's rows (fresh snapshot for IT or ST).
    async with async_session() as db:
        await db.execute(delete(AtlTaxpayer).where(AtlTaxpayer.list_type == list_type))
        await db.commit()

    total, batch = 0, []
    async with async_session() as db:
        for row in src:
            if not row["ntn"]:
                continue
            batch.append(row)
            if len(batch) >= BATCH:
                await db.execute(insert(AtlTaxpayer), batch)
                await db.commit()
                total += len(batch); batch = []
                if total % 100000 == 0:
                    print(f"  ...{total:,} imported")
        if batch:
            await db.execute(insert(AtlTaxpayer), batch)
            await db.commit()
            total += len(batch)
    print(f"ATL {list_type} import complete: {total:,} taxpayers loaded.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: py -3 import_atl.py <file> [--type IT|ST]")
    src = sys.argv[1]
    lt = "IT"
    if "--type" in sys.argv:
        lt = sys.argv[sys.argv.index("--type") + 1].upper()
    elif "_ST" in src.upper() or "ATL_ST" in src.upper():
        lt = "ST"
    asyncio.run(main(src, lt))
