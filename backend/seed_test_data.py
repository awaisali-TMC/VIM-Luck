"""
Seed script: Populate the database with realistic Pakistani test data.
  - 5 Purchase Orders (various types)
  - 12 Invoices (across all statuses, some linked to POs, one credit note, one foreign currency)

Run:  py -3 seed_test_data.py
"""

import asyncio
import sys
import os

# Make sure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, async_session, init_db
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.purchase_order import PurchaseOrder, POLineItem
from sqlalchemy import select, text


async def seed():
    await init_db()

    async with async_session() as session:
        # ── Check if we already have test data ──────────────────────
        result = await session.execute(select(PurchaseOrder).limit(1))
        if result.scalars().first():
            print("[!]  PO data already exists — skipping PO seed.")
        else:
            await seed_purchase_orders(session)

        result = await session.execute(select(Invoice).limit(1))
        existing = result.scalars().first()
        if existing and existing.id > 2:
            print("[!]  Invoice test data already exists — skipping invoice seed.")
        else:
            await seed_invoices(session)

        await session.commit()
        print("\n[OK]  Test data seeded successfully!")

        # Print summary
        inv_count = (await session.execute(text("SELECT COUNT(*) FROM invoices"))).scalar()
        po_count = (await session.execute(text("SELECT COUNT(*) FROM purchase_orders"))).scalar()
        print(f"   [INV] {inv_count} Invoices")
        print(f"   [PO] {po_count} Purchase Orders")


async def seed_purchase_orders(session):
    """Create 5 realistic POs from Pakistani suppliers."""

    pos = [
        # PO-1: IT Equipment (local)
        PurchaseOrder(
            po_number="PO-2026-0001",
            vendor_name="Haier Pakistan (Pvt) Ltd",
            vendor_ntn="0912345-6",
            po_date="2026-01-15",
            po_type="local",
            total_amount=1_250_000.00,
            currency="PKR",
            status="open",
            notes="IT hardware procurement — laptops and monitors for new hires Q1",
            source_type="manual",
        ),
        # PO-2: Office Supplies (local)
        PurchaseOrder(
            po_number="PO-2026-0002",
            vendor_name="Office Solutions Karachi",
            vendor_ntn="1234567-8",
            po_date="2026-01-20",
            po_type="local",
            total_amount=185_400.00,
            currency="PKR",
            status="open",
            notes="Monthly office supplies — Jan 2026",
            source_type="manual",
        ),
        # PO-3: Janitorial Services (contract)
        PurchaseOrder(
            po_number="PO-2026-0003",
            vendor_name="CleanPro Services",
            vendor_ntn="9876543-2",
            po_date="2026-02-01",
            po_type="contract",
            total_amount=360_000.00,
            currency="PKR",
            status="open",
            notes="Annual janitorial services contract — Head Office Islamabad",
            source_type="manual",
        ),
        # PO-4: Foreign - Server Equipment (import)
        PurchaseOrder(
            po_number="PO-2026-0004",
            vendor_name="Dell Technologies Inc.",
            vendor_ntn=None,
            po_date="2026-02-10",
            po_type="foreign",
            total_amount=45_000.00,
            currency="USD",
            status="open",
            notes="Dell PowerEdge R760 server cluster for data center expansion",
            source_type="manual",
        ),
        # PO-5: Construction Materials (local)
        PurchaseOrder(
            po_number="PO-2026-0005",
            vendor_name="Bestway Cement Ltd",
            vendor_ntn="0456789-1",
            po_date="2026-02-20",
            po_type="local",
            total_amount=2_780_000.00,
            currency="PKR",
            status="partially_received",
            notes="Cement and steel for Lahore office extension project",
            source_type="manual",
        ),
    ]

    session.add_all(pos)
    await session.flush()

    # ── PO Line Items ───────────────────────────────────────────

    # PO-1 lines
    po1_lines = [
        POLineItem(po_id=pos[0].id, item_number=1, description="HP ProBook 450 G10 Laptop", quantity=10, unit="Each", unit_price=95_000.00, amount=950_000.00),
        POLineItem(po_id=pos[0].id, item_number=2, description="Dell 27\" UltraSharp Monitor U2723QE", quantity=10, unit="Each", unit_price=28_000.00, amount=280_000.00),
        POLineItem(po_id=pos[0].id, item_number=3, description="Laptop Bag + Accessories Kit", quantity=10, unit="Each", unit_price=2_000.00, amount=20_000.00),
    ]

    # PO-2 lines
    po2_lines = [
        POLineItem(po_id=pos[1].id, item_number=1, description="A4 Printing Paper (500 sheets)", quantity=100, unit="Ream", unit_price=850.00, amount=85_000.00),
        POLineItem(po_id=pos[1].id, item_number=2, description="HP 26A Toner Cartridge", quantity=20, unit="Each", unit_price=3_500.00, amount=70_000.00),
        POLineItem(po_id=pos[1].id, item_number=3, description="Whiteboard Marker (Assorted Box 12)", quantity=15, unit="Box", unit_price=600.00, amount=9_000.00),
        POLineItem(po_id=pos[1].id, item_number=4, description="File Folders (Pack of 50)", quantity=10, unit="Pack", unit_price=2_140.00, amount=21_400.00),
    ]

    # PO-3 lines
    po3_lines = [
        POLineItem(po_id=pos[2].id, item_number=1, description="Daily Office Cleaning — Ground & 1st Floor", quantity=12, unit="Month", unit_price=20_000.00, amount=240_000.00),
        POLineItem(po_id=pos[2].id, item_number=2, description="Deep Cleaning (Monthly)", quantity=12, unit="Month", unit_price=10_000.00, amount=120_000.00),
    ]

    # PO-4 lines (USD)
    po4_lines = [
        POLineItem(po_id=pos[3].id, item_number=1, description="Dell PowerEdge R760 Server", quantity=2, unit="Each", unit_price=18_500.00, amount=37_000.00),
        POLineItem(po_id=pos[3].id, item_number=2, description="Dell 960GB SSD SAS 12Gbps (per server pack)", quantity=2, unit="Pack", unit_price=4_000.00, amount=8_000.00),
    ]

    # PO-5 lines
    po5_lines = [
        POLineItem(po_id=pos[4].id, item_number=1, description="OPC Cement 50kg bags", quantity=2000, unit="Bag", unit_price=950.00, amount=1_900_000.00),
        POLineItem(po_id=pos[4].id, item_number=2, description="Steel Rebar Grade 60 (12mm)", quantity=20, unit="Ton", unit_price=44_000.00, amount=880_000.00),
    ]

    session.add_all(po1_lines + po2_lines + po3_lines + po4_lines + po5_lines)
    await session.flush()
    print("   [PO] 5 Purchase Orders with line items created")


async def seed_invoices(session):
    """Create 12 realistic invoices across various statuses, suppliers, and types."""

    invoices = []

    # ─── Invoice 1: Draft — just uploaded, waiting for review ────────
    inv1 = Invoice(
        original_filename="INV-2026-HAI-001.pdf",
        stored_filepath="uploads/test/inv1.pdf",
        mime_type="application/pdf",
        file_size_bytes=245_000,
        page_count=1,
        invoice_number="HAI-2026-0042",
        invoice_date="2026-02-15",
        due_date="2026-03-15",
        currency="PKR",
        supplier_name="Haier Pakistan (Pvt) Ltd",
        supplier_address="Plot 28, Sector 19, Korangi Industrial Area, Karachi",
        supplier_ntn="0912345-6",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=950_000.00,
        tax_amount=161_500.00,
        gst_amount=161_500.00,
        total_amount=1_111_500.00,
        po_reference="PO-2026-0001",
        document_type="invoice",
        overall_confidence=92.5,
        field_confidences='{"supplier_name": 98, "invoice_number": 95, "total_amount": 88, "tax_amount": 85}',
        processing_time_ms=3200,
        status="draft",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="HAIER PAKISTAN (PRIVATE) LIMITED",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv1)

    # ─── Invoice 2: Pending Processing — AI extraction in progress ───
    inv2 = Invoice(
        original_filename="scan_20260220.jpg",
        stored_filepath="uploads/test/inv2.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1_820_000,
        page_count=1,
        invoice_number="OS-2026-0188",
        invoice_date="2026-02-20",
        due_date="2026-03-20",
        currency="PKR",
        supplier_name="Office Solutions Karachi",
        supplier_address="Office No 12, Business Center, Shahrah-e-Faisal, Karachi",
        supplier_ntn="1234567-8",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=155_000.00,
        tax_amount=26_350.00,
        gst_amount=26_350.00,
        total_amount=181_350.00,
        po_reference="PO-2026-0002",
        document_type="invoice",
        overall_confidence=76.3,
        field_confidences='{"supplier_name": 82, "invoice_number": 70, "total_amount": 90, "tax_amount": 63}',
        processing_time_ms=5400,
        status="pending_processing",
        source_type="upload",
        fbr_verification_status="not_verified",
    )
    invoices.append(inv2)

    # ─── Invoice 3: Validated — ready for approval ────────────────────
    inv3 = Invoice(
        original_filename="CleanPro_Jan2026.pdf",
        stored_filepath="uploads/test/inv3.pdf",
        mime_type="application/pdf",
        file_size_bytes=156_000,
        page_count=1,
        invoice_number="CP-2026-012",
        invoice_date="2026-01-31",
        due_date="2026-02-28",
        currency="PKR",
        supplier_name="CleanPro Services",
        supplier_address="House 45, Street 12, G-10/2, Islamabad",
        supplier_ntn="9876543-2",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=30_000.00,
        tax_amount=5_100.00,
        gst_amount=5_100.00,
        total_amount=35_100.00,
        po_reference="PO-2026-0003",
        document_type="invoice",
        overall_confidence=95.2,
        status="validated",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="CLEANPRO SERVICES",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv3)

    # ─── Invoice 4: Pending Approval — submitted for manager review ──
    inv4 = Invoice(
        original_filename="BestwayCement_Batch1.pdf",
        stored_filepath="uploads/test/inv4.pdf",
        mime_type="application/pdf",
        file_size_bytes=312_000,
        page_count=2,
        invoice_number="BWC-2026-7891",
        invoice_date="2026-02-25",
        due_date="2026-03-25",
        currency="PKR",
        supplier_name="Bestway Cement Ltd",
        supplier_address="63-Mozang Road, Lahore",
        supplier_ntn="0456789-1",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=1_900_000.00,
        tax_amount=323_000.00,
        gst_amount=323_000.00,
        total_amount=2_223_000.00,
        po_reference="PO-2026-0005",
        document_type="invoice",
        overall_confidence=88.7,
        status="pending_approval",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="BESTWAY CEMENT LIMITED",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv4)

    # ─── Invoice 5: Approved — waiting to post ───────────────────────
    inv5 = Invoice(
        original_filename="PakElec_Feb2026.pdf",
        stored_filepath="uploads/test/inv5.pdf",
        mime_type="application/pdf",
        file_size_bytes=89_000,
        page_count=1,
        invoice_number="IESCO-02-2026-38192",
        invoice_date="2026-02-01",
        due_date="2026-02-15",
        currency="PKR",
        supplier_name="Islamabad Electric Supply Co (IESCO)",
        supplier_address="IESCO HQ, Street 40, G-7/4, Islamabad",
        supplier_ntn="0567890-3",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=142_800.00,
        tax_amount=24_276.00,
        gst_amount=24_276.00,
        total_amount=167_076.00,
        document_type="utility",
        overall_confidence=91.0,
        status="approved",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="ISLAMABAD ELECTRIC SUPPLY COMPANY",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv5)

    # ─── Invoice 6: Posted — complete lifecycle ──────────────────────
    inv6 = Invoice(
        original_filename="PTCL_Jan2026.pdf",
        stored_filepath="uploads/test/inv6.pdf",
        mime_type="application/pdf",
        file_size_bytes=120_000,
        page_count=1,
        invoice_number="PTCL-ISB-2026-0456",
        invoice_date="2026-01-15",
        due_date="2026-02-14",
        currency="PKR",
        supplier_name="Pakistan Telecomm Company Ltd (PTCL)",
        supplier_address="PTCL HQ, G-8/4, Islamabad",
        supplier_ntn="0112233-4",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=45_000.00,
        tax_amount=8_775.00,
        gst_amount=7_650.00,
        wht_amount=1_125.00,
        total_amount=53_775.00,
        document_type="utility",
        overall_confidence=97.1,
        status="posted",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="PAKISTAN TELECOMMUNICATION COMPANY LIMITED",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv6)

    # ─── Invoice 7: Exception — flagged issue ────────────────────────
    inv7 = Invoice(
        original_filename="QuickPrint_scan.png",
        stored_filepath="uploads/test/inv7.png",
        mime_type="image/png",
        file_size_bytes=2_450_000,
        page_count=1,
        invoice_number="QP-5523",
        invoice_date="2026-03-01",
        due_date="2026-03-31",
        currency="PKR",
        supplier_name="Quick Print Lahore",
        supplier_address="23-A, Main Boulevard, Gulberg III, Lahore",
        supplier_ntn="7654321-0",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=72_000.00,
        tax_amount=12_240.00,
        gst_amount=12_240.00,
        total_amount=84_240.00,
        document_type="invoice",
        overall_confidence=52.1,
        field_confidences='{"supplier_name": 45, "invoice_number": 38, "total_amount": 72, "tax_amount": 53}',
        warnings='["Low confidence on supplier name", "Invoice number partially obscured", "Possible duplicate — similar total to QP-5519"]',
        processing_time_ms=8900,
        status="exception",
        source_type="upload",
        fbr_verification_status="failed",
    )
    invoices.append(inv7)

    # ─── Invoice 8: Rejected — manager sent back ────────────────────
    inv8 = Invoice(
        original_filename="AlFalah_consulting.pdf",
        stored_filepath="uploads/test/inv8.pdf",
        mime_type="application/pdf",
        file_size_bytes=198_000,
        page_count=1,
        invoice_number="AFC-2026-0091",
        invoice_date="2026-02-28",
        due_date="2026-03-28",
        currency="PKR",
        supplier_name="Al-Falah Consulting",
        supplier_address="Office 901, The Centaurus, Islamabad",
        supplier_ntn="3456789-5",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=500_000.00,
        tax_amount=85_000.00,
        gst_amount=85_000.00,
        total_amount=585_000.00,
        document_type="invoice",
        overall_confidence=89.4,
        status="rejected",
        source_type="upload",
        fbr_verification_status="verified",
        fbr_taxpayer_name="AL-FALAH CONSULTING (PVT) LTD",
        fbr_filing_status="non_filer",
        wht_compliance_status="non_compliant",
    )
    invoices.append(inv8)

    # ─── Invoice 9: Posted — Foreign currency (USD) ──────────────────
    inv9 = Invoice(
        original_filename="Dell_ServerInv.pdf",
        stored_filepath="uploads/test/inv9.pdf",
        mime_type="application/pdf",
        file_size_bytes=287_000,
        page_count=2,
        invoice_number="DELL-US-2026-88412",
        invoice_date="2026-02-12",
        due_date="2026-03-12",
        currency="USD",
        supplier_name="Dell Technologies Inc.",
        supplier_address="One Dell Way, Round Rock, TX 78682, USA",
        supplier_ntn=None,
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=45_000.00,
        tax_amount=0.00,
        total_amount=45_000.00,
        po_reference="PO-2026-0004",
        document_type="import_invoice",
        overall_confidence=94.8,
        status="posted",
        source_type="upload",
        base_currency="PKR",
        exchange_rate=278.50,
        base_total_amount=12_532_500.00,
    )
    invoices.append(inv9)

    # ─── Invoice 10: Credit Note — linked to Invoice 6 ───────────────
    inv10 = Invoice(
        original_filename="PTCL_creditnote.pdf",
        stored_filepath="uploads/test/inv10.pdf",
        mime_type="application/pdf",
        file_size_bytes=95_000,
        page_count=1,
        invoice_number="PTCL-CN-2026-0012",
        invoice_date="2026-02-20",
        currency="PKR",
        supplier_name="Pakistan Telecomm Company Ltd (PTCL)",
        supplier_address="PTCL HQ, G-8/4, Islamabad",
        supplier_ntn="0112233-4",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=-5_000.00,
        tax_amount=-975.00,
        gst_amount=-850.00,
        wht_amount=-125.00,
        total_amount=-5_975.00,
        document_type="credit_note",
        overall_confidence=93.6,
        status="validated",
        source_type="upload",
        credit_debit_reason="Overbilling adjustment for January 2026 — incorrect metered usage",
        original_invoice_number="PTCL-ISB-2026-0456",
        fbr_verification_status="verified",
        fbr_taxpayer_name="PAKISTAN TELECOMMUNICATION COMPANY LIMITED",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv10)

    # ─── Invoice 11: Validated — Fuel/Transport ───────────────────────
    inv11 = Invoice(
        original_filename="PSO_fuel_feb.pdf",
        stored_filepath="uploads/test/inv11.pdf",
        mime_type="application/pdf",
        file_size_bytes=134_000,
        page_count=1,
        invoice_number="PSO-ISB-2026-22341",
        invoice_date="2026-02-28",
        due_date="2026-03-15",
        currency="PKR",
        supplier_name="Pakistan State Oil (PSO)",
        supplier_address="PSO House, Khayaban-e-Iqbal, Clifton, Karachi",
        supplier_ntn="0998877-6",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=210_000.00,
        tax_amount=37_800.00,
        gst_amount=35_700.00,
        wht_amount=2_100.00,
        total_amount=247_800.00,
        document_type="invoice",
        overall_confidence=96.0,
        status="validated",
        source_type="email",
        source_email_from="billing@pso.com.pk",
        fbr_verification_status="verified",
        fbr_taxpayer_name="PAKISTAN STATE OIL COMPANY LIMITED",
        fbr_filing_status="filer",
        wht_compliance_status="compliant",
    )
    invoices.append(inv11)

    # ─── Invoice 12: Draft — recent upload ────────────────────────────
    inv12 = Invoice(
        original_filename="JazzBiz_March.pdf",
        stored_filepath="uploads/test/inv12.pdf",
        mime_type="application/pdf",
        file_size_bytes=167_000,
        page_count=1,
        invoice_number="JAZZ-B2B-2026-MAR-0089",
        invoice_date="2026-03-01",
        due_date="2026-03-31",
        currency="PKR",
        supplier_name="Jazz Business (PMCL)",
        supplier_address="Jazz HQ, Jinnah Avenue, Blue Area, Islamabad",
        supplier_ntn="0223344-7",
        receiver_name="TMC Energy Pvt Ltd",
        receiver_address="Blue Area, Jinnah Avenue, Islamabad",
        subtotal_amount=28_500.00,
        tax_amount=5_557.50,
        gst_amount=4_845.00,
        wht_amount=712.50,
        total_amount=34_057.50,
        document_type="utility",
        overall_confidence=90.2,
        status="draft",
        source_type="upload",
        fbr_verification_status="not_verified",
    )
    invoices.append(inv12)

    session.add_all(invoices)
    await session.flush()

    # ── Line Items for each invoice ──────────────────────────────────

    line_items = []

    # Invoice 1: Haier — IT equipment (matches PO-1)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[0].id, description="HP ProBook 450 G10 Laptop", quantity=10, unit="Each", unit_price=95_000.00, amount=950_000.00, description_confidence=96, quantity_confidence=98, unit_price_confidence=92, amount_confidence=94),
    ]

    # Invoice 2: Office Solutions (matches PO-2)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[1].id, description="A4 Printing Paper (500 sheets)", quantity=80, unit="Ream", unit_price=850.00, amount=68_000.00, description_confidence=75, quantity_confidence=68, amount_confidence=82),
        InvoiceLineItem(invoice_id=invoices[1].id, description="HP 26A Toner Cartridge", quantity=15, unit="Each", unit_price=3_500.00, amount=52_500.00, description_confidence=80, quantity_confidence=72, amount_confidence=85),
        InvoiceLineItem(invoice_id=invoices[1].id, description="Whiteboard Markers Box (12pc)", quantity=15, unit="Box", unit_price=600.00, amount=9_000.00, description_confidence=70, quantity_confidence=74, amount_confidence=78),
        InvoiceLineItem(invoice_id=invoices[1].id, description="File Folders (Pack 50)", quantity=10, unit="Pack", unit_price=2_550.00, amount=25_500.00, description_confidence=68, quantity_confidence=70, amount_confidence=75),
    ]

    # Invoice 3: CleanPro (matches PO-3)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[2].id, description="Daily Cleaning — Ground & 1st Floor (Jan)", quantity=1, unit="Month", unit_price=20_000.00, amount=20_000.00),
        InvoiceLineItem(invoice_id=invoices[2].id, description="Deep Cleaning (Jan)", quantity=1, unit="Month", unit_price=10_000.00, amount=10_000.00),
    ]

    # Invoice 4: Bestway Cement (matches PO-5)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[3].id, description="OPC Cement 50kg bags (Batch 1)", quantity=2000, unit="Bag", unit_price=950.00, amount=1_900_000.00),
    ]

    # Invoice 5: IESCO Electricity
    line_items += [
        InvoiceLineItem(invoice_id=invoices[4].id, description="Electricity Charges — Feb 2026 (HT Commercial)", quantity=1, unit="Bill", unit_price=128_000.00, amount=128_000.00),
        InvoiceLineItem(invoice_id=invoices[4].id, description="Fuel Price Adjustment Surcharge", quantity=1, unit="Bill", unit_price=14_800.00, amount=14_800.00),
    ]

    # Invoice 6: PTCL Telecom
    line_items += [
        InvoiceLineItem(invoice_id=invoices[5].id, description="Internet — 100 Mbps Business (Jan)", quantity=1, unit="Month", unit_price=25_000.00, amount=25_000.00),
        InvoiceLineItem(invoice_id=invoices[5].id, description="IPTV Corporate Package", quantity=1, unit="Month", unit_price=8_000.00, amount=8_000.00),
        InvoiceLineItem(invoice_id=invoices[5].id, description="Voice — 10 PSTN Lines", quantity=1, unit="Month", unit_price=12_000.00, amount=12_000.00),
    ]

    # Invoice 7: Quick Print (exception)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[6].id, description="Brochure Printing (A4 glossy)", quantity=500, unit="Pc", unit_price=90.00, amount=45_000.00, description_confidence=42, quantity_confidence=38, amount_confidence=55),
        InvoiceLineItem(invoice_id=invoices[6].id, description="Business Cards (350gsm)", quantity=2000, unit="Pc", unit_price=6.00, amount=12_000.00, description_confidence=50, quantity_confidence=35, amount_confidence=48),
        InvoiceLineItem(invoice_id=invoices[6].id, description="Binding & Lamination", quantity=1, unit="Lot", unit_price=15_000.00, amount=15_000.00, description_confidence=55, quantity_confidence=40, amount_confidence=62),
    ]

    # Invoice 8: Al-Falah Consulting (rejected)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[7].id, description="Strategic Advisory — Phase 2 (Feb)", quantity=1, unit="Lumpsum", unit_price=350_000.00, amount=350_000.00),
        InvoiceLineItem(invoice_id=invoices[7].id, description="Market Research Report", quantity=1, unit="Report", unit_price=150_000.00, amount=150_000.00),
    ]

    # Invoice 9: Dell (USD — posted)
    line_items += [
        InvoiceLineItem(invoice_id=invoices[8].id, description="Dell PowerEdge R760 Server", quantity=2, unit="Each", unit_price=18_500.00, amount=37_000.00),
        InvoiceLineItem(invoice_id=invoices[8].id, description="Dell 960GB SSD SAS 12Gbps (Server Pack)", quantity=2, unit="Pack", unit_price=4_000.00, amount=8_000.00),
    ]

    # Invoice 10: PTCL Credit Note
    line_items += [
        InvoiceLineItem(invoice_id=invoices[9].id, description="Credit — Internet overbilling Jan 2026", quantity=1, unit="Adj", unit_price=-5_000.00, amount=-5_000.00),
    ]

    # Invoice 11: PSO Fuel
    line_items += [
        InvoiceLineItem(invoice_id=invoices[10].id, description="Hi-Octane (RON 97) — 1500 Liters", quantity=1500, unit="Ltr", unit_price=95.00, amount=142_500.00),
        InvoiceLineItem(invoice_id=invoices[10].id, description="Diesel (HSD) — 750 Liters", quantity=750, unit="Ltr", unit_price=90.00, amount=67_500.00),
    ]

    # Invoice 12: Jazz Telecom
    line_items += [
        InvoiceLineItem(invoice_id=invoices[11].id, description="Jazz Business 20-SIM Fleet (Mar)", quantity=20, unit="SIM", unit_price=1_200.00, amount=24_000.00),
        InvoiceLineItem(invoice_id=invoices[11].id, description="Data Add-on 50GB (10 SIMs)", quantity=10, unit="Each", unit_price=450.00, amount=4_500.00),
    ]

    session.add_all(line_items)
    await session.flush()

    # Link credit note to original invoice
    invoices[9].linked_invoice_id = invoices[5].id
    await session.flush()

    print(f"   [INV] {len(invoices)} Invoices with {len(line_items)} line items created")


if __name__ == "__main__":
    asyncio.run(seed())
