// Date-range presets shared by the filter UI and the pages that consume it.
// Kept out of the component file so fast-refresh stays happy.

const iso = (d) => d.toISOString().slice(0, 10);

/** OGDCL fiscal year runs July → June. Returns the FY start for a given date. */
function fyStart(now) {
  const y = now.getFullYear();
  return new Date(Date.UTC(now.getMonth() >= 6 ? y : y - 1, 6, 1));
}

export const DATE_PRESETS = [
  { key: "30", label: "Last 30 days" },
  { key: "90", label: "Last 90 days" },
  { key: "365", label: "Last 12 months" },
  { key: "fy", label: "This fiscal year" },
  { key: "custom", label: "Custom range" },
];

/** Resolve a preset (+ optional custom dates) to { date_from, date_to }. */
export function resolveDateRange({ preset, date_from, date_to }) {
  const now = new Date();
  const today = iso(now);
  if (preset === "custom") return { date_from: date_from || null, date_to: date_to || null };
  if (preset === "fy") return { date_from: iso(fyStart(now)), date_to: today };
  const days = Number(preset) || 90;
  const from = new Date(now);
  from.setDate(from.getDate() - days);
  return { date_from: iso(from), date_to: today };
}
