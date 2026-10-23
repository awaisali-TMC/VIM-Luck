import Card from "../common/Card";
import ConfidenceLabel from "../common/ConfidenceLabel";

function fmtAmount(v) {
  const num = parseFloat(String(v).replace(/,/g, ""));
  if (isNaN(num)) return null;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Cycles through brand, info, success, warning, danger
const TAX_PALETTES = [
  { bg: "#EEF2FF", border: "#BCCBFD", text: "#2F35CC", dot: "#4F62F2" },  // brand
  { bg: "#EFF6FF", border: "#BFDBFE", text: "#1D4ED8", dot: "#3B82F6" },  // info
  { bg: "#ECFDF5", border: "#A7F3D0", text: "#047857", dot: "#10B981" },  // success
  { bg: "#FFFBEB", border: "#FDE68A", text: "#B45309", dot: "#F59E0B" },  // warning
  { bg: "#FEF2F2", border: "#FECACA", text: "#B91C1C", dot: "#EF4444" },  // danger
];

function confColors(conf) {
  if (conf >= 0.85) return "text-emerald-600 bg-emerald-50 border-emerald-200";
  if (conf >= 0.6)  return "text-amber-600  bg-amber-50  border-amber-200";
  return "text-red-600 bg-red-50 border-red-200";
}

export default function SalesTaxCard({
  fields = [],
  lineItems = [],
  detectedTaxes = [],
  taxSummary,
  geminiConfidence,
  geminiProcessingTimeMs,
  alwaysShow = false,   // render the card (with —/0%) even when the invoice has no tax
  // SAP tax code dropdown (rendered at the bottom of the card when provided)
  taxCodes = [],
  taxCode = "",
  aiSuggestedTaxCode = null,
  onTaxCodeChange,
  taxCodesLoading = false,
  taxCodeEditable = true,
}) {
  const inputTaxCodes = (taxCodes || []).filter((c) => c.tax_type === "input");
  const selectedTaxMeta = inputTaxCodes.find((c) => c.code === taxCode);
  const aiSuggestedMeta = inputTaxCodes.find((c) => c.code === aiSuggestedTaxCode);
  // Only show the SAP tax-code control when a parent opts in (passes a handler).
  const showSapTaxCode = typeof onTaxCodeChange === "function";
  const fieldMap = {};
  const confMap = {};
  for (const f of fields) {
    fieldMap[f.field_name] = f.value;
    confMap[f.field_name] = f.confidence;
  }

  const taxRaw  = fieldMap.total_tax_amount ?? fieldMap.tax_amount ?? fieldMap.gst_amount;
  const taxConf = confMap.total_tax_amount ?? confMap.tax_amount ?? confMap.gst_amount;
  const taxAmount = taxRaw != null ? parseFloat(String(taxRaw).replace(/,/g, "")) : NaN;

  let subtotal = NaN, subtotalSource = null;
  const subtotalRaw = fieldMap.net_amount ?? fieldMap.subtotal;
  if (subtotalRaw) {
    subtotal = parseFloat(String(subtotalRaw).replace(/,/g, ""));
    subtotalSource = "field";
  }
  if (isNaN(subtotal) && lineItems.length > 0) {
    const sum = lineItems.reduce((acc, li) => acc + (parseFloat(li.amount) || 0), 0);
    if (sum > 0) { subtotal = sum; subtotalSource = "line_items"; }
  }
  if (isNaN(subtotal) && fieldMap.total_amount && !isNaN(taxAmount)) {
    const total = parseFloat(String(fieldMap.total_amount).replace(/,/g, ""));
    if (!isNaN(total)) { subtotal = total - taxAmount; subtotalSource = "derived"; }
  }

  const taxPct = !isNaN(taxAmount) && !isNaN(subtotal) && subtotal !== 0
    ? (taxAmount / subtotal) * 100 : null;

  const hasDetectedTaxes = detectedTaxes.length > 0;
  const hasScalarTax     = taxRaw != null;
  if (!hasScalarTax && !hasDetectedTaxes && !alwaysShow && !showSapTaxCode) return null;

  const totalDetectedTax = detectedTaxes.reduce((s, t) => s + (t.amount || 0), 0);
  const fmtTotal = fmtAmount(totalDetectedTax);

  return (
    <Card
      title="Tax Details"
      subtitle={
        hasDetectedTaxes
          ? `${detectedTaxes.length} tax type${detectedTaxes.length !== 1 ? "s" : ""} identified by AI${
              geminiProcessingTimeMs ? ` · ${(geminiProcessingTimeMs / 1000).toFixed(1)}s` : ""
            }`
          : undefined
      }
      action={
        hasDetectedTaxes && geminiConfidence != null ? (
          <span className={`text-2xs font-semibold px-2.5 py-1 rounded-full border ${confColors(geminiConfidence)}`}>
            {Math.round(geminiConfidence * 100)}% AI confidence
          </span>
        ) : null
      }
    >
      {/* ── Gemini detected tax rows ── */}
      {hasDetectedTaxes && (
        <div className="flex flex-col gap-2 mb-4">
          {detectedTaxes.map((tax, i) => {
            const palette = TAX_PALETTES[i % TAX_PALETTES.length];
            const amt = fmtAmount(tax.amount);
            return (
              <div
                key={`${tax.tax_type}-${i}`}
                style={{ borderLeftColor: palette.dot }}
                className="flex items-start gap-3 pl-3 pr-4 py-3 rounded-md border border-neutral-100 border-l-[3px] bg-neutral-0 hover:bg-neutral-25 transition-colors"
              >
                {/* Title + rate */}
                <div className="flex flex-col gap-0.5 pt-px min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      style={{ color: palette.dot }}
                      className="text-sm font-bold leading-snug"
                    >
                      {tax.tax_type}
                    </span>
                    {tax.rate != null && (
                      <span className="text-2xs font-medium text-neutral-500 bg-neutral-50 border border-neutral-200 px-2 py-0.5 rounded-md whitespace-nowrap">
                        {tax.rate}%
                      </span>
                    )}
                  </div>
                  {tax.description && tax.description !== tax.tax_type && !tax.description.startsWith(tax.tax_type) && (
                    <p className="text-xs text-neutral-500 leading-snug m-0">
                      {tax.description}
                    </p>
                  )}
                </div>

                {/* Amount */}
                <div className="flex-shrink-0 text-right pt-px">
                  {amt ? (
                    <span className="text-sm font-semibold font-mono text-neutral-900">
                      PKR {amt}
                    </span>
                  ) : (
                    <span className="text-xs text-neutral-400 font-mono">—</span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Total row */}
          <div className="flex items-center justify-between px-4 py-2.5 rounded-md bg-neutral-50 border border-neutral-200">
            <span className="text-xs font-semibold text-neutral-700">Total Tax</span>
            <span className="text-sm font-bold font-mono text-neutral-900">
              {fmtTotal ? `PKR ${fmtTotal}` : "—"}
            </span>
          </div>

          {/* AI summary */}
          {taxSummary && (
            <p className="text-2xs text-neutral-400 leading-relaxed px-1 m-0">{taxSummary}</p>
          )}
        </div>
      )}

      {/* ── Document AI scalar fields ── */}
      {(hasScalarTax || alwaysShow) && (
        <div
          className={`grid grid-cols-4 gap-x-6 gap-y-4 ${
            hasDetectedTaxes ? "pt-4 border-t border-neutral-100" : ""
          }`}
        >
          <div>
            <div className="mb-0.5">
              <ConfidenceLabel label="Tax Amount" confidence={taxConf} />
            </div>
            <div className="text-xs text-neutral-800 font-medium font-mono">
              {!isNaN(taxAmount) ? fmtAmount(taxAmount) : "—"}
            </div>
          </div>

          <div>
            <div className="mb-0.5">
              <span className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider">
                Tax %
              </span>
            </div>
            <div className="text-xs text-neutral-800 font-medium">
              {taxPct != null ? `${taxPct.toFixed(2)}%` : "—"}
            </div>
          </div>

          {!isNaN(subtotal) && (
            <div>
              <div className="mb-0.5">
                {subtotalSource === "field" ? (
                  <ConfidenceLabel
                    label="Subtotal"
                    confidence={confMap.net_amount ?? confMap.subtotal}
                  />
                ) : (
                  <span className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider">
                    Subtotal{subtotalSource === "line_items" ? " (items)" : " (derived)"}
                  </span>
                )}
              </div>
              <div className="text-xs text-neutral-800 font-medium font-mono">
                {fmtAmount(subtotal)}
              </div>
            </div>
          )}

          {fieldMap.total_amount && (
            <div>
              <div className="mb-0.5">
                <ConfidenceLabel label="Total Amount" confidence={confMap.total_amount} />
              </div>
              <div className="text-xs text-neutral-800 font-medium font-mono">
                {fmtAmount(fieldMap.total_amount)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── SAP Tax Code — sourced from the cached SAP lookup, pre-selected to
          the AI-suggested code; the code used when parking to SAP ── */}
      {showSapTaxCode && (
        <div className="pt-4 mt-4 border-t border-neutral-100">
          <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
            SAP Tax Code <span className="text-danger-base">*</span>
          </div>
          {taxCodeEditable && inputTaxCodes.length > 0 ? (
            <>
              <select
                value={taxCode || ""}
                onChange={(e) => onTaxCodeChange(e.target.value)}
                className="w-full max-w-md bg-neutral-0 border border-neutral-200 rounded-base px-3 py-2 text-xs
                           outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400/20 transition-colors"
              >
                {inputTaxCodes.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.code} — {c.description || "(no description)"}
                    {c.code === aiSuggestedTaxCode ? "  ·  AI suggested" : ""}
                  </option>
                ))}
              </select>
              {aiSuggestedMeta && (
                <span className="text-2xs text-brand-600 mt-1.5 block">
                  {aiSuggestedTaxCode === taxCode ? "✓ " : ""}AI suggested:{" "}
                  <strong>{aiSuggestedMeta.code}</strong> — {aiSuggestedMeta.description}
                  {aiSuggestedTaxCode !== taxCode && (
                    <button
                      type="button"
                      className="ml-2 text-brand-500 underline hover:text-brand-700 bg-transparent border-none cursor-pointer p-0"
                      onClick={() => onTaxCodeChange(aiSuggestedTaxCode)}
                    >
                      use this
                    </button>
                  )}
                </span>
              )}
            </>
          ) : (
            <span className="inline-flex items-center gap-2 text-xs text-neutral-800 font-medium">
              {selectedTaxMeta
                ? `${selectedTaxMeta.code} — ${selectedTaxMeta.description}`
                : taxCode || (taxCodesLoading ? "Loading from SAP…" : "—")}
              {!taxCodeEditable && taxCode && (
                <span className="text-2xs text-neutral-400">(locked — sent to SAP)</span>
              )}
            </span>
          )}
        </div>
      )}
    </Card>
  );
}
