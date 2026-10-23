"""Auto-classify invoices into types based on extracted data and rules.

Classification types:
- po_material: Purchase order for physical goods
- po_service: Purchase order for services
- non_po: Invoice without a purchase order
- import_invoice: International/import invoice
- credit_note: Credit note / credit memo
- debit_note: Debit note / debit memo
- utility: Utility bill (electricity, gas, water, telecom)
- expense: Expense reimbursement / petty cash
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Keywords for classification
CREDIT_NOTE_KEYWORDS = [
    "credit note", "credit memo", "cn-", "credit adjustment", "refund",
    "return", "credit", "allowance",
]
DEBIT_NOTE_KEYWORDS = [
    "debit note", "debit memo", "dn-", "debit adjustment",
    "supplementary", "additional charge",
]
IMPORT_KEYWORDS = [
    "import", "customs", "bill of lading", "bl number", "hs code",
    "c&f", "cif", "fob", "letter of credit", "lc number",
    "port of", "country of origin", "shipping",
]
UTILITY_KEYWORDS = [
    "electricity", "electric bill", "gas bill", "water bill",
    "telephone", "telecom", "internet", "sui northern",
    "sui southern", "k-electric", "lesco", "pesco", "gepco",
    "iesco", "fesco", "mepco", "hesco", "qesco", "tesco",
    "ptcl", "jazz", "telenor", "zong", "ufone",
]
SERVICE_KEYWORDS = [
    "professional services", "consulting", "consultancy",
    "legal fees", "audit fees", "advisory", "management fee",
    "service charges", "labour", "labor", "manpower",
    "training", "maintenance contract", "rental",
    "lease", "subscription", "license fee",
]
MATERIAL_KEYWORDS = [
    "material", "goods", "equipment", "spare parts", "consumables",
    "chemicals", "pipe", "valve", "pump", "motor",
    "steel", "cement", "lubricant", "fuel", "diesel",
    "hardware", "cable", "instrument",
]


def classify_invoice(
    document_type: Optional[str] = None,
    invoice_number: Optional[str] = None,
    supplier_name: Optional[str] = None,
    po_reference: Optional[str] = None,
    line_items: Optional[list] = None,
    currency: Optional[str] = None,
    total_amount: Optional[float] = None,
    detected_taxes: Optional[list] = None,
    raw_text: Optional[str] = None,
) -> dict:
    """
    Classify an invoice based on extracted data.

    Returns:
        {
            "invoice_type": str,
            "confidence": float (0-100),
            "reasoning": str,
            "sub_type": str | None,
        }
    """
    scores = {
        "credit_note": 0,
        "debit_note": 0,
        "import_invoice": 0,
        "utility": 0,
        "po_material": 0,
        "po_service": 0,
        "non_po": 0,
        "expense": 0,
    }
    reasons = []

    # Build searchable text
    text_parts = []
    if document_type:
        text_parts.append(document_type.lower())
    if invoice_number:
        text_parts.append(invoice_number.lower())
    if supplier_name:
        text_parts.append(supplier_name.lower())
    if line_items:
        for li in line_items:
            desc = li.get("description") or ""
            text_parts.append(desc.lower())
    if raw_text:
        text_parts.append(raw_text.lower())
    full_text = " ".join(text_parts)

    # 1. Document type from AI extraction
    if document_type:
        dt = document_type.lower()
        if "credit" in dt:
            scores["credit_note"] += 50
            reasons.append("Document type indicates credit note")
        elif "debit" in dt:
            scores["debit_note"] += 50
            reasons.append("Document type indicates debit note")

    # 2. Keyword matching in full text
    for kw in CREDIT_NOTE_KEYWORDS:
        if kw in full_text:
            scores["credit_note"] += 15
            reasons.append(f"Credit note keyword found: '{kw}'")
            break

    for kw in DEBIT_NOTE_KEYWORDS:
        if kw in full_text:
            scores["debit_note"] += 15
            reasons.append(f"Debit note keyword found: '{kw}'")
            break

    for kw in IMPORT_KEYWORDS:
        if kw in full_text:
            scores["import_invoice"] += 10
            reasons.append(f"Import keyword found: '{kw}'")

    for kw in UTILITY_KEYWORDS:
        if kw in full_text:
            scores["utility"] += 20
            reasons.append(f"Utility keyword found: '{kw}'")
            break

    # 3. PO reference presence
    if po_reference and po_reference.strip():
        scores["po_material"] += 20
        scores["po_service"] += 20
        reasons.append(f"PO reference present: {po_reference}")

        # Differentiate material vs service based on line items
        material_score = 0
        service_score = 0
        for kw in MATERIAL_KEYWORDS:
            if kw in full_text:
                material_score += 1
        for kw in SERVICE_KEYWORDS:
            if kw in full_text:
                service_score += 1

        if material_score > service_score:
            scores["po_material"] += 15
            reasons.append("Line items suggest material/goods")
        elif service_score > material_score:
            scores["po_service"] += 15
            reasons.append("Line items suggest services")
        else:
            scores["po_material"] += 5  # Default to material if ambiguous
    else:
        scores["non_po"] += 15
        reasons.append("No PO reference found")

    # 4. Currency-based classification
    if currency and currency.upper() not in ("PKR", ""):
        scores["import_invoice"] += 15
        reasons.append(f"Foreign currency detected: {currency}")

    # 5. Invoice number pattern
    if invoice_number:
        inv_lower = invoice_number.lower()
        if re.match(r"^cn[-/]", inv_lower) or "credit" in inv_lower:
            scores["credit_note"] += 20
            reasons.append("Invoice number pattern suggests credit note")
        elif re.match(r"^dn[-/]", inv_lower) or "debit" in inv_lower:
            scores["debit_note"] += 20
            reasons.append("Invoice number pattern suggests debit note")

    # 6. Tax-based hints
    if detected_taxes:
        for tax in detected_taxes:
            tax_type = (tax.get("tax_type") or "").lower()
            if "customs" in tax_type or "import" in tax_type:
                scores["import_invoice"] += 10
                reasons.append("Customs/import tax detected")

    # Determine winner
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    # If no strong signal, default to non_po
    if best_score < 10:
        best_type = "non_po"
        best_score = 30
        reasons.append("No strong classification signals; defaulting to non-PO")

    # Normalize confidence
    total_score = sum(scores.values()) or 1
    confidence = min(round((best_score / total_score) * 100, 1), 99)
    if best_score >= 50:
        confidence = max(confidence, 75)

    # Sub-type
    sub_type = None
    if best_type == "utility":
        for kw in ["electricity", "gas", "water", "telecom", "internet", "telephone"]:
            if kw in full_text:
                sub_type = kw
                break

    return {
        "invoice_type": best_type,
        "confidence": confidence,
        "reasoning": "; ".join(reasons[:5]),
        "sub_type": sub_type,
        "all_scores": scores,
    }
