import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { tokens } from "../../styles/tokens";
import { STATUS_COLORS } from "../../utils/statusColors";

function DonutTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-neutral-900 rounded-base px-3.5 py-2.5 shadow-lg">
      <div className="flex items-center gap-2 text-xs text-white">
        <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: d.color }} />
        <span className="font-semibold">{d.label}</span>
      </div>
      <div className="text-2xs text-neutral-300 mt-1">
        {d.count.toLocaleString()} invoice{d.count !== 1 ? "s" : ""} · PKR {Math.round(d.amount).toLocaleString()}
      </div>
    </div>
  );
}

/**
 * Donut of invoice status distribution.
 * @param data [{ status, label, count, amount }]
 */
export default function StatusDonut({ data = [] }) {
  const rows = data
    .filter((d) => d.count > 0)
    .map((d) => ({ ...d, color: STATUS_COLORS[d.status] || tokens.color.neutral[300] }));
  const total = rows.reduce((s, d) => s + d.count, 0);

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-[240px] text-xs text-neutral-400">
        No invoices in this period
      </div>
    );
  }

  return (
    <div className="flex items-center gap-5">
      <div className="relative flex-none" style={{ width: 190, height: 190 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={rows}
              dataKey="count"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius={62}
              outerRadius={90}
              paddingAngle={rows.length > 1 ? 2 : 0}
              stroke="none"
            >
              {rows.map((d) => (
                <Cell key={d.status} fill={d.color} />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-neutral-900 leading-none tabular-nums">
            {total.toLocaleString()}
          </span>
          <span className="text-2xs text-neutral-400 uppercase tracking-wider mt-1">Invoices</span>
        </div>
      </div>

      <div className="flex-1 min-w-0 grid grid-cols-1 gap-1.5">
        {rows.map((d) => (
          <div key={d.status} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-sm flex-none" style={{ background: d.color }} />
            <span className="text-neutral-600 truncate flex-1">{d.label}</span>
            <span className="font-semibold text-neutral-800 tabular-nums">{d.count.toLocaleString()}</span>
            <span className="text-2xs text-neutral-400 tabular-nums w-10 text-right">
              {total ? Math.round((d.count / total) * 100) : 0}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
