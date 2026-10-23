import Card from "../common/Card";
import ConfidenceLabel from "../common/ConfidenceLabel";

// Preferred display order — fields not listed here appear at the end
const FIELD_ORDER = [
  "document_type",
  "invoice_id",
  "invoice_number",
  "invoice_date",
  "due_date",
  "payment_terms",
  "purchase_order",
  "receiver_name",
  "receiver_address",
  "currency",
  "net_amount",
  "subtotal",
  "total_tax_amount",
  "total_amount",
];

function sortFields(fields) {
  const orderMap = {};
  FIELD_ORDER.forEach((name, i) => { orderMap[name] = i; });
  return [...fields].sort((a, b) => {
    const ai = orderMap[a.field_name] ?? 999;
    const bi = orderMap[b.field_name] ?? 999;
    return ai - bi;
  });
}

// Amount-related field names
const AMOUNT_FIELDS = new Set([
  "net_amount", "subtotal", "total_amount", "total_tax_amount",
  "tax_amount", "gst_amount", "wht_amount",
]);

function formatValue(value, fieldName) {
  if (!value) return "—";
  if (AMOUNT_FIELDS.has(fieldName)) {
    const num = parseFloat(String(value).replace(/,/g, ""));
    if (!isNaN(num)) return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return value;
}

/**
 * Full-width card displaying all extracted invoice header fields (non-supplier,
 * non-line-item) in a grid layout. Labels act as confidence tooltip triggers.
 *
 * Props:
 *  - fields: Array of { label, value, field_name, confidence }
 */
export default function InvoiceInfoCard({ fields = [] }) {
  if (fields.length === 0) return null;

  const sorted = sortFields(fields);

  return (
    <Card title="Invoice Details">
      <div className="grid grid-cols-4 gap-x-6 gap-y-4">
        {sorted.map((f) => (
          <div key={f.field_name || f.label}>
            <div className="mb-0.5">
              <ConfidenceLabel label={f.label} confidence={f.confidence} />
            </div>
            <div className="text-xs text-neutral-800 font-medium break-words">
              {formatValue(f.value, f.field_name)}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
