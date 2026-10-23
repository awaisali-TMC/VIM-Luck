import { useState } from "react";

/**
 * Compact inline warnings indicator — designed to sit inside the Upload Card
 * below the FilePreview. Shows a small amber pill with count; expands on click
 * to reveal the full warning list.
 */
export default function WarningsBanner({ warnings }) {
  const [expanded, setExpanded] = useState(false);

  if (!warnings || warnings.length === 0) return null;

  return (
    <div className="mt-3 border-t border-neutral-100 pt-3">
      {/* Compact trigger row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-2xs font-medium text-warning-dark
                   bg-transparent border-none cursor-pointer p-0 hover:text-warning-text
                   transition-colors"
      >
        <span className="inline-flex items-center gap-1.5 bg-warning-bg border border-warning-base rounded-full px-2.5 py-0.5">
          <span>&#9888;&#65039;</span>
          <span className="font-semibold">
            {warnings.length} warning{warnings.length > 1 ? "s" : ""}
          </span>
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`}
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M3 4.5L6 7.5L9 4.5" />
          </svg>
        </span>
        <span className="text-neutral-400">
          {expanded ? "Hide details" : "Low confidence fields detected"}
        </span>
      </button>

      {/* Expandable warning list */}
      {expanded && (
        <div className="mt-2 bg-warning-bg/50 rounded-base px-3 py-2 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="text-2xs text-warning-dark leading-relaxed">
              <span className="text-warning-base mr-1">&bull;</span>
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
