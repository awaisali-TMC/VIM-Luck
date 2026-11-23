"""HEADER_TXT (RBKP-BKTXT) carries the parking employee in characters 1-8.

Lucky Cement's ABAP team reads the PERNR from BKTXT(8):
    "<8-digit PERNR> <header text cut to 16>"   (25 chars max)

Offline: unit checks of build_header_text, then a real park through the fake
SAP connector, reading back what landed in RBKP.

    py -3 backend/test_header_text_pernr.py
"""
import os
import sys

os.environ["DEBUG"] = "true"
os.environ["SAP_ENABLED"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["SAP_FAKE_DB_PATH"] = ""
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings  # noqa: E402
from app.services.sap_invoice_post import build_header_text, post_invoice_to_sap  # noqa: E402

PARK_ARGS = dict(
    invoice_number="HP-2026-0417", invoice_date="2026-11-19", posting_date="2026-11-19",
    vendor_number="0002000101", company_code="1000", currency="PKR",
    gross_amount=117000.0, tax_amount=17000.0, po_number="4500009001",
    line_items=[{"po_item": "00010", "amount": 100000.0, "quantity": 20, "po_unit": "EA"}],
    tax_code="2I", header_text="einv-HP-2026-0417", initiator_sap_user="00004007",
)

failures = 0


def check(label, got, want):
    global failures
    ok = got == want
    failures += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<38} sent {got!r:<30} ({len(got)} chars)"
          + ("" if ok else f"  expected {want!r}"))


print("UNIT: build_header_text(text, sap_user) -> HEADER_TXT")
check("PERNR 00004007 + default text", build_header_text("einv-HP-2026-0417", "00004007"),
      "00004007 einv-HP-2026-041")
check("short id 4007 is zero-padded", build_header_text("einv-HP-2026-0417", "4007"),
      "00004007 einv-HP-2026-041")
check("short text kept whole", build_header_text("Cement bags", "00009001"),
      "00009001 Cement bags")
check("empty text -> PERNR only", build_header_text("", "00009001"), "00009001")
check("no SAP id -> text as before", build_header_text("einv-HP-2026-0417", ""),
      "einv-HP-2026-0417")
check("non-numeric SAP id -> text as before", build_header_text("einv-HP-2026-0417", "TMC_VIM"),
      "einv-HP-2026-0417")
settings.SAP_HEADER_TEXT_PERNR = False
check("setting off -> text as before", build_header_text("einv-HP-2026-0417", "00004007"),
      "einv-HP-2026-0417")
settings.SAP_HEADER_TEXT_PERNR = True

print("\nPARK (fake SAP): BAPI_INCOMINGINVOICE_PARK, then read RBKP back")
r = post_invoice_to_sap(
    invoice_number="HP-2026-0417", invoice_date="2026-11-19", posting_date="2026-11-19",
    vendor_number="0002000101", company_code="1000", currency="PKR",
    gross_amount=117000.0, tax_amount=17000.0, po_number="4500009001",
    line_items=[{"po_item": "00010", "amount": 100000.0, "quantity": 20, "po_unit": "EA"}],
    tax_code="2I", header_text="einv-HP-2026-0417", mode="park",
    initiator_sap_user="00004007",
)
print(f"  park: success={r.get('success')} doc={r.get('invoice_doc_number')} msg={r.get('message')!r}")
from app.services.sap_connector_fake import _store  # noqa: E402
row = _store().execute("SELECT BELNR, RBSTAT, BKTXT FROM RBKP WHERE BELNR = ?",
                       (r.get("invoice_doc_number"),)).fetchone()
print(f"  RBKP: BELNR={row[0] if row else None} RBSTAT={row[1] if row else None} BKTXT={row[2] if row else None!r}")
check("RBKP-BKTXT", (row[2] if row else ""), "00004007 einv-HP-2026-041")
check("BKTXT(8) = what ABAP reads", (row[2] if row else "")[:8], "00004007")

print("\nDRY RUN (validate): BKTXT = VALIDATE, so SAP raises no workflow")
_sent = []
from app.services import sap_connector_fake as _fk  # noqa: E402
_orig = _fk.SAPConnectorFake.call


def _spy(self, name, **kw):
    if name == "BAPI_INCOMINGINVOICE_PARK":
        _sent.append(kw["input_structures"]["HEADERDATA"]["HEADER_TXT"])
    return _orig(self, name, **kw)


_fk.SAPConnectorFake.call = _spy
post_invoice_to_sap(**PARK_ARGS, mode="validate")
check("validate HEADER_TXT", _sent[-1] if _sent else "", "VALIDATE")
post_invoice_to_sap(**PARK_ARGS, mode="park")
check("real park HEADER_TXT", _sent[-1] if _sent else "", "00004007 einv-HP-2026-041")
_fk.SAPConnectorFake.call = _orig

print(f"\n{'ALL PASS' if not failures else f'{failures} FAILED'}")
sys.exit(1 if failures else 0)
