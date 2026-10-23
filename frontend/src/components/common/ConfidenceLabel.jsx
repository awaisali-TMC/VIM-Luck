/**
 * Renders a field label that doubles as a confidence tooltip trigger.
 * The label gets a subtle dotted underline when confidence data exists,
 * and hovering reveals the AI confidence tooltip.
 *
 * Props:
 *  - label: string
 *  - confidence: number (0-100) or null
 */
export default function ConfidenceLabel({ label, confidence }) {
  // No confidence data — plain label
  if (confidence == null) {
    return (
      <span className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider">
        {label}
      </span>
    );
  }

  const rounded = Math.round(confidence);
  let underlineColor, tooltipBg, tooltipText;

  if (confidence >= 85) {
    underlineColor = "decoration-emerald-400";
    tooltipBg = "bg-emerald-700";
    tooltipText = `AI Confidence: ${rounded}%`;
  } else if (confidence >= 60) {
    underlineColor = "decoration-amber-400";
    tooltipBg = "bg-amber-700";
    tooltipText = `AI Confidence: ${rounded}% — Review suggested`;
  } else {
    underlineColor = "decoration-red-400";
    tooltipBg = "bg-red-700";
    tooltipText = `AI Confidence: ${rounded}% — Needs verification`;
  }

  return (
    <span className="relative inline-flex group">
      <span
        className={`text-2xs font-semibold text-neutral-500 uppercase tracking-wider cursor-help underline decoration-dotted underline-offset-2 ${underlineColor}`}
      >
        {label}
      </span>
      {/* Tooltip */}
      <span
        className={`absolute bottom-full left-0 mb-1.5 px-2 py-1 rounded text-[10px] font-medium text-white whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 z-10 ${tooltipBg}`}
      >
        {tooltipText}
      </span>
    </span>
  );
}
