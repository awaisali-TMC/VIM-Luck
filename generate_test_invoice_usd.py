"""Generate a USD vendor invoice PDF matching PO 4500000001."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

OUTPUT = "test_invoice_4500000001.pdf"

BRAND = HexColor("#1a3a5c")
ACCENT = HexColor("#2563eb")
LIGHT_BG = HexColor("#f8fafc")
BORDER = HexColor("#cbd5e1")
BLACK = HexColor("#111827")
GRAY = HexColor("#64748b")
WHITE = HexColor("#ffffff")

w, h = A4


def draw(c):
    # Header band
    c.setFillColor(BRAND)
    c.rect(0, h - 90, w, 90, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, h - 50, "INVOICE")

    c.setFont("Helvetica", 9)
    c.drawString(40, h - 68, "Domestic US Supplier 1")
    c.drawString(40, h - 80, "456 Industrial Blvd, Houston, TX 77001, USA")

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(w - 40, h - 40, "Invoice No:  INV-2026-0100")
    c.setFont("Helvetica", 9)
    c.drawRightString(w - 40, h - 55, "Date:  2026-04-08")
    c.drawRightString(w - 40, h - 68, "Due Date:  2026-05-08")
    c.drawRightString(w - 40, h - 81, "PO Ref:  4500000001")

    y = h - 120

    # Bill To
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "BILL TO")
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 15, "TMC FAA 2023")
    c.drawString(40, y - 27, "Company Code: 1710")
    c.drawString(40, y - 39, "Houston, TX, USA")

    # Supplier details
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(340, y, "SUPPLIER DETAILS")
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(340, y - 15, "Domestic US Supplier 1")
    c.drawString(340, y - 27, "Vendor No: 0017300001")
    c.drawString(340, y - 39, "Currency: USD")

    y -= 70

    # Table header
    col_x = [40, 60, 260, 340, 400, 470]
    col_labels = ["#", "Description", "Qty", "Unit", "Unit Price", "Amount"]
    col_widths = [20, 200, 50, 50, 70, 70]

    c.setFillColor(ACCENT)
    c.rect(35, y - 5, w - 75, 20, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    for i, label in enumerate(col_labels):
        if i >= 2:
            c.drawRightString(col_x[i] + col_widths[i], y + 5, label)
        else:
            c.drawString(col_x[i], y + 5, label)

    y -= 25

    items = [
        {"no": "10", "desc": "Trad.Good 11, PD, Reg.Trading", "qty": "50", "unit": "ST", "price": "25.00", "amount": "1,250.00"},
    ]

    c.setFont("Helvetica", 9)
    for item in items:
        c.setFillColor(LIGHT_BG)
        c.rect(35, y - 5, w - 75, 20, fill=1, stroke=0)
        c.setFillColor(BLACK)
        c.drawString(col_x[0], y + 3, item["no"])
        c.drawString(col_x[1], y + 3, item["desc"])
        c.drawRightString(col_x[2] + col_widths[2], y + 3, item["qty"])
        c.drawRightString(col_x[3] + col_widths[3], y + 3, item["unit"])
        c.drawRightString(col_x[4] + col_widths[4], y + 3, item["price"])
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(col_x[5] + col_widths[5], y + 3, item["amount"])
        c.setFont("Helvetica", 9)
        y -= 22

    # Totals
    y -= 5
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(300, y + 10, w - 40, y + 10)

    totals_x = 400
    val_x = w - 40

    y -= 8
    c.setFont("Helvetica", 9)
    c.setFillColor(GRAY)
    c.drawString(totals_x, y, "Subtotal")
    c.setFillColor(BLACK)
    c.drawRightString(val_x, y, "USD 1,250.00")

    y -= 18
    c.setFillColor(GRAY)
    c.drawString(totals_x, y, "Tax (0%)")
    c.setFillColor(BLACK)
    c.drawRightString(val_x, y, "USD 0.00")

    y -= 22
    c.setFillColor(ACCENT)
    c.rect(totals_x - 10, y - 6, w - 40 - totals_x + 20, 22, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(totals_x, y + 2, "TOTAL")
    c.drawRightString(val_x, y + 2, "USD 1,250.00")

    # Payment Info
    y -= 55
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y, "PAYMENT INFORMATION")
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 15, "Bank: JPMorgan Chase")
    c.drawString(40, y - 27, "Account: 9876-5432-1098")
    c.drawString(40, y - 39, "Routing: 021000021")
    c.drawString(40, y - 51, "Payment Terms: Net 30")

    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(340, y, "NOTES")
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    c.drawString(340, y - 15, "Purchase Order: 4500000001")
    c.drawString(340, y - 27, "Material: TG11")
    c.drawString(340, y - 39, "Please reference PO on remittance.")

    # Footer
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(40, 50, w - 40, 50)
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 7)
    c.drawCentredString(w / 2, 38, "Domestic US Supplier 1  |  456 Industrial Blvd, Houston TX  |  ar@ussupplier1.com  |  +1-713-555-0100")
    c.drawCentredString(w / 2, 28, "Thank you for your business!")


def main():
    c = canvas.Canvas(OUTPUT, pagesize=A4)
    draw(c)
    c.save()
    print(f"Invoice saved to {OUTPUT}")


if __name__ == "__main__":
    main()
