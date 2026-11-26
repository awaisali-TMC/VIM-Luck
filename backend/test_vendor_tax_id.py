"""Vendor tax ID: an NTN, or a CNIC (13 digits) when the vendor is an individual.

Covers:
  - extraction prompt asks for the NTN or the CNIC, NTN first, never the STRN;
    the field label is "Vendor NTN / CNIC"; the missing-ID flag names both
  - FBR identifier detection: a 13-digit CNIC (with or without dashes) is a CNIC,
    an NTN stays an NTN, a labelled NTN wins over an STRN in the same field
  - SAP vendor lookup (vendors_by_ntn) also tries the dashed CNIC form, so a
    CNIC printed without dashes finds a vendor stored with them (and back)

Offline: no Gemini, no SAP (the RFC connector is stubbed).

    py -3 backend/test_vendor_tax_id.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ["GEMINI_API_KEY"] = ""

from app.services import sap_po_service  # noqa: E402
from app.services.fbr_verification import normalize_identifier  # noqa: E402
from app.services.gemini_extract import EXTRACTION_PROMPT, FIELD_LABELS, _detect_attention_flags  # noqa: E402

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def test_extraction():
    print("\nUNIT: extraction prompt and label")
    expect("prompt mentions CNIC for individuals", "CNIC when the vendor is an individual" in EXTRACTION_PROMPT)
    expect("prompt prefers the NTN when both are printed", "When both are printed, take the NTN" in EXTRACTION_PROMPT)
    expect("prompt excludes the STRN", "Never the STRN" in EXTRACTION_PROMPT)
    expect("label is Vendor NTN / CNIC", FIELD_LABELS.get("supplier_tax_id") == "Vendor NTN / CNIC")
    flags = _detect_attention_flags({"invoice_id": "1", "supplier_name": "V", "total_amount": 1}, [], [], 99.0)
    titles = [f.get("title") for f in flags]
    expect("missing-ID flag names NTN / CNIC", "No vendor NTN / CNIC" in titles, titles)


def test_fbr_detection():
    print("\nUNIT: FBR identifier detection")
    expect("dashed CNIC", normalize_identifier("42201-1234567-1") == ("4220112345671", "CNIC"),
           normalize_identifier("42201-1234567-1"))
    expect("plain CNIC", normalize_identifier("4220112345671") == ("4220112345671", "CNIC"))
    expect("NTN with check digit", normalize_identifier("1234567-8")[1] == "NTN")
    expect("labelled NTN wins over STRN",
           normalize_identifier("STRN # 3277876177886, NTN # 5433744-3")[1] == "NTN")


class _StubSAP:
    def __init__(self):
        self.options = []

    def connect(self):
        pass

    def disconnect(self):
        pass

    def call(self, fn, **kw):
        self.options.append(" ".join(o["TEXT"] for o in kw["input_tables"]["OPTIONS"]))
        return {"DATA": [], "FIELDS": []}


def test_sap_lookup():
    print("\nUNIT: SAP vendor lookup by CNIC")
    for printed in ("4220112345671", "42201-1234567-1"):
        stub = _StubSAP()
        orig = sap_po_service._get_connector
        sap_po_service._get_connector = lambda: stub
        try:
            sap_po_service.vendors_by_ntn(printed, "")
        finally:
            sap_po_service._get_connector = orig
        where = stub.options[0] if stub.options else ""
        expect(f"{printed}: tries the dashed form", "'42201-1234567-1'" in where, where[:200])
        expect(f"{printed}: tries the plain form", "'4220112345671'" in where, where[:200])


if __name__ == "__main__":
    test_extraction()
    test_fbr_detection()
    test_sap_lookup()
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL VENDOR TAX ID TESTS PASSED")
    print("=" * 60)
