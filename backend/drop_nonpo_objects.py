"""Drop the Non-PO lane's database objects. One-off, destructive, run by hand.

The lane's code was removed; this clears what it left behind in the database.
Deliberately NOT part of run_migrations(): that list executes at startup on every
instance, so a DROP there would destroy these tables on the next deploy of any
environment that still wants them.

    py -3 backend/drop_nonpo_objects.py           # report only, changes nothing
    py -3 backend/drop_nonpo_objects.py --yes     # actually drop

Targets whatever DATABASE_URL points at, so a cloud run needs cloud-sql-proxy.
Leaving it unrun is harmless — orphan tables and one unused column cost nothing.

Deletes any invoice that was uploaded through the Non-PO lane. Those rows have no
purchase order and nothing left to render them, so they cannot complete a
lifecycle in the PO-only app.
"""

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.config import settings
from app.database import engine

TABLES = ["nonpo_gl_lines", "nonpo_reference_checks", "sap_gl_accounts"]


async def _scalar(conn, sql):
    """Return one value, or None if the object does not exist."""
    try:
        return (await conn.execute(text(sql))).scalar()
    except Exception:
        return None


async def report(conn):
    print(f"\n  {settings.DATABASE_URL}\n")
    invoices = await _scalar(conn, "SELECT count(*) FROM invoices WHERE procurement_type = 'non_po'")
    print(f"  {'invoices with procurement_type=non_po':<40} "
          f"{'(column already gone)' if invoices is None else invoices}")
    for t in TABLES:
        n = await _scalar(conn, f"SELECT count(*) FROM {t}")
        print(f"  {t:<40} {'(already dropped)' if n is None else f'{n} rows'}")
    return invoices


async def drop(conn, invoices):
    if invoices:
        await conn.execute(text("DELETE FROM invoices WHERE procurement_type = 'non_po'"))
        print(f"  deleted {invoices} Non-PO invoice(s)")

    for t in TABLES:
        await conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        print(f"  dropped {t}")

    # Reported rather than fatal: SQLite gained DROP COLUMN in 3.35, and the
    # column is harmless if it stays. Everything above has already succeeded.
    try:
        await conn.execute(text("ALTER TABLE invoices DROP COLUMN procurement_type"))
        print("  dropped invoices.procurement_type")
    except Exception as e:
        print(f"  could NOT drop invoices.procurement_type: {e}")
        print("  (harmless — the column is unused. Everything else was dropped.)")


async def main(confirmed: bool):
    async with engine.begin() as conn:
        invoices = await report(conn)

        if not confirmed:
            print("\n  Nothing changed. Re-run with --yes to drop these.\n")
            return 0

        print("\n  --yes given, dropping:\n")
        await drop(conn, invoices)

    print("\n  Done.\n")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true",
                    help="perform the deletion and drops (without this, only reports)")
    sys.exit(asyncio.run(main(ap.parse_args().yes)))
