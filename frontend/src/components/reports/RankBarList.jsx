import { tokens } from "../../styles/tokens";

/**
 * Horizontal ranked-bar list — e.g. "invoices pending with each approver".
 * @param items    [{ label, count, amount }]
 * @param accent   bar colour (hex)
 * @param currency prefix for the amount subtext (default "PKR")
 * @param empty    message shown when there are no items
 */
export default function RankBarList({
  items = [],
  accent = tokens.color.brand[500],
  currency = "PKR",
  empty = "Nothing pending",
}) {
  if (!items.length) {
    return <div className="py-8 text-center text-xs text-neutral-400">{empty}</div>;
  }
  const max = Math.max(...items.map((i) => i.count), 1);

  return (
    <div className="flex flex-col gap-3">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-xs font-medium text-neutral-700 truncate">{it.label}</span>
            <span className="text-xs font-semibold text-neutral-900 tabular-nums flex-none">
              {it.count.toLocaleString()}
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="flex-1 h-2 rounded-full bg-neutral-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${Math.max((it.count / max) * 100, 4)}%`, background: accent }}
              />
            </div>
            {it.amount != null && (
              <span className="text-2xs text-neutral-400 tabular-nums flex-none w-28 text-right">
                {currency} {Math.round(it.amount).toLocaleString()}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
