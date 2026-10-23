import Card from "../common/Card";

const FIELD_GROUPS = [
  {
    title: "Invoice Details",
    fields: [
      { key: "invoice_number", label: "Invoice #" },
      { key: "invoice_date", label: "Invoice Date" },
      { key: "due_date", label: "Due Date" },
      { key: "currency", label: "Currency" },
      { key: "document_type", label: "Document Type" },
      { key: "po_reference", label: "PO Reference" },
    ],
  },
  {
    title: "Vendor Information",
    fields: [
      { key: "supplier_name", label: "Vendor Name" },
      { key: "supplier_address", label: "Vendor Address" },
      { key: "supplier_ntn", label: "Vendor NTN" },
    ],
  },
  {
    title: "Receiver Information",
    fields: [
      { key: "receiver_name", label: "Receiver Name" },
      { key: "receiver_address", label: "Receiver Address" },
    ],
  },
  {
    title: "Financial Details",
    fields: [
      { key: "subtotal_amount", label: "Subtotal", type: "number" },
      { key: "tax_amount", label: "Tax Amount", type: "number" },
      { key: "gst_amount", label: "GST Amount", type: "number" },
      { key: "wht_amount", label: "WHT Amount", type: "number" },
      { key: "total_amount", label: "Total Amount", type: "number" },
      { key: "bank_iban", label: "Bank IBAN" },
    ],
  },
];

function confidenceColor(c) {
  if (c == null) return { dot: "bg-neutral-300", text: "text-neutral-400" };
  if (c >= 95) return { dot: "bg-success-base", text: "text-success-base" };
  if (c >= 85) return { dot: "bg-warning-base", text: "text-warning-base" };
  return { dot: "bg-danger-base", text: "text-danger-base" };
}

function formatValue(value, type) {
  if (value == null || value === "") return "\u2014";
  if (type === "number" && typeof value === "number") {
    return Number(value).toLocaleString();
  }
  return String(value);
}

export default function InvoiceDetailFields({
  invoice,
  editing,
  editFields,
  onFieldChange,
  onFieldBlur,   // (key, value) => persist a single field (inline autosave)
}) {
  if (!invoice) return null;

  const confidences = invoice.field_confidences || {};

  return (
    <Card
      title="Invoice Fields"
      subtitle={editing ? "Click a field to edit — changes save automatically" : "AI-extracted values with confidence"}
      noPad
    >
      <div className="divide-y divide-neutral-100">
        {FIELD_GROUPS.map((group) => (
          <div key={group.title}>
            {/* Group header */}
            <div className="bg-neutral-25 px-3.5 py-1.5 border-b border-neutral-100">
              <span className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider">
                {group.title}
              </span>
            </div>

            {/* Field rows */}
            <table className="w-full border-collapse text-xs">
              <tbody>
                {group.fields.map((field, i) => {
                  const rawValue = invoice[field.key];
                  const conf = confidences[field.key];
                  const colors = confidenceColor(conf);

                  return (
                    <tr
                      key={field.key}
                      className={i % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}
                    >
                      {/* Label */}
                      <td className="px-3.5 py-2 border-b border-neutral-50 text-neutral-500 text-2xs font-medium w-[140px]">
                        {field.label}
                      </td>

                      {/* Value or Input */}
                      <td className="px-3.5 py-2 border-b border-neutral-50 text-neutral-900 font-medium">
                        {editing ? (
                          <input
                            type={field.type === "number" ? "number" : "text"}
                            step={field.type === "number" ? "0.01" : undefined}
                            value={editFields[field.key] ?? ""}
                            onChange={(e) =>
                              onFieldChange(
                                field.key,
                                field.type === "number"
                                  ? e.target.value === ""
                                    ? null
                                    : parseFloat(e.target.value)
                                  : e.target.value
                              )
                            }
                            onBlur={(e) =>
                              onFieldBlur?.(
                                field.key,
                                field.type === "number"
                                  ? e.target.value === "" ? null : parseFloat(e.target.value)
                                  : e.target.value
                              )
                            }
                            className="w-full bg-neutral-0 border border-neutral-200 rounded-base px-2 py-1 text-xs
                                       outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400/20 transition-colors"
                          />
                        ) : (
                          formatValue(rawValue, field.type)
                        )}
                      </td>

                      {/* Confidence */}
                      <td className="px-3.5 py-2 border-b border-neutral-50 text-center w-[70px]">
                        <span className="inline-flex items-center gap-1">
                          <span
                            className={`w-[7px] h-[7px] rounded-full ${colors.dot}`}
                          />
                          <span
                            className={`text-2xs font-semibold ${colors.text}`}
                          >
                            {conf != null ? `${Math.round(conf)}%` : "N/A"}
                          </span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Card>
  );
}
