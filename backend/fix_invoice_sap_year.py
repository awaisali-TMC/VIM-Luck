"""One-off repair: an invoice whose SAP fiscal year was saved as "0000".

A resubmit (BAPI_INCOMINGINVOICE_CHANGE) before commit-after-d8b05fb stored
SAP's initial FISCALYEAR_NEW "0000", which also broke the workflow key
(OBJKEY = company code + document + year), so "Refresh from SAP" found nothing.
This puts the real year back and rebuilds the key. Report-only without --yes.

    backend/.venv/bin/python backend/fix_invoice_sap_year.py 54 2027          # show
    backend/.venv/bin/python backend/fix_invoice_sap_year.py 54 2027 --yes    # fix

Targets DATABASE_URL from backend/.env (the LAN box's own database).
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.invoice import Invoice  # noqa: E402
from app.services.sap_workflow import build_objkey  # noqa: E402


async def main(invoice_id: int, year: str, apply: bool) -> int:
    async with async_session() as db:
        inv = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
        if not inv:
            print(f"Invoice {invoice_id} not found")
            return 1
        cc = inv.sap_company_code or (inv.sap_wf_objkey or "")[:4]
        new_key = build_objkey(cc, inv.sap_document_number or "", year)
        print(f"Invoice {inv.id}: document {inv.sap_document_number}/{inv.sap_fiscal_year}, "
              f"company {cc}, workflow key {inv.sap_wf_objkey}")
        print(f"  ->  year {year}, workflow key {new_key}")
        if not apply:
            print("Report only. Add --yes to apply.")
            return 0
        inv.sap_fiscal_year = year
        inv.sap_wf_objkey = new_key
        inv.sap_wf_status = ""          # read fresh on the next refresh
        inv.sap_wf_checked_at = None
        await db.commit()
        print("Fixed. Open the invoice and click 'Refresh from SAP'.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("invoice_id", type=int)
    ap.add_argument("fiscal_year")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if not (len(a.fiscal_year) == 4 and a.fiscal_year.isdigit()):
        sys.exit("fiscal_year must be 4 digits, e.g. 2027")
    sys.exit(asyncio.run(main(a.invoice_id, a.fiscal_year, a.yes)))
