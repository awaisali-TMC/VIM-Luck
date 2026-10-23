"""Update invoices with varied FBR verification and WHT compliance data."""
import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect("invoices.db")
now = datetime.utcnow().isoformat()

updates = [
    # ID 1: Damco - verified_active, filer, compliant
    (1, "verified_active", "DAMCO PAKISTAN (PVT) LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 9820.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 2713.0, "rate": 4.0, "description": "WHT @ 4% (ATL Rate)"},
     ]), 2713.0, 9820.0),

    # ID 4: Office Solutions - verified_inactive, non_filer, non_compliant
    (4, "verified_inactive", "OFFICE SOLUTIONS KARACHI", "Non Filer", "non_compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 26350.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 6975.0, "rate": 4.5, "description": "WHT @ 4.5% (ATL rate) applied but supplier is Non-ATL, expected 9%"},
     ]), 6975.0, 26350.0),

    # ID 5: CleanPro - verified_active, filer, compliant
    (5, "verified_active", "CLEANPRO SERVICES", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 5100.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 2400.0, "rate": 8.0, "description": "WHT on Services (ATL Rate)"},
     ]), 2400.0, 5100.0),

    # ID 6: Bestway - verified_active, filer, compliant
    (6, "verified_active", "BESTWAY CEMENT LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 323000.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 85500.0, "rate": 4.5, "description": "WHT on Goods Supply (ATL Rate)"},
     ]), 85500.0, 323000.0),

    # ID 7: IESCO - verified_active, filer, compliant (utility, no WHT)
    (7, "verified_active", "ISLAMABAD ELECTRIC SUPPLY COMPANY", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 24276.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
     ]), None, 24276.0),

    # ID 8: PTCL - verified_active, filer, compliant
    (8, "verified_active", "PAKISTAN TELECOMMUNICATION COMPANY LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 7650.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 1125.0, "rate": 2.5, "description": "WHT on Telecom Services"},
     ]), 1125.0, 7650.0),

    # ID 10: Al-Falah - verified_inactive, non_filer, non_compliant
    (10, "verified_inactive", "AL-FALAH CONSULTING (PVT) LTD", "Non Filer", "non_compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 85000.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 40000.0, "rate": 8.0, "description": "WHT @ 8% (ATL rate) applied but supplier is Non-ATL, expected 16%"},
     ]), 40000.0, 85000.0),

    # ID 12: PTCL Credit - verified_active, filer, compliant
    (12, "verified_active", "PAKISTAN TELECOMMUNICATION COMPANY LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": -850.0, "rate": 17.0, "description": "GST Credit (Reversal)"},
         {"tax_type": "WHT", "amount": -125.0, "rate": 2.5, "description": "WHT Credit (Reversal)"},
     ]), -125.0, -850.0),

    # ID 13: PSO - verified_active, filer, compliant
    (13, "verified_active", "PAKISTAN STATE OIL COMPANY LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 35700.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 2100.0, "rate": 1.0, "description": "WHT on Goods Supply"},
     ]), 2100.0, 35700.0),

    # ID 14: Jazz - verified_active, filer, needs_review
    (14, "verified_active", "PAKISTAN MOBILE COMMUNICATIONS LTD", "Active Filer", "needs_review",
     json.dumps([
         {"tax_type": "GST", "amount": 4845.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 712.5, "rate": 2.5, "description": "WHT detected but rate needs verification"},
     ]), 712.5, 4845.0),

    # ID 15: Haier - verified_active, filer, compliant
    (15, "verified_active", "HAIER PAKISTAN (PRIVATE) LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 161500.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 42750.0, "rate": 4.5, "description": "WHT on Goods Supply (ATL Rate)"},
     ]), 42750.0, 161500.0),

    # ID 21: Haier dup - verified_inactive, non_filer, non_compliant
    (21, "verified_inactive", "HAIER PAKISTAN", "Non Filer", "non_compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 161500.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 42750.0, "rate": 4.5, "description": "WHT @ 4.5% (ATL rate) but supplier is Non-ATL, expected 9%"},
     ]), 42750.0, 161500.0),

    # ID 25: Office Solutions rejected - verified_active, filer, needs_review (no WHT)
    (25, "verified_active", "OFFICE SOLUTIONS KARACHI (PVT) LTD", "Active Filer", "needs_review",
     json.dumps([
         {"tax_type": "GST", "amount": 26350.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
     ]), None, 26350.0),

    # ID 26: Haier posted - verified_active, filer, compliant
    (26, "verified_active", "HAIER PAKISTAN (PRIVATE) LIMITED", "Active Filer", "compliant",
     json.dumps([
         {"tax_type": "GST", "amount": 161500.0, "rate": 17.0, "description": "General Sales Tax @ 17%"},
         {"tax_type": "WHT", "amount": 42750.0, "rate": 4.5, "description": "WHT on Goods Supply (ATL Rate)"},
     ]), 42750.0, 161500.0),

    # ID 27: Office Solutions processing - keep not_verified for variety
]

sql = """UPDATE invoices SET
    fbr_verification_status = ?,
    fbr_taxpayer_name = ?,
    fbr_filing_status = ?,
    wht_compliance_status = ?,
    detected_taxes = ?,
    wht_amount = ?,
    gst_amount = ?,
    fbr_verified_at = ?
WHERE id = ?"""

for u in updates:
    inv_id = u[0]
    params = u[1:] + (now, inv_id)
    conn.execute(sql, params)
    print(f"Updated invoice ID {inv_id}: FBR={u[1]}, WHT={u[4]}")

conn.commit()
conn.close()
print("\nDone! Updated", len(updates), "invoices.")
