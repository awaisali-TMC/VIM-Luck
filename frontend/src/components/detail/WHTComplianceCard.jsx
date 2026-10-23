import Card from "../common/Card";

const STATUS_STYLES = {
  compliant: {
    label: "Compliant",
    bg: "bg-success-bg",
    border: "border-success-base",
    text: "text-success-dark",
    icon: "\u2713",
  },
  non_compliant: {
    label: "Non-Compliant",
    bg: "bg-danger-bg",
    border: "border-danger-base",
    text: "text-danger-dark",
    icon: "\u2717",
  },
  needs_review: {
    label: "Needs Review",
    bg: "bg-warning-bg",
    border: "border-warning-base",
    text: "text-warning-dark",
    icon: "!",
  },
};

export default function WHTComplianceCard({ whtCompliance, fbrStatus, invoice }) {
  if (!whtCompliance && !fbrStatus) return null;

  const style =
    STATUS_STYLES[whtCompliance?.status] || STATUS_STYLES.needs_review;

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-neutral-800 m-0">
          WHT Compliance Check
        </h3>
        {whtCompliance?.status && (
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-2xs font-semibold border ${style.bg} ${style.border} ${style.text}`}
          >
            <span className="font-bold">{style.icon}</span>
            {style.label}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {/* Supplier ATL Status */}
        <div className="flex justify-between text-2xs">
          <span className="text-neutral-500">Supplier ATL Status</span>
          <span className="font-medium text-neutral-800">
            {fbrStatus === "verified_active"
              ? "Active Taxpayer"
              : fbrStatus === "verified_inactive"
              ? "Non-Active Taxpayer"
              : fbrStatus === "not_found"
              ? "Not Found in ATL"
              : "Not Verified"}
          </span>
        </div>

        {/* Detected WHT */}
        {whtCompliance?.detected_rate != null && (
          <div className="flex justify-between text-2xs">
            <span className="text-neutral-500">Detected WHT Rate</span>
            <span className="font-medium text-neutral-800">
              {whtCompliance.detected_rate}%
              {whtCompliance.detected_amount != null && (
                <span className="text-neutral-400 ml-1">
                  ({invoice?.currency || "PKR"}{" "}
                  {Number(whtCompliance.detected_amount).toLocaleString()})
                </span>
              )}
            </span>
          </div>
        )}

        {/* Expected WHT Rate */}
        {whtCompliance?.applicable_rate != null && (
          <div className="flex justify-between text-2xs">
            <span className="text-neutral-500">Expected WHT Rate</span>
            <span className="font-medium text-neutral-800">
              {whtCompliance.applicable_rate}%
            </span>
          </div>
        )}

        {/* Compliance Message */}
        {whtCompliance?.message && (
          <div
            className={`mt-2 px-3 py-2 rounded-md text-2xs border ${style.bg} ${style.border} ${style.text}`}
          >
            {whtCompliance.message}
          </div>
        )}
      </div>
    </Card>
  );
}
