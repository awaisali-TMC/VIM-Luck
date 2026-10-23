"""Generate invoice PDFs that match the fake SAP fixtures, for demos.

The repo's existing generate_test_invoice.py targets PO 4500000000 with a
Canadian supplier — it predates this and matches nothing in sap_fixtures/. These
PDFs match the fixture POs, so an uploaded invoice actually finds its PO, the
2-way match lands, and the numbers on screen agree with the numbers in "SAP".

    pip install reportlab                              # not in requirements.txt
    py -3 backend/generate_demo_invoices.py            # all of them
    py -3 backend/generate_demo_invoices.py 4500009001 # just one PO's invoice(s)

reportlab is deliberately NOT a declared dependency: this is a local authoring
tool and requirements.txt is what the Cloud Run image installs. The repo's older
generate_test_invoice*.py scripts have the same undeclared dependency.

Writes to backend/demo_invoices/ (git-ignored — regenerate rather than commit).
Uploading them needs a working GEMINI_API_KEY, since extraction is what reads the
PDF; test_sap_fake.py exercises the same flow without one by posting to
/api/invoices/save directly.

Every identifier is invented; nothing here is copied from a real SAP system.
"""

import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).parent / "demo_invoices"

BRAND = HexColor("#1a3a5c")
ACCENT = HexColor("#2563eb")
LIGHT_BG = HexColor("#f8fafc")
BORDER = HexColor("#cbd5e1")
BLACK = HexColor("#111827")
GRAY = HexColor("#64748b")
WHITE = HexColor("#ffffff")
WARN = HexColor("#b45309")

W, H = A4

# Supplier block shared by the Haier variations at the end of INVOICES.
_HAIER = {
    "po": "4500009001",
    "supplier": "Haier Pakistan (Pvt) Ltd",
    "address": "Plot 42, Sundar Industrial Estate, Lahore, Pakistan",
    "ntn": "0912345-6",
    "vendor_no": "0002000101",
    "currency": "PKR",
    "terms": "Net 30",
    "bank": "Habib Bank Ltd  |  IBAN PK36HABB0000001234567890",
    "gst_rate": 18.0,
}

# TechServ is the vendor on PO 4500009005 (so the supplier login sees it); the three
# invoices against it share this block.
_KPI = {
    "po": "4500009005",
    "supplier": "TechServ Solutions (Pvt) Ltd",
    "address": "Office 12, Business Avenue, Shahrah-e-Faisal, Karachi, Pakistan",
    "ntn": "3456789-2",
    "vendor_no": "0002000105",
    "currency": "PKR",
    "terms": "Net 15",
    "bank": "Bank Al Habib Ltd  |  IBAN PK11BAHL0000002233445566",
    "gst_rate": 18.0,
}
_KPI_ITEMS = [
    ("10", "Aluminium Foil Roll 20 Micron", 400, "ST", 2250),
    ("20", "PVC Blister Film Roll 250mm", 300, "ST", 2200),
    ("30", "Corrugated Carton 5-Ply", 5000, "EA", 120),
]

# Each entry mirrors a PO in sap_fixtures/data.sql. `note` says what the invoice
# is for in a demo — the happy path, or which failure it provokes.
INVOICES = [
    {
        "po": "4500009001",
        "invoice_no": "HP-2026-0417",
        "date": "2026-03-12",
        "supplier": "Haier Pakistan (Pvt) Ltd",
        "address": "Plot 42, Sundar Industrial Estate, Lahore, Pakistan",
        "ntn": "0912345-6",
        "vendor_no": "0002000101",
        "currency": "PKR",
        "terms": "Net 30",
        "bank": "Habib Bank Ltd  |  IBAN PK36HABB0000001234567890",
        "gst_rate": 18.0,
        "delivery_note": "DN-2026-00417",
        "items": [
            ("10", "Split AC Unit 1.5 Ton Inverter", 20, "ST", 185000),
            ("20", "Deep Freezer 500L", 5, "ST", 240000),
        ],
        "note": "HAPPY PATH — matches the PO exactly, has a goods receipt, parks cleanly.",
    },
    {
        "po": "4700009001",
        "invoice_no": "OSK-2026-0088",
        "date": "2026-03-02",
        "supplier": "Office Solutions Karachi",
        "address": "Suite 7, Progressive Centre, Shahrah-e-Faisal, Karachi",
        "ntn": "1234567-8",
        "vendor_no": "0002000103",
        "currency": "PKR",
        "terms": "Net 15",
        "bank": "Meezan Bank Ltd  |  IBAN PK24MEZN0000009876543210",
        "gst_rate": 15.0,   # services — provincial sales tax on services
        "entry_sheet": "1000009001",
        "items": [
            ("10", "Annual Office Cleaning Contract - February 2026", 1, "AU", 360000),
        ],
        "note": "SERVICE PO — value-based, confirmed by entry sheet 1000009001, no quantity sent to SAP.",
    },
    {
        "po": "4500009002",
        "invoice_no": "SCT-2026-0031",
        "date": "2026-03-14",
        "supplier": "Sindh Chemical Traders",
        "address": "Plot 19, Korangi Industrial Area, Karachi, Pakistan",
        "ntn": "7788990-3",
        "vendor_no": "0002000104",
        "currency": "PKR",
        "terms": "Net 30",
        "bank": "Bank Alfalah Ltd  |  IBAN PK77ALFH0000005544332211",
        "gst_rate": 18.0,
        "items": [
            ("10", "Industrial Solvent Drums 200L", 100, "EA", 3500),
        ],
        "note": "SAP REFUSES IT — vendor 0002000104 is blocked for posting in company code 1100.",
    },
    {
        "po": "4500009003",
        "invoice_no": "BWC-2026-1204",
        "date": "2026-03-08",
        "supplier": "Bestway Cement Ltd",
        "address": "Hattar Road, Haripur, Khyber Pakhtunkhwa, Pakistan",
        "ntn": "0456789-1",
        "vendor_no": "0002000102",
        "currency": "PKR",
        "terms": "Net 30",
        "bank": "United Bank Ltd  |  IBAN PK52UNIL0000001122334455",
        "gst_rate": 18.0,
        "items": [
            ("10", "OPC Cement 50kg Bags", 2000, "BAG", 950),
            ("20", "Steel Rebar Grade 60 12mm", 20, "TO", 44000),
        ],
        "note": "STOPPED BEFORE SAP — GR-based invoice verification, and no goods receipt exists yet.",
    },
    {
        "po": "4700009002",
        "invoice_no": "TSS-2026-0142",
        "date": "2026-04-02",
        "supplier": "TechServ Solutions (Pvt) Ltd",
        "address": "Office 12, Business Avenue, Shahrah-e-Faisal, Karachi, Pakistan",
        "ntn": "3456789-2",
        "vendor_no": "0002000105",
        "currency": "PKR",
        "terms": "Net 15",
        "bank": "Bank Al Habib Ltd  |  IBAN PK11BAHL0000002233445566",
        "gst_rate": 15.0,   # services
        "entry_sheet": "1000009002",
        "items": [
            ("10", "IT Support & Maintenance - Q1 2026", 1, "AU", 540000),
        ],
        "note": "SECOND SERVICE PO — confirmed by entry sheet 1000009002, parks cleanly.",
    },
    # Two invoices against the same PO: 30 laptops ordered, 18 received so far.
    {
        "po": "4500009004",
        "invoice_no": "HP-2026-0533",
        "date": "2026-03-18",
        "supplier": "Haier Pakistan (Pvt) Ltd",
        "address": "Plot 42, Sundar Industrial Estate, Lahore, Pakistan",
        "ntn": "0912345-6",
        "vendor_no": "0002000101",
        "currency": "PKR",
        "terms": "Net 30",
        "bank": "Habib Bank Ltd  |  IBAN PK36HABB0000001234567890",
        "gst_rate": 18.0,
        "items": [
            ("10", "Laptop Core i7 16GB 512GB SSD", 30, "ST", 250000),
        ],
        "note": "PARTIAL DELIVERY, OVER-BILLED — bills all 30 laptops, only 18 received: the 3-way match flags it.",
    },
    {
        "po": "4500009004",
        "invoice_no": "HP-2026-0534",
        "date": "2026-03-18",
        "supplier": "Haier Pakistan (Pvt) Ltd",
        "address": "Plot 42, Sundar Industrial Estate, Lahore, Pakistan",
        "ntn": "0912345-6",
        "vendor_no": "0002000101",
        "currency": "PKR",
        "terms": "Net 30",
        "bank": "Habib Bank Ltd  |  IBAN PK36HABB0000001234567890",
        "gst_rate": 18.0,
        "delivery_note": "DN-2026-00533",
        "items": [
            ("10", "Laptop Core i7 16GB 512GB SSD", 18, "ST", 250000),
        ],
        "note": "PARTIAL DELIVERY, BILLED CORRECTLY — bills only the 18 laptops received: matches the receipt, parks.",
    },
    {
        "po": "4700009003",
        "invoice_no": "SGP-2026-0310",
        "date": "2026-03-31",
        "supplier": "Securitas Guarding Pakistan",
        "address": "45-B, Gulberg III, Lahore, Pakistan",
        "ntn": "5566778-4",
        "vendor_no": "0002000106",
        "currency": "PKR",
        "terms": "Net 15",
        "bank": "MCB Bank Ltd  |  IBAN PK63MUCB0000006677889900",
        "gst_rate": 15.0,   # services
        "items": [
            ("10", "Security Guard Services - March 2026", 1, "AU", 480000),
        ],
        "note": "STOPPED BEFORE SAP — service PO with no accepted service entry sheet.",
    },

    # ── PO 4500009005: which invoice lines can be parked ────────────────────
    # Dates are more than 7 days apart so the duplicate check stays quiet.
    {
        **_KPI,
        "invoice_no": "TSS-2026-0721",
        "date": "2026-04-06",
        "delivery_note": "DN-2026-00531",
        "items": _KPI_ITEMS,
        "note": "SELECT ALL — all three lines are on the PO, so every line starts checked and the invoice parks.",
    },
    {
        **_KPI,
        "invoice_no": "TSS-2026-0722",
        "date": "2026-04-20",
        "delivery_note": "DN-2026-00532",
        "items": _KPI_ITEMS + [
            ("40", "Freight and delivery charges", 1, "AU", 25000),
        ],
        "note": "FREIGHT NOT ON THE PO — the freight line starts checked but has no PO item, so it is flagged and "
                "Submit is blocked until it is unchecked or deleted. Parking it anyway is refused by name.",
    },
    {
        **_KPI,
        "invoice_no": "TSS-2026-0723",
        "date": "2026-05-04",
        "delivery_note": "DN-2026-00533",
        "items": [
            ("10", "Aluminium Foil Roll 20 Micron - DELIVERY INFO: DN-2026-00533, Weight 412 KG", 400, "ST", 2250),
            _KPI_ITEMS[1],
            _KPI_ITEMS[2],
        ],
        "note": "NOT FREIGHT — a goods line whose text says \"DELIVERY INFO\". It is an ordinary line: it stays "
                "checked, is matched to its PO item, and nothing is copied into a header field.",
    },

    # ── Variations on the original POs: no new fixture data needed ──────────
    # Dates are spread out on purpose. The duplicate check treats the same NTN
    # with a total within 1% and a date within 7 days as a probable duplicate,
    # so only the deliberate re-send below should trip it.
    {
        **_HAIER,
        "invoice_no": "HP-2026-0612",
        "date": "2026-03-26",
        "delivery_note": "DN-2026-00417",
        "items": [
            ("10", "Split AC Unit 1.5 Ton Inverter", 20, "ST", 190000),
            ("20", "Deep Freezer 500L", 5, "ST", 240000),
        ],
        "note": "PRICE DIFFERENCE — AC units billed at 190,000 against a PO price of 185,000 (over the 2% tolerance).",
    },
    {
        **_HAIER,
        "invoice_no": "HP-2026-0625",
        "date": "2026-04-06",
        "items": [
            ("10", "Split AC Unit 1.5 Ton Inverter", 22, "ST", 185000),
            ("20", "Deep Freezer 500L", 5, "ST", 240000),
        ],
        "note": "QUANTITY DIFFERENCE — bills 22 AC units against 20 ordered and 20 received.",
    },
    {
        **_HAIER,
        "invoice_no": "HP-2026-0417",
        "date": "2026-03-12",
        "delivery_note": "DN-2026-00417",
        "file_suffix": "_RESENT",
        "items": [
            ("10", "Split AC Unit 1.5 Ton Inverter", 20, "ST", 185000),
            ("20", "Deep Freezer 500L", 5, "ST", 240000),
        ],
        "note": "DUPLICATE — Haier re-sends HP-2026-0417. Upload the original first; this copy should be flagged.",
    },
    {
        **_HAIER,
        "title": "CREDIT NOTE",
        "invoice_no": "HP-CN-2026-0021",
        "date": "2026-03-25",
        "original_invoice": "HP-2026-0417",
        "items": [
            ("20", "Deep Freezer 500L - returned, damaged in transit", 2, "ST", 240000),
        ],
        "note": "CREDIT NOTE — Haier credits 2 returned freezers against invoice HP-2026-0417.",
    },
    {
        **_HAIER,
        "invoice_no": "HP-2026-0650",
        "date": "2026-04-15",
        "gst_rate": 17.0,
        "delivery_note": "DN-2026-00417",
        "items": [
            ("10", "Split AC Unit 1.5 Ton Inverter", 20, "ST", 185000),
            ("20", "Deep Freezer 500L", 5, "ST", 240000),
        ],
        "note": "DIFFERENT TAX RATE — sales tax at 17%, so the app should suggest tax code I2 instead of I1.",
    },
    {
        "po": "4700009001",
        "invoice_no": "OSK-2026-0101",
        "date": "2026-04-01",
        "supplier": "Office Solutions Karachi",
        "address": "Suite 7, Progressive Centre, Shahrah-e-Faisal, Karachi",
        "ntn": "1234567-8",
        "vendor_no": "0002000103",
        "currency": "PKR",
        "terms": "Net 15",
        "bank": "Meezan Bank Ltd  |  IBAN PK24MEZN0000009876543210",
        "gst_rate": 15.0,
        "hide_po": True,
        "items": [
            ("10", "Annual Office Cleaning Contract - March 2026", 1, "AU", 360000),
        ],
        "note": "NO PO NUMBER — the invoice doesn't quote its PO; find it by searching the vendor name.",
    },
]


def _money(v):
    return f"{v:,.2f}"


def draw(c, spec):
    items = spec["items"]
    subtotal = sum(q * p for _, _, q, p, in ((a, b, q, p) for a, b, q, _, p in items))
    cur = spec["currency"]
    gst_rate = spec.get("gst_rate", 0.0)
    gst = round(subtotal * gst_rate / 100, 2)
    total = subtotal + gst

    # ── Header band ──────────────────────────────────────────────
    c.setFillColor(BRAND)
    c.rect(0, H - 90, W, 90, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, H - 50, spec.get("title", "INVOICE"))
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 68, spec["supplier"])
    c.drawString(40, H - 80, spec["address"])

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(W - 40, H - 40, f"Invoice No:  {spec['invoice_no']}")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 40, H - 55, f"Date:  {spec['date']}")
    c.drawRightString(W - 40, H - 68, f"Terms:  {spec['terms']}")
    # `hide_po` leaves the PO off the page entirely, so the operator has to find
    # it in the app (the PO search matches vendor names too).
    if not spec.get("hide_po"):
        c.drawRightString(W - 40, H - 81, f"PO Ref:  {spec['po']}")

    y = H - 120

    # ── Bill to / supplier ───────────────────────────────────────
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "BILL TO")
    c.drawString(340, y, "SUPPLIER DETAILS")

    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 15, "Lucky Cement Limited")
    c.drawString(40, y - 27, "Company Code: 1100")
    c.drawString(40, y - 39, "Karachi, Pakistan")

    c.drawString(340, y - 15, f"NTN: {spec['ntn']}")
    c.drawString(340, y - 27, f"Vendor No: {spec['vendor_no']}")
    c.drawString(340, y - 39, f"Currency: {cur}")

    y -= 70

    # ── Reference line (delivery note / entry sheet) ─────────────
    ref = None
    if spec.get("original_invoice"):
        ref = f"Against Invoice: {spec['original_invoice']}"
    elif spec.get("delivery_note"):
        ref = f"Delivery Note: {spec['delivery_note']}"
    elif spec.get("entry_sheet"):
        ref = f"Service Entry Sheet: {spec['entry_sheet']}"
    if ref:
        c.setFillColor(GRAY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(40, y, "REFERENCE")
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 9)
        c.drawString(100, y, ref)
        y -= 25

    # ── Line items ───────────────────────────────────────────────
    col_x = [40, 62, 300, 355, 420, 480]
    col_w = [20, 230, 50, 50, 55, 75]
    labels = ["#", "Description", "Qty", "Unit", "Unit Price", "Amount"]

    c.setFillColor(ACCENT)
    c.rect(35, y - 5, W - 75, 20, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    for i, label in enumerate(labels):
        if i >= 2:
            c.drawRightString(col_x[i] + col_w[i], y + 5, label)
        else:
            c.drawString(col_x[i], y + 5, label)
    y -= 25

    for no, desc, qty, unit, price in items:
        c.setFillColor(LIGHT_BG)
        c.rect(35, y - 5, W - 75, 20, fill=1, stroke=0)
        c.setFillColor(BLACK)
        c.setFont("Helvetica", 9)
        c.drawString(col_x[0], y + 3, no)
        c.drawString(col_x[1], y + 3, desc)
        c.drawRightString(col_x[2] + col_w[2], y + 3, f"{qty:,}")
        c.drawRightString(col_x[3] + col_w[3], y + 3, unit)
        c.drawRightString(col_x[4] + col_w[4], y + 3, _money(price))
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(col_x[5] + col_w[5], y + 3, _money(qty * price))
        y -= 22

    y -= 5
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(300, y + 10, W - 40, y + 10)

    # ── Totals ───────────────────────────────────────────────────
    tx, vx = 400, W - 40
    y -= 8
    c.setFont("Helvetica", 9)
    c.setFillColor(GRAY)
    c.drawString(tx, y, "Subtotal")
    c.setFillColor(BLACK)
    c.drawRightString(vx, y, f"{cur} {_money(subtotal)}")

    y -= 18
    c.setFillColor(GRAY)
    c.drawString(tx, y, f"Sales Tax ({gst_rate:g}%)")
    c.setFillColor(BLACK)
    c.drawRightString(vx, y, f"{cur} {_money(gst)}")

    y -= 22
    c.setFillColor(ACCENT)
    c.rect(tx - 10, y - 6, W - 40 - tx + 20, 22, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(tx, y + 2, "TOTAL")
    c.drawRightString(vx, y + 2, f"{cur} {_money(total)}")

    # ── Payment ──────────────────────────────────────────────────
    y -= 55
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "PAYMENT INFORMATION")
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 15, spec["bank"])
    c.drawString(40, y - 27, f"Payment Terms: {spec['terms']}")
    if not spec.get("hide_po"):
        c.drawString(40, y - 39, f"Please quote PO {spec['po']} on remittance.")

    # ── Demo note — visible on the page, not hidden in a filename ─
    c.setFillColor(WARN)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(40, 66, "DEMO DOCUMENT — fictitious supplier and amounts, generated for the fixture SAP connector.")
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 7)
    c.drawString(40, 56, spec["note"])

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(40, 48, W - 40, 48)
    c.setFillColor(GRAY)
    c.drawCentredString(W / 2, 36, f"{spec['supplier']}  |  NTN {spec['ntn']}  |  {spec['address']}")
    c.drawCentredString(W / 2, 27, "Thank you for your business!")


def main(only=None):
    OUT_DIR.mkdir(exist_ok=True)
    made = []
    for spec in INVOICES:
        if only and spec["po"] not in only:
            continue
        # file_suffix keeps a deliberate re-send from overwriting the original.
        path = OUT_DIR / f"invoice_{spec['po']}_{spec['invoice_no']}{spec.get('file_suffix', '')}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        draw(c, spec)
        c.save()
        made.append((path, spec["note"]))

    if not made:
        print(f"No PO matched {only}. Known: {[s['po'] for s in INVOICES]}")
        return 1
    print(f"Wrote {len(made)} invoice(s) to {OUT_DIR}:")
    for path, note in made:
        print(f"  {path.name}\n      {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
