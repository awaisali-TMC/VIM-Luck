const STATUS_CONFIG = {
  posted:              { label: "ERP Posting",          bg: "bg-posted-bg",    text: "text-posted-dark",   dot: "bg-posted-base" },
  parked:              { label: "Parked",               bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  validated:           { label: "Validated",            bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  pending_processing:  { label: "Processing",           bg: "bg-pending-bg",   text: "text-pending-dark",  dot: "bg-pending-base" },
  pending_approval:    { label: "Pending Approval",     bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  exception:           { label: "Exception",            bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  matching:            { label: "In Matching",          bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  ocr_review:          { label: "OCR Review",           bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  submitted:           { label: "Submitted",            bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  cleared:             { label: "Cleared",              bg: "bg-posted-bg",    text: "text-posted-dark",   dot: "bg-posted-base" },
  pending:             { label: "Pending",              bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
  draft:               { label: "Draft",                bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
  blocked:             { label: "Blocked",              bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  rejected:            { label: "Rejected",             bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  extracting:          { label: "Extracting...",        bg: "bg-pending-bg",   text: "text-pending-dark",  dot: "bg-pending-base" },
  info:                { label: "Info",                 bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  success:             { label: "Success",              bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  warning:             { label: "Warning",              bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  low:                 { label: "Low",                  bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  medium:              { label: "Medium",               bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  high:                { label: "High",                 bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  active:              { label: "Active",               bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  change:              { label: "Change",               bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  override:            { label: "Override",             bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  escalation:          { label: "Escalation",           bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  system:              { label: "System",               bg: "bg-pending-bg",   text: "text-pending-dark",  dot: "bg-pending-base" },
  // Approval workflow statuses
  approved:            { label: "Approved",              bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  in_progress:         { label: "In Progress",           bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  delegated:           { label: "Delegated",             bg: "bg-pending-bg",   text: "text-pending-dark",  dot: "bg-pending-base" },
  returned:            { label: "Returned",              bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  skipped:             { label: "Skipped",               bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
  upcoming:            { label: "Upcoming",              bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
  // PO statuses
  open:                { label: "Open",                 bg: "bg-info-bg",      text: "text-info-dark",     dot: "bg-info-base" },
  partially_received:  { label: "Partial Receipt",      bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  fully_received:      { label: "Fully Received",       bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  closed:              { label: "Closed",               bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
  cancelled:           { label: "Cancelled",            bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  // PO Match statuses
  full_match:          { label: "Full Match",           bg: "bg-success-bg",   text: "text-success-dark",  dot: "bg-success-base" },
  partial_match:       { label: "Partial Match",        bg: "bg-warning-bg",   text: "text-warning-dark",  dot: "bg-warning-base" },
  mismatch:            { label: "Mismatch",             bg: "bg-danger-bg",    text: "text-danger-dark",   dot: "bg-danger-base" },
  unmatched:           { label: "Unmatched",            bg: "bg-neutral-50",   text: "text-neutral-600",   dot: "bg-neutral-400" },
};

export default function Badge({ status, label: customLabel, size = "sm" }) {
  const cfg = STATUS_CONFIG[status] || {
    label: status,
    bg: "bg-neutral-100",
    text: "text-neutral-700",
    dot: "bg-neutral-400",
  };
  const label = customLabel || cfg.label;

  const sizeClasses = size === "xs"
    ? "text-2xs px-1.5 py-0.5"
    : "text-xs px-2.5 py-0.5";

  return (
    <span className={`inline-flex items-center gap-1.5 ${cfg.bg} ${cfg.text} ${sizeClasses} font-semibold rounded-full whitespace-nowrap tracking-wide`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} shrink-0`} />
      {label}
    </span>
  );
}
