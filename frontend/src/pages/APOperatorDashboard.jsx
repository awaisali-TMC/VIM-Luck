import { useState, useEffect } from "react";
import {
  BarChart, Bar, Treemap, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import KpiCard from "../components/common/KpiCard";
import ConfidenceMeter from "../components/common/ConfidenceMeter";
import DataTable from "../components/common/DataTable";
import ChartTooltip from "../components/common/ChartTooltip";
import api from "../services/api";
import { getInvoices } from "../services/invoiceService";
import { tokens } from "../styles/tokens";
import { CHART_AXIS_STYLE } from "../utils/chartConfig";

const STAGE_LABELS = {
  draft: "Received",
  pending_processing: "Validated",
  validated: "Approved",
  pending_approval: "In Approval",
  approved: "Ready to Post",
  posted: "Posted",
  exception: "Exception",
  rejected: "Rejected",
};

export default function APOperatorDashboard({ onViewInvoice, onOpenInbox }) {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [statusDist, setStatusDist] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [ov, st, sup, inv] = await Promise.all([
          api.get("/api/analytics/overview", { params: { days: 30 } }),
          api.get("/api/analytics/by-status", { params: { days: 30 } }),
          api.get("/api/analytics/by-supplier", { params: { days: 90, limit: 12 } }),
          getInvoices(0, 5),
        ]);
        setOverview(ov.data);
        setStatusDist(st.data);
        setSuppliers(sup.data?.suppliers || []);
        setRecent(inv.invoices || []);
      } catch {
        /* sections render their own empty states */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-sm text-neutral-400">Loading dashboard…</div>;
  }

  const counts = overview?.status_counts || {};
  const total = overview?.total_invoices || 0;
  const openCount = total - (counts.posted || 0) - (counts.parked || 0) - (counts.rejected || 0);

  const pipelineData = (statusDist?.statuses || []).map((s) => ({
    stage: STAGE_LABELS[s.status] || s.status,
    count: s.count,
  }));

  const treemapData = suppliers
    .filter((s) => (s.total_amount || 0) > 0)
    .map((s) => ({
      name: s.supplier_name,
      value: s.total_amount,
      hasExceptions: (s.exception_count || 0) > 0,
    }));

  return (
    <div>
      {/* KPIs — live, last 30 days */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KpiCard size="lg" label="In Pipeline" value={String(openCount)} sub="Not yet posted" accentColor={tokens.color.brand[500]} icon="📥" />
        <KpiCard size="lg" label="Invoices (30d)" value={String(total)} sub={`PKR ${Number(overview?.total_amount || 0).toLocaleString()}`} accentColor={tokens.color.status.success.base} icon="✓" />
        <KpiCard size="lg" label="Avg Confidence" value={`${overview?.avg_confidence || 0}%`} sub="AI extraction" accentColor={tokens.color.status.info.base} icon="🤖" />
        <KpiCard size="lg" label="Exceptions" value={String(counts.exception || 0)} sub={`${overview?.exception_rate || 0}% of volume`} accentColor={tokens.color.status.warning.base} icon="⚠" />
        <KpiCard size="lg" label="Pending Approval" value={String(counts.pending_approval || 0)} sub="Awaiting approvers" accentColor={tokens.color.status.danger.base} icon="⏱" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-5 mb-6">
        <Card title="Processing Pipeline" subtitle={`Last 30 days — ${total} invoices`}>
          {pipelineData.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No invoices in this period</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={pipelineData} layout="vertical" barSize={24} margin={{ left: 10, right: 30 }}>
                <XAxis type="number" tick={CHART_AXIS_STYLE} allowDecimals={false} />
                <YAxis type="category" dataKey="stage" tick={{ fontSize: 11, fill: tokens.color.neutral[600], fontWeight: 500 }} width={92} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Invoices" radius={[0, 6, 6, 0]} fill={tokens.color.brand[400]} label={{ position: "right", fontSize: 11, fontWeight: 600, fill: tokens.color.neutral[600] }} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Invoice Volume by Vendor" subtitle="Last 90 days — sized by PKR value">
          {treemapData.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No vendor volume yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <Treemap
                data={treemapData}
                dataKey="value"
                nameKey="name"
                stroke={tokens.color.neutral[0]}
                strokeWidth={3}
                content={({ x, y, width, height, name, value, hasExceptions }) => {
                  if (width < 4 || height < 4) return null;
                  const fill = hasExceptions ? "#D94040" : tokens.color.brand[400];
                  const isLarge = width > 90 && height > 55;
                  const isMedium = width > 55 && height > 38;
                  const nameFontSize = isLarge ? 12 : isMedium ? 10.5 : 9;
                  const valFontSize = isLarge ? 10.5 : 9;
                  const showLabel = width > 40 && height > 24;
                  const showValue = width > 50 && height > 42;
                  const maxChars = Math.max(3, Math.floor(width / (nameFontSize * 0.62)));
                  const displayName = (name || "").length > maxChars ? name.slice(0, maxChars - 1) + "…" : name;
                  const textStyle = { fontFamily: "'Helvetica Neue', Arial, Verdana, sans-serif", textRendering: "geometricPrecision", stroke: "none", strokeWidth: 0 };
                  return (
                    <g>
                      <rect x={x} y={y} width={width} height={height} rx={5} fill={fill} />
                      {showLabel && (
                        <text x={x + 8} y={y + 10 + nameFontSize} style={{ ...textStyle, fill: "#FFFFFF", fontSize: nameFontSize, fontWeight: 400, letterSpacing: "0.3px" }}>
                          {displayName}
                        </text>
                      )}
                      {showValue && (
                        <text x={x + 8} y={y + 14 + nameFontSize + valFontSize} style={{ ...textStyle, fill: "rgba(255,255,255,0.8)", fontSize: valFontSize, fontWeight: 300, letterSpacing: "0.4px" }}>
                          PKR {value >= 1000000 ? `${(value / 1000000).toFixed(1)}M` : Number(value).toLocaleString()}
                        </text>
                      )}
                    </g>
                  );
                }}
              />
            </ResponsiveContainer>
          )}
          <div className="flex gap-4 pt-2 border-t border-neutral-100 text-2xs">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: tokens.color.brand[400] }} /> Clean</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: "#D94040" }} /> Has exceptions</span>
          </div>
        </Card>
      </div>

      {/* Recent Invoices — live */}
      <Card
        title="Recent Invoices"
        action={
          <Button variant="secondary" size="xs" onClick={() => onOpenInbox?.()}>
            View All →
          </Button>
        }
        noPad
      >
        {recent.length === 0 ? (
          <div className="text-center py-10 text-2xs text-neutral-400">No invoices yet</div>
        ) : (
          <DataTable
            columns={[
              {
                key: "invoice_number", label: "Invoice #",
                render: (v, row) => (
                  <span
                    className="text-brand-600 font-semibold cursor-pointer hover:underline"
                    onClick={() => onViewInvoice?.(row.id)}
                  >
                    {v || `#${row.id}`}
                  </span>
                ),
              },
              { key: "supplier_name", label: "Vendor", render: (v) => <span className="font-medium">{v || "—"}</span> },
              {
                key: "total_amount", label: "Amount", align: "right",
                render: (v, row) => (
                  <span className="font-semibold font-mono text-xs whitespace-nowrap">
                    {row.currency || "PKR"} {v != null ? Number(v).toLocaleString() : "—"}
                  </span>
                ),
              },
              { key: "status", label: "Status", render: (v) => <Badge status={v} /> },
              {
                key: "overall_confidence", label: "AI Conf.",
                render: (v) => (v != null ? <ConfidenceMeter value={Math.round(v)} /> : <span className="text-2xs text-neutral-400">—</span>),
              },
            ]}
            data={recent}
          />
        )}
      </Card>
    </div>
  );
}
