"""Update invoice records with real file paths and sizes."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import async_session, init_db
from app.models.invoice import Invoice
from sqlalchemy import select

BASE = os.path.dirname(os.path.abspath(__file__))

FILE_MAP = {
    'INV-2026-HAI-001.pdf': ('inv1.pdf', 'application/pdf'),
    'scan_20260220.jpg': ('inv2.jpg', 'image/jpeg'),
    'CleanPro_Jan2026.pdf': ('inv3.pdf', 'application/pdf'),
    'BestwayCement_Batch1.pdf': ('inv4.pdf', 'application/pdf'),
    'PakElec_Feb2026.pdf': ('inv5.pdf', 'application/pdf'),
    'PTCL_Jan2026.pdf': ('inv6.pdf', 'application/pdf'),
    'QuickPrint_scan.png': ('inv7.png', 'image/png'),
    'AlFalah_consulting.pdf': ('inv8.pdf', 'application/pdf'),
    'Dell_ServerInv.pdf': ('inv9.pdf', 'application/pdf'),
    'PTCL_creditnote.pdf': ('inv10.pdf', 'application/pdf'),
    'PSO_fuel_feb.pdf': ('inv11.pdf', 'application/pdf'),
    'JazzBiz_March.pdf': ('inv12.pdf', 'application/pdf'),
}

async def update():
    await init_db()
    async with async_session() as session:
        result = await session.execute(select(Invoice))
        invoices = result.scalars().all()
        updated = 0
        for inv in invoices:
            if inv.original_filename in FILE_MAP:
                test_file, mime = FILE_MAP[inv.original_filename]
                rel_path = os.path.join('uploads', 'test', test_file)
                abs_path = os.path.join(BASE, rel_path)
                if os.path.exists(abs_path):
                    inv.stored_filepath = rel_path
                    inv.file_size_bytes = os.path.getsize(abs_path)
                    inv.mime_type = mime
                    updated += 1
                    print(f"  {inv.invoice_number:30s} -> {rel_path} ({inv.file_size_bytes:,} bytes)")
        await session.commit()
        print(f"\nUpdated {updated} invoice file paths")

asyncio.run(update())
