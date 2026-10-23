import { useState, useEffect } from "react";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import KpiCard from "../components/common/KpiCard";
import DataTable from "../components/common/DataTable";
import ChartTooltip from "../components/common/ChartTooltip";
import api from "../services/api";
import { tokens } from "../styles/tokens";
import { CHART_AXIS_STYLE, CHART_GRID_STYLE } from "../utils/chartConfig";

const FBR_STATUS_LABELS = {
  verified_active: "Verified — Active",
  verified_inactive: "Verified — Inactive",
  not_verified: "Not Verified",
  verification_failed: "Verification Failed",
};

function fmtPkr(n) {
  if (n == null) return "PKR 0";
  if (Math.abs(n) >= 1000000) return `PKR ${(n / 1000000).toFixed(1)}M`;
  return `PKR ${Number(n).toLocaleString()}`;
}

export default function TaxManagerDashboard({ onViewInvoice }) {
  const [loading, setLoading] = useState(true);
  const [taxSummary, setTaxSummary] = useState(null);
  const [fbr, setFbr] = useState(null);
  const [rules, setRules] = useState([]);
  const [exceptions, setExceptions] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [tax, fbrRes, rulesRes, excRes] = await Promise.all([
          api.get("/api/analytics/tax-summary", { params: { days: 30 } }),
          api.get("/api/analytics/fbr-compliance", { params: { days: 90 } }),
          api.get("/api/tax-rules", { params: { active_only: true, limit: 10 } }),
          api.get("/api/invoices/", { params: { status: "exception", limit: 8 } }),
        ]);
        setTaxSummary(tax.data);
        setFbr(fbrRes.data);
        setRules(rulesRes.data?.rules || []);
        setExceptions(excRes.data?.invoices || []);
      } catch {
        /* sections render their own empty states */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-sm text-neutral-400">Loading tax dashboard…</div>;
  }

  const fbrData = Object.entries(fbr?.fbr_verification || {}).map(([status, count]) => ({
    status: FBR_STATUS_LABELS[status] || status,
    count,
  }));
  const whtData = Object.entries(fbr?.wht_compliance || {}).map(([status, count]) => ({
    status,
    count,
  }));

  const taxBreakdown = [
    { type: "GST", collected: taxSummary?.total_gst || 0 },
    { type: "WHT", collected: taxSummary?.total_wht || 0 },
    { type: "All Taxes", collected: taxSummary?.total_tax || 0 },
  ].filter((t) => t.collected > 0);

  return (
    <div>
      {/* KPIs — live, last 30 days */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KpiCard size="lg" label="Invoices (30d)" value={String(taxSummary?.invoice_count || 0)} sub={fmtPkr(taxSummary?.total_amount)} accentColor={tokens.color.brand[500]} icon="📋" />
        <KpiCard size="lg" label="Tax Amount" value={fmtPkr(taxSummary?.total_tax)} sub="All taxes, 30 days" accentColor={tokens.color.status.success.base} icon="✓" />
        <KpiCard size="lg" label="GST" value={fmtPkr(taxSummary?.total_gst)} sub="Sales tax detected" accentColor={tokens.color.status.info.base} icon="🏛" />
        <KpiCard size="lg" label="WHT" value={fmtPkr(taxSummary?.total_wht)} sub="Withholding detected" accentColor={tokens.color.status.warning.base} icon="⚖" />
        <KpiCard size="lg" label="FBR Verified" value={`${fbr?.total_verified || 0}/${fbr?.total_invoices || 0}`} sub="ATL checks, 90 days" accentColor={tokens.color.status.posted.base} icon="🛡" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-5 mb-6">
        <Card title="FBR ATL Verification" subtitle="Vendor verification status — last 90 days">
          {fbrData.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No invoices in this period</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={fbrData} layout="vertical" barSize={24} margin={{ left: 10, right: 30 }}>
                <CartesianGrid {...CHART_GRID_STYLE} />
                <XAxis type="number" tick={CHART_AXIS_STYLE} allowDecimals={false} />
                <YAxis type="category" dataKey="status" tick={{ fontSize: 11, fill: tokens.color.neutral[600], fontWeight: 500 }} width={130} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Invoices" radius={[0, 6, 6, 0]} fill={tokens.color.brand[400]} label={{ position: "right", fontSize: 11, fontWeight: 600, fill: tokens.color.neutral[600] }} />
              </BarChart>
            </ResponsiveContainer>
          )}
          {whtData.length > 0 && (
            <div className="flex gap-4 pt-2 border-t border-neutral-100 text-2xs text-neutral-500">
              WHT compliance:&nbsp;
              {whtData.map((w) => (
                <span key={w.status}>
                  {w.status}: <strong className="text-neutral-800">{w.count}</strong>
                </span>
              ))}
            </div>
          )}
        </Card>

        <Card title="Tax Detected by Type" subtitle="Last 30 days">
          {taxBreakdown.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No tax amounts detected yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={taxBreakdown} layout="vertical" barSize={18}>
                <CartesianGrid {...CHART_GRID_STYLE} />
                <XAxis type="number" tick={CHART_AXIS_STYLE} tickFormatter={(v) => fmtPkr(v)} />
                <YAxis type="category" dataKey="type" tick={CHART_AXIS_STYLE} width={80} />
                <Tooltip content={<ChartTooltip />} formatter={(v) => fmtPkr(v)} />
                <Bar dataKey="collected" name="Amount" fill={tokens.color.brand[500]} radius={[0, 4, 4, 0]}>
                  {taxBreakdown.map((_, i) => (
                    <Cell key={i} fill={tokens.color.chart[i % tokens.color.chart.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Active FBR tax rules — live from the rules engine */}
      <div className="mb-6">
        <Card title="Jurisdiction Tax Rules — Pakistan" subtitle="Active rules (manage under Admin → FBR Tax Rules)" noPad>
          {rules.length === 0 ? (
            <div className="text-center py-10 text-2xs text-neutral-400">No active tax rules configured</div>
          ) : (
            <DataTable
              columns={[
                { key: "rule_name", label: "Rule", render: (v) => <span className="font-semibold">{v}</span> },
                { key: "tax_type", label: "Type", render: (v) => <span className="uppercase">{v}</span> },
                { key: "rate", label: "Rate", render: (v) => `${v}%` },
                { key: "applies_to", label: "Applies To", render: (v) => <span className="capitalize">{v || "all"}</span> },
                { key: "fbr_section", label: "FBR Reference", render: (v) => v || "—" },
                { key: "is_active", label: "Status", render: (v) => <Badge status={v ? "active" : "pending"} size="xs" /> },
              ]}
              data={rules}
            />
          )}
        </Card>
      </div>

      {/* Open exceptions — live */}
      <Card
        title="Tax & Processing Exceptions — Open"
        action={<Badge status={exceptions.length > 0 ? "high" : "low"} label={`${exceptions.length} Open`} />}
        noPad
      >
        {exceptions.length === 0 ? (
          <div className="text-center py-10 text-2xs text-neutral-400">No open exceptions 🎉</div>
        ) : (
          <DataTable
            columns={[
              {
                key: "invoice_number", label: "Invoice",
                render: (v, row) => (
                  <span
                    className="text-brand-600 font-semibold cursor-pointer hover:underline"
                    onClick={() => onViewInvoice?.(row.id)}
                  >
                    {v || `#${row.id}`}
                  </span>
                ),
              },
              { key: "supplier_name", label: "Vendor", render: (v) => v || "—" },
              {
                key: "total_amount", label: "Amount", align: "right",
                render: (v, row) => `${row.currency || "PKR"} ${v != null ? Number(v).toLocaleString() : "—"}`,
              },
              { key: "fbr_verification_status", label: "FBR Status", render: (v) => FBR_STATUS_LABELS[v] || v || "—" },
              { key: "status", label: "Status", render: (v) => <Badge status={v} size="xs" /> },
            ]}
            data={exceptions}
          />
        )}
      </Card>
    </div>
  );
}
