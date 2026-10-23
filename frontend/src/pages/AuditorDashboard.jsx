import { useState, useEffect } from "react";
import {
  ComposedChart, Bar, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import KpiCard from "../components/common/KpiCard";
import DataTable from "../components/common/DataTable";
import ChartTooltip from "../components/common/ChartTooltip";
import api from "../services/api";
import { tokens } from "../styles/tokens";
import { CHART_AXIS_STYLE, CHART_GRID_STYLE } from "../utils/chartConfig";

const STATUS_COLORS = {
  draft: "#94A3B8",
  pending_processing: "#3B82F6",
  validated: "#10B981",
  pending_approval: "#F59E0B",
  approved: "#059669",
  posted: "#8B5CF6",
  exception: "#EF4444",
  rejected: "#B91C1C",
};

const ACTION_BADGE = {
  create: "info",
  update: "change",
  status_change: "change",
  delete: "danger",
  login: "system",
  post: "posted",
};

function fmtTs(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-PK", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function AuditorDashboard({ onViewInvoice }) {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [trend, setTrend] = useState(null);
  const [statusDist, setStatusDist] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [ov, tr, st, sup, logs] = await Promise.all([
          api.get("/api/analytics/overview", { params: { days: 30 } }),
          api.get("/api/analytics/volume-trend", { params: { days: 90, group_by: "week" } }),
          api.get("/api/analytics/by-status", { params: { days: 90 } }),
          api.get("/api/analytics/by-supplier", { params: { days: 90, limit: 8 } }),
          api.get("/api/audit-logs", { params: { limit: 10 } }),
        ]);
        setOverview(ov.data);
        setTrend(tr.data);
        setStatusDist(st.data);
        setSuppliers(sup.data?.suppliers || []);
        setAuditLogs(logs.data?.logs || []);
      } catch {
        /* sections render their own empty states */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return <div className="text-center py-12 text-sm text-neutral-400">Loading audit dashboard…</div>;
  }

  const counts = overview?.status_counts || {};
  const statusPie = (statusDist?.statuses || []).map((s) => ({
    name: s.status,
    value: s.count,
    color: STATUS_COLORS[s.status] || "#94A3B8",
  }));
  const trendData = (trend?.data || []).map((d) => ({
    period: d.period,
    count: d.count,
    confidence: d.avg_confidence,
  }));

  return (
    <div>
      {/* KPIs — live, last 30 days */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KpiCard size="lg" label="Processed (30d)" value={String(overview?.total_invoices || 0)} sub={`PKR ${Number(overview?.total_amount || 0).toLocaleString()}`} accentColor={tokens.color.brand[500]} icon="📊" />
        <KpiCard size="lg" label="Straight-Through" value={`${overview?.straight_through_rate || 0}%`} sub="Posted without issues" accentColor={tokens.color.status.success.base} icon="⚡" />
        <KpiCard size="lg" label="Exceptions" value={String(counts.exception || 0)} sub={`${overview?.exception_rate || 0}% of volume`} accentColor={tokens.color.status.warning.base} icon="✋" />
        <KpiCard size="lg" label="Avg Extraction" value={`${((overview?.avg_processing_ms || 0) / 1000).toFixed(1)}s`} sub="Per invoice" accentColor={tokens.color.status.info.base} icon="⏱" />
        <KpiCard size="lg" label="Avg Confidence" value={`${overview?.avg_confidence || 0}%`} sub="AI extraction" accentColor={tokens.color.status.posted.base} icon="🛡" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-5 mb-6">
        <Card title="Processing Volume & Confidence" subtitle="Weekly — last 90 days">
          {trendData.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No volume in this period</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={trendData}>
                <CartesianGrid {...CHART_GRID_STYLE} />
                <XAxis dataKey="period" tick={CHART_AXIS_STYLE} />
                <YAxis yAxisId="left" tick={CHART_AXIS_STYLE} allowDecimals={false} />
                <YAxis yAxisId="right" orientation="right" tick={CHART_AXIS_STYLE} domain={[0, 100]} unit="%" />
                <Tooltip content={<ChartTooltip />} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="count" name="Invoices" fill={tokens.color.brand[400]} radius={[2, 2, 0, 0]} barSize={24} />
                <Line yAxisId="right" type="monotone" dataKey="confidence" name="Avg Confidence %" stroke={tokens.color.status.success.base} strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Status Distribution" subtitle="Last 90 days">
          {statusPie.length === 0 ? (
            <div className="text-center py-16 text-2xs text-neutral-400">No invoices in this period</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={statusPie}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={{ stroke: tokens.color.neutral[300] }}
                  style={{ fontSize: 10 }}
                >
                  {statusPie.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Vendor signals — live */}
      <div className="mb-6">
        <Card title="Vendor Signals" subtitle="Top vendors by value — confidence and exception counts" noPad>
          {suppliers.length === 0 ? (
            <div className="text-center py-10 text-2xs text-neutral-400">No vendor activity yet</div>
          ) : (
            <DataTable
              columns={[
                { key: "supplier_name", label: "Vendor", render: (v) => <span className="font-medium">{v}</span> },
                { key: "invoice_count", label: "Invoices", align: "right" },
                {
                  key: "total_amount", label: "Value", align: "right",
                  render: (v) => `PKR ${Number(v || 0).toLocaleString()}`,
                },
                {
                  key: "avg_confidence", label: "Avg Confidence", align: "right",
                  render: (v) => (
                    <span className={`font-semibold ${v >= 90 ? "text-success-dark" : v >= 75 ? "text-warning-dark" : "text-danger-dark"}`}>
                      {v}%
                    </span>
                  ),
                },
                {
                  key: "exception_count", label: "Exceptions", align: "right",
                  render: (v) => (
                    <Badge status={v > 0 ? "high" : "low"} label={String(v)} size="xs" />
                  ),
                },
              ]}
              data={suppliers}
            />
          )}
        </Card>
      </div>

      {/* Audit trail — live from /api/audit-logs */}
      <Card title="Recent Audit Trail" subtitle="Latest recorded actions" noPad>
        {auditLogs.length === 0 ? (
          <div className="text-center py-10 text-2xs text-neutral-400">
            No audit entries yet — actions appear here as users work
          </div>
        ) : (
          <DataTable
            columns={[
              { key: "created_at", label: "Timestamp", render: (v) => <span className="font-mono text-2xs">{fmtTs(v)}</span> },
              {
                key: "entity_type", label: "Entity",
                render: (v, row) =>
                  v === "invoice" ? (
                    <span
                      className="text-brand-600 font-semibold cursor-pointer hover:underline"
                      onClick={() => onViewInvoice?.(row.entity_id)}
                    >
                      invoice #{row.entity_id}
                    </span>
                  ) : (
                    <span>{v} #{row.entity_id}</span>
                  ),
              },
              { key: "action", label: "Action", render: (v) => <Badge status={ACTION_BADGE[v] || "pending"} label={v} size="xs" /> },
              { key: "actor_name", label: "Actor", render: (v, row) => v || row.actor_type || "system" },
              {
                key: "new_value", label: "Details",
                render: (v, row) => {
                  const detail = v && typeof v === "object" ? Object.entries(v).slice(0, 2).map(([k, val]) => `${k}: ${val}`).join(", ") : "";
                  return <span className="text-2xs text-neutral-500">{detail || row.action}</span>;
                },
              },
            ]}
            data={auditLogs}
          />
        )}
      </Card>
    </div>
  );
}
