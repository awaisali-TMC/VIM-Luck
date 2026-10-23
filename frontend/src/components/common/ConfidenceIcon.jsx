/**
 * Small info icon that shows an AI confidence tooltip on hover.
 * Color-coded: green >= 85%, amber >= 60%, red below.
 *
 * Props:
 *  - confidence: number (0-100) or null
 */
export default function ConfidenceIcon({ confidence }) {
  if (confidence == null) return null;

  const rounded = Math.round(confidence);
  let dotColor, ringColor, tooltipBg, tooltipText;

  if (confidence >= 85) {
    dotColor = "bg-emerald-500";
    ringColor = "hover:ring-emerald-200";
    tooltipBg = "bg-emerald-700";
    tooltipText = `AI Confidence: ${rounded}%`;
  } else if (confidence >= 60) {
    dotColor = "bg-amber-500";
    ringColor = "hover:ring-amber-200";
    tooltipBg = "bg-amber-700";
    tooltipText = `AI Confidence: ${rounded}% — Review suggested`;
  } else {
    dotColor = "bg-red-500";
    ringColor = "hover:ring-red-200";
    tooltipBg = "bg-red-700";
    tooltipText = `AI Confidence: ${rounded}% — Needs verification`;
  }

  return (
    <span className="relative inline-flex items-center group">
      <span
        className={`inline-flex items-center justify-center w-3.5 h-3.5 rounded-full cursor-help transition-all ring-0 ring-transparent ${ringColor} hover:ring-4 ${dotColor}`}
      >
        <svg
          width="8"
          height="8"
          viewBox="0 0 8 8"
          fill="none"
          className="opacity-90"
        >
          <path
            d="M4 1.5V1.5M4 3.25V6"
            stroke="white"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </svg>
      </span>
      {/* Tooltip */}
      <span
        className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded text-[10px] font-medium text-white whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-150 ${tooltipBg}`}
      >
        {tooltipText}
      </span>
    </span>
  );
}
