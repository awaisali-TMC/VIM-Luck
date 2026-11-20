"""Approve or reject a parked invoice in the FAKE SAP workflow — demos only.

Plays the SAP approver for WS90000096, so the VIM side of the approval
workflow (services/sap_workflow.py) can be shown end to end without SAP:

    py -3 backend/sap_wf_decide.py                               list open workflows
    py -3 backend/sap_wf_decide.py 110051050000012026 approve    SAP posts it
    py -3 backend/sap_wf_decide.py 110051050000012026 reject
    py -3 backend/sap_wf_decide.py 110051050000012026 approve --error "Posting period 11 2026 is not open"

Needs a file-backed fake SAP (SAP_FAKE_DB_PATH in backend/.env), the same file
the running backend uses; with the default in-memory store the running app's
SAP is invisible from here. VIM picks the change up on its next poll
(SAP_WF_POLL_SECONDS) or when someone presses Refresh on the invoice.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("DEBUG", "true")       # the fake connector refuses to load otherwise
os.environ.setdefault("SAP_MODE", "fake")

from app.config import settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("objkey", nargs="?", help="18-character OBJKEY (company code + document + year)")
    ap.add_argument("decision", nargs="?", choices=["approve", "reject"])
    ap.add_argument("--error", default="", help="approve, but SAP fails to post with this message")
    args = ap.parse_args()

    if not (settings.SAP_FAKE_DB_PATH or "").strip():
        sys.exit("SAP_FAKE_DB_PATH is empty, so the fake SAP lives inside the running backend's "
                 "memory and can't be changed from here. Set it in backend/.env and restart the backend.")

    from app.services.sap_connector_fake import _store, decide_workflow

    if not args.objkey:
        rows = _store().execute("SELECT OBJKEY, ITEM, WF_STATUS, ERDAT, ERZET FROM ZMIR7_WF_LOG "
                                "ORDER BY OBJKEY, ITEM").fetchall()
        if not rows:
            print("No workflows yet — park an invoice in VIM first.")
        for r in rows:
            print(f"{r['OBJKEY']}  {r['ITEM']}  {r['WF_STATUS']:4}  {r['ERDAT']} {r['ERZET']}")
        return
    if not args.decision:
        ap.error("give a decision: approve or reject")

    try:
        print(decide_workflow(args.objkey, args.decision == "approve", error=args.error))
    except (LookupError, sqlite3.Error) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
