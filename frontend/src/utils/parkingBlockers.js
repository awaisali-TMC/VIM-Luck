/**
 * Which selected invoice lines cannot be parked to SAP.
 *
 * A parked invoice line has to sit on a PO item: the park payload carries one
 * row per PO item and has no row type for anything else. The backend therefore
 * refuses a selected line it cannot route (routers/sap.py, route_invoice_lines),
 * and this mirrors that rule so the screen can say so before the user tries.
 *
 * A selected line is blocked when ALL of these hold:
 *  - the latest PO match says it is not on the PO ("unmatched"),
 *  - the PO has more than one item (a one-item PO takes every line),
 *  - the layout sends goods lines at all ("delivery" parks planned freight only).
 *
 * Without match data (nothing to compare against) nothing is flagged here; the
 * backend stays the authority and answers with "run PO matching".
 */
export function blockedLineIds(lines, selectedIds, matchStatusById, poLineCount, layout) {
  const blocked = new Set();
  if (!selectedIds || !matchStatusById) return blocked;
  if (layout === "delivery") return blocked;
  if (!(poLineCount > 1)) return blocked;
  for (const li of lines || []) {
    if (selectedIds.has(li.id) && matchStatusById[li.id] === "unmatched") blocked.add(li.id);
  }
  return blocked;
}

const SHOWN = 3;

function shorten(text, max = 40) {
  const t = (text || "").trim() || "(no description)";
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

/** One sentence naming the blocked lines and what to do about them. */
export function blockedLinesMessage(lines, blockedIds) {
  const names = (lines || []).filter((li) => blockedIds.has(li.id)).map((li) => `"${shorten(li.description)}"`);
  const n = names.length;
  if (n === 0) return null;
  const listed = names.slice(0, SHOWN).join(", ") + (n > SHOWN ? ` and ${n - SHOWN} more` : "");
  return (
    `${n} selected line${n > 1 ? "s are" : " is"} not on the PO and cannot be parked: ${listed}. ` +
    `Uncheck or delete ${n > 1 ? "them" : "it"} to continue.`
  );
}
