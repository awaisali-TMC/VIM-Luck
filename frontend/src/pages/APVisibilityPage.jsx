import { useState, useEffect } from "react";
import Card from "../components/common/Card";
import KpiCard from "../components/common/KpiCard";
import Badge from "../components/common/Badge";
import api from "../services/api";
import { getInvoices } from "../services/invoiceService";
import { tokens } from "../styles/tokens";

// Pipeline stages in processing order (exception shown separately)
const PIPELINE = [
  { key: "draft", label: "Received" },
  { key: "pending_processing", label: "Validated" },
  { key: "validated", label: "Approved" },
  { key: "pending_approval", label: "In Approval" },
  { key: "approved", label: "Ready to Post" },
  { key: "posted", label: "Posted to ERP" },
];

const SOURCE_LABELS = {
  upload: { label: "Web Upload", icon: "🖥" },
  web_upload: { label: "Web Upload", icon: "🖥" },
  email: { label: "Email", icon: "📬" },
  supplier: { label: "Supplier Portal", icon: "🏢" },
  mobile_upload: { label: "Mobile Scan", icon: "📱" },
  po_flip: { label: "PO Flip", icon: "🔁" },
  manual: { label: "Manual", icon: "✍" },
};

function sourceInfo(s) {
  return SOURCE_LABELS[s] || { label: s || "Unknown", icon: "❔" };
}

function ageDays(createdAt) {
  if (!createdAt) return 0;
  return Math.floor((Date.now() - new Date(createdAt).getTime()) / 86400000);
}

function fmtAmount(n) {
  if (n == null) return "—";
  return `PKR ${Number(n).toLocaleString()}`;
}

export default function APVisibilityPage({ onViewInvoice }) {
  const [loading, setLoading] = useState(true);
  const [statusDist, setStatusDist] = useState(null);
  const [sources, setSources] = useState(null);
  const [aging, setAging] = useState(null);
  const [invoices, setInvoices] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [statusRes, sourceRes, agingRes, invRes] = await Promise.all([
          api.get("/api/analytics/by-status", { params: { days: 90 } }),
          api.get("/api/analytics/source-breakdown", { params: { days: 90 } }),
          api.get("/api/analytics/aging"),
          getInvoices(0, 100),
        ]);
        setStatusDist(statusRes.data);
        setSources(sourceRes.data);
        setAging(agingRes.data);
        setInvoices(invRes.data?.invoices || invRes.invoices || []);
      } catch {
        /* sections render their own empty states */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-sm text-neutral-400">Loading AP pipeline…</div>;
  }

  const statusCounts = {};
  for (const s of statusDist?.statuses || []) statusCounts[s.status] = s.count;

  const buckets = aging?.buckets || {};
  const agedCount = (buckets["15-30"] || 0) + (buckets["31-60"] || 0) + (buckets["60+"] || 0);
  const exceptionCount = statusCounts.exception || 0;
  const openCount = aging?.total_open || 0;

  const maxSource = Math.max(...(sources?.sources || []).map((s) => s.count), 1);

  // Worklist: everything not yet sent to SAP — exceptions first, then oldest first
  const worklist = invoices
    .filter((inv) => !["posted", "parked"].includes(inv.status))
    .sort((a, b) => {
      const exA = a.status === "exception" ? 1 : 0;
      const exB = b.status === "exception" ? 1 : 0;
      if (exA !== exB) return exB - exA;
      return ageDays(b.created_at) - ageDays(a.created_at);
    });

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Open in Pipeline"
          value={openCount}
          sub="Not yet posted to ERP"
          accentColor={tokens.color.brand[500]}
          icon="📥"
        />
        <KpiCard
          label="Exceptions"
          value={exceptionCount}
          sub="Need AP action"
          accentColor={tokens.color.status.danger.base}
          icon="⚠"
        />
        <KpiCard
          label="Aged > 14 Days"
          value={agedCount}
          sub="Stuck invoices"
          accentColor={tokens.color.status.warning.base}
          icon="⏳"
        />
        <KpiCard
          label="Capture Channels"
          value={(sources?.sources || []).length}
          sub="Active invoice sources"
          accentColor="#8B5CF6"
          icon="🛰"
        />
      </div>

      {/* Pipeline strip */}
      <Card title="Processing Pipeline" subtitle="Where invoices are right now (last 90 days)">
        <div className="flex items-stretch gap-2">
          {PIPELINE.map((stage, i) => (
            <div key={stage.key} className="flex items-center gap-2 flex-1 min-w-0">
              <div className="flex-1 bg-neutral-50 border border-neutral-100 rounded-md px-3 py-3 text-center">
                <div className="text-xl font-bold text-neutral-900">
                  {statusCounts[stage.key] || 0}
                </div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wide truncate">
                  {stage.label}
                </div>
              </div>
              {i < PIPELINE.length - 1 && (
                <span className="text-neutral-300 text-sm flex-shrink-0">→</span>
              )}
            </div>
          ))}
          <div className="flex items-center gap-2">
            <span className="text-neutral-200 text-sm">|</span>
            <div className="bg-danger-bg border border-danger-base/20 rounded-md px-3 py-3 text-center min-w-[90px]">
              <div className="text-xl font-bold text-danger-dark">{exceptionCount}</div>
              <div className="text-2xs font-semibold text-danger-dark uppercase tracking-wide">
                Exception
              </div>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {/* Source breakdown */}
        <Card title="Capture Channels" subtitle="Invoice origin (last 90 days)">
          <div className="flex flex-col gap-2.5">
            {(sources?.sources || []).map((s) => {
              const info = sourceInfo(s.source);
              return (
                <div key={s.source} className="flex items-center gap-3">
                  <div className="w-32 flex items-center gap-1.5 text-xs text-neutral-700 flex-shrink-0">
                    <span>{info.icon}</span>
                    <span className="truncate">{info.label}</span>
                  </div>
                  <div className="flex-1 h-5 bg-neutral-50 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-brand-400"
                      style={{ width: `${Math.max((s.count / maxSource) * 100, 3)}%` }}
                    />
                  </div>
                  <div className="w-8 text-right text-2xs font-bold text-neutral-700">{s.count}</div>
                  <div className="w-24 text-right text-2xs text-neutral-500">
                    {fmtAmount(s.total_amount)}
                  </div>
                </div>
              );
            })}
            {(!sources?.sources || sources.sources.length === 0) && (
              <div className="text-center py-6 text-2xs text-neutral-400">No invoices captured yet</div>
            )}
          </div>
        </Card>

        {/* Aging buckets */}
        <Card title="Aging" subtitle="Days since capture (open invoices)">
          <div className="flex items-end gap-3 h-32 px-2">
            {Object.entries(buckets).map(([bucket, count]) => {
              const max = Math.max(...Object.values(buckets), 1);
              const danger = bucket === "31-60" || bucket === "60+";
              return (
                <div key={bucket} className="flex-1 flex flex-col items-center gap-1">
                  <div className="text-2xs font-bold text-neutral-700">{count}</div>
                  <div
                    className={`w-full rounded-t-md ${danger ? "bg-danger-base/70" : "bg-brand-300"}`}
                    style={{ height: `${Math.max((count / max) * 90, 4)}%` }}
                  />
                  <div className="text-2xs text-neutral-500">{bucket}d</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Worklist */}
      <Card title="AP Worklist" subtitle="Exceptions first, then oldest — click to open" noPad>
        {worklist.length === 0 ? (
          <div className="text-center py-10 text-2xs text-neutral-400">
            Nothing pending — pipeline is clear 🎉
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-neutral-25 border-b border-neutral-100">
                  {["Invoice", "Vendor", "Origin", "Stage", "Age", "Amount"].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {worklist.map((inv) => {
                  const info = sourceInfo(inv.source_type);
                  const age = ageDays(inv.created_at);
                  return (
                    <tr
                      key={inv.id}
                      onClick={() => onViewInvoice?.(inv.id)}
                      className="hover:bg-neutral-25 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-2.5 font-mono font-semibold text-neutral-800">
                        {inv.invoice_number || `#${inv.id}`}
                      </td>
                      <td className="px-4 py-2.5 text-neutral-600 max-w-[180px] truncate">
                        {inv.supplier_name || "—"}
                      </td>
                      <td className="px-4 py-2.5 text-neutral-600 whitespace-nowrap">
                        {info.icon} {info.label}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge status={inv.status} size="xs" />
                      </td>
                      <td className={`px-4 py-2.5 whitespace-nowrap font-semibold ${
                        age > 14 ? "text-danger-base" : age > 7 ? "text-warning-dark" : "text-neutral-500"
                      }`}>
                        {age}d
                      </td>
                      <td className="px-4 py-2.5 font-semibold text-neutral-800 whitespace-nowrap">
                        {fmtAmount(inv.total_amount)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
