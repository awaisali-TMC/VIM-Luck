import { useState, useEffect, useCallback } from "react";
import Card from "../components/common/Card";
import KpiCard from "../components/common/KpiCard";
import Badge from "../components/common/Badge";
import api from "../services/api";
import { tokens } from "../styles/tokens";

function fmt(amount, currency = "PKR") {
  if (amount == null) return "---";
  if (amount >= 1e6) return `${currency} ${(amount / 1e6).toFixed(1)}M`;
  if (amount >= 1e3) return `${currency} ${(amount / 1e3).toFixed(0)}K`;
  return `${currency} ${Number(amount).toLocaleString()}`;
}

function pct(val) {
  return val != null ? `${val}%` : "---";
}

const STATUS_COLORS = {
  draft: "#94A3B8",
  pending_processing: "#F59E0B",
  validated: "#3B82F6",
  pending_approval: "#8B5CF6",
  approved: "#10B981",
  rejected: "#EF4444",
  exception: "#EF4444",
  parked: "#F59E0B",
  posted: "#059669",
};

const STATUS_LABELS = {
  draft: "Draft",
  pending_processing: "Processing",
  validated: "Validated",
  pending_approval: "Pending Approval",
  approved: "Approved",
  rejected: "Rejected",
  exception: "Exception",
  parked: "Parked",
  posted: "Posted",
};

export default function AnalyticsDashboard() {
  const [overview, setOverview] = useState(null);
  const [volumeTrend, setVolumeTrend] = useState(null);
  const [suppliers, setSuppliers] = useState(null);
  const [statusDist, setStatusDist] = useState(null);
  const [taxSummary, setTaxSummary] = useState(null);
  const [fbrCompliance, setFbrCompliance] = useState(null);
  const [aging, setAging] = useState(null);
  const [sourceDist, setSourceDist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(30);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, vt, sup, st, tax, fbr, ag, src] = await Promise.all([
        api.get("/api/analytics/overview", { params: { days: period } }),
        api.get("/api/analytics/volume-trend", { params: { days: period * 3, group_by: period <= 30 ? "day" : "week" } }),
        api.get("/api/analytics/by-supplier", { params: { days: period, limit: 10 } }),
        api.get("/api/analytics/by-status", { params: { days: period } }),
        api.get("/api/analytics/tax-summary", { params: { days: period } }),
        api.get("/api/analytics/fbr-compliance", { params: { days: period } }),
        api.get("/api/analytics/aging"),
        api.get("/api/analytics/source-breakdown", { params: { days: period } }),
      ]);
      setOverview(ov.data);
      setVolumeTrend(vt.data);
      setSuppliers(sup.data);
      setStatusDist(st.data);
      setTaxSummary(tax.data);
      setFbrCompliance(fbr.data);
      setAging(ag.data);
      setSourceDist(src.data);
    } catch (err) {
      console.error("Analytics load failed:", err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex flex-col gap-5">
        <div className="text-center py-12 text-sm text-neutral-400">Loading analytics...</div>
      </div>
    );
  }

  const statusTotal = statusDist?.statuses?.reduce((s, r) => s + r.count, 0) || 1;
  const maxVolume = volumeTrend?.data?.length > 0
    ? Math.max(...volumeTrend.data.map((d) => d.count))
    : 1;

  const agingBuckets = aging?.buckets || {};
  const maxBucket = Math.max(...Object.values(agingBuckets), 1);

  return (
    <div className="flex flex-col gap-5">
      {/* Period Selector — the page title is already in the Layout top bar */}
      <div className="flex items-center justify-end">
        <div className="flex items-center gap-1 bg-neutral-100 rounded-base p-0.5">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setPeriod(d)}
              className={`px-3 py-1 text-2xs font-semibold rounded-base cursor-pointer border-none transition-colors ${
                period === d
                  ? "bg-white text-brand-600 shadow-xs"
                  : "bg-transparent text-neutral-500 hover:text-neutral-700"
              }`}
            >
              {d}D
            </button>
          ))}
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-5 gap-4">
        <KpiCard
          label="Total Invoices"
          value={overview?.total_invoices || 0}
          sub={`Last ${period} days`}
          accentColor={tokens.color.brand[500]}
          icon="&#128203;"
        />
        <KpiCard
          label="Total Value"
          value={fmt(overview?.total_amount)}
          sub="All currencies"
          accentColor="#059669"
          icon="&#128176;"
        />
        <KpiCard
          label="Avg AI Confidence"
          value={pct(overview?.avg_confidence)}
          sub="Extraction accuracy"
          accentColor={tokens.color.status.success.base}
          icon="&#127919;"
        />
        <KpiCard
          label="Exception Rate"
          value={pct(overview?.exception_rate)}
          sub={`${overview?.status_counts?.exception || 0} exceptions`}
          accentColor={tokens.color.status.danger.base}
          icon="&#9888;"
        />
        <KpiCard
          label="Straight-Through"
          value={pct(overview?.straight_through_rate)}
          sub="Processed without issues"
          accentColor="#8B5CF6"
          icon="&#9889;"
        />
      </div>

      {/* Row 2: Status Distribution + Volume Trend */}
      <div className="grid grid-cols-2 gap-5">
        {/* Status Distribution */}
        <Card>
          <h3 className="text-xs font-bold text-neutral-800 mb-3">Status Distribution</h3>
          <div className="flex flex-col gap-2">
            {statusDist?.statuses?.map((s) => {
              const pctWidth = Math.max((s.count / statusTotal) * 100, 2);
              return (
                <div key={s.status} className="flex items-center gap-3">
                  <div className="w-28 flex-shrink-0">
                    <Badge status={s.status} size="xs" />
                  </div>
                  <div className="flex-1 h-5 bg-neutral-50 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${pctWidth}%`,
                        backgroundColor: STATUS_COLORS[s.status] || "#94A3B8",
                      }}
                    />
                  </div>
                  <div className="w-10 text-right text-2xs font-bold text-neutral-700">{s.count}</div>
                  <div className="w-20 text-right text-2xs text-neutral-500">
                    {fmt(s.total_amount)}
                  </div>
                </div>
              );
            })}
            {(!statusDist?.statuses || statusDist.statuses.length === 0) && (
              <div className="text-center py-4 text-2xs text-neutral-400">No data</div>
            )}
          </div>
        </Card>

        {/* Volume Trend */}
        <Card>
          <h3 className="text-xs font-bold text-neutral-800 mb-3">Volume Trend</h3>
          {volumeTrend?.data?.length > 0 ? (
            <div className="flex items-end gap-1 h-40">
              {volumeTrend.data.slice(-30).map((d, i) => {
                const h = Math.max((d.count / maxVolume) * 100, 4);
                return (
                  <div
                    key={i}
                    className="flex-1 rounded-t-sm transition-all group relative cursor-default"
                    style={{
                      height: `${h}%`,
                      backgroundColor: tokens.color.brand[400],
                      opacity: 0.7 + (d.count / maxVolume) * 0.3,
                    }}
                    title={`${d.period}: ${d.count} invoices, ${fmt(d.total_amount)}`}
                  />
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-2xs text-neutral-400">No volume data</div>
          )}
          <div className="flex justify-between mt-2 text-2xs text-neutral-400">
            <span>{volumeTrend?.data?.[0]?.period || ""}</span>
            <span>{volumeTrend?.data?.[volumeTrend.data.length - 1]?.period || ""}</span>
          </div>
        </Card>
      </div>

      {/* Row 3: Top Suppliers + Tax Summary */}
      <div className="grid grid-cols-3 gap-5">
        {/* Top Suppliers */}
        <div className="col-span-2">
          <Card>
            <h3 className="text-xs font-bold text-neutral-800 mb-3">Top Suppliers by Value</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-neutral-100">
                    <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Supplier</th>
                    <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Invoices</th>
                    <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Amount</th>
                    <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Avg Conf</th>
                    <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Exceptions</th>
                  </tr>
                </thead>
                <tbody>
                  {suppliers?.suppliers?.map((s, i) => (
                    <tr key={i} className="border-b border-neutral-50 hover:bg-neutral-25">
                      <td className="py-2 px-2 font-medium text-neutral-800 max-w-[200px] truncate">
                        {s.supplier_name}
                      </td>
                      <td className="py-2 px-2 text-right text-neutral-600">{s.invoice_count}</td>
                      <td className="py-2 px-2 text-right font-medium text-neutral-900">{fmt(s.total_amount)}</td>
                      <td className="py-2 px-2 text-right">
                        <span className={`font-medium ${s.avg_confidence >= 80 ? "text-success-dark" : s.avg_confidence >= 60 ? "text-warning-dark" : "text-danger-dark"}`}>
                          {pct(s.avg_confidence)}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right">
                        {s.exception_count > 0 ? (
                          <span className="text-danger-dark font-medium">{s.exception_count}</span>
                        ) : (
                          <span className="text-neutral-400">0</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(!suppliers?.suppliers || suppliers.suppliers.length === 0) && (
                    <tr><td colSpan={5} className="py-4 text-center text-2xs text-neutral-400">No supplier data</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Tax Summary */}
        <Card>
          <h3 className="text-xs font-bold text-neutral-800 mb-3">Tax Summary</h3>
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-2xs text-neutral-500">Invoice Count</span>
              <span className="text-xs font-bold text-neutral-900">{taxSummary?.invoice_count || 0}</span>
            </div>
            <div className="border-t border-neutral-100" />
            <div className="flex items-center justify-between">
              <span className="text-2xs text-neutral-500">Subtotal</span>
              <span className="text-xs font-medium">{fmt(taxSummary?.total_subtotal)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-2xs text-neutral-500">Tax Amount</span>
              <span className="text-xs font-medium text-warning-dark">{fmt(taxSummary?.total_tax)}</span>
            </div>
            {taxSummary?.total_gst > 0 && (
              <div className="flex items-center justify-between ml-3">
                <span className="text-2xs text-neutral-400">GST</span>
                <span className="text-2xs">{fmt(taxSummary.total_gst)}</span>
              </div>
            )}
            {taxSummary?.total_wht > 0 && (
              <div className="flex items-center justify-between ml-3">
                <span className="text-2xs text-neutral-400">WHT</span>
                <span className="text-2xs">{fmt(taxSummary.total_wht)}</span>
              </div>
            )}
            <div className="border-t border-neutral-200" />
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-neutral-700">Total</span>
              <span className="text-sm font-bold text-neutral-900">{fmt(taxSummary?.total_amount)}</span>
            </div>
          </div>

          {/* FBR Compliance Mini */}
          <div className="mt-4 pt-3 border-t border-neutral-100">
            <h4 className="text-2xs font-bold text-neutral-600 uppercase mb-2">FBR Compliance</h4>
            <div className="flex flex-col gap-1.5">
              {Object.entries(fbrCompliance?.fbr_verification || {}).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <span className="text-2xs text-neutral-500 capitalize">{status.replace(/_/g, " ")}</span>
                  <span className="text-2xs font-bold">{count}</span>
                </div>
              ))}
            </div>
            {fbrCompliance?.total_invoices > 0 && (
              <div className="mt-2 text-2xs text-neutral-400">
                {Math.round((fbrCompliance.total_verified / fbrCompliance.total_invoices) * 100)}% verified
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Row 4: Aging + Source */}
      <div className="grid grid-cols-2 gap-5">
        {/* Aging Analysis */}
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-neutral-800">Invoice Aging</h3>
            <span className="text-2xs text-neutral-400">{aging?.total_open || 0} open</span>
          </div>
          <div className="flex items-end gap-3 h-32 mb-2">
            {Object.entries(agingBuckets).map(([bucket, count]) => {
              const h = Math.max((count / maxBucket) * 100, 4);
              const isOld = bucket === "31-60" || bucket === "60+";
              return (
                <div key={bucket} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-2xs font-bold text-neutral-700">{count}</span>
                  <div
                    className="w-full rounded-t-sm transition-all"
                    style={{
                      height: `${h}%`,
                      backgroundColor: isOld ? "#EF4444" : bucket === "15-30" ? "#F59E0B" : "#10B981",
                    }}
                  />
                  <span className="text-2xs text-neutral-500">{bucket}d</span>
                </div>
              );
            })}
          </div>
          {aging?.aged_invoices?.length > 0 && (
            <div className="mt-3 border-t border-neutral-100 pt-2">
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Oldest Invoices</div>
              {aging.aged_invoices.slice(0, 5).map((inv) => (
                <div key={inv.id} className="flex items-center justify-between py-1 text-2xs">
                  <span className="text-brand-600 font-medium">{inv.invoice_number || `#${inv.id}`}</span>
                  <span className="text-neutral-500 truncate max-w-[120px]">{inv.supplier_name || "---"}</span>
                  <Badge status={inv.status} size="xs" />
                  <span className="text-danger-dark font-bold">{inv.age_days}d</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Source + Currency */}
        <Card>
          <h3 className="text-xs font-bold text-neutral-800 mb-3">Intake Sources</h3>
          <div className="grid grid-cols-2 gap-4 mb-4">
            {sourceDist?.sources?.map((s) => (
              <div
                key={s.source}
                className="bg-neutral-25 border border-neutral-100 rounded-base p-3 text-center"
              >
                <div className="text-lg mb-1">{s.source === "email" ? "Email" : "Upload"}</div>
                <div className="text-xl font-bold text-neutral-900">{s.count}</div>
                <div className="text-2xs text-neutral-500 capitalize">{s.source}</div>
                <div className="text-2xs text-neutral-400 mt-0.5">{fmt(s.total_amount)}</div>
              </div>
            ))}
            {(!sourceDist?.sources || sourceDist.sources.length === 0) && (
              <div className="col-span-2 text-center py-4 text-2xs text-neutral-400">No source data</div>
            )}
          </div>

          {/* Processing Speed */}
          <div className="border-t border-neutral-100 pt-3">
            <h4 className="text-2xs font-bold text-neutral-600 uppercase mb-2">Processing Performance</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-neutral-25 rounded-base p-2 text-center">
                <div className="text-sm font-bold text-neutral-900">
                  {overview?.avg_processing_ms ? `${(overview.avg_processing_ms / 1000).toFixed(1)}s` : "---"}
                </div>
                <div className="text-2xs text-neutral-500">Avg Processing</div>
              </div>
              <div className="bg-neutral-25 rounded-base p-2 text-center">
                <div className="text-sm font-bold text-neutral-900">
                  {overview?.pending_approval || 0}
                </div>
                <div className="text-2xs text-neutral-500">Awaiting Approval</div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
