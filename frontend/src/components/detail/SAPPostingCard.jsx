import { useState, useEffect } from "react";
import Card from "../common/Card";
import { todayIso } from "../../utils/dateRange";

const LAYOUT_OPTIONS = [
  // Same wording and numbers as MIR7's "Layout" dropdown.
  { value: "goods", label: "1 Goods/service items" },
  { value: "delivery", label: "2 Planned delivery costs" },
  { value: "both", label: "3 Goods/service items + planned delivery costs" },
];

const layoutLabel = (v) => LAYOUT_OPTIONS.find((o) => o.value === v)?.label || "1 Goods/service items";

/**
 * SAP Parking parameters — all the inputs we ready for parking to SAP. Editable
 * during review (before approval), then locked read-only.
 *
 * Props:
 *  - invoice            : the invoice (source of saved values)
 *  - editable           : whether the fields can be changed
 *  - onSave(patch)      : persist a partial update ({ sap_layout } etc.)
 *  - foreignCurrency    : true when invoice currency != company local currency
 *  - errors             : { taxCode?, layout?, postingDate?, headerText?, exchangeRate? }
 *                         message strings to show inline + mark the field invalid
 *  - taxCodes, taxCode, aiSuggestedTaxCode, onTaxCodeChange, taxCodesLoading
 *
 * Mount with key={invoice.id} so local input state seeds once per invoice and
 * the background matching-poll refetch can't wipe in-progress typing.
 */
export default function SAPPostingCard({
  invoice,
  editable = false,
  onSave,
  foreignCurrency = false,
  currencies = [],
  errors = {},
  taxCodes = [],
  taxCode = "",
  aiSuggestedTaxCode = null,
  onTaxCodeChange,
  taxCodesLoading = false,
  onValuesChange,
}) {
  // Seed with `??` (not `||`) so a value the user cleared to "" stays empty
  // (and flags as invalid), while a never-set null shows the sensible default.
  const [layout, setLayout] = useState(invoice?.sap_layout || "goods");
  const [postingDate, setPostingDate] = useState(invoice?.sap_posting_date ?? todayIso());
  const [baselineDate, setBaselineDate] = useState(invoice?.sap_baseline_date ?? todayIso());
  const [headerText, setHeaderText] = useState(
    invoice?.sap_header_text ?? `einv-${invoice?.invoice_number || invoice?.id}`
  );
  const [itemText, setItemText] = useState(
    invoice?.sap_item_text ?? (invoice?.invoice_number || `einv-${invoice?.id}`)
  );
  const [currency, setCurrency] = useState(invoice?.sap_currency || invoice?.currency || "PKR");
  const [exchangeRate, setExchangeRate] = useState(invoice?.exchange_rate ?? "");

  // Currency options: the full SAP currency list (cached) when available,
  // else fall back to just the invoice's own currency + PKR. Always ensure the
  // invoice currency and PKR are present so the default is selectable.
  const localCcy = invoice?.currency || "PKR";
  const currencyList = (currencies || []).length
    ? currencies.map((c) => ({ code: c.code, name: c.name }))
    : [{ code: localCcy, name: "" }, { code: "PKR", name: "" }];
  const currencyOptions = (() => {
    const seen = new Set();
    const out = [];
    for (const c of [{ code: localCcy }, { code: "PKR" }, ...currencyList]) {
      if (c.code && !seen.has(c.code)) {
        seen.add(c.code);
        const meta = currencyList.find((x) => x.code === c.code);
        out.push({ code: c.code, name: meta?.name || "" });
      }
    }
    return out;
  })();

  // Report the live input values up so the page can validate synchronously
  // (the backend save is async and lags, so we can't validate the saved value).
  useEffect(() => {
    onValuesChange?.({ layout, postingDate, baselineDate, headerText, itemText, currency, exchangeRate });
  }, [layout, postingDate, baselineDate, headerText, itemText, currency, exchangeRate, onValuesChange]);

  const inputTaxCodes = (taxCodes || []).filter((c) => c.tax_type === "input");
  const selectedTaxMeta = inputTaxCodes.find((c) => c.code === taxCode);
  const aiSuggestedMeta = inputTaxCodes.find((c) => c.code === aiSuggestedTaxCode);

  // MIR7's "Calculate Tax": SAP works the tax out from the tax code (CALC_TAX_IND).
  // Preview the same sum here, next to the tax printed on the invoice.
  const [calcTax, setCalcTax] = useState(!!invoice?.sap_calc_tax);
  const netForTax = (invoice?.line_items || []).reduce((s, li) => s + (Number(li.amount) || 0), 0)
    || Number(invoice?.subtotal_amount) || 0;
  const taxRate = selectedTaxMeta?.rate;
  const calculatedTax = taxRate != null ? Math.round(netForTax * taxRate) / 100 : null;
  const invoiceTax = Number(invoice?.tax_amount ?? invoice?.gst_amount ?? 0);
  const fmtMoney = (n) => Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const save = (patch) => onSave?.(patch);
  const req = <span className="text-danger-base">*</span>;
  const labelCls = "text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1 block";
  const inputCls =
    "w-full bg-neutral-0 border border-neutral-200 rounded-base px-3 py-2 text-xs " +
    "outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400/20 transition-colors";
  const errBorder = (k) => (errors[k] ? " !border-danger-base ring-1 ring-danger-base/40" : "");
  const errMsg = (k) =>
    errors[k] ? <span className="text-2xs text-danger-dark font-medium mt-0.5 block">{errors[k]}</span> : null;

  return (
    <Card
      title="SAP Parking"
      subtitle={
        editable
          ? "Set these before submitting for approval — they're used when parking to SAP"
          : "Locked — these were set before approval and will be used when parking"
      }
    >
      <div className="flex flex-col gap-4">
        {/* SAP Tax Code (full width) */}
        <div>
          <span className={labelCls}>
            SAP Tax Code {req}
            {taxCodesLoading && <span className="text-neutral-400 font-normal normal-case"> · loading from SAP…</span>}
          </span>
          {editable && inputTaxCodes.length > 0 ? (
            <>
              <select
                value={taxCode || ""}
                onChange={(e) => onTaxCodeChange?.(e.target.value)}
                className={`${inputCls} max-w-md${errBorder("taxCode")}`}
              >
                {inputTaxCodes.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.code} — {c.description || "(no description)"}
                    {c.code === aiSuggestedTaxCode ? "  ·  AI suggested" : ""}
                  </option>
                ))}
              </select>
              {errMsg("taxCode")}
              {aiSuggestedMeta && (
                <span className="text-2xs text-brand-600 mt-1.5 block">
                  {aiSuggestedTaxCode === taxCode ? "✓ " : ""}AI suggested:{" "}
                  <strong>{aiSuggestedMeta.code}</strong> — {aiSuggestedMeta.description}
                  {aiSuggestedTaxCode !== taxCode && (
                    <button
                      type="button"
                      className="ml-2 text-brand-500 underline hover:text-brand-700 bg-transparent border-none cursor-pointer p-0"
                      onClick={() => onTaxCodeChange?.(aiSuggestedTaxCode)}
                    >
                      use this
                    </button>
                  )}
                </span>
              )}
            </>
          ) : (
            <div className="text-xs text-neutral-800 font-medium">
              {selectedTaxMeta ? `${selectedTaxMeta.code} — ${selectedTaxMeta.description}` : taxCode || "—"}
            </div>
          )}

          {/* MIR7 "Calculate Tax" (client 2026-11-27) */}
          <label className={`mt-2.5 inline-flex items-center gap-2 text-xs font-medium text-neutral-800 ${editable ? "cursor-pointer" : ""}`}>
            <input
              type="checkbox"
              checked={calcTax}
              disabled={!editable}
              onChange={(e) => { setCalcTax(e.target.checked); save({ sap_calc_tax: e.target.checked }); }}
            />
            Calculate Tax
            <span className="text-2xs font-normal text-neutral-500">— SAP calculates the tax from the tax code, as in MIR7</span>
          </label>
          {calcTax && (
            <div className="mt-1.5 text-2xs rounded-md border border-neutral-100 bg-neutral-25 px-3 py-2 max-w-xl">
              {calculatedTax == null ? (
                <span className="text-warning-dark">No rate known for tax code {taxCode || "—"}: SAP still calculates it when parking.</span>
              ) : (
                <table className="w-full border-collapse">
                  <tbody>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Tax code</td>
                      <td className="py-0.5 text-right text-neutral-800">
                        <span className="font-mono font-semibold">{taxCode}</span>
                        {selectedTaxMeta?.description ? ` — ${selectedTaxMeta.description}` : ""}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Base amount (net of the lines)</td>
                      <td className="py-0.5 text-right font-mono text-neutral-800">{fmtMoney(netForTax)}</td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Tax rate</td>
                      <td className="py-0.5 text-right font-mono text-neutral-800">{taxRate}%</td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Formula</td>
                      <td className="py-0.5 text-right font-mono text-neutral-800">
                        {fmtMoney(netForTax)} × {taxRate}% = {fmtMoney(calculatedTax)}
                      </td>
                    </tr>
                    <tr className="border-t border-neutral-200">
                      <td className="pt-1 font-semibold text-neutral-900">Tax amount (SAP calculates)</td>
                      <td className="pt-1 text-right font-mono font-semibold text-neutral-900">{fmtMoney(calculatedTax)}</td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Gross amount = Base + Tax</td>
                      <td className="py-0.5 text-right font-mono text-neutral-800">
                        {fmtMoney(netForTax)} + {fmtMoney(calculatedTax)} = {fmtMoney(netForTax + calculatedTax)}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Tax on the invoice</td>
                      <td className="py-0.5 text-right font-mono text-neutral-800">{fmtMoney(invoiceTax)}</td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-neutral-500">Difference (SAP − invoice)</td>
                      <td className={`py-0.5 text-right font-mono ${invoiceTax > 0 && Math.abs(calculatedTax - invoiceTax) > 1 ? "text-warning-dark font-semibold" : "text-neutral-800"}`}>
                        {fmtMoney(calculatedTax - invoiceTax)}
                      </td>
                    </tr>
                  </tbody>
                  {invoiceTax > 0 && Math.abs(calculatedTax - invoiceTax) > 1 && (
                    <caption className="caption-bottom pt-1 text-left text-warning-dark">
                      SAP's tax differs from the invoice by {fmtMoney(calculatedTax - invoiceTax)}: check the tax code.
                    </caption>
                  )}
                </table>
              )}
            </div>
          )}
        </div>

        {/* Items to Park + posting/baseline dates */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 pt-2">
          {/* Items to Park (SAP MIR7 "layout") */}
          <div>
            <span className={labelCls}>Layout (items to park) {req}</span>
            {editable ? (
              <select
                value={layout}
                onChange={(e) => { setLayout(e.target.value); save({ sap_layout: e.target.value }); }}
                className={`${inputCls}${errBorder("layout")}`}
              >
                {LAYOUT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : (
              <div className="text-xs text-neutral-800 font-medium">{layoutLabel(invoice?.sap_layout)}</div>
            )}
            {errMsg("layout")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">Which items to send to SAP — goods, freight, or both.</span>
          </div>

          {/* Posting Date */}
          <div>
            <span className={labelCls}>Posting Date {req}</span>
            {editable ? (
              <input
                type="date"
                value={postingDate}
                onChange={(e) => { setPostingDate(e.target.value); save({ sap_posting_date: e.target.value }); }}
                className={`${inputCls}${errBorder("postingDate")}`}
              />
            ) : (
              <div className="text-xs text-neutral-800 font-medium font-mono">{invoice?.sap_posting_date || "—"}</div>
            )}
            {errMsg("postingDate")}
          </div>

          {/* Baseline Date (mandatory — drives payment due date) */}
          <div>
            <span className={labelCls}>Baseline Date {req}</span>
            {editable ? (
              <input
                type="date"
                value={baselineDate}
                onChange={(e) => { setBaselineDate(e.target.value); save({ sap_baseline_date: e.target.value }); }}
                className={`${inputCls}${errBorder("baselineDate")}`}
              />
            ) : (
              <div className="text-xs text-neutral-800 font-medium font-mono">{invoice?.sap_baseline_date || "—"}</div>
            )}
            {errMsg("baselineDate")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">Payment terms are calculated from this date.</span>
          </div>
        </div>

        {/* Currency + Exchange Rate — grouped: change the currency and the rate opens */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 pt-3">
          {/* Currency */}
          <div>
            <span className={labelCls}>Currency {req}</span>
            {editable ? (
              <select
                value={currency}
                onChange={(e) => { setCurrency(e.target.value); save({ sap_currency: e.target.value }); }}
                className={`${inputCls}${errBorder("currency")}`}
              >
                {currencyOptions.map((c) => (
                  <option key={c.code} value={c.code}>
                    {`${c.code}${c.name ? ` — ${c.name}` : ""}${c.code === localCcy ? " · invoice currency" : c.code === "PKR" ? " · local" : ""}`}
                  </option>
                ))}
              </select>
            ) : (
              <div className="text-xs text-neutral-800 font-medium">{invoice?.sap_currency || invoice?.currency || "PKR"}</div>
            )}
            {errMsg("currency")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">Defaults to the invoice's currency. Switch to convert to another currency.</span>
          </div>

          {/* Exchange Rate — opens when a non-local currency is selected */}
          <div>
            <span className={labelCls}>Exchange Rate {foreignCurrency && req}</span>
            {editable && foreignCurrency ? (
              <input
                type="number"
                step="0.00001"
                value={exchangeRate}
                placeholder="e.g. 0.72"
                onChange={(e) => setExchangeRate(e.target.value)}
                onBlur={() => save({ exchange_rate: exchangeRate === "" ? null : parseFloat(exchangeRate) })}
                className={`${inputCls}${errBorder("exchangeRate")}`}
              />
            ) : (
              <div className="text-xs text-neutral-500 font-medium">
                {foreignCurrency ? (invoice?.exchange_rate ?? "—") : "N/A — local currency"}
              </div>
            )}
            {errMsg("exchangeRate")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">
              {foreignCurrency ? "Required — foreign currency selected; you can edit the rate." : "Opens when you pick a non-local currency."}
            </span>
          </div>
        </div>

        {/* Header Text + Item Text — grouped */}
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 pt-3">
          {/* Header Text — Basic Data tab → HEADER_TXT (BKTXT) */}
          <div>
            <span className={labelCls}>Header Text {req}</span>
            {editable ? (
              <input
                type="text"
                maxLength={25}
                value={headerText}
                placeholder={`einv-${invoice?.invoice_number || invoice?.id}`}
                onChange={(e) => setHeaderText(e.target.value)}
                onBlur={() => save({ sap_header_text: headerText })}
                className={`${inputCls}${errBorder("headerText")}`}
              />
            ) : (
              <div className="text-xs text-neutral-800 font-medium">
                {invoice?.sap_header_text || `einv-${invoice?.invoice_number || invoice?.id}`}
              </div>
            )}
            {errMsg("headerText")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">Basic Data tab — sent to SAP as your 8-digit employee ID + space + first 16 characters (e.g. 00004007 einv-HP-2026-041).</span>
          </div>

          {/* Item Text — Details tab → ITEM_TEXT (SGTXT) */}
          <div>
            <span className={labelCls}>Item Text {req}</span>
            {editable ? (
              <input
                type="text"
                maxLength={50}
                value={itemText}
                placeholder={invoice?.invoice_number || `einv-${invoice?.id}`}
                onChange={(e) => setItemText(e.target.value)}
                onBlur={() => save({ sap_item_text: itemText })}
                className={`${inputCls}${errBorder("itemText")}`}
              />
            ) : (
              <div className="text-xs text-neutral-800 font-medium">
                {invoice?.sap_item_text || (invoice?.invoice_number || `einv-${invoice?.id}`)}
              </div>
            )}
            {errMsg("itemText")}
            <span className="text-2xs text-neutral-400 mt-0.5 block">Details tab — line item text.</span>
          </div>
        </div>
      </div>
    </Card>
  );
}
