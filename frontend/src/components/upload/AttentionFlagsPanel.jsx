import { useState } from "react";

/**
 * Prominent "Items Needing Attention" panel shown above the extraction results.
 * Surfaces anomalies detected during upload (currency mismatches, math errors,
 * revised/duplicate documents, missing fields, low confidence, etc.).
 *
 * Props:
 *  - flags: Array<{ severity, category, title, message, detail }>
 */

const SEVERITY_STYLES = {
  high: {
    label: "High",
    border: "border-l-danger-base",
    chip: "bg-danger-bg text-danger-dark border-danger-base",
    dot: "bg-danger-base",
    icon: "⚠️", // ⚠️
  },
  medium: {
    label: "Medium",
    border: "border-l-warning-base",
    chip: "bg-warning-bg text-warning-dark border-warning-base",
    dot: "bg-warning-base",
    icon: "⚠️",
  },
  low: {
    label: "Low",
    border: "border-l-info-base",
    chip: "bg-info-bg text-info-dark border-info-base",
    dot: "bg-info-base",
    icon: "ℹ️", // ℹ️
  },
};

const CATEGORY_LABELS = {
  currency: "Currency",
  math: "Amounts",
  tax: "Tax",
  missing_field: "Missing data",
  document: "Document",
  confidence: "Confidence",
};

export default function AttentionFlagsPanel({ flags }) {
  const [collapsed, setCollapsed] = useState(false);

  // No flags → a calm "all clear" confirmation
  if (!flags || flags.length === 0) {
    return (
      <div className="bg-success-bg/60 border border-success-base rounded-base px-4 py-3 flex items-center gap-2.5">
        <span className="text-success-dark text-sm">&#10003;</span>
        <span className="text-xs font-medium text-success-dark">
          No issues detected — all key fields and amounts look consistent.
        </span>
      </div>
    );
  }

  const counts = flags.reduce((acc, f) => {
    const s = (f.severity || "medium").toLowerCase();
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const topSeverity = counts.high ? "high" : counts.medium ? "medium" : "low";
  const headerStyle = SEVERITY_STYLES[topSeverity];

  return (
    <div
      className={`bg-neutral-0 border border-neutral-200 rounded-base shadow-xs overflow-hidden`}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className={`w-full flex items-center justify-between px-4 py-3 bg-transparent border-none
                    border-l-4 ${headerStyle.border} cursor-pointer text-left`}
      >
        <div className="flex items-center gap-2.5">
          <span className="text-base">{headerStyle.icon}</span>
          <span className="text-xs font-bold text-neutral-800">
            Items Needing Attention
          </span>
          <span className="flex items-center gap-1.5 ml-1">
            {["high", "medium", "low"].map((sev) =>
              counts[sev] ? (
                <span
                  key={sev}
                  className={`inline-flex items-center gap-1 text-2xs font-semibold
                              border rounded-full px-2 py-0.5 ${SEVERITY_STYLES[sev].chip}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${SEVERITY_STYLES[sev].dot}`} />
                  {counts[sev]} {SEVERITY_STYLES[sev].label}
                </span>
              ) : null
            )}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-neutral-400 transition-transform ${collapsed ? "" : "rotate-180"}`}
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Flag list */}
      {!collapsed && (
        <div className="border-t border-neutral-100 divide-y divide-neutral-100">
          {flags.map((f, i) => {
            const sev = (f.severity || "medium").toLowerCase();
            const style = SEVERITY_STYLES[sev] || SEVERITY_STYLES.medium;
            return (
              <div
                key={i}
                className={`flex items-start gap-3 px-4 py-3 border-l-4 ${style.border}`}
              >
                <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-neutral-800">
                      {f.title}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide text-neutral-400 font-medium">
                      {CATEGORY_LABELS[f.category] || f.category}
                    </span>
                  </div>
                  <div className="text-2xs text-neutral-600 leading-relaxed mt-0.5">
                    {f.message}
                  </div>
                  {f.detail && (
                    <div className="text-2xs text-neutral-400 leading-relaxed mt-1 font-mono">
                      {f.detail}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
