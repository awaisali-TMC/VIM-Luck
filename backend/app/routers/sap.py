"""
SAP integration endpoints — fetch POs from SAP, sync to local DB, post invoices.

  GET  /api/sap/test           — test SAP connectivity
  GET  /api/sap/pos            — fetch PO list from SAP (live)
  GET  /api/sap/pos/{po_number} — fetch single PO detail from SAP
  POST /api/sap/pos/{po_number}/sync — sync a SAP PO into local database
  POST /api/sap/pos/sync-all   — sync all SAP POs into local database
  POST /api/sap/invoices/{id}/post — post an invoice to SAP (MIRO)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import settings
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from app.models.purchase_order import PurchaseOrder, POLineItem
from app.models.internal_user import InternalUser
from app.security import get_current_internal_user, require_admin
from app.routers.role_permissions import role_labels, humanize_role
from app.services.invoice_line_rules import (
    find_zero_quantity_goods,
    route_invoice_lines,
    unrouted_lines_message,
    zero_quantity_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sap", tags=["sap"])

# Only these roles may park/post (or dry-run validate) an invoice to SAP.
SAP_PARK_ROLES = ("admin", "ap_operator")


def _ensure_dll():
    """Add DLL directory so sapnwrfc.dll is findable."""
    try:
        os.add_dll_directory(os.path.join(settings.SAP_NWRFC_SDK_PATH, "lib"))
    except (OSError, AttributeError):
        pass


def _sap_mode() -> str:
    """"live" or "fake" — which connector is actually answering.

    Reported on every SAP response that could be mistaken for evidence. A green
    run against the fixture connector proves the app's plumbing, not that SAP
    accepted anything, and nobody reading a screenshot should have to guess which
    they are looking at.
    """
    return "fake" if (settings.SAP_MODE == "fake" and settings.DEBUG) else "live"


def _sap_target() -> dict:
    """Mode plus the system that was actually contacted.

    In fake mode the SAP_* settings still hold the live landscape's address, and
    echoing it back would put a real SAP host on screen beside a green tick for a
    system nothing ever spoke to. Report the fixture connector instead.
    """
    if _sap_mode() == "fake":
        return {"mode": "fake", "host": "in-process fixtures", "client": "n/a"}
    return {"mode": "live", "host": settings.SAP_ASHOST, "client": settings.SAP_CLIENT}


@router.get("/test")
async def test_connection():
    """Test SAP RFC connectivity — returns system info on success."""
    _ensure_dll()
    try:
        from app.services.sap_connector import SAPConnector
        sap = SAPConnector()
        sap.connect()
        ping_ok = sap.ping()
        info = sap.get_system_info()
        sap.disconnect()
        return {
            "connected": True,
            "ping": ping_ok,
            "system_info": info,
            **_sap_target(),
            "sysid": settings.SAP_SYSID if _sap_mode() == "live" else "FAKE",
        }
    except Exception as e:
        logger.warning("SAP connection check failed: %s", e)
        return {
            "connected": False,
            "error": "SAP connection failed — see server logs for details.",
            **_sap_target(),
        }


class ExchangeRateRequest(BaseModel):
    from_currency: str          # e.g. "CAD"
    to_currency: str            # e.g. "USD"
    rate_type: str = "M"        # M = standard, EURX, etc.
    valid_from: str             # YYYY-MM-DD
    rate: float                 # e.g. 0.73
    rate_indirect: Optional[float] = None  # indirect quotation (1/rate)


@router.post("/exchange-rate")
async def create_exchange_rate(req: ExchangeRateRequest):
    """
    Maintain a currency exchange rate in SAP via BAPI_EXCHANGERATE_CREATEMULTIPLE.

    This is the correct standard BAPI in S/4HANA — it accepts a RATE_LIST table
    and supports UPSERT (create OR update). Equivalent to transaction OB08.
    """
    _ensure_dll()
    try:
        from app.services.sap_connector import SAPConnector
        sap = SAPConnector()
        sap.connect()

        # Format date to SAP format YYYYMMDD
        valid_from = req.valid_from.replace("-", "").replace("/", "").replace(".", "")

        # Build the rate row — fields match TCURR / OB08 columns
        rate_row = {
            "RATE_TYPE": req.rate_type.upper(),
            "FROM_CURR": req.from_currency.upper(),
            "TO_CURRNCY": req.to_currency.upper(),
            "VALID_FROM": valid_from,
            "EXCH_RATE": str(req.rate),
            "FROM_FACTOR": "1",
            "TO_FACTOR": "1",
        }
        if req.rate_indirect:
            rate_row["EXCH_RATE_V"] = str(req.rate_indirect)

        # BAPI_EXCHANGERATE_CREATEMULTIPLE: takes RATE_LIST as a TABLE, with UPSERT flag
        result = sap.call(
            "BAPI_EXCHANGERATE_CREATEMULTIPLE",
            UPSERT_ALLOWED="X",  # allow updating existing rates
            input_tables={
                "RATE_LIST": [rate_row],
            },
            tables=["RETURN"],
            table_fields={
                "RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE", "MESSAGE_V1", "MESSAGE_V2"],
            },
        )

        return_msgs = result.get("RETURN", [])
        errors = [m for m in return_msgs if m.get("TYPE", "").strip() in ("E", "A")]
        successes = [m for m in return_msgs if m.get("TYPE", "").strip() in ("S", "I")]

        if errors:
            error_texts = [m.get("MESSAGE", "Unknown error") for m in errors]
            try:
                sap.call("BAPI_TRANSACTION_ROLLBACK")
            except Exception:
                pass
            sap.disconnect()
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "; ".join(error_texts),
                    "return_messages": return_msgs,
                },
            )

        # Commit so the rate is persisted to TCURR
        sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
        sap.disconnect()

        return {
            "success": True,
            "marker": "NEW_CODE_V2",
            "bapi_used": "BAPI_EXCHANGERATE_CREATEMULTIPLE",
            "message": (
                f"Exchange rate {req.from_currency}/{req.to_currency} = {req.rate} "
                f"set for {req.valid_from} (type: {req.rate_type})"
            ),
            "successes": [m.get("MESSAGE") for m in successes],
            "msg_count": len(return_msgs),
            "return_messages": return_msgs,
        }

    except HTTPException:
        raise
    except Exception as e:
        # If BAPI_EXCHANGERATE_CREATEMULTIPLE doesn't exist, fall back to single-create BAPI
        if "GetFunctionDesc" in str(e) or "not found" in str(e).lower():
            return await _create_rate_fallback(req)
        logger.exception("Exchange rate creation failed")
        raise HTTPException(status_code=500, detail="Exchange rate creation failed — see server logs.")


async def _create_rate_fallback(req: ExchangeRateRequest):
    """Fallback to BAPI_EXCHANGERATE_CREATE (older systems) if MULTIPLE not available."""
    from app.services.sap_connector import SAPConnector
    sap = SAPConnector()
    sap.connect()

    valid_from = req.valid_from.replace("-", "").replace("/", "").replace(".", "")
    exch_rate = {
        "RATE_TYPE": req.rate_type.upper(),
        "FROM_CURR": req.from_currency.upper(),
        "TO_CURRNCY": req.to_currency.upper(),
        "VALID_FROM": valid_from,
        "EXCH_RATE": str(req.rate),
        "FROM_FACTOR": "1",
        "TO_FACTOR": "1",
    }
    result = sap.call(
        "BAPI_EXCHANGERATE_CREATE",
        input_structures={"EXCH_RATE": exch_rate},
        tables=["RETURN"],
        table_fields={"RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE", "MESSAGE_V1", "MESSAGE_V2"]},
    )
    return_msgs = result.get("RETURN", [])
    errors = [m for m in return_msgs if m.get("TYPE", "").strip() in ("E", "A")]
    if errors:
        sap.disconnect()
        raise HTTPException(
            status_code=422,
            detail={"message": "; ".join(m.get("MESSAGE", "") for m in errors), "return_messages": return_msgs},
        )
    sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
    sap.disconnect()
    return {
        "success": True,
        "message": f"Exchange rate {req.from_currency}/{req.to_currency} = {req.rate} set (fallback BAPI)",
        "return_messages": return_msgs,
    }


@router.get("/vendors", dependencies=[Depends(require_admin)])
async def search_sap_vendors(
    search: str = Query(..., min_length=2, max_length=60),
    max_rows: int = Query(20, ge=1, le=50),
):
    """Live SAP vendor-master search — powers the admin "Add from SAP" supplier
    onboarding picker. Digit queries match the vendor number, text queries the
    name. Admin-only."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import search_vendors
        vendors = search_vendors(search, max_rows=max_rows)
        return {"vendors": vendors, "count": len(vendors)}
    except Exception:
        logger.exception("SAP vendor search failed for %r", search)
        raise HTTPException(
            status_code=502,
            detail="SAP vendor search failed — check SAP connectivity and try again.",
        )


@router.get("/pos")
async def list_sap_pos(
    max_rows: int = Query(100, ge=1, le=500),
    company_code: str = None,
    vendor: str = None,
):
    """Fetch PO list directly from SAP (live query, not cached)."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import fetch_po_list
        pos = fetch_po_list(max_rows=max_rows, company_code=company_code, vendor=vendor)
        return {"pos": pos, "total": len(pos), "source": "sap_live"}
    except Exception:
        logger.exception("SAP PO fetch failed")
        raise HTTPException(status_code=500, detail="SAP PO fetch failed — see server logs.")


@router.get("/pos/{po_number}")
async def get_sap_po_detail(po_number: str):
    """Fetch a single PO with line items from SAP."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import fetch_po_detail
        detail = fetch_po_detail(po_number)
        if not detail:
            raise HTTPException(status_code=404, detail=f"PO {po_number} not found in SAP")
        return detail
    except HTTPException:
        raise
    except Exception:
        logger.exception("SAP PO detail fetch failed for %s", po_number)
        raise HTTPException(status_code=500, detail="SAP PO detail fetch failed — see server logs.")


@router.post("/pos/{po_number}/sync")
async def sync_single_po(po_number: str, db: AsyncSession = Depends(get_db)):
    """Fetch a PO from SAP and save/update it in the local database."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import fetch_po_detail, sync_po_to_db

        # Check if PO already exists locally
        existing = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.po_number == po_number.strip())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"PO {po_number} already exists in local database"
            )

        # Fetch from SAP
        sap_po = fetch_po_detail(po_number)
        if not sap_po:
            raise HTTPException(status_code=404, detail=f"PO {po_number} not found in SAP")

        # Convert to local format
        po_data = sync_po_to_db(sap_po, None)

        # Save to DB
        po = PurchaseOrder(
            po_number=po_data["po_number"],
            vendor_name=po_data["vendor_name"],
            sap_vendor_number=(sap_po.get("vendor_number") or "").strip() or None,
            vendor_ntn=po_data["vendor_ntn"],
            po_date=po_data["po_date"],
            po_type=po_data["po_type"],
            total_amount=po_data["total_amount"],
            currency=po_data["currency"],
            status=po_data["status"],
            notes=po_data["notes"],
            source_type="sap",
        )
        db.add(po)
        await db.flush()

        for li_data in po_data["line_items"]:
            li = POLineItem(
                po_id=po.id,
                item_number=li_data["item_number"],
                description=li_data["description"],
                quantity=li_data["quantity"],
                unit=li_data["unit"],
                unit_price=li_data["unit_price"],
                amount=li_data["amount"],
            )
            db.add(li)

        await db.commit()
        await db.refresh(po)

        logger.info(f"Synced PO {po_number} from SAP (id={po.id}, {len(po_data['line_items'])} items)")

        return {
            "message": f"PO {po_number} synced successfully",
            "po_id": po.id,
            "line_items_count": len(po_data["line_items"]),
            "vendor_name": po_data["vendor_name"],
            "total_amount": po_data["total_amount"],
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("SAP PO sync failed for %s", po_number)
        raise HTTPException(status_code=500, detail="SAP PO sync failed — see server logs.")


@router.post("/pos/sync-all")
async def sync_all_pos(
    max_rows: int = Query(100, ge=1, le=500),
    company_code: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Fetch all POs from SAP and sync new ones into local database."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import fetch_po_list, fetch_po_detail, sync_po_to_db

        # Get list from SAP
        sap_pos = fetch_po_list(max_rows=max_rows, company_code=company_code)

        synced = 0
        skipped = 0
        errors = []

        for sap_po in sap_pos:
            po_number = sap_po["po_number"]

            # Check if already exists
            existing = await db.execute(
                select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            try:
                # Fetch detail with line items
                detail = fetch_po_detail(po_number)
                if not detail:
                    skipped += 1
                    continue

                po_data = sync_po_to_db(detail, None)

                po = PurchaseOrder(
                    po_number=po_data["po_number"],
                    vendor_name=po_data["vendor_name"],
                    sap_vendor_number=(detail.get("vendor_number") or "").strip() or None,
                    vendor_ntn=po_data["vendor_ntn"],
                    po_date=po_data["po_date"],
                    po_type=po_data["po_type"],
                    total_amount=po_data["total_amount"],
                    currency=po_data["currency"],
                    status=po_data["status"],
                    notes=po_data["notes"],
                    source_type="sap",
                )
                db.add(po)
                await db.flush()

                for li_data in po_data["line_items"]:
                    li = POLineItem(
                        po_id=po.id,
                        item_number=li_data["item_number"],
                        description=li_data["description"],
                        quantity=li_data["quantity"],
                        unit=li_data["unit"],
                        unit_price=li_data["unit_price"],
                        amount=li_data["amount"],
                    )
                    db.add(li)

                synced += 1

            except Exception:
                logger.exception("Sync failed for PO %s", po_number)
                errors.append(f"PO {po_number}: sync failed (see server logs)")

        await db.commit()

        return {
            "message": f"Sync complete: {synced} new, {skipped} already existed",
            "synced": synced,
            "skipped": skipped,
            "total_in_sap": len(sap_pos),
            "errors": errors[:10],  # limit error messages
        }

    except Exception:
        logger.exception("SAP sync-all failed")
        raise HTTPException(status_code=500, detail="SAP sync-all failed — see server logs.")


# ══════════════════════════════════════════════════════════════════════════════
#  Goods Received Notes (GRN) from SAP
# ══════════════════════════════════════════════════════════════════════════════


@router.get("/pos/{po_number}/grn")
async def get_sap_grn(po_number: str):
    """Fetch goods-receipt notes (GRNs) for a PO live from SAP (EKBE history)."""
    _ensure_dll()
    try:
        from app.services.sap_po_service import fetch_grn_for_po
        grns = fetch_grn_for_po(po_number)
        return {
            "po_number": po_number.strip(),
            "grns": grns,
            "total": len(grns),
            "source": "sap_live",
        }
    except Exception:
        logger.exception("SAP GRN fetch failed for %s", po_number)
        raise HTTPException(status_code=500, detail="SAP GRN fetch failed — see server logs.")


@router.post("/pos/{po_number}/grn/sync")
async def sync_sap_grn(po_number: str, db: AsyncSession = Depends(get_db)):
    """Fetch a PO's GRNs from SAP and persist them locally for 3-way matching.

    Ensures the PO exists locally (pulling it from SAP if needed), then creates a
    GoodsReceivedNote (+ line items) per SAP material document, mapping each PO
    item number to the local PO line item. GRNs already present (by grn_number)
    are skipped.
    """
    _ensure_dll()
    from app.services.sap_po_service import fetch_po_detail, sync_po_to_db, fetch_grn_for_po
    from app.models.purchase_order import GoodsReceivedNote, GRNLineItem

    ponum = po_number.strip()

    # 1. Ensure the local PO exists (with its line items) ───────────────
    res = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.po_number == ponum)
    )
    po = res.scalar_one_or_none()

    if po:
        item_map = {li.item_number: li.id for li in po.line_items}
    else:
        try:
            sap_po = fetch_po_detail(ponum)
        except Exception:
            logger.exception("SAP PO fetch failed for %s", ponum)
            raise HTTPException(status_code=502, detail="Failed to fetch PO from SAP — see server logs.")
        if not sap_po:
            raise HTTPException(status_code=404, detail=f"PO {ponum} not found in SAP.")
        po_data = sync_po_to_db(sap_po, None)
        po = PurchaseOrder(
            po_number=po_data["po_number"], vendor_name=po_data["vendor_name"],
            vendor_ntn=po_data["vendor_ntn"], po_date=po_data["po_date"],
            po_type=po_data["po_type"], total_amount=po_data["total_amount"],
            currency=po_data["currency"], status=po_data["status"],
            notes=po_data["notes"], source_type="sap",
        )
        db.add(po)
        await db.flush()
        new_lines = []
        for li_data in po_data["line_items"]:
            pli = POLineItem(
                po_id=po.id, item_number=li_data["item_number"],
                description=li_data["description"], quantity=li_data["quantity"],
                unit=li_data["unit"], unit_price=li_data["unit_price"], amount=li_data["amount"],
            )
            db.add(pli)
            new_lines.append(pli)
        await db.flush()
        item_map = {pli.item_number: pli.id for pli in new_lines}

    # 2. Fetch GRNs from SAP ─────────────────────────────────────────────
    try:
        grns = fetch_grn_for_po(ponum)
    except Exception:
        logger.exception("SAP GRN fetch failed for %s", ponum)
        raise HTTPException(status_code=502, detail="Failed to fetch GRNs from SAP — see server logs.")

    created, skipped = 0, 0
    created_numbers = []
    for g in grns:
        grn_no = g["grn_number"]
        existing = await db.execute(
            select(GoodsReceivedNote).where(GoodsReceivedNote.grn_number == grn_no)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        grn = GoodsReceivedNote(
            grn_number=grn_no,
            grn_date=g.get("grn_date"),
            po_id=po.id,
            plant_location=g.get("plant"),
            notes=f"Imported from SAP (material doc {grn_no}/{g.get('grn_year')})",
        )
        db.add(grn)
        await db.flush()
        line_count = 0
        for li in g["line_items"]:
            pli_id = item_map.get(li["po_item"])
            if not pli_id or (li.get("received_quantity") or 0) == 0:
                continue
            db.add(GRNLineItem(
                grn_id=grn.id,
                po_line_item_id=pli_id,
                received_quantity=li["received_quantity"],
                inspection_status="accepted",
            ))
            line_count += 1
        if line_count == 0:
            await db.delete(grn)  # no mappable lines — drop the empty GRN
        else:
            created += 1
            created_numbers.append(grn_no)

    await db.commit()
    return {
        "po_number": ponum,
        "po_id": po.id,
        "grns_created": created,
        "grns_skipped": skipped,
        "created_grn_numbers": created_numbers,
        "total_in_sap": len(grns),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Tax codes
# ══════════════════════════════════════════════════════════════════════════════


async def _sync_tax_codes(db: AsyncSession, company_code: str) -> dict:
    """Pull tax codes from SAP and replace the locally cached rows for the company."""
    from app.services.sap_po_service import fetch_tax_codes
    from app.models.sap_tax_code import SapTaxCode

    data = fetch_tax_codes(company_code)  # live RFC read from SAP
    await db.execute(delete(SapTaxCode).where(SapTaxCode.company_code == company_code))
    for c in data["tax_codes"]:
        db.add(SapTaxCode(
            company_code=company_code,
            country=data.get("country"),
            procedure=data.get("procedure"),
            code=c["code"],
            description=c["description"],
            tax_type=c["tax_type"],
            rate=c["rate"],
        ))
    await db.commit()
    return data


def _tax_codes_response(company_code, rows):
    return {
        "company_code": company_code,
        "procedure": rows[0].procedure if rows else None,
        "country": rows[0].country if rows else None,
        "source": "db",
        "tax_codes": [
            {"code": r.code, "description": r.description, "tax_type": r.tax_type, "rate": r.rate}
            for r in rows
        ],
    }


@router.get("/tax-codes")
async def get_sap_tax_codes(company_code: str = "1100", db: AsyncSession = Depends(get_db)):
    """Tax codes for the Park-to-SAP dropdown — served from the local
    `sap_tax_codes` cache. On first use (empty cache) it lazily syncs from SAP."""
    from app.models.sap_tax_code import SapTaxCode

    async def _load():
        res = await db.execute(
            select(SapTaxCode).where(SapTaxCode.company_code == company_code).order_by(SapTaxCode.code)
        )
        return res.scalars().all()

    rows = await _load()
    if not rows:
        # No-SAP instance: serve a static Pakistan tax-code set for the dropdown.
        if not settings.SAP_ENABLED:
            return {
                "company_code": company_code,
                "source": "static",
                "tax_codes": [
                    {"code": "I0", "description": "0% — Exempt / no input tax", "rate": 0},
                    {"code": "I1", "description": "18% — Standard input sales tax", "rate": 18},
                    {"code": "I2", "description": "17% — Input sales tax", "rate": 17},
                ],
            }
        _ensure_dll()
        try:
            await _sync_tax_codes(db, company_code)
            rows = await _load()
        except Exception:
            logger.exception("Tax-code lazy sync failed")
            return {"company_code": company_code, "tax_codes": [], "source": "empty"}
    return _tax_codes_response(company_code, rows)


@router.post("/tax-codes/sync")
async def sync_sap_tax_codes(company_code: str = "1100", db: AsyncSession = Depends(get_db)):
    """Refresh the cached tax codes from SAP (admin/maintenance action)."""
    _ensure_dll()
    try:
        data = await _sync_tax_codes(db, company_code)
    except Exception:
        logger.exception("Tax-code sync failed")
        raise HTTPException(status_code=500, detail="Tax-code sync failed — see server logs.")
    return {"company_code": company_code, "procedure": data.get("procedure"), "synced": len(data["tax_codes"])}


# ── SAP currencies (TCURT) — cached locally for the Park currency dropdown ──

async def _sync_currencies(db: AsyncSession) -> list[dict]:
    """Pull currencies from SAP (TCURT) and replace the locally cached rows."""
    from app.services.sap_po_service import fetch_currencies
    from app.models.sap_currency import SapCurrency

    data = fetch_currencies()  # live RFC read from SAP
    await db.execute(delete(SapCurrency))
    for c in data:
        db.add(SapCurrency(code=c["code"], name=c.get("name")))
    await db.commit()
    return data


@router.get("/vendor-lookup")
async def sap_vendor_lookup(ntn: str = "", name: str = ""):
    """Is this supplier registered as a vendor in SAP (LFA1)? Matches by tax
    number (NTN/STRN/CNIC) or name. Drives the invoice's 'ERP Registration' badge."""
    if not (ntn or name).strip():
        raise HTTPException(status_code=400, detail="Provide ntn or name to look up.")
    # No-SAP instance: no vendor master to check — report 'unknown' so the ERP
    # Registration badge renders instead of erroring.
    if not settings.SAP_ENABLED:
        return {"found": False, "sap_disabled": True, "vendor_number": None,
                "vendor_name": None, "message": "SAP not configured for this instance."}
    _ensure_dll()
    try:
        from app.services.sap_po_service import lookup_vendor
        return lookup_vendor(ntn=ntn, name=name)
    except Exception:
        logger.exception("SAP vendor lookup failed (ntn=%s name=%s)", ntn, name)
        raise HTTPException(status_code=502, detail="SAP vendor lookup failed — see server logs.")


@router.get("/currencies")
async def get_sap_currencies(db: AsyncSession = Depends(get_db)):
    """Currency list for the Park-to-SAP dropdown — served from the local
    `sap_currencies` cache. On first use (empty cache) it lazily syncs from SAP."""
    from app.models.sap_currency import SapCurrency

    async def _load():
        res = await db.execute(select(SapCurrency).order_by(SapCurrency.code))
        return res.scalars().all()

    rows = await _load()
    if not rows:
        # No-SAP instance: serve a static currency set for the dropdown.
        if not settings.SAP_ENABLED:
            return {
                "source": "static",
                "currencies": [
                    {"code": "PKR", "name": "Pakistani Rupee"},
                    {"code": "USD", "name": "US Dollar"},
                    {"code": "EUR", "name": "Euro"},
                    {"code": "GBP", "name": "Pound Sterling"},
                ],
            }
        _ensure_dll()
        try:
            await _sync_currencies(db)
            rows = await _load()
        except Exception:
            logger.exception("Currency lazy sync failed")
            return {"currencies": [], "source": "empty"}
    return {
        "source": "db",
        "currencies": [{"code": r.code, "name": r.name} for r in rows],
    }


@router.post("/currencies/sync")
async def sync_sap_currencies(db: AsyncSession = Depends(get_db)):
    """Refresh the cached currencies from SAP (admin/maintenance action)."""
    _ensure_dll()
    try:
        data = await _sync_currencies(db)
    except Exception:
        logger.exception("Currency sync failed")
        raise HTTPException(status_code=500, detail="Currency sync failed — see server logs.")
    return {"synced": len(data)}


# ══════════════════════════════════════════════════════════════════════════════
#  Invoice Posting to SAP
# ══════════════════════════════════════════════════════════════════════════════


class SAPPostRequest(BaseModel):
    """Optional overrides when sending an invoice to SAP."""
    mode: str = "park"                     # "park" (MIR7, held — default) | "post" (MIRO, final)
    company_code: Optional[str] = None     # defaults to PO's company code from SAP
    posting_date: Optional[str] = None     # defaults to today
    tax_code: str = "I0"                   # SAP tax code (I0 = Exempt from Input Sales Tax; valid in TAXPK)
    header_text: Optional[str] = None
    exchange_rate: Optional[float] = None  # direct exchange rate (e.g. 0.72 for CAD→USD)
    layout: str = "goods"                  # SAP MIR7 item layout: "goods" | "delivery" | "both"
    line_item_ids: Optional[list[int]] = None  # if set, only these invoice lines are parked


async def _simulated_sap_result(db: AsyncSession, invoice: Invoice, req: SAPPostRequest) -> dict:
    """No-SAP instances (settings.SAP_ENABLED is False): assume the SAP process.

    - validate  → report success (nothing to check; parking is assumed to pass)
    - park/post → stamp a SIMULATED document number and advance the invoice,
                  mirroring the real path's DB updates so the rest of the app
                  (status stepper, badges) behaves identically.
    """
    if req.mode == "validate":
        return {
            "ok": True,
            "simulated": True,
            "message": "SAP is not configured for this instance — parking validation assumed to pass.",
            "sap_return": [],
        }

    doc_status = "posted" if req.mode == "post" else "parked"
    now = datetime.now(timezone.utc)
    sim_doc = f"90{invoice.id:08d}"[:10]           # 10-digit placeholder doc no.
    fiscal_year = (invoice.sap_posting_date or "")[:4] or str(now.year)

    invoice.sap_document_number = sim_doc
    invoice.sap_fiscal_year = fiscal_year
    invoice.sap_company_code = req.company_code or invoice.sap_company_code or "1000"
    invoice.sap_posted_at = now
    invoice.sap_doc_status = doc_status
    invoice.sap_tax_code = invoice.sap_tax_code or req.tax_code
    invoice.sap_layout = invoice.sap_layout or req.layout
    invoice.sap_posting_date = invoice.sap_posting_date or req.posting_date
    invoice.sap_baseline_date = invoice.sap_baseline_date or invoice.sap_posting_date
    invoice.status = doc_status
    await db.commit()

    logger.info("Invoice %s %s (SIMULATED — SAP disabled): doc=%s/%s",
                invoice.id, doc_status, sim_doc, fiscal_year)
    return {
        "success": True,
        "simulated": True,
        "invoice_id": invoice.id,
        "mode": req.mode,
        "sap_doc_status": doc_status,
        "sap_document_number": sim_doc,
        "sap_fiscal_year": fiscal_year,
        "company_code": invoice.sap_company_code,
        "message": f"Simulated SAP {doc_status} (no SAP configured for this instance).",
    }


@router.post("/invoices/{invoice_id}/post")
async def post_invoice_to_sap_endpoint(
    invoice_id: int,
    req: SAPPostRequest = SAPPostRequest(),
    db: AsyncSession = Depends(get_db),
    user: InternalUser = Depends(get_current_internal_user),
):
    """
    Send a matched invoice to SAP — PARK it (BAPI_INCOMINGINVOICE_PARK, the
    default) so a SAP user posts it later, or POST it outright
    (BAPI_INCOMINGINVOICE_CREATE1) when mode="post". mode="validate" is a
    non-persisting dry run used at submit-for-approval time.

    Only purchasers (ap_operator) and admins may park/post to SAP — enforced here so it
    cannot be bypassed by calling the API directly (the UI also hides the button
    for other roles).

    Prerequisites:
      - Invoice must be in 'validated' or 'approved' status
      - Invoice must have a matched PO (matched_po_id set)
      - The PO must exist in SAP (fetched live to get vendor_number + company_code)
    """
    if user.role not in SAP_PARK_ROLES:
        labels = await role_labels(db)
        allowed = ", ".join(labels.get(r) or humanize_role(r) for r in SAP_PARK_ROLES)
        raise HTTPException(
            status_code=403,
            detail=f"Only these roles can park invoices to SAP: {allowed}.",
        )

    # ── Load invoice with line items ────────────────────────────
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.line_items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check status — must be validated or approved
    if invoice.status not in ("validated", "approved"):
        raise HTTPException(
            status_code=400,
            detail=f"Invoice status is '{invoice.status}'. Must be 'validated' or 'approved' to post to SAP.",
        )

    # Check already sent (parked or posted)
    if invoice.sap_document_number:
        raise HTTPException(
            status_code=409,
            detail=f"Invoice already sent to SAP as document {invoice.sap_document_number}/{invoice.sap_fiscal_year} ({invoice.sap_doc_status or 'posted'})",
        )

    # ── No-SAP instance (e.g. Martin Dow demo): assume the SAP process ──
    # Skip PO-in-SAP lookup and the live BAPI call entirely.
    if not settings.SAP_ENABLED:
        return await _simulated_sap_result(db, invoice, req)

    _ensure_dll()

    # ── Effective SAP parking values ──────────────────────────────
    # These are completed during review and saved on the invoice (locked at
    # approval). The persisted values win; the request is only a fallback.
    eff_layout = invoice.sap_layout or req.layout or "goods"
    eff_tax_code = invoice.sap_tax_code or req.tax_code or "I0"
    eff_posting_date = invoice.sap_posting_date or req.posting_date
    eff_baseline_date = invoice.sap_baseline_date or eff_posting_date  # BLINE_DATE
    eff_header_text = invoice.sap_header_text or req.header_text
    eff_item_text = invoice.sap_item_text  # Details-tab text → ITEM_TEXT (SGTXT)
    eff_currency = invoice.sap_currency or invoice.currency or "PKR"   # document currency
    eff_exchange_rate = invoice.exchange_rate or req.exchange_rate
    # SAP rejects an exchange rate on a local-currency document — only send it
    # when the chosen document currency differs from the company's base currency.
    if eff_currency == (invoice.base_currency or "PKR"):
        eff_exchange_rate = None

    # Item layout (mirrors SAP MIR7's item-selection dropdown):
    #   goods    → goods/service items only
    #   delivery → planned delivery costs only (freight conditions, e.g. ZFRT)
    #   both     → goods items + planned delivery costs
    if eff_layout not in ("goods", "delivery", "both"):
        raise HTTPException(status_code=400, detail=f"Invalid layout '{eff_layout}'. Use goods | delivery | both.")

    # Must have a matched PO
    if not invoice.matched_po_id:
        raise HTTPException(
            status_code=400,
            detail="Invoice has no matched Purchase Order. Run PO matching first.",
        )

    # ── Load local PO ──────────────────────────────────────────
    po_result = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.line_items))
        .where(PurchaseOrder.id == invoice.matched_po_id)
    )
    po = po_result.scalar_one_or_none()
    if not po:
        raise HTTPException(status_code=404, detail="Matched Purchase Order not found in local DB")

    # ── Fetch PO from SAP to get vendor_number + company_code ──
    try:
        from app.services.sap_po_service import fetch_po_detail
        sap_po = fetch_po_detail(po.po_number)
    except Exception:
        logger.exception("Failed to fetch PO %s from SAP", po.po_number)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch PO {po.po_number} from SAP — see server logs.",
        )

    if not sap_po:
        raise HTTPException(
            status_code=404,
            detail=f"PO {po.po_number} not found in SAP. Cannot post invoice.",
        )

    vendor_number = sap_po.get("vendor_number", "")
    company_code = req.company_code or sap_po.get("company_code", "")

    if not vendor_number:
        raise HTTPException(
            status_code=400,
            detail="Could not determine vendor number from SAP PO.",
        )
    if not company_code:
        raise HTTPException(
            status_code=400,
            detail="Company code not found. Provide it in the request or ensure PO has one in SAP.",
        )

    # ── Build line items for BAPI — one row per PO item ─────────
    # SAP rejects ITEMDATA that references the same PO item twice ("Document
    # contains same order item more than once"). So: map each invoice line to a
    # PO item using the saved match pairing (or the PO's only item), aggregate
    # amounts/quantities per PO item, and REFUSE any selected line that has no PO
    # counterpart (e.g. an extra delivery-charge line not present on the PO): the
    # park payload has no row type for it, and guessing a PO item would park the
    # wrong amount.
    from app.models.purchase_order import POMatchResult

    po_lines = sorted(sap_po.get("line_items", []), key=lambda x: x.get("item_number", 0))
    po_item_units = {pl.get("item_number"): (pl.get("unit") or "ST") for pl in po_lines}

    # invoice_line_item_id -> PO item number, from the most recent match result
    inv_to_po_item: dict[int, int] = {}
    mr_res = await db.execute(
        select(POMatchResult)
        .options(selectinload(POMatchResult.line_matches))
        .where(
            POMatchResult.invoice_id == invoice_id,
            POMatchResult.po_id == invoice.matched_po_id,
        )
        .order_by(POMatchResult.created_at.desc())
    )
    match_result = mr_res.scalars().first()
    if match_result:
        po_li_item_no = {li.id: li.item_number for li in po.line_items}
        for lm in match_result.line_matches:
            if lm.invoice_line_item_id and lm.po_line_item_id:
                item_no = po_li_item_no.get(lm.po_line_item_id)
                if item_no is not None:
                    inv_to_po_item[lm.invoice_line_item_id] = item_no

    # When the PO has a single line item — common for service POs, where several
    # invoice detail lines (e.g. inspection + mobilization) roll up into one
    # service line — every invoice line aggregates into that one PO item. Without
    # this, the positional fallback below only maps the first N invoice lines
    # (N = PO line count) and silently drops the rest, under-parking the invoice.
    single_po_item = po_lines[0].get("item_number") if len(po_lines) == 1 else None

    # Which invoice lines to park: the request's explicit selection wins;
    # otherwise fall back to the selection persisted on the invoice at
    # submit-for-approval (parking_line_item_ids). None = all lines.
    selected_ids = None
    if req.line_item_ids is not None:
        selected_ids = set(req.line_item_ids)
    elif invoice.parking_line_item_ids:
        try:
            import json as _json
            selected_ids = set(_json.loads(invoice.parking_line_item_ids)) or None
        except Exception:
            selected_ids = None

    routed, unrouted = route_invoice_lines(
        invoice.line_items, selected_ids, inv_to_po_item, single_po_item
    )
    if unrouted and eff_layout in ("goods", "both"):
        # Not on this PO: refuse by name instead of guessing an item or dropping
        # the line (the SAP document would silently total less than the invoice).
        matching_missing = (
            single_po_item is None
            and (match_result is None or not match_result.line_matches)
        )
        raise HTTPException(
            status_code=422,
            detail=unrouted_lines_message(unrouted, po.po_number, matching_missing),
        )

    agg: dict[int, dict] = {}
    # Which invoice lines fed each PO item — so a rule violation can name the
    # line the user has to fix, not just the PO item it aggregated into.
    line_ids_by_po_item: dict[int, list] = {}
    for inv_line in invoice.line_items:
        item_no = routed.get(inv_line.id)
        if item_no is None:
            continue  # not selected (unrouted lines were refused above)
        row = agg.setdefault(item_no, {"amount": 0.0, "quantity": 0.0, "po_unit": po_item_units.get(item_no, "ST")})
        row["amount"] += float(inv_line.amount or 0)
        row["quantity"] += float(inv_line.quantity or 0)
        line_ids_by_po_item.setdefault(item_no, []).append(inv_line.id)

    goods_items = [
        {
            "po_item": item_no,
            "amount": v["amount"],
            "quantity": v["quantity"],
            "po_unit": v["po_unit"],
            "tax_code": eff_tax_code,
        }
        for item_no, v in sorted(agg.items())
    ]

    # Items under GR-based invoice verification must reference the receipt doc,
    # else SAP rejects: service items (PSTYP=9, confirmed via a Service Entry
    # Sheet) need SHEET_NO/SHEET_ITEM (or SE 509); goods items with WEBRE='X'
    # need REF_DOC/REF_DOC_YEAR/REF_DOC_IT (or "Fill in mandatory field
    # REF_DOC…"). Both references come from the same EKBE (GR) history.
    service_po_items = {pl.get("item_number") for pl in po_lines if pl.get("is_service")}
    grbased_po_items = {pl.get("item_number") for pl in po_lines if pl.get("gr_based_iv")}

    # A goods line with an amount but no quantity would reach the BAPI as
    # QUANTITY=0 — a document billing a real amount for zero units — because the
    # value is defaulted to 0 both here (`or 0`, above) and in
    # sap_invoice_post.py. Refuse it instead. Service items are exempt: they are
    # value-based and SAP rejects QUANTITY on them. Checked here rather than in
    # the aggregation loop because `service_po_items` is only known now.
    zero_qty = find_zero_quantity_goods(agg, service_po_items, line_ids_by_po_item)
    if zero_qty:
        raise HTTPException(status_code=422, detail=zero_quantity_message(zero_qty))

    needs_ref = service_po_items | grbased_po_items
    if needs_ref and any(gi["po_item"] in needs_ref for gi in goods_items):
        from app.services.sap_po_service import fetch_service_grn_refs
        try:
            gr_refs = fetch_service_grn_refs(po.po_number)
        except Exception:
            logger.exception("Failed to read GR/entry-sheet refs for PO %s", po.po_number)
            raise HTTPException(status_code=502, detail="Could not read goods-receipt data from SAP.")
        for gi in goods_items:
            item_no = gi["po_item"]
            is_service = item_no in service_po_items
            is_grbased = item_no in grbased_po_items
            if not (is_service or is_grbased):
                continue
            ref = gr_refs.get(item_no)
            has_service_ref = ref and ref.get("sheet_no")
            has_goods_ref = ref and ref.get("ref_doc")
            if is_service and not has_service_ref:
                raise HTTPException(status_code=422, detail=(
                    f"PO {po.po_number} item {item_no} is a service line with no accepted "
                    "Service Entry Sheet in SAP. Enter and accept the service (ML81N) first."))
            if is_grbased and not is_service and not has_goods_ref:
                raise HTTPException(status_code=422, detail=(
                    f"PO {po.po_number} item {item_no} needs a goods receipt before invoicing "
                    "(GR-based invoice verification). Post the goods receipt (MIGO) first."))
            if is_service:
                gi["sheet_no"] = ref["sheet_no"]
                gi["sheet_item"] = ref["sheet_item"]
            else:
                gi["ref_doc"] = ref["ref_doc"]
                gi["ref_doc_year"] = ref["ref_doc_year"]
                gi["ref_doc_item"] = ref["ref_doc_item"]

    # Planned delivery costs (freight conditions, e.g. ZFRT) read live from SAP
    # (EKBZ). Only the GR-accrued, still-open amount is invoiceable.
    delivery_items = []
    if eff_layout in ("delivery", "both"):
        from app.services.sap_po_service import fetch_delivery_costs
        try:
            dcs = fetch_delivery_costs(po.po_number)
        except Exception:
            logger.exception("Failed to read delivery costs for PO %s", po.po_number)
            raise HTTPException(status_code=502, detail="Could not read planned delivery costs from SAP.")
        if not dcs:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No invoiceable planned delivery costs found on this PO in SAP. "
                    "A goods receipt for the freight must be posted first."
                ),
            )
        delivery_items = [
            {
                "po_item": dc["po_item"],
                "amount": dc["amount"],
                "quantity": dc["quantity"],
                "po_unit": po_item_units.get(dc["po_item"], "ST"),
                "tax_code": eff_tax_code,
                "cond_type": dc["cond_type"],   # marks this as a delivery cost
            }
            for dc in dcs
        ]

    if eff_layout == "goods":
        sap_line_items = goods_items
    elif eff_layout == "delivery":
        sap_line_items = delivery_items
    else:  # both
        sap_line_items = goods_items + delivery_items

    if not sap_line_items:
        if selected_ids is not None and not selected_ids:
            raise HTTPException(
                status_code=400,
                detail="No line items are selected for parking. Select at least one line.",
            )
        raise HTTPException(
            status_code=400,
            detail="No items to park for this layout. Run/adjust PO matching first.",
        )

    # Gross = sum of the items actually sent + tax (delivery-only carries no goods GST).
    sent_net = round(sum(float(li["amount"]) for li in sap_line_items), 2)
    full_tax = float(invoice.tax_amount or invoice.gst_amount or 0)
    from app.services.sap_po_service import tax_rate_for_code
    code_rate = tax_rate_for_code(company_code, eff_tax_code)
    # "Partial" = a proper subset of the invoice's lines (selected_ids is also
    # populated when the user keeps ALL lines — that's still a full park).
    all_line_ids = {li.id for li in invoice.line_items}
    partial_park = selected_ids is not None and bool(all_line_ids - selected_ids)
    if eff_layout == "delivery":
        tax_amount_used = 0
    elif partial_park:
        # Partial park: the header tax belongs to the FULL document and goes
        # stale when line quantities are edited, so prorating it can produce
        # impossible rates. Compute the selection's tax from the chosen SAP tax
        # code's rate — exactly what SAP itself would assess for these lines.
        if code_rate:
            tax_amount_used = round(sent_net * (code_rate / 100.0), 2)
        elif full_tax > 0:
            # No known rate for the code — fall back to prorating the header tax.
            full_net = round(sum(float(li.amount or 0) for li in invoice.line_items), 2) \
                or float(invoice.subtotal_amount or 0)
            tax_amount_used = round(full_tax * (sent_net / full_net), 2) if full_net else full_tax
        else:
            tax_amount_used = 0
    elif full_tax > 0:
        # Full park: the invoice carries its own tax — keep the document's value.
        tax_amount_used = full_tax
    else:
        # No tax on the invoice — derive it from the chosen SAP tax code's rate
        # (e.g. AY = 19.5%). Exempt/0% codes (I0) yield no tax.
        tax_amount_used = round(sent_net * (code_rate / 100.0), 2) if code_rate else 0

    gross_amount = round(sent_net + (tax_amount_used or 0), 2)

    # ── Call SAP posting service ───────────────────────────────
    try:
        from app.services.sap_invoice_post import post_invoice_to_sap

        sap_result = post_invoice_to_sap(
            invoice_number=invoice.invoice_number or f"INV-{invoice.id}",
            invoice_date=invoice.invoice_date,
            posting_date=eff_posting_date,
            baseline_date=eff_baseline_date,
            vendor_number=vendor_number,
            company_code=company_code,
            currency=eff_currency,
            gross_amount=gross_amount,
            tax_amount=tax_amount_used,
            po_number=po.po_number,
            line_items=sap_line_items,
            tax_code=eff_tax_code,
            header_text=eff_header_text or f"einv-{invoice.invoice_number or invoice.id}",
            item_text=eff_item_text,
            exchange_rate=eff_exchange_rate,
            mode=req.mode,
        )
    except Exception:
        logger.exception("SAP posting call failed for invoice %s", invoice.id)
        raise HTTPException(
            status_code=502,
            detail="SAP posting call failed — see server logs.",
        )

    # ── VALIDATE (dry run): return the outcome, never touch the DB ──
    if req.mode == "validate":
        return {
            "ok": sap_result.get("success", False),
            "message": sap_result.get("message"),
            "sap_return": sap_result.get("return_messages", []),
        }

    if not sap_result.get("success"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": sap_result.get("message", "SAP posting failed"),
                "sap_return": sap_result.get("return_messages", []),
            },
        )

    # ── Update invoice in local DB ─────────────────────────────
    doc_status = "parked" if req.mode == "park" else "posted"
    invoice.sap_document_number = sap_result["invoice_doc_number"]
    invoice.sap_fiscal_year = sap_result["fiscal_year"]
    invoice.sap_company_code = company_code
    invoice.sap_posted_at = datetime.now(timezone.utc)
    invoice.sap_doc_status = doc_status
    invoice.sap_tax_code = eff_tax_code   # record the values actually used
    invoice.sap_layout = eff_layout
    invoice.sap_posting_date = eff_posting_date
    invoice.sap_baseline_date = eff_baseline_date
    invoice.sap_header_text = eff_header_text
    invoice.sap_item_text = eff_item_text
    invoice.sap_currency = eff_currency
    invoice.status = doc_status  # "parked" (held in SAP) or "posted"

    await db.commit()

    logger.info(
        f"Invoice {invoice.id} {doc_status} to SAP: doc={sap_result['invoice_doc_number']}, "
        f"year={sap_result['fiscal_year']}, company={company_code}"
    )

    return {
        "success": True,
        "invoice_id": invoice.id,
        "mode": req.mode,
        "sap_doc_status": doc_status,
        "sap_document_number": sap_result["invoice_doc_number"],
        "sap_fiscal_year": sap_result["fiscal_year"],
        "company_code": company_code,
        "message": sap_result["message"],
    }


@router.post("/invoices/{invoice_id}/unpark")
async def unpark_invoice_endpoint(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Unpark (delete/reverse) an invoice's parked document in SAP, then
    soft-delete the invoice on our side.

    A parked invoice can't be deleted locally until it's removed from SAP — this
    is the supported path to do both in one action.
    """
    _ensure_dll()

    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted == 0))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.sap_document_number:
        raise HTTPException(status_code=409, detail="Invoice is not parked in SAP — nothing to unpark.")
    if invoice.sap_doc_status == "posted":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invoice is POSTED in SAP as {invoice.sap_document_number}/{invoice.sap_fiscal_year}. "
                f"A posted document must be reversed in SAP (MR8M), not unparked."
            ),
        )

    # ── Delete the parked document in SAP ──
    try:
        from app.services.sap_invoice_post import unpark_invoice_in_sap
        sap_result = unpark_invoice_in_sap(invoice.sap_document_number, invoice.sap_fiscal_year)
    except Exception:
        logger.exception("SAP unpark call failed for invoice %s", invoice.id)
        raise HTTPException(status_code=502, detail="SAP unpark call failed — see server logs.")

    if not sap_result.get("success"):
        raise HTTPException(
            status_code=422,
            detail={
                "message": sap_result.get("message", "SAP unpark failed"),
                "sap_return": sap_result.get("return_messages", []),
            },
        )

    # ── Reset on our side so the invoice can be parked again ──
    # Unparking deletes the SAP document; the invoice returns to "approved" with
    # its SAP fields cleared (rather than being soft-deleted) so a corrected
    # version can be re-parked.
    doc_ref = f"{invoice.sap_document_number}/{invoice.sap_fiscal_year}"
    invoice.sap_document_number = None
    invoice.sap_fiscal_year = None
    invoice.sap_doc_status = None
    invoice.status = "approved"
    await db.commit()

    logger.info(f"Invoice {invoice.id} unparked from SAP ({doc_ref}) — reset to approved for re-parking")
    return {
        "success": True,
        "invoice_id": invoice.id,
        "sap_document": doc_ref,
        "already_gone": sap_result.get("already_gone", False),
        "message": sap_result.get("message", "Unparked from SAP — ready to park again."),
    }
