import { useEffect } from "react";

function fmtAmount(v) {
  const num = parseFloat(String(v).replace(/,/g, ""));
  if (isNaN(num)) return v;
  return num.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function confidenceColor(conf) {
  if (conf >= 0.85) return "text-emerald-600 bg-emerald-50 border-emerald-200";
  if (conf >= 0.6) return "text-amber-600 bg-amber-50 border-amber-200";
  return "text-red-600 bg-red-50 border-red-200";
}

export default function TaxDetectionModal({
  open,
  onClose,
  detectedTaxes = [],
  taxSummary,
  geminiConfidence,
  geminiProcessingTimeMs,
}) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const totalTaxAmount = detectedTaxes.reduce(
    (sum, t) => sum + (t.amount || 0),
    0
  );
  const confColors = confidenceColor(geminiConfidence || 0);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl w-[540px] max-h-[80vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center text-lg">
              &#128270;
            </div>
            <div>
              <div className="text-sm font-semibold text-neutral-900">
                Gemini Tax Detection
              </div>
              <div className="text-2xs text-neutral-500">
                {detectedTaxes.length} tax type
                {detectedTaxes.length !== 1 ? "s" : ""} detected
                {geminiProcessingTimeMs
                  ? ` in ${(geminiProcessingTimeMs / 1000).toFixed(1)}s`
                  : ""}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 bg-transparent border-none cursor-pointer text-base"
          >
            &#10005;
          </button>
        </div>

        {/* Confidence + Summary bar */}
        <div className="px-5 py-3 bg-neutral-25 border-b border-neutral-100 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-2xs font-medium text-neutral-500 uppercase tracking-wider">
              Confidence
            </span>
            <span
              className={`text-2xs font-semibold px-2 py-0.5 rounded-full border ${confColors}`}
            >
              {geminiConfidence != null
                ? `${Math.round(geminiConfidence * 100)}%`
                : "N/A"}
            </span>
          </div>
          {taxSummary && (
            <span className="text-2xs text-neutral-500 truncate max-w-[280px]">
              {taxSummary}
            </span>
          )}
        </div>

        {/* Tax list */}
        <div className="flex-1 overflow-y-auto">
          {detectedTaxes.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <div className="text-2xl mb-2 opacity-30">&#128269;</div>
              <div className="text-xs text-neutral-500">
                No taxes were detected in this document
              </div>
            </div>
          ) : (
            <div className="divide-y divide-neutral-50">
              {detectedTaxes.map((tax, i) => (
                <div
                  key={`${tax.tax_type}-${i}`}
                  className="px-5 py-3.5 flex items-center gap-4 hover:bg-neutral-25 transition-colors"
                >
                  {/* Tax type badge */}
                  <div className="w-16 flex-shrink-0">
                    <span className="inline-block text-2xs font-bold text-brand-700 bg-brand-50 border border-brand-100 px-2.5 py-1 rounded-md text-center w-full">
                      {tax.tax_type}
                    </span>
                  </div>

                  {/* Description + rate */}
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-neutral-800">
                      {tax.description || tax.tax_type}
                    </div>
                    {tax.rate != null && (
                      <div className="text-2xs text-neutral-400 mt-0.5">
                        Rate: {tax.rate}%
                      </div>
                    )}
                  </div>

                  {/* Amount */}
                  <div className="text-right flex-shrink-0">
                    <div className="text-sm font-semibold font-mono text-neutral-900">
                      {tax.amount != null ? `PKR ${fmtAmount(tax.amount)}` : "---"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer with total */}
        {detectedTaxes.length > 0 && (
          <div className="px-5 py-3.5 border-t-2 border-neutral-200 bg-neutral-25 flex items-center justify-between">
            <span className="text-xs font-semibold text-neutral-700">
              Total Detected Tax
            </span>
            <span className="text-sm font-bold font-mono text-neutral-900">
              PKR {fmtAmount(totalTaxAmount)}
            </span>
          </div>
        )}

        {/* Close button */}
        <div className="px-5 py-3 border-t border-neutral-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium text-neutral-700 bg-neutral-0 border border-neutral-200 rounded-base cursor-pointer hover:bg-neutral-50 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
