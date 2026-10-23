export default function Spinner({ text = "Processing...", subtext = "" }) {
  return (
    <div className="text-center py-8">
      <div className="text-[28px] mb-3" style={{ animation: "spin 1.5s linear infinite" }}>
        &#9881;&#65039;
      </div>
      <div className="font-semibold text-neutral-800 mb-1">{text}</div>
      {subtext && <div className="text-xs text-neutral-500">{subtext}</div>}
    </div>
  );
}
