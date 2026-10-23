const STATUS_MAP = {
  verified_active: {
    label: "ATL Active",
    bg: "bg-success-bg",
    border: "border-success-light",
    text: "text-success-dark",
    dot: "bg-success-base",
  },
  verified_inactive: {
    label: "Non-ATL",
    bg: "bg-danger-bg",
    border: "border-danger-light",
    text: "text-danger-dark",
    dot: "bg-danger-base",
  },
  not_found: {
    label: "NTN Not Found",
    bg: "bg-warning-bg",
    border: "border-warning-light",
    text: "text-warning-dark",
    dot: "bg-warning-base",
  },
  not_verified: {
    label: "Not Verified",
    bg: "bg-neutral-50",
    border: "border-neutral-200",
    text: "text-neutral-500",
    dot: "bg-neutral-400",
  },
  error: {
    label: "Verify Error",
    bg: "bg-neutral-50",
    border: "border-neutral-200",
    text: "text-neutral-500",
    dot: "bg-neutral-400",
  },
};

const SOURCE_LABELS = {
  local_db: "Local DB",
  live_api: "Live API",
};

export default function FBRVerificationBadge({
  status,
  taxpayerName,
  filingStatus,
  source,
  showDetails = false,
  size = "sm",
}) {
  const config = STATUS_MAP[status] || STATUS_MAP.not_verified;
  const isSmall = size === "xs";

  return (
    <div className="inline-flex flex-col items-start">
      <span
        className={`inline-flex items-center gap-1.5 border rounded-full font-semibold ${config.bg} ${config.border} ${config.text} ${
          isSmall ? "px-1.5 py-0.5 text-[9px]" : "px-2.5 py-1 text-2xs"
        }`}
        title={
          taxpayerName
            ? `FBR: ${taxpayerName}${filingStatus ? ` — ${filingStatus}` : ""}${source ? ` (${SOURCE_LABELS[source] || source})` : ""}`
            : config.label
        }
      >
        <span
          className={`rounded-full ${config.dot} ${isSmall ? "w-1.5 h-1.5" : "w-2 h-2"}`}
        />
        {config.label}
      </span>

      {showDetails && taxpayerName && status !== "not_verified" && (
        <span className="text-[10px] text-neutral-500 mt-0.5 pl-1 truncate max-w-[200px]">
          FBR: {taxpayerName}
          {source && (
            <span className="text-neutral-400 ml-1">
              ({SOURCE_LABELS[source] || source})
            </span>
          )}
        </span>
      )}
    </div>
  );
}
