export default function ConfidenceMeter({ value }) {
  const color =
    value >= 90
      ? "bg-success-base text-success-base"
      : value >= 75
        ? "bg-warning-base text-warning-base"
        : "bg-danger-base text-danger-base";

  const [bgClass, textClass] = color.split(" ");

  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1 bg-neutral-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${bgClass}`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className={`text-2xs font-semibold ${textClass} min-w-[28px]`}>
        {value}%
      </span>
    </div>
  );
}
