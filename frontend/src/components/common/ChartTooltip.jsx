export default function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-neutral-900 rounded-base px-3.5 py-2.5 shadow-lg">
      <div className="text-2xs text-neutral-300 mb-1.5">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-white mb-0.5">
          <span
            className="w-2 h-2 rounded-sm shrink-0"
            style={{ background: p.color }}
          />
          <span className="text-neutral-300">{p.name}:</span>
          <span className="font-semibold">
            {typeof p.value === "number" ? p.value.toLocaleString() : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}
