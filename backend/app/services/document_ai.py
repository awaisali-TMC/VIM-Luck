import logging
import time

from google.cloud import documentai_v1 as documentai

from app.config import settings

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "invoice_id": "Invoice #",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "supplier_name": "Vendor Name",
    "supplier_address": "Vendor Address",
    "receiver_name": "Receiver Name",
    "receiver_address": "Receiver Address",
    "total_amount": "Total Amount",
    "net_amount": "Subtotal",
    "total_tax_amount": "Tax Amount",
    "currency": "Currency",
    "purchase_order": "PO Reference",
    "remit_to_address": "Bank / IBAN",
    "invoice_type": "Document Type",
    "supplier_tax_id": "Vendor NTN",
}

DOCUMENT_TYPE_LABELS = {
    "invoice_statement": "Invoice Statement",
    "invoice_receipt": "Invoice / Receipt",
    "invoice": "Tax Invoice",
    "credit_note": "Credit Note",
    "debit_note": "Debit Note",
    "purchase_order": "Purchase Order",
    "remittance_advice": "Remittance Advice",
    "utility_bill": "Utility Bill",
    "statement": "Statement",
    "expense_report": "Expense Report",
    "receipt": "Receipt",
}

CONFIDENCE_THRESHOLD_HIGH = 0.95
CONFIDENCE_THRESHOLD_MEDIUM = 0.85


# ---------------------------------------------------------------------------
#  Text extraction helper (used for form fields, tables, etc.)
# ---------------------------------------------------------------------------

def _layout_to_text(layout, full_text: str) -> str:
    """Extract text from a layout element using text_anchor segments."""
    if not layout or not layout.text_anchor or not layout.text_anchor.text_segments:
        return ""
    parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index)
        end = int(segment.end_index)
        parts.append(full_text[start:end])
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
#  Raw output extraction — build plain dicts directly from Python objects
# ---------------------------------------------------------------------------

def _extract_raw_output(document) -> dict:
    """
    Walk the Document AI response and build a plain-dict representation
    that covers:
      - entities (fields)
      - form_fields (key-value pairs)
      - tables (header_rows + body_rows)
      - ocr text + page-level stats
    No protobuf serialization required — we read attributes directly.
    """
    full_text = document.text or ""

    # --- Entities (same as our parsed fields, but include everything raw) ---
    raw_entities = []
    for entity in document.entities:
        e = {
            "type": entity.type_,
            "mention_text": entity.mention_text,
            "confidence": round(entity.confidence, 4),
        }
        if entity.normalized_value and entity.normalized_value.text:
            e["normalized_value"] = entity.normalized_value.text
        # Nested properties (e.g. line_item sub-fields)
        if entity.properties:
            e["properties"] = []
            for prop in entity.properties:
                p = {
                    "type": prop.type_,
                    "mention_text": prop.mention_text,
                    "confidence": round(prop.confidence, 4),
                }
                if prop.normalized_value and prop.normalized_value.text:
                    p["normalized_value"] = prop.normalized_value.text
                e["properties"].append(p)
        raw_entities.append(e)

    # --- Pages: form fields, tables, blocks/paragraphs/lines ---
    raw_pages = []
    for page in document.pages:
        page_data = {
            "page_number": page.page_number,
            "width": page.dimension.width if page.dimension else None,
            "height": page.dimension.height if page.dimension else None,
        }

        # Detected languages
        if page.detected_languages:
            page_data["languages"] = [
                {"code": dl.language_code, "confidence": round(dl.confidence, 3)}
                for dl in page.detected_languages
            ]

        # Form fields (key-value pairs)
        form_fields = []
        for ff in page.form_fields:
            name_text = _layout_to_text(ff.field_name, full_text)
            value_text = _layout_to_text(ff.field_value, full_text)
            name_conf = round(ff.field_name.confidence, 4) if ff.field_name else None
            value_conf = round(ff.field_value.confidence, 4) if ff.field_value else None
            form_fields.append({
                "key": name_text.rstrip(":").strip(),
                "value": value_text.strip(),
                "key_confidence": name_conf,
                "value_confidence": value_conf,
            })
        if form_fields:
            page_data["form_fields"] = form_fields

        # Tables
        tables = []
        for table in page.tables:
            header_rows = []
            for row in table.header_rows:
                cells = []
                for cell in row.cells:
                    cells.append({
                        "text": _layout_to_text(cell.layout, full_text),
                        "row_span": cell.row_span,
                        "col_span": cell.col_span,
                    })
                header_rows.append(cells)

            body_rows = []
            for row in table.body_rows:
                cells = []
                for cell in row.cells:
                    cells.append({
                        "text": _layout_to_text(cell.layout, full_text),
                        "row_span": cell.row_span,
                        "col_span": cell.col_span,
                    })
                body_rows.append(cells)

            tables.append({
                "header_rows": header_rows,
                "body_rows": body_rows,
            })
        if tables:
            page_data["tables"] = tables

        # Paragraphs (full text of each)
        if page.paragraphs:
            page_data["paragraphs"] = [
                _layout_to_text(p.layout, full_text) for p in page.paragraphs
            ]

        # Lines (full text of each)
        if page.lines:
            page_data["lines"] = [
                _layout_to_text(ln.layout, full_text) for ln in page.lines
            ]

        # Detected barcodes
        if hasattr(page, "detected_barcodes") and page.detected_barcodes:
            page_data["barcodes"] = [
                {
                    "raw_value": bc.barcode.raw_value if bc.barcode else "",
                    "format": bc.barcode.format_ if bc.barcode else "",
                    "value_format": bc.barcode.value_format if bc.barcode else "",
                }
                for bc in page.detected_barcodes
            ]

        # Visual elements (checkboxes, signatures, etc.)
        if page.visual_elements:
            page_data["visual_elements"] = [
                {
                    "type": ve.type_,
                    "text": _layout_to_text(ve.layout, full_text),
                }
                for ve in page.visual_elements
            ]

        # Image quality scores
        if hasattr(page, "image_quality_scores") and page.image_quality_scores:
            iqs = page.image_quality_scores
            page_data["image_quality"] = {
                "quality_score": round(iqs.quality_score, 4) if iqs.quality_score else None,
                "defects": [
                    {"type": d.type_, "confidence": round(d.confidence, 4)}
                    for d in (iqs.detected_defects or [])
                ],
            }

        # Stats
        page_data["block_count"] = len(page.blocks) if page.blocks else 0
        page_data["paragraph_count"] = len(page.paragraphs) if page.paragraphs else 0
        page_data["line_count"] = len(page.lines) if page.lines else 0
        page_data["token_count"] = len(page.tokens) if page.tokens else 0

        raw_pages.append(page_data)

    return {
        "text": full_text,
        "entities": raw_entities,
        "pages": raw_pages,
    }


# ---------------------------------------------------------------------------
#  Client + process
# ---------------------------------------------------------------------------

def _friendly_value(entity_type: str, raw_value: str) -> str:
    """Convert raw Document AI values to user-friendly display text."""
    if entity_type == "invoice_type":
        return DOCUMENT_TYPE_LABELS.get(
            raw_value.strip().lower(),
            raw_value.replace("_", " ").title(),
        )
    return raw_value


def _get_client():
    try:
        return documentai.DocumentProcessorServiceClient()
    except Exception as e:
        raise RuntimeError(
            f"Failed to create Document AI client. "
            f"Check GOOGLE_APPLICATION_CREDENTIALS in .env: {e}"
        )


def process_invoice(file_content: bytes, mime_type: str) -> dict:
    """Send document to Google Document AI Invoice Parser and return structured data."""
    client = _get_client()
    resource_name = client.processor_path(
        settings.GCP_PROJECT_ID,
        settings.GCP_LOCATION,
        settings.DOCAI_PROCESSOR_ID,
    )

    raw_document = documentai.RawDocument(
        content=file_content,
        mime_type=mime_type,
    )

    request = documentai.ProcessRequest(
        name=resource_name,
        raw_document=raw_document,
    )

    start_time = time.time()
    result = client.process_document(request=request)
    processing_time_ms = int((time.time() - start_time) * 1000)

    # Extract raw output by walking the Python objects directly — no
    # protobuf serialization, so nothing can silently fail.
    try:
        raw_output = _extract_raw_output(result.document)
        logger.info(
            "Raw output extracted: %d entities, %d pages, text=%d chars",
            len(raw_output["entities"]),
            len(raw_output["pages"]),
            len(raw_output["text"]),
        )
    except Exception as e:
        logger.error("Failed to extract raw output: %s", e, exc_info=True)
        raw_output = None

    return _parse_document(result.document, processing_time_ms, raw_output)


def _parse_document(document, processing_time_ms: int, raw_output: dict | None = None) -> dict:
    """Parse Document AI response into application schema."""
    fields = []
    line_items = []
    confidences = {}
    warnings = []

    for entity in document.entities:
        entity_type = entity.type_
        mention_text = entity.mention_text
        confidence = round(entity.confidence, 4)

        # Use normalized value if available
        normalized = ""
        if entity.normalized_value and entity.normalized_value.text:
            normalized = entity.normalized_value.text

        display_value = _friendly_value(entity_type, normalized or mention_text)

        if entity_type == "line_item":
            line_item = _parse_line_item(entity)
            line_items.append(line_item)
        else:
            label = FIELD_LABELS.get(
                entity_type, entity_type.replace("_", " ").title()
            )
            conf_percent = round(confidence * 100, 1)
            fields.append(
                {
                    "label": label,
                    "value": display_value,
                    "field_name": entity_type,
                    "confidence": conf_percent,
                }
            )
            confidences[entity_type] = conf_percent

            if confidence < CONFIDENCE_THRESHOLD_MEDIUM:
                warnings.append(
                    f"{label} has low confidence ({conf_percent}%) — manual verification recommended"
                )
            elif confidence < CONFIDENCE_THRESHOLD_HIGH:
                warnings.append(
                    f"{label} confidence is moderate ({conf_percent}%) — consider reviewing"
                )

    # Fix: if total_tax_amount == total_amount, Document AI likely misread — zero it out
    field_vals = {f["field_name"]: f["value"] for f in fields}
    try:
        tax_val = float(str(field_vals.get("total_tax_amount", "")).replace(",", ""))
        total_val = float(str(field_vals.get("total_amount", "")).replace(",", ""))
        if tax_val == total_val:
            for f in fields:
                if f["field_name"] == "total_tax_amount":
                    f["value"] = "0"
                    break
    except (ValueError, TypeError):
        pass

    all_confidences = [f["confidence"] for f in fields]
    overall = (
        round(sum(all_confidences) / len(all_confidences), 1) if all_confidences else 0.0
    )

    doc_type_field = next(
        (f for f in fields if f["field_name"] == "invoice_type"), None
    )
    document_type = doc_type_field["value"] if doc_type_field else "Tax Invoice"
    # Ensure document_type is always friendly (in case value was already mapped)
    document_type = DOCUMENT_TYPE_LABELS.get(
        document_type.strip().lower(), document_type
    )

    page_count = len(document.pages) if document.pages else 1

    return {
        "fields": fields,
        "line_items": line_items,
        "overall_confidence": overall,
        "document_type": document_type,
        "page_count": page_count,
        "processing_time_ms": processing_time_ms,
        "warnings": warnings,
        "field_confidences": confidences,
        "raw_document_ai": raw_output,
    }


def _parse_line_item(entity) -> dict:
    """Extract line item sub-properties."""
    item = {
        "description": None,
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "amount": None,
        "description_confidence": None,
        "quantity_confidence": None,
        "unit_price_confidence": None,
        "amount_confidence": None,
    }

    for prop in entity.properties:
        prop_type = prop.type_
        value = prop.mention_text
        conf = round(prop.confidence * 100, 1)

        if prop.normalized_value and prop.normalized_value.text:
            value = prop.normalized_value.text

        field_key = prop_type.replace("line_item/", "")

        if field_key == "description":
            item["description"] = value
            item["description_confidence"] = conf
        elif field_key == "quantity":
            item["quantity"] = _safe_float(value)
            item["quantity_confidence"] = conf
        elif field_key in ("unit_price", "unit_cost"):
            item["unit_price"] = _safe_float(value)
            item["unit_price_confidence"] = conf
        elif field_key == "amount":
            item["amount"] = _safe_float(value)
            item["amount_confidence"] = conf
        elif field_key == "unit":
            item["unit"] = value

    return item


def _safe_float(value: str) -> float | None:
    """Parse string to float, stripping currency symbols and commas."""
    if not value:
        return None
    try:
        cleaned = (
            value.replace(",", "")
            .replace("PKR", "")
            .replace("Rs", "")
            .replace("Rs.", "")
            .strip()
        )
        return float(cleaned)
    except (ValueError, TypeError):
        return None
