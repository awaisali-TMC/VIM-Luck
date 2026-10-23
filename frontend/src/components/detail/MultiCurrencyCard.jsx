import { useState, useEffect } from "react";
import Card from "../common/Card";
import api from "../../services/api";

function formatCurrency(amount, currency = "PKR") {
  if (amount == null) return "---";
  return `${currency} ${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function MultiCurrencyCard({ invoice }) {
  const [convertedTotal, setConvertedTotal] = useState(null);
  const [latestRate, setLatestRate] = useState(null);
  const [loading, setLoading] = useState(false);

  const currency = invoice?.currency || "PKR";
  const baseCurrency = invoice?.base_currency || "PKR";
  const isForeignCurrency = currency.toUpperCase() !== baseCurrency.toUpperCase();

  useEffect(() => {
    if (!isForeignCurrency || !invoice?.total_amount) return;

    // If already converted, use stored values
    if (invoice.exchange_rate && invoice.base_total_amount) {
      setConvertedTotal(invoice.base_total_amount);
      setLatestRate(invoice.exchange_rate);
      return;
    }

    // Fetch latest rate
    const fetchRate = async () => {
      setLoading(true);
      try {
        const res = await api.get("/api/currency/convert", {
          params: {
            amount: invoice.total_amount,
            from_currency: currency,
            to_currency: baseCurrency,
            date: invoice.invoice_date || undefined,
          },
        });
        setConvertedTotal(res.data.converted);
        setLatestRate(parseFloat(res.data.rate));
      } catch {
        // No rate available, that's fine
      } finally {
        setLoading(false);
      }
    };
    fetchRate();
  }, [isForeignCurrency, invoice?.total_amount, currency, baseCurrency, invoice?.exchange_rate, invoice?.base_total_amount, invoice?.invoice_date]);

  // Multi-currency only applies across different currencies — a same-currency
  // invoice has no exchange rate, so don't show this (even if a stray rate was set).
  if (!isForeignCurrency) return null;

  const effectiveRate = invoice?.exchange_rate || latestRate;
  // Prefer a stored/fetched base total; otherwise derive it from the rate the
  // same way the breakup below does, so the tile never blanks when we have a
  // rate (base_total_amount isn't returned by the backend).
  const effectiveTotal =
    invoice?.base_total_amount ||
    convertedTotal ||
    (effectiveRate && invoice?.total_amount != null
      ? invoice.total_amount * effectiveRate
      : null);

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">&#128177;</span>
        <h3 className="text-xs font-bold text-neutral-800 m-0">Multi-Currency</h3>
        <span className="bg-info-bg text-info-dark text-2xs font-bold px-2 py-0.5 rounded-full">
          {currency} &#8594; {baseCurrency}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {/* Original amount */}
        <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3 text-center">
          <div className="text-2xs text-neutral-500 mb-1">Invoice Amount</div>
          <div className="text-sm font-bold text-neutral-900">
            {formatCurrency(invoice.total_amount, currency)}
          </div>
          <div className="text-2xs text-neutral-400 mt-0.5">Original currency</div>
        </div>

        {/* Exchange rate */}
        <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3 text-center">
          <div className="text-2xs text-neutral-500 mb-1">Exchange Rate</div>
          <div className="text-sm font-bold text-brand-600">
            {loading ? (
              <span className="text-neutral-400">Loading...</span>
            ) : effectiveRate ? (
              effectiveRate.toFixed(4)
            ) : (
              <span className="text-warning-dark">Not set</span>
            )}
          </div>
          <div className="text-2xs text-neutral-400 mt-0.5">
            1 {currency} = {effectiveRate ? effectiveRate.toFixed(2) : "?"} {baseCurrency}
          </div>
        </div>

        {/* Converted amount */}
        <div className="bg-success-bg border border-success-base rounded-base p-3 text-center">
          <div className="text-2xs text-success-dark mb-1">Base Amount</div>
          <div className="text-sm font-bold text-success-dark">
            {loading ? (
              <span className="text-neutral-400">Loading...</span>
            ) : effectiveTotal ? (
              formatCurrency(effectiveTotal, baseCurrency)
            ) : (
              "---"
            )}
          </div>
          <div className="text-2xs text-success-dark opacity-70 mt-0.5">Company currency</div>
        </div>

        {/* Subtotals in base */}
        <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3">
          <div className="text-2xs text-neutral-500 mb-1">Breakup ({baseCurrency})</div>
          {effectiveRate && invoice.subtotal_amount != null && (
            <div className="flex justify-between text-2xs mb-0.5">
              <span className="text-neutral-500">Subtotal:</span>
              <span className="text-neutral-700 font-medium">
                {formatCurrency(invoice.subtotal_amount * effectiveRate, baseCurrency)}
              </span>
            </div>
          )}
          {effectiveRate && invoice.tax_amount != null && (
            <div className="flex justify-between text-2xs mb-0.5">
              <span className="text-neutral-500">Tax:</span>
              <span className="text-neutral-700 font-medium">
                {formatCurrency(invoice.tax_amount * effectiveRate, baseCurrency)}
              </span>
            </div>
          )}
          {effectiveRate && invoice.total_amount != null && (
            <div className="flex justify-between text-2xs border-t border-neutral-100 pt-0.5 mt-0.5">
              <span className="text-neutral-600 font-semibold">Total:</span>
              <span className="text-neutral-900 font-bold">
                {formatCurrency(invoice.total_amount * effectiveRate, baseCurrency)}
              </span>
            </div>
          )}
          {!effectiveRate && (
            <div className="text-2xs text-neutral-400">No rate available</div>
          )}
        </div>
      </div>

      {/* Source info */}
      {invoice?.exchange_rate && (
        <div className="text-2xs text-neutral-400 mt-2 text-right">
          Rate stored at save time. {invoice.invoice_date && `Invoice date: ${invoice.invoice_date}`}
        </div>
      )}
    </Card>
  );
}
