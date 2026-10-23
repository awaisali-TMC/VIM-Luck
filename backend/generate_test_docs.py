"""
Generate realistic Pakistani invoice/PO document images and PDFs for test data.
Produces files in backend/uploads/test/ that match the seeded DB records.

Run:  py -3 generate_test_docs.py
"""

import os
import random
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import Table, TableStyle

OUT = os.path.join(os.path.dirname(__file__), "uploads", "test")
os.makedirs(OUT, exist_ok=True)

W_A4, H_A4 = A4  # 595.27, 841.89 points


# ────────────────────────────────────────────────────────
# Helper: format PKR
# ────────────────────────────────────────────────────────
def fmt(n):
    if n is None:
        return ""
    sign = "-" if n < 0 else ""
    n = abs(n)
    return f"{sign}{n:,.2f}"


# ────────────────────────────────────────────────────────
# PDF Invoice Generator
# ────────────────────────────────────────────────────────
def make_pdf_invoice(filename, inv):
    """Generate a professional-looking PDF invoice."""
    path = os.path.join(OUT, filename)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    brand = HexColor("#1a56db")
    dark = HexColor("#111827")
    gray = HexColor("#6b7280")
    light_bg = HexColor("#f9fafb")
    line_color = HexColor("#e5e7eb")

    # ── Header band ──
    c.setFillColor(brand)
    c.rect(0, h - 80, w, 80, fill=True, stroke=False)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30, h - 35, inv.get("company", "SUPPLIER COMPANY"))
    c.setFont("Helvetica", 9)
    c.drawString(30, h - 52, inv.get("company_address", ""))

    # Invoice label
    doc_type = inv.get("document_type", "INVOICE").upper()
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(w - 30, h - 38, doc_type)

    c.setFont("Helvetica", 9)
    c.drawRightString(w - 30, h - 55, f"NTN: {inv.get('ntn', 'N/A')}")

    # ── Invoice details box ──
    y = h - 100
    c.setFillColor(light_bg)
    c.rect(30, y - 60, w - 60, 58, fill=True, stroke=False)
    c.setStrokeColor(line_color)
    c.rect(30, y - 60, w - 60, 58, fill=False, stroke=True)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(dark)
    pairs = [
        ("Invoice #:", inv.get("invoice_number", "")),
        ("Date:", inv.get("invoice_date", "")),
        ("Due Date:", inv.get("due_date", "")),
        ("PO Ref:", inv.get("po_reference", "N/A")),
        ("Currency:", inv.get("currency", "PKR")),
    ]
    col_w = (w - 80) / len(pairs)
    for i, (lbl, val) in enumerate(pairs):
        x = 40 + i * col_w
        c.setFont("Helvetica", 7)
        c.setFillColor(gray)
        c.drawString(x, y - 20, lbl)
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(dark)
        c.drawString(x, y - 34, str(val))

    # ── Bill To ──
    y -= 85
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(brand)
    c.drawString(30, y, "BILL TO")
    c.setFont("Helvetica", 9)
    c.setFillColor(dark)
    c.drawString(30, y - 14, inv.get("receiver_name", "TMC Energy Pvt Ltd"))
    c.setFillColor(gray)
    c.setFont("Helvetica", 8)
    c.drawString(30, y - 27, inv.get("receiver_address", "Blue Area, Jinnah Avenue, Islamabad"))

    # ── Line items table ──
    y -= 55
    items = inv.get("line_items", [])
    table_data = [["#", "Description", "Qty", "Unit", "Rate", "Amount"]]
    for idx, li in enumerate(items, 1):
        table_data.append([
            str(idx),
            li.get("description", ""),
            str(li.get("quantity", "")),
            li.get("unit", ""),
            fmt(li.get("unit_price")),
            fmt(li.get("amount")),
        ])

    col_widths = [25, 220, 45, 45, 80, 80]
    tbl = Table(table_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, light_bg]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, brand),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, line_color),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    tw, th = tbl.wrap(0, 0)
    tbl.drawOn(c, 30, y - th)

    # ── Totals ──
    y = y - th - 20
    totals_x = w - 200
    c.setStrokeColor(line_color)
    c.line(totals_x, y + 5, w - 30, y + 5)

    def draw_total_row(label, value, bold=False, color=dark):
        nonlocal y
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, 9 if not bold else 10)
        c.setFillColor(gray if not bold else color)
        c.drawString(totals_x, y - 5, label)
        c.setFillColor(color)
        c.drawRightString(w - 30, y - 5, fmt(value))
        y -= 18

    draw_total_row("Subtotal:", inv.get("subtotal_amount", 0))
    if inv.get("gst_amount"):
        draw_total_row("GST (17%):", inv.get("gst_amount", 0))
    if inv.get("wht_amount"):
        draw_total_row("WHT:", inv.get("wht_amount", 0))
    if inv.get("tax_amount") and not inv.get("gst_amount"):
        draw_total_row("Tax:", inv.get("tax_amount", 0))

    y -= 3
    c.setStrokeColor(brand)
    c.setLineWidth(1.5)
    c.line(totals_x, y + 5, w - 30, y + 5)
    draw_total_row("TOTAL DUE:", inv.get("total_amount", 0), bold=True, color=brand)

    # ── Multi-currency note ──
    if inv.get("base_currency") and inv.get("currency") != inv.get("base_currency"):
        y -= 8
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(gray)
        rate = inv.get("exchange_rate", 0)
        base_total = inv.get("base_total_amount", 0)
        base_cur = inv.get("base_currency", "PKR")
        c.drawString(totals_x, y, f"Exchange Rate: 1 {inv['currency']} = {rate} {base_cur}")
        y -= 12
        c.drawString(totals_x, y, f"Equivalent: {base_cur} {fmt(base_total)}")

    # ── Footer ──
    c.setFont("Helvetica", 7)
    c.setFillColor(gray)
    c.drawString(30, 40, f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}")
    c.drawCentredString(w / 2, 40, "Thank you for your business!")
    c.drawRightString(w - 30, 40, "Page 1 of 1")

    # Bottom brand line
    c.setFillColor(brand)
    c.rect(0, 0, w, 8, fill=True, stroke=False)

    c.save()
    print(f"  [PDF] {filename} ({os.path.getsize(path):,} bytes)")
    return path


# ────────────────────────────────────────────────────────
# Image Invoice Generator (for JPG/PNG scanned look)
# ────────────────────────────────────────────────────────
def make_image_invoice(filename, inv, fmt_type="JPEG"):
    """Generate a scanned-look invoice image."""
    path = os.path.join(OUT, filename)
    img_w, img_h = 1240, 1754  # ~A4 at 150dpi

    # Slightly off-white for scanned look
    bg_color = (252, 251, 249) if fmt_type == "JPEG" else (255, 255, 255)
    img = Image.new("RGB", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Use default font (no external font files needed)
    try:
        font_big = ImageFont.truetype("arial.ttf", 36)
        font_med = ImageFont.truetype("arialbd.ttf", 22)
        font_sm = ImageFont.truetype("arial.ttf", 18)
        font_xs = ImageFont.truetype("arial.ttf", 14)
        font_bold = ImageFont.truetype("arialbd.ttf", 18)
    except:
        font_big = ImageFont.load_default()
        font_med = font_big
        font_sm = font_big
        font_xs = font_big
        font_bold = font_big

    brand_color = (26, 86, 219)
    dark_color = (17, 24, 39)
    gray_color = (107, 114, 128)
    line_color = (229, 231, 235)

    # Header band
    draw.rectangle([0, 0, img_w, 110], fill=brand_color)
    draw.text((40, 20), inv.get("company", "SUPPLIER"), fill=(255, 255, 255), font=font_big)
    draw.text((40, 68), inv.get("company_address", ""), fill=(200, 210, 240), font=font_xs)

    doc_label = inv.get("document_type", "INVOICE").upper()
    # right-align the doc type
    draw.text((img_w - 300, 25), doc_label, fill=(255, 255, 255), font=font_big)
    draw.text((img_w - 300, 75), f"NTN: {inv.get('ntn', 'N/A')}", fill=(200, 210, 240), font=font_xs)

    # Invoice details
    y = 135
    details = [
        f"Invoice #: {inv.get('invoice_number', '')}",
        f"Date: {inv.get('invoice_date', '')}",
        f"Due: {inv.get('due_date', 'N/A')}",
        f"PO: {inv.get('po_reference', 'N/A')}",
        f"Currency: {inv.get('currency', 'PKR')}",
    ]
    draw.rectangle([30, y, img_w - 30, y + 50], fill=(249, 250, 251), outline=line_color)
    x_pos = 45
    for detail in details:
        draw.text((x_pos, y + 15), detail, fill=dark_color, font=font_xs)
        x_pos += 230

    # Bill To
    y += 75
    draw.text((40, y), "BILL TO:", fill=brand_color, font=font_bold)
    draw.text((40, y + 25), inv.get("receiver_name", "TMC Energy Pvt Ltd"), fill=dark_color, font=font_sm)
    draw.text((40, y + 50), inv.get("receiver_address", "Blue Area, Islamabad"), fill=gray_color, font=font_xs)

    # Table header
    y += 90
    draw.rectangle([30, y, img_w - 30, y + 35], fill=brand_color)
    headers = ["#", "Description", "Qty", "Unit", "Rate", "Amount"]
    col_x = [40, 80, 540, 640, 740, 930]
    for i, hdr in enumerate(headers):
        draw.text((col_x[i], y + 7), hdr, fill=(255, 255, 255), font=font_bold if i == 0 else font_xs)

    # Table rows
    y += 35
    items = inv.get("line_items", [])
    for idx, li in enumerate(items, 1):
        row_bg = (249, 250, 251) if idx % 2 == 0 else bg_color
        draw.rectangle([30, y, img_w - 30, y + 32], fill=row_bg)
        draw.text((45, y + 7), str(idx), fill=dark_color, font=font_xs)
        desc = li.get("description", "")[:45]
        draw.text((80, y + 7), desc, fill=dark_color, font=font_xs)
        draw.text((545, y + 7), str(li.get("quantity", "")), fill=dark_color, font=font_xs)
        draw.text((640, y + 7), li.get("unit", ""), fill=gray_color, font=font_xs)
        rate_str = f"{li.get('unit_price', 0):,.2f}"
        draw.text((730, y + 7), rate_str, fill=dark_color, font=font_xs)
        amt_str = f"{li.get('amount', 0):,.2f}"
        draw.text((920, y + 7), amt_str, fill=dark_color, font=font_xs)
        y += 32

    # Totals
    y += 15
    draw.line([700, y, img_w - 30, y], fill=line_color, width=1)
    y += 10

    def draw_row(label, val, bold_row=False):
        nonlocal y
        fnt = font_bold if bold_row else font_sm
        clr = brand_color if bold_row else dark_color
        draw.text((700, y), label, fill=gray_color if not bold_row else clr, font=fnt)
        val_str = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
        draw.text((920, y), val_str, fill=clr, font=fnt)
        y += 28

    draw_row("Subtotal:", inv.get("subtotal_amount", 0))
    if inv.get("gst_amount"):
        draw_row("GST:", inv.get("gst_amount", 0))
    if inv.get("wht_amount"):
        draw_row("WHT:", inv.get("wht_amount", 0))
    if inv.get("tax_amount") and not inv.get("gst_amount"):
        draw_row("Tax:", inv.get("tax_amount", 0))

    draw.line([700, y, img_w - 30, y], fill=brand_color, width=2)
    y += 5
    draw_row("TOTAL:", inv.get("total_amount", 0), bold_row=True)

    # Add some scan artifacts for realism on JPEG
    if fmt_type == "JPEG":
        # Slight rotation
        angle = random.uniform(-0.3, 0.3)
        img = img.rotate(angle, expand=False, fillcolor=bg_color)
        # slight noise
        import numpy as np
        arr = np.array(img)
        noise = np.random.normal(0, 2, arr.shape).astype(np.int16)
        arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)

    # Footer
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, img_h - 25, img_w, img_h], fill=brand_color)
    draw.text((40, img_h - 50), "Thank you for your business!", fill=gray_color, font=font_xs)

    if fmt_type == "JPEG":
        img.save(path, "JPEG", quality=82)
    else:
        img.save(path, "PNG")

    print(f"  [{fmt_type}] {filename} ({os.path.getsize(path):,} bytes)")
    return path


# ────────────────────────────────────────────────────────
# PO PDF Generator
# ────────────────────────────────────────────────────────
def make_po_pdf(filename, po):
    """Generate a Purchase Order PDF."""
    path = os.path.join(OUT, filename)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    brand = HexColor("#059669")  # Green for POs
    dark = HexColor("#111827")
    gray = HexColor("#6b7280")
    light_bg = HexColor("#f0fdf4")
    line_color = HexColor("#d1d5db")

    # Header
    c.setFillColor(brand)
    c.rect(0, h - 80, w, 80, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(30, h - 35, "PURCHASE ORDER")
    c.setFont("Helvetica", 10)
    c.drawString(30, h - 52, "TMC Energy Pvt Ltd")

    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - 30, h - 35, po.get("po_number", ""))
    c.setFont("Helvetica", 9)
    c.drawRightString(w - 30, h - 52, f"Date: {po.get('po_date', '')}")

    # Vendor info
    y = h - 105
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(brand)
    c.drawString(30, y, "VENDOR")
    c.setFont("Helvetica", 9)
    c.setFillColor(dark)
    c.drawString(30, y - 15, po.get("vendor_name", ""))
    c.setFillColor(gray)
    c.setFont("Helvetica", 8)
    if po.get("vendor_ntn"):
        c.drawString(30, y - 28, f"NTN: {po['vendor_ntn']}")

    # PO details
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(brand)
    c.drawString(350, y, "PO DETAILS")
    c.setFont("Helvetica", 8)
    c.setFillColor(dark)
    c.drawString(350, y - 15, f"Type: {po.get('po_type', 'local').title()}")
    c.drawString(350, y - 28, f"Currency: {po.get('currency', 'PKR')}")
    c.drawString(350, y - 41, f"Status: {po.get('status', 'open').title()}")

    # Notes
    if po.get("notes"):
        y -= 60
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(gray)
        c.drawString(30, y, f"Notes: {po['notes'][:90]}")

    # Line items
    y -= 30
    items = po.get("line_items", [])
    table_data = [["#", "Description", "Qty", "Unit", "Unit Price", "Amount"]]
    for li in items:
        table_data.append([
            str(li["item_number"]),
            li["description"],
            str(li["quantity"]),
            li.get("unit", ""),
            fmt(li["unit_price"]),
            fmt(li["amount"]),
        ])

    col_widths = [25, 230, 50, 45, 80, 80]
    tbl = Table(table_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, light_bg]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, line_color),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    tw, th = tbl.wrap(0, 0)
    tbl.drawOn(c, 30, y - th)

    # Total
    y = y - th - 15
    c.setStrokeColor(brand)
    c.setLineWidth(1.5)
    c.line(380, y + 3, w - 30, y + 3)
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(brand)
    c.drawString(380, y - 12, "TOTAL:")
    c.drawRightString(w - 30, y - 12, f"{po.get('currency', 'PKR')} {fmt(po.get('total_amount', 0))}")

    # Authorization
    y -= 60
    c.setFont("Helvetica", 8)
    c.setFillColor(dark)
    c.drawString(30, y, "Authorized By: ___________________________")
    c.drawString(320, y, "Approved By: ___________________________")
    c.setFillColor(gray)
    c.drawString(30, y - 14, "Procurement Department")
    c.drawString(320, y - 14, "Finance Department")

    # Footer
    c.setFillColor(brand)
    c.rect(0, 0, w, 8, fill=True, stroke=False)
    c.setFont("Helvetica", 7)
    c.setFillColor(gray)
    c.drawCentredString(w / 2, 20, "TMC Energy Pvt Ltd | Blue Area, Jinnah Avenue, Islamabad | NTN: 0001122-3")

    c.save()
    print(f"  [PO-PDF] {filename} ({os.path.getsize(path):,} bytes)")


# ────────────────────────────────────────────────────────
# Data definitions (matching seed_test_data.py)
# ────────────────────────────────────────────────────────

INVOICES = [
    {
        "filename": "inv1.pdf", "type": "pdf",
        "company": "Haier Pakistan (Pvt) Ltd",
        "company_address": "Plot 28, Sector 19, Korangi Industrial Area, Karachi",
        "ntn": "0912345-6",
        "invoice_number": "HAI-2026-0042",
        "invoice_date": "15 Feb 2026", "due_date": "15 Mar 2026",
        "currency": "PKR", "po_reference": "PO-2026-0001",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 950000, "gst_amount": 161500, "tax_amount": 161500, "total_amount": 1111500,
        "line_items": [
            {"description": "HP ProBook 450 G10 Laptop", "quantity": 10, "unit": "Each", "unit_price": 95000, "amount": 950000},
        ],
    },
    {
        "filename": "inv2.jpg", "type": "JPEG",
        "company": "Office Solutions Karachi",
        "company_address": "Office No 12, Business Center, Shahrah-e-Faisal, Karachi",
        "ntn": "1234567-8",
        "invoice_number": "OS-2026-0188",
        "invoice_date": "20 Feb 2026", "due_date": "20 Mar 2026",
        "currency": "PKR", "po_reference": "PO-2026-0002",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 155000, "gst_amount": 26350, "tax_amount": 26350, "total_amount": 181350,
        "line_items": [
            {"description": "A4 Printing Paper (500 sheets)", "quantity": 80, "unit": "Ream", "unit_price": 850, "amount": 68000},
            {"description": "HP 26A Toner Cartridge", "quantity": 15, "unit": "Each", "unit_price": 3500, "amount": 52500},
            {"description": "Whiteboard Markers Box (12pc)", "quantity": 15, "unit": "Box", "unit_price": 600, "amount": 9000},
            {"description": "File Folders (Pack 50)", "quantity": 10, "unit": "Pack", "unit_price": 2550, "amount": 25500},
        ],
    },
    {
        "filename": "inv3.pdf", "type": "pdf",
        "company": "CleanPro Services",
        "company_address": "House 45, Street 12, G-10/2, Islamabad",
        "ntn": "9876543-2",
        "invoice_number": "CP-2026-012",
        "invoice_date": "31 Jan 2026", "due_date": "28 Feb 2026",
        "currency": "PKR", "po_reference": "PO-2026-0003",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 30000, "gst_amount": 5100, "tax_amount": 5100, "total_amount": 35100,
        "line_items": [
            {"description": "Daily Cleaning - Ground & 1st Floor (Jan)", "quantity": 1, "unit": "Month", "unit_price": 20000, "amount": 20000},
            {"description": "Deep Cleaning (Jan)", "quantity": 1, "unit": "Month", "unit_price": 10000, "amount": 10000},
        ],
    },
    {
        "filename": "inv4.pdf", "type": "pdf",
        "company": "Bestway Cement Ltd",
        "company_address": "63-Mozang Road, Lahore",
        "ntn": "0456789-1",
        "invoice_number": "BWC-2026-7891",
        "invoice_date": "25 Feb 2026", "due_date": "25 Mar 2026",
        "currency": "PKR", "po_reference": "PO-2026-0005",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 1900000, "gst_amount": 323000, "tax_amount": 323000, "total_amount": 2223000,
        "line_items": [
            {"description": "OPC Cement 50kg bags (Batch 1)", "quantity": 2000, "unit": "Bag", "unit_price": 950, "amount": 1900000},
        ],
    },
    {
        "filename": "inv5.pdf", "type": "pdf",
        "company": "IESCO",
        "company_address": "IESCO HQ, Street 40, G-7/4, Islamabad",
        "ntn": "0567890-3",
        "invoice_number": "IESCO-02-2026-38192",
        "invoice_date": "01 Feb 2026", "due_date": "15 Feb 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Utility Bill",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 142800, "gst_amount": 24276, "tax_amount": 24276, "total_amount": 167076,
        "line_items": [
            {"description": "Electricity Charges - Feb 2026 (HT Commercial)", "quantity": 1, "unit": "Bill", "unit_price": 128000, "amount": 128000},
            {"description": "Fuel Price Adjustment Surcharge", "quantity": 1, "unit": "Bill", "unit_price": 14800, "amount": 14800},
        ],
    },
    {
        "filename": "inv6.pdf", "type": "pdf",
        "company": "PTCL",
        "company_address": "PTCL HQ, G-8/4, Islamabad",
        "ntn": "0112233-4",
        "invoice_number": "PTCL-ISB-2026-0456",
        "invoice_date": "15 Jan 2026", "due_date": "14 Feb 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Utility Bill",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 45000, "gst_amount": 7650, "wht_amount": 1125, "tax_amount": 8775, "total_amount": 53775,
        "line_items": [
            {"description": "Internet - 100 Mbps Business (Jan)", "quantity": 1, "unit": "Month", "unit_price": 25000, "amount": 25000},
            {"description": "IPTV Corporate Package", "quantity": 1, "unit": "Month", "unit_price": 8000, "amount": 8000},
            {"description": "Voice - 10 PSTN Lines", "quantity": 1, "unit": "Month", "unit_price": 12000, "amount": 12000},
        ],
    },
    {
        "filename": "inv7.png", "type": "PNG",
        "company": "Quick Print Lahore",
        "company_address": "23-A, Main Boulevard, Gulberg III, Lahore",
        "ntn": "7654321-0",
        "invoice_number": "QP-5523",
        "invoice_date": "01 Mar 2026", "due_date": "31 Mar 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 72000, "gst_amount": 12240, "tax_amount": 12240, "total_amount": 84240,
        "line_items": [
            {"description": "Brochure Printing (A4 glossy)", "quantity": 500, "unit": "Pc", "unit_price": 90, "amount": 45000},
            {"description": "Business Cards (350gsm)", "quantity": 2000, "unit": "Pc", "unit_price": 6, "amount": 12000},
            {"description": "Binding & Lamination", "quantity": 1, "unit": "Lot", "unit_price": 15000, "amount": 15000},
        ],
    },
    {
        "filename": "inv8.pdf", "type": "pdf",
        "company": "Al-Falah Consulting",
        "company_address": "Office 901, The Centaurus, Islamabad",
        "ntn": "3456789-5",
        "invoice_number": "AFC-2026-0091",
        "invoice_date": "28 Feb 2026", "due_date": "28 Mar 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 500000, "gst_amount": 85000, "tax_amount": 85000, "total_amount": 585000,
        "line_items": [
            {"description": "Strategic Advisory - Phase 2 (Feb)", "quantity": 1, "unit": "Lumpsum", "unit_price": 350000, "amount": 350000},
            {"description": "Market Research Report", "quantity": 1, "unit": "Report", "unit_price": 150000, "amount": 150000},
        ],
    },
    {
        "filename": "inv9.pdf", "type": "pdf",
        "company": "Dell Technologies Inc.",
        "company_address": "One Dell Way, Round Rock, TX 78682, USA",
        "ntn": "N/A (Foreign)",
        "invoice_number": "DELL-US-2026-88412",
        "invoice_date": "12 Feb 2026", "due_date": "12 Mar 2026",
        "currency": "USD", "po_reference": "PO-2026-0004",
        "document_type": "Import Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 45000, "tax_amount": 0, "total_amount": 45000,
        "base_currency": "PKR", "exchange_rate": 278.50, "base_total_amount": 12532500,
        "line_items": [
            {"description": "Dell PowerEdge R760 Server", "quantity": 2, "unit": "Each", "unit_price": 18500, "amount": 37000},
            {"description": "Dell 960GB SSD SAS 12Gbps (Server Pack)", "quantity": 2, "unit": "Pack", "unit_price": 4000, "amount": 8000},
        ],
    },
    {
        "filename": "inv10.pdf", "type": "pdf",
        "company": "PTCL",
        "company_address": "PTCL HQ, G-8/4, Islamabad",
        "ntn": "0112233-4",
        "invoice_number": "PTCL-CN-2026-0012",
        "invoice_date": "20 Feb 2026", "due_date": "",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Credit Note",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": -5000, "gst_amount": -850, "wht_amount": -125, "tax_amount": -975, "total_amount": -5975,
        "line_items": [
            {"description": "Credit - Internet overbilling Jan 2026", "quantity": 1, "unit": "Adj", "unit_price": -5000, "amount": -5000},
        ],
    },
    {
        "filename": "inv11.pdf", "type": "pdf",
        "company": "Pakistan State Oil (PSO)",
        "company_address": "PSO House, Khayaban-e-Iqbal, Clifton, Karachi",
        "ntn": "0998877-6",
        "invoice_number": "PSO-ISB-2026-22341",
        "invoice_date": "28 Feb 2026", "due_date": "15 Mar 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Invoice",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 210000, "gst_amount": 35700, "wht_amount": 2100, "tax_amount": 37800, "total_amount": 247800,
        "line_items": [
            {"description": "Hi-Octane (RON 97) - 1500 Liters", "quantity": 1500, "unit": "Ltr", "unit_price": 95, "amount": 142500},
            {"description": "Diesel (HSD) - 750 Liters", "quantity": 750, "unit": "Ltr", "unit_price": 90, "amount": 67500},
        ],
    },
    {
        "filename": "inv12.pdf", "type": "pdf",
        "company": "Jazz Business (PMCL)",
        "company_address": "Jazz HQ, Jinnah Avenue, Blue Area, Islamabad",
        "ntn": "0223344-7",
        "invoice_number": "JAZZ-B2B-2026-MAR-0089",
        "invoice_date": "01 Mar 2026", "due_date": "31 Mar 2026",
        "currency": "PKR", "po_reference": "N/A",
        "document_type": "Utility Bill",
        "receiver_name": "TMC Energy Pvt Ltd",
        "receiver_address": "Blue Area, Jinnah Avenue, Islamabad",
        "subtotal_amount": 28500, "gst_amount": 4845, "wht_amount": 712.5, "tax_amount": 5557.5, "total_amount": 34057.5,
        "line_items": [
            {"description": "Jazz Business 20-SIM Fleet (Mar)", "quantity": 20, "unit": "SIM", "unit_price": 1200, "amount": 24000},
            {"description": "Data Add-on 50GB (10 SIMs)", "quantity": 10, "unit": "Each", "unit_price": 450, "amount": 4500},
        ],
    },
]

PURCHASE_ORDERS = [
    {
        "filename": "po1.pdf",
        "po_number": "PO-2026-0001",
        "vendor_name": "Haier Pakistan (Pvt) Ltd", "vendor_ntn": "0912345-6",
        "po_date": "15 Jan 2026", "po_type": "local", "currency": "PKR", "status": "open",
        "total_amount": 1250000,
        "notes": "IT hardware procurement - laptops and monitors for new hires Q1",
        "line_items": [
            {"item_number": 1, "description": "HP ProBook 450 G10 Laptop", "quantity": 10, "unit": "Each", "unit_price": 95000, "amount": 950000},
            {"item_number": 2, "description": "Dell 27\" UltraSharp Monitor U2723QE", "quantity": 10, "unit": "Each", "unit_price": 28000, "amount": 280000},
            {"item_number": 3, "description": "Laptop Bag + Accessories Kit", "quantity": 10, "unit": "Each", "unit_price": 2000, "amount": 20000},
        ],
    },
    {
        "filename": "po2.pdf",
        "po_number": "PO-2026-0002",
        "vendor_name": "Office Solutions Karachi", "vendor_ntn": "1234567-8",
        "po_date": "20 Jan 2026", "po_type": "local", "currency": "PKR", "status": "open",
        "total_amount": 185400,
        "notes": "Monthly office supplies - Jan 2026",
        "line_items": [
            {"item_number": 1, "description": "A4 Printing Paper (500 sheets)", "quantity": 100, "unit": "Ream", "unit_price": 850, "amount": 85000},
            {"item_number": 2, "description": "HP 26A Toner Cartridge", "quantity": 20, "unit": "Each", "unit_price": 3500, "amount": 70000},
            {"item_number": 3, "description": "Whiteboard Marker (Assorted Box 12)", "quantity": 15, "unit": "Box", "unit_price": 600, "amount": 9000},
            {"item_number": 4, "description": "File Folders (Pack of 50)", "quantity": 10, "unit": "Pack", "unit_price": 2140, "amount": 21400},
        ],
    },
    {
        "filename": "po3.pdf",
        "po_number": "PO-2026-0003",
        "vendor_name": "CleanPro Services", "vendor_ntn": "9876543-2",
        "po_date": "01 Feb 2026", "po_type": "contract", "currency": "PKR", "status": "open",
        "total_amount": 360000,
        "notes": "Annual janitorial services contract - Head Office Islamabad",
        "line_items": [
            {"item_number": 1, "description": "Daily Office Cleaning - Ground & 1st Floor", "quantity": 12, "unit": "Month", "unit_price": 20000, "amount": 240000},
            {"item_number": 2, "description": "Deep Cleaning (Monthly)", "quantity": 12, "unit": "Month", "unit_price": 10000, "amount": 120000},
        ],
    },
    {
        "filename": "po4.pdf",
        "po_number": "PO-2026-0004",
        "vendor_name": "Dell Technologies Inc.", "vendor_ntn": None,
        "po_date": "10 Feb 2026", "po_type": "foreign", "currency": "USD", "status": "open",
        "total_amount": 45000,
        "notes": "Dell PowerEdge R760 server cluster for data center expansion",
        "line_items": [
            {"item_number": 1, "description": "Dell PowerEdge R760 Server", "quantity": 2, "unit": "Each", "unit_price": 18500, "amount": 37000},
            {"item_number": 2, "description": "Dell 960GB SSD SAS 12Gbps (per server pack)", "quantity": 2, "unit": "Pack", "unit_price": 4000, "amount": 8000},
        ],
    },
    {
        "filename": "po5.pdf",
        "po_number": "PO-2026-0005",
        "vendor_name": "Bestway Cement Ltd", "vendor_ntn": "0456789-1",
        "po_date": "20 Feb 2026", "po_type": "local", "currency": "PKR", "status": "partially_received",
        "total_amount": 2780000,
        "notes": "Cement and steel for Lahore office extension project",
        "line_items": [
            {"item_number": 1, "description": "OPC Cement 50kg bags", "quantity": 2000, "unit": "Bag", "unit_price": 950, "amount": 1900000},
            {"item_number": 2, "description": "Steel Rebar Grade 60 (12mm)", "quantity": 20, "unit": "Ton", "unit_price": 44000, "amount": 880000},
        ],
    },
]


# ────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating test documents...\n")

    print("--- INVOICES ---")
    for inv in INVOICES:
        fn = inv["filename"]
        t = inv.get("type", "pdf")
        if t == "pdf":
            make_pdf_invoice(fn, inv)
        else:
            make_image_invoice(fn, inv, fmt_type=t)

    print("\n--- PURCHASE ORDERS ---")
    for po in PURCHASE_ORDERS:
        make_po_pdf(po["filename"], po)

    total = len(INVOICES) + len(PURCHASE_ORDERS)
    print(f"\nDone! {total} documents generated in: {OUT}")
