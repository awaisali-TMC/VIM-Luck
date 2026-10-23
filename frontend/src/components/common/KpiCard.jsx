export default function KpiCard({ label, value, sub, accentColor, icon, size = "sm" }) {
  const isLg = size === "lg";
  return (
    <div
      className={`bg-neutral-0 border border-neutral-100 rounded-md shadow-xs ${isLg ? "px-5 py-4" : "px-3.5 py-2.5"}`}
      style={{ borderLeftWidth: isLg ? 3 : 2, borderLeftColor: accentColor || "#4F62F2" }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon && <span className={`${isLg ? "text-base" : "text-xs"} opacity-40`}>{icon}</span>}
          <span className={`${isLg ? "text-xs" : "text-2xs"} font-medium text-neutral-400 uppercase tracking-wider`}>
            {label}
          </span>
        </div>
      </div>
      <div className={`flex items-baseline gap-2 ${isLg ? "mt-1" : "mt-0.5"}`}>
        <span className={`${isLg ? "text-3xl font-bold text-neutral-900" : "text-sm font-semibold text-neutral-800"} leading-tight`}>{value}</span>
        {sub && <span className={`${isLg ? "text-xs" : "text-2xs"} text-neutral-400`}>{sub}</span>}
      </div>
    </div>
  );
}
