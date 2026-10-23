"""
SAP Invoice Posting Service — post vendor invoices to SAP via RFC.

Uses BAPI_INCOMINGINVOICE_CREATE1 to create a vendor invoice (MIRO equivalent)
linked to a Purchase Order, then BAPI_TRANSACTION_COMMIT to finalise.

SAP tables used by the BAPI:
  HEADERDATA   — invoice header (doc date, posting date, amount, vendor, etc.)
  ITEMDATA     — line items linked to PO items
  TAXDATA      — tax breakdown (optional)
"""

import logging
import os
from datetime import datetime

from app.services.sap_connector import SAPConnector
from app.config import settings

logger = logging.getLogger(__name__)


def _get_connector() -> SAPConnector:
    """Create a new SAP connector (adds DLL directory if needed)."""
    try:
        os.add_dll_directory(os.path.join(settings.SAP_NWRFC_SDK_PATH, "lib"))
    except (OSError, AttributeError):
        pass
    return SAPConnector()


def _sap_date(iso_date: str | None, default: str | None = None) -> str:
    """Convert a date string (various formats) to SAP YYYYMMDD.

    Returns `default` (or today) when the value is missing, unparseable, or
    yields an implausible year. This guards against corrupt stored values like
    "0202-05-20" (year 202), which datetime would happily accept and then render
    as the 7-char "2020520" — PyRFC rejects that as an invalid date, crashing the
    whole park call.
    """
    fallback = default or datetime.now().strftime("%Y%m%d")
    if not iso_date:
        return fallback
    # Drop any trailing time component ("05.01.2026 09:33:55" -> "05.01.2026").
    clean = iso_date.strip().replace("/", "-").split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%Y%m%d",
                "%d.%m.%Y", "%m.%d.%Y", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(clean, fmt)
        except ValueError:
            continue
        if 2000 <= dt.year <= 2099:
            return dt.strftime("%Y%m%d")
        break  # parsed but implausible year — use the fallback
    return fallback


def post_invoice_to_sap(
    invoice_number: str,
    invoice_date: str,
    posting_date: str | None,
    vendor_number: str,
    company_code: str,
    currency: str,
    gross_amount: float,
    tax_amount: float | None,
    po_number: str,
    line_items: list[dict],
    tax_code: str = "I0",
    header_text: str = "",
    item_text: str | None = None,
    exchange_rate: float | None = None,
    baseline_date: str | None = None,
    mode: str = "post",
) -> dict:
    """
    Post a vendor invoice to SAP via BAPI_INCOMINGINVOICE_CREATE1.

    Parameters:
        invoice_number: vendor's invoice reference
        invoice_date:   invoice date (ISO or SAP format)
        posting_date:   posting date (defaults to today)
        vendor_number:  SAP vendor number (LIFNR — 10 chars, zero-padded)
        company_code:   SAP company code (BUKRS)
        currency:       currency key (e.g. PKR, CAD, USD)
        gross_amount:   total invoice amount including tax
        tax_amount:     tax portion (GST/VAT)
        po_number:      SAP PO number to reference
        line_items:     list of dicts with:
                          - po_item (EBELP — PO line item number)
                          - amount (net amount for this line)
                          - quantity (invoiced qty)
                          - po_unit (unit of measure, e.g. ST, EA)
                          - tax_code (per-line tax code, optional)
        tax_code:       default tax code for header/lines
        header_text:    free-text note on the document

    Returns:
        dict with: invoice_doc_number, fiscal_year, success, message
    """
    sap = _get_connector()
    sap.connect()

    try:
        # SAP DEV (company 1100, July–June fiscal year) currently has open periods
        # 11/2025 (May 2025), 10/2025 (Apr 2025), 12/2024 (Jun 2024). Default to a
        # date in the current open period; override via posting_date / the UI's
        # "Posting Date" field when SAP rolls the open periods forward. A corrupt/
        # unparseable posting date falls back to this safe default rather than
        # crashing the BAPI call.
        sap_post_date = _sap_date(posting_date, default="20250520")
        sap_inv_date = _sap_date(invoice_date, default=sap_post_date)
        # Baseline date (payment terms) — defaults to the posting date if not given.
        sap_bline_date = _sap_date(baseline_date, default=sap_post_date)
        # Doc date must not be after posting date
        if sap_inv_date > sap_post_date:
            sap_inv_date = sap_post_date
        po_num = po_number.strip().zfill(10)

        # ── HEADERDATA ───────────────────────────────────────────
        header_data = {
            "INVOICE_IND": "X",           # Vendor invoice (not credit memo)
            "DOC_TYPE": "RE",             # RE = Invoice receipt
            "DOC_DATE": sap_inv_date,     # Invoice date
            "PSTNG_DATE": sap_post_date,  # Posting date
            "BLINE_DATE": sap_bline_date,  # Baseline date for due-date calc — without it SAP rejects with M8 366 "Terms of payment are incorrect"
            "COMP_CODE": company_code,
            "CURRENCY": currency,
            "GROSS_AMOUNT": str(gross_amount),
            # Manual tax: we always supply the exact tax amount in TAXDATA, so
            # CALC_TAX_IND must be blank. Setting "X" tells SAP to CALCULATE the
            # tax itself, which then conflicts with the supplied amount and is
            # rejected with M8 738 ("enter value in either CALC_TAX_IND or
            # TAX_AMOUNT").
            "CALC_TAX_IND": "",
            "REF_DOC_NO": invoice_number[:16] if invoice_number else "",
            "HEADER_TXT": header_text[:25] if header_text else f"einv-{invoice_number}"[:25],  # Basic Data "Text" (BKTXT)
        }
        if item_text:
            header_data["ITEM_TEXT"] = item_text[:50]  # Details "Text" (SGTXT)

        # Supply exchange rate directly so SAP doesn't look up TCURR
        if exchange_rate:
            header_data["EXCH_RATE"] = str(exchange_rate)
            header_data["EXCH_RATE_V"] = "0"  # direct quotation

        # ── ITEMDATA — one row per PO line item ──────────────────
        # A row with "cond_type" set is a PLANNED DELIVERY COST (e.g. freight
        # condition ZFRT): SAP keys it off COND_TYPE rather than the goods value.
        item_data_rows = []
        for idx, li in enumerate(line_items, start=1):
            po_item = str(li.get("po_item", idx * 10)).zfill(5)
            item_row = {
                "INVOICE_DOC_ITEM": str(idx).zfill(6),
                "PO_NUMBER": po_num,
                "PO_ITEM": po_item,
                "TAX_CODE": li.get("tax_code", tax_code),
                "ITEM_AMOUNT": str(li.get("amount", 0)),
            }
            if li.get("sheet_no"):
                # SERVICE item — invoice against the accepted Service Entry Sheet
                # (SHEET_NO/SHEET_ITEM). Service lines are value-based: sending
                # QUANTITY/PO_UNIT makes SAP reject with "Quantities and units of
                # measure … not permitted". This also clears SE 509.
                item_row["SHEET_NO"] = str(li["sheet_no"]).zfill(10)
                item_row["SHEET_ITEM"] = str(li.get("sheet_item", "10"))
            else:
                # Goods item — quantity/unit based.
                item_row["QUANTITY"] = str(li.get("quantity", 0))
                item_row["PO_UNIT"] = li.get("po_unit", li.get("unit", "ST"))
                # GR-based invoice verification (EKPO-WEBRE='X'): the line must
                # reference its goods-receipt material document, else SAP rejects
                # with "Fill in mandatory field REF_DOC/REF_DOC_YEAR/REF_DOC_IT".
                if li.get("ref_doc"):
                    item_row["REF_DOC"] = str(li["ref_doc"]).zfill(10)
                    item_row["REF_DOC_YEAR"] = str(li.get("ref_doc_year", ""))
                    item_row["REF_DOC_IT"] = str(li.get("ref_doc_item", "1")).zfill(4)
            if li.get("cond_type"):
                item_row["COND_TYPE"] = li["cond_type"]  # planned delivery cost
            item_data_rows.append(item_row)

        # ── TAXDATA — aggregate tax line (if tax present) ────────
        tax_data_rows = []
        if tax_amount and tax_amount > 0:
            tax_data_rows.append({
                "TAX_CODE": tax_code,
                "TAX_AMOUNT": str(tax_amount),
            })

        # PARK (BAPI_INCOMINGINVOICE_PARK) saves the invoice as a held document
        # with NO accounting posting — a SAP user reviews and posts it later (MIR7).
        # POST (BAPI_INCOMINGINVOICE_CREATE1) creates the final posted document (MIRO).
        # VALIDATE is a dry run: it calls PARK to exercise every SAP validation
        # (duplicate check, entry-sheet/account assignment, dates, tax) but ALWAYS
        # rolls back, so no document is created — used to pre-flight an invoice at
        # submit-for-approval time.
        bapi_name = "BAPI_INCOMINGINVOICE_CREATE1" if mode == "post" else "BAPI_INCOMINGINVOICE_PARK"
        verb = {"park": "Parking", "post": "Posting", "validate": "Validating"}.get(mode, "Posting")
        logger.info(
            f"{verb} invoice to SAP via {bapi_name}: ref={invoice_number}, PO={po_num}, "
            f"vendor={vendor_number}, amount={gross_amount} {currency}, "
            f"{len(item_data_rows)} line items"
        )

        # ── Call BAPI ────────────────────────────────────────────
        result = sap.call(
            bapi_name,
            input_structures={
                "HEADERDATA": header_data,
            },
            input_tables={
                "ITEMDATA": item_data_rows,
                "TAXDATA": tax_data_rows,
            },
            tables=["RETURN"],
            table_fields={
                "RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE", "MESSAGE_V1", "MESSAGE_V2"],
            },
            output_params=["INVOICEDOCNUMBER", "FISCALYEAR"],
        )

        doc_number = result.get("INVOICEDOCNUMBER", "").strip()
        fiscal_year = result.get("FISCALYEAR", "").strip()
        return_messages = result.get("RETURN", [])

        # Check for errors in RETURN table
        errors = [
            msg for msg in return_messages
            if msg.get("TYPE", "").strip() in ("E", "A")  # Error or Abort
        ]

        # ── VALIDATE (dry run): never persist — roll back and report ──
        if mode == "validate":
            try:
                sap.call("BAPI_TRANSACTION_ROLLBACK")
            except Exception:
                pass
            error_texts = [m.get("MESSAGE", "Unknown error") for m in errors]
            logger.info(
                f"SAP validation for {invoice_number}: "
                f"{'FAILED — ' + '; '.join(error_texts) if errors else 'passed'}"
            )
            return {
                "success": not errors,
                "validation": True,
                "invoice_doc_number": "",
                "fiscal_year": "",
                "message": "; ".join(error_texts) if errors else "SAP validation passed — no errors.",
                "return_messages": return_messages,
            }

        if errors:
            error_texts = [msg.get("MESSAGE", "Unknown error") for msg in errors]
            logger.error(f"SAP posting failed: {error_texts}")
            return {
                "success": False,
                "invoice_doc_number": "",
                "fiscal_year": "",
                "message": "; ".join(error_texts),
                "return_messages": return_messages,
            }

        if not doc_number:
            logger.error("SAP returned no document number and no errors")
            return {
                "success": False,
                "invoice_doc_number": "",
                "fiscal_year": "",
                "message": "SAP returned no document number. Check RETURN messages.",
                "return_messages": return_messages,
            }

        # ── Commit the transaction ───────────────────────────────
        sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")

        done = "parked" if mode == "park" else "posted"
        logger.info(f"SAP invoice {done}: doc={doc_number}, year={fiscal_year}")

        return {
            "success": True,
            "invoice_doc_number": doc_number,
            "fiscal_year": fiscal_year,
            "mode": mode,
            "message": f"Invoice {done} successfully as document {doc_number}/{fiscal_year}",
            "return_messages": return_messages,
        }

    except Exception as e:
        # Rollback on failure
        try:
            sap.call("BAPI_TRANSACTION_ROLLBACK")
        except Exception:
            pass
        logger.error(f"SAP invoice posting exception: {e}")
        raise

    finally:
        sap.disconnect()


def unpark_invoice_in_sap(doc_number: str, fiscal_year: str) -> dict:
    """Delete a PARKED incoming invoice in SAP (BAPI_INCOMINGINVOICE_DELETE).

    Includes a reversal check: if the document no longer exists in SAP (already
    deleted), it's treated as success so our record can still be soft-deleted.

    Returns: {success, already_gone, message, return_messages}
    """
    sap = _get_connector()
    sap.connect()
    try:
        doc = (doc_number or "").strip().zfill(10)
        year = (fiscal_year or "").strip()

        # ── Reversal check — does the parked doc still exist in RBKP? ──
        try:
            chk = sap.call(
                "RFC_READ_TABLE",
                QUERY_TABLE="RBKP",
                DELIMITER="|",
                input_tables={
                    "OPTIONS": [{"TEXT": f"BELNR = '{doc}' AND GJAHR = '{year}'"}],
                    "FIELDS": [{"FIELDNAME": "RBSTAT"}],  # invoice status
                },
                tables=["DATA", "FIELDS"],
                table_fields={"DATA": ["WA"], "FIELDS": ["FIELDNAME", "OFFSET", "LENGTH"]},
            )
            rows = chk.get("DATA", [])
            if not rows:
                logger.info(f"Parked doc {doc}/{year} not found in SAP — already gone")
                return {"success": True, "already_gone": True,
                        "message": f"Document {doc}/{year} no longer exists in SAP.",
                        "return_messages": []}
        except Exception:
            logger.exception("RBKP reversal check failed; attempting delete anyway")

        # ── Delete the parked document ──
        result = sap.call(
            "BAPI_INCOMINGINVOICE_DELETE",
            INVOICEDOCNUMBER=doc,
            FISCALYEAR=year,
            tables=["RETURN"],
            table_fields={"RETURN": ["TYPE", "ID", "NUMBER", "MESSAGE"]},
        )
        return_messages = result.get("RETURN", [])
        # M8 417 "Document & deleted" is the SUCCESS confirmation of the delete
        # BAPI — SAP returns it with TYPE 'E', but it means the deletion took, so
        # it must NOT be treated as an error (otherwise we roll back the delete).
        errors = [
            m for m in return_messages
            if m.get("TYPE", "").strip() in ("E", "A")
            and not (m.get("ID", "").strip() == "M8" and m.get("NUMBER", "").strip() == "417")
        ]
        if errors:
            try:
                sap.call("BAPI_TRANSACTION_ROLLBACK")
            except Exception:
                pass
            return {"success": False, "already_gone": False,
                    "message": "; ".join(m.get("MESSAGE", "") for m in errors),
                    "return_messages": return_messages}

        sap.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
        logger.info(f"Parked invoice {doc}/{year} deleted (unparked) in SAP")
        return {"success": True, "already_gone": False,
                "message": f"Parked invoice {doc}/{year} deleted in SAP.",
                "return_messages": return_messages}

    except Exception as e:
        try:
            sap.call("BAPI_TRANSACTION_ROLLBACK")
        except Exception:
            pass
        logger.error(f"SAP unpark exception: {e}")
        raise
    finally:
        sap.disconnect()
