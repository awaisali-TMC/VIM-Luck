import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api from "../../services/api";
import Badge from "../common/Badge";

// refreshKey: re-check when the fields the duplicate key depends on change
// (matched PO, invoice number, NTN).
export default function DuplicateWarningCard({ invoiceId, refreshKey }) {
  // The result is tagged with the inputs it was fetched for, so a stale
  // response is never shown for newer inputs.
  const fetchKey = `${invoiceId}|${refreshKey ?? ""}`;
  const [result, setResult] = useState({ key: null, data: null });
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!invoiceId) return;
    let cancelled = false;
    api
      .get(`/api/invoices/${invoiceId}/duplicates`)
      .then((res) => {
        if (cancelled) return;
        setResult({ key: fetchKey, data: res.data });
        // A blocking duplicate opens with its details showing.
        setExpanded(!!res.data?.is_duplicate);
      })
      .catch(() => {
        if (!cancelled) setResult({ key: fetchKey, data: null });
      });
    return () => { cancelled = true; };
  }, [invoiceId, fetchKey]);

  const data = result.key === fetchKey ? result.data : null;
  if (!data || !data.has_duplicates) return null;

  const duplicates = data.duplicate_matches || [];
  const allMatches = [
    ...duplicates,
    ...data.exact_matches,
    ...data.probable_matches,
    ...data.possible_matches,
  ];

  const severity = duplicates.length > 0
    ? "blocked"
    : data.exact_matches.length > 0
    ? "danger"
    : data.probable_matches.length > 0
    ? "warning"
    : "info";

  const severityConfig = {
    blocked: { bg: "bg-danger-bg", border: "border-danger-base", text: "text-danger-dark", icon: "⛔", title: "Duplicate Invoice — Blocked" },
    danger: { bg: "bg-danger-bg", border: "border-danger-base", text: "text-danger-dark", icon: "🚨", title: "Same Invoice Number Found" },
    warning: { bg: "bg-warning-bg", border: "border-warning-base", text: "text-warning-dark", icon: "⚠️", title: "Probable Duplicate" },
    info: { bg: "bg-info-bg", border: "border-info-base", text: "text-info-dark", icon: "ℹ️", title: "Possible Duplicate" },
  };

  const cfg = severityConfig[severity];
  const matchBadge = { duplicate: "danger", exact: "danger", probable: "warning", possible: "info" };

  return (
    <div className={`${cfg.bg} border ${cfg.border} rounded-lg px-4 py-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{cfg.icon}</span>
          <div>
            <span className={`text-xs font-semibold ${cfg.text}`}>{cfg.title}</span>
            <span className={`text-2xs ${cfg.text} ml-2`}>
              {severity === "blocked"
                ? `Same ${duplicates[0].matched_on.join(", ")} as an earlier invoice. It cannot be submitted for approval or sent to SAP.`
                : `${data.total_matches} potential match${data.total_matches !== 1 ? "es" : ""} found`}
            </span>
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className={`text-2xs font-semibold ${cfg.text} bg-transparent border-none cursor-pointer`}
        >
          {expanded ? "Hide" : "View Details"}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 border-t border-opacity-30 pt-2">
          <table className="w-full text-2xs">
            <thead>
              <tr className="border-b border-opacity-20">
                <th className="text-left py-1 font-semibold">Invoice #</th>
                <th className="text-left py-1 font-semibold">Supplier</th>
                <th className="text-right py-1 font-semibold">Amount</th>
                <th className="text-left py-1 font-semibold">Date</th>
                <th className="text-left py-1 font-semibold">Status</th>
                <th className="text-left py-1 font-semibold">Match</th>
              </tr>
            </thead>
            <tbody>
              {allMatches.map((m) => (
                <tr key={`${m.match_type}-${m.id}`} className="border-b border-opacity-10">
                  <td className="py-1 font-medium">
                    <Link to={`/invoices/${m.id}`} className="underline">{m.invoice_number || `#${m.id}`}</Link>
                  </td>
                  <td className="py-1">{m.supplier_name || "—"}</td>
                  <td className="py-1 text-right">{m.currency} {Number(m.total_amount || 0).toLocaleString()}</td>
                  <td className="py-1">{m.invoice_date || "—"}</td>
                  <td className="py-1"><Badge status={m.status} size="xs" /></td>
                  <td className="py-1" title={m.matched_on ? `Matched on ${m.matched_on.join(", ")}` : undefined}>
                    <Badge status={matchBadge[m.match_type] || "info"} label={m.match_type} size="xs" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
