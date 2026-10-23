import { useState, useEffect } from "react";
import api from "../../services/api";
import Card from "../common/Card";
import Badge from "../common/Badge";

export default function DuplicateWarningCard({ invoiceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!invoiceId) return;
    setLoading(true);
    api
      .get(`/api/invoices/${invoiceId}/duplicates`)
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [invoiceId]);

  if (loading || !data || !data.has_duplicates) return null;

  const allMatches = [
    ...data.exact_matches,
    ...data.probable_matches,
    ...data.possible_matches,
  ];

  const severity = data.exact_matches.length > 0
    ? "danger"
    : data.probable_matches.length > 0
    ? "warning"
    : "info";

  const severityConfig = {
    danger: { bg: "bg-danger-bg", border: "border-danger-base", text: "text-danger-dark", icon: "🚨", title: "Exact Duplicate Found" },
    warning: { bg: "bg-warning-bg", border: "border-warning-base", text: "text-warning-dark", icon: "⚠️", title: "Probable Duplicate" },
    info: { bg: "bg-info-bg", border: "border-info-base", text: "text-info-dark", icon: "ℹ️", title: "Possible Duplicate" },
  };

  const cfg = severityConfig[severity];

  return (
    <div className={`${cfg.bg} border ${cfg.border} rounded-lg px-4 py-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{cfg.icon}</span>
          <div>
            <span className={`text-xs font-semibold ${cfg.text}`}>{cfg.title}</span>
            <span className={`text-2xs ${cfg.text} ml-2`}>
              {data.total_matches} potential match{data.total_matches !== 1 ? "es" : ""} found
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
                <tr key={m.id} className="border-b border-opacity-10">
                  <td className="py-1 font-medium">{m.invoice_number || `#${m.id}`}</td>
                  <td className="py-1">{m.supplier_name || "—"}</td>
                  <td className="py-1 text-right">{m.currency} {Number(m.total_amount || 0).toLocaleString()}</td>
                  <td className="py-1">{m.invoice_date || "—"}</td>
                  <td className="py-1"><Badge status={m.status} size="xs" /></td>
                  <td className="py-1">
                    <Badge
                      status={m.match_type === "exact" ? "danger" : m.match_type === "probable" ? "warning" : "info"}
                      label={m.match_type}
                      size="xs"
                    />
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
