import Card from "../common/Card";
import ConfidenceLabel from "../common/ConfidenceLabel";

const STATUS_STYLES = {
  active: {
    dot: "bg-emerald-500",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-700",
    label: "Active",
  },
  inactive: {
    dot: "bg-red-500",
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-700",
    label: "Inactive",
  },
  not_found: {
    dot: "bg-amber-500",
    bg: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-700",
    label: "Not Found",
  },
  verifying: {
    dot: "bg-blue-400",
    bg: "bg-blue-50",
    border: "border-blue-200",
    text: "text-blue-600",
    label: "Verifying...",
  },
  error: {
    dot: "bg-neutral-400",
    bg: "bg-neutral-50",
    border: "border-neutral-200",
    text: "text-neutral-500",
    label: "Unavailable",
  },
  registered: {
    dot: "bg-emerald-500",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-700",
    label: "Registered",
  },
  not_registered: {
    dot: "bg-amber-500",
    bg: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-700",
    label: "Not Registered",
  },
};

function StatusPill({ styleKey }) {
  const s = STATUS_STYLES[styleKey];
  if (!s) return null;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-2xs font-semibold border ${s.bg} ${s.border} ${s.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

/**
 * Displays supplier information extracted from the invoice,
 * along with Tax Payer status and ERP registration status.
 *
 * Props:
 *  - supplierFields: Array of { label, value, confidence }
 *  - taxPayerStatus: "active" | "inactive"
 *  - erpStatus: "registered" | "not_registered"
 */
export default function SupplierInfoCard({
  supplierFields = [],
  taxPayerStatus = "verifying",
  taxpayerName,
  erpStatus = "not_registered",
}) {
  return (
    <Card title="Supplier">
      <div className="flex gap-6">
        {/* Left: Supplier fields */}
        <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-3">
          {supplierFields.map((f) => (
            <div key={f.label}>
              <div className="mb-0.5">
                <ConfidenceLabel label={f.label} confidence={f.confidence} />
              </div>
              <div className="text-xs text-neutral-800 font-medium">
                {f.value}
              </div>
            </div>
          ))}
        </div>

        {/* Right: Status indicators */}
        <div className="flex flex-col gap-3 min-w-[220px] border-l border-neutral-100 pl-6">
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
              Tax Payer Status
            </div>
            <StatusPill styleKey={taxPayerStatus} />
            {taxpayerName && (
              <div className="text-2xs text-neutral-600 mt-1 truncate max-w-[200px]" title={taxpayerName}>
                {taxpayerName}
              </div>
            )}
          </div>
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
              ERP Registration
            </div>
            <StatusPill styleKey={erpStatus} />
          </div>
        </div>
      </div>
    </Card>
  );
}
