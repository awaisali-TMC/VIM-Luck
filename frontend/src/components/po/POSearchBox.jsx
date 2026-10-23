import { useState, useCallback, useRef, useEffect } from "react";
import { searchPurchaseOrders } from "../../services/purchaseOrderService";
import { fetchSAPPODetail, syncSAPPO } from "../../services/sapService";

/**
 * Unified PO search: one field that (a) autocompletes against POs already in the
 * local DB and (b) fetches a PO live from SAP by exact number when it isn't
 * local yet. Selecting a local PO or "using" a fetched SAP PO calls onSelect
 * with a {id, po_number, vendor_name, total_amount, currency} object that the
 * parent uses for "Run PO Match".
 */
export default function POSearchBox({ onSelect }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);

  // Live SAP fetch panel
  const [sapLoading, setSapLoading] = useState(false);
  const [sapPo, setSapPo] = useState(null);
  const [sapError, setSapError] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [usedId, setUsedId] = useState(null);

  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const runLocalSearch = useCallback((value) => {
    setQuery(value);
    // typing invalidates any previously fetched SAP panel
    setSapPo(null);
    setSapError(null);
    setUsedId(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim() || value.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await searchPurchaseOrders(value);
        setResults(data || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
        setOpen(true);
      }
    }, 300);
  }, []);

  const selectLocal = (po) => {
    setQuery(po.po_number);
    setOpen(false);
    setResults([]);
    onSelect?.(po);
  };

  const fetchFromSAP = async () => {
    const num = query.trim();
    if (!num) return;
    setOpen(false);
    setSapLoading(true);
    setSapError(null);
    setSapPo(null);
    setUsedId(null);
    try {
      const d = await fetchSAPPODetail(num);
      setSapPo(d);
    } catch (err) {
      const s = err.response?.status;
      setSapError(
        s === 404
          ? `PO ${num} not found in SAP.`
          : err.response?.data?.detail || err.message || "SAP fetch failed — check the backend logs."
      );
    } finally {
      setSapLoading(false);
    }
  };

  const useForMatch = async () => {
    if (!sapPo) return;
    setSyncing(true);
    setSapError(null);
    try {
      let localId = null;
      try {
        const res = await syncSAPPO(sapPo.po_number);
        localId = res.po_id;
      } catch (err) {
        // 409 = already synced locally — resolve its id instead.
        if (err.response?.status === 409) {
          const found = await searchPurchaseOrders(sapPo.po_number);
          localId = found?.find((p) => p.po_number === sapPo.po_number)?.id ?? found?.[0]?.id ?? null;
        } else {
          throw err;
        }
      }
      if (!localId) throw new Error("Could not resolve the local PO id after sync.");
      setUsedId(localId);
      onSelect?.({
        id: localId,
        po_number: sapPo.po_number,
        vendor_name: sapPo.vendor_name,
        total_amount: sapPo.total_value,
        currency: sapPo.currency,
      });
    } catch (err) {
      setSapError(err.response?.data?.detail || err.message || "Could not use this PO for matching.");
    } finally {
      setSyncing(false);
    }
  };

  const fmt = (n) => (n != null && n !== "" ? Number(n).toLocaleString() : "—");
  const showSapOption = query.trim().length >= 4;

  return (
    <div ref={wrapperRef} className="flex flex-col gap-3">
      {/* Input + dropdown */}
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => runLocalSearch(e.target.value)}
          onFocus={() => (results.length > 0 || showSapOption) && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results.length === 0 && showSapOption) fetchFromSAP();
          }}
          className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 transition-colors"
          placeholder="Search by PO number — local or live from SAP…"
        />
        {(loading || sapLoading) && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-3 h-3 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {open && (
          <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-neutral-0 border border-neutral-200 rounded-base shadow-lg max-h-60 overflow-y-auto">
            {results.map((po) => (
              <button
                key={po.id}
                onClick={() => selectLocal(po)}
                className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-brand-50 cursor-pointer border-none bg-transparent text-left transition-colors border-b border-neutral-50"
              >
                <div>
                  <span className="font-semibold text-brand-600">{po.po_number}</span>
                  <span className="text-neutral-500 ml-2">{po.vendor_name}</span>
                  <span className="text-2xs text-neutral-400 ml-2">local</span>
                </div>
                <span className="text-neutral-600 font-mono text-2xs">
                  {po.currency} {fmt(po.total_amount)}
                </span>
              </button>
            ))}
            {results.length === 0 && !loading && (
              <div className="px-3 py-2 text-2xs text-neutral-500">No local POs match "{query.trim()}".</div>
            )}
            {showSapOption && (
              <button
                onClick={fetchFromSAP}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-brand-50 cursor-pointer border-none bg-neutral-25 text-left transition-colors border-t border-neutral-100"
              >
                <span className="text-brand-600 font-semibold">↪ Fetch</span>
                <span className="font-mono text-neutral-800">{query.trim()}</span>
                <span className="text-neutral-500">live from SAP</span>
              </button>
            )}
          </div>
        )}
      </div>

      {sapError && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2">
          <span className="text-2xs text-danger-dark font-medium">{sapError}</span>
        </div>
      )}

      {/* Fetched SAP PO detail */}
      {sapPo && (
        <div className="border border-neutral-200 rounded-base overflow-hidden">
          <div className="px-4 py-3 bg-neutral-25 border-b border-neutral-100">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold text-neutral-900">{sapPo.po_number}</span>
                <span className="text-2xs font-semibold px-1.5 py-0.5 rounded-full bg-brand-50 text-brand-700">SAP live</span>
                {sapPo.doc_type && <span className="text-2xs text-neutral-500">{sapPo.doc_type}</span>}
              </div>
              <span className="font-mono text-xs text-neutral-700">
                {sapPo.currency} {fmt(sapPo.total_value)}
              </span>
            </div>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1.5 text-2xs">
              <Field label="Vendor" value={sapPo.vendor_name} />
              <Field label="Vendor No." value={sapPo.vendor_number} />
              <Field label="Vendor NTN" value={sapPo.vendor_ntn} />
              <Field label="Company Code" value={sapPo.company_code} />
              <Field label="PO Date" value={sapPo.po_date} />
              <Field label="Currency" value={sapPo.currency} />
              <Field label="Purch. Group" value={sapPo.purchasing_group} />
              <Field label="Payment Terms" value={sapPo.payment_terms} />
            </div>
          </div>

          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="bg-neutral-25">
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Item</th>
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Description</th>
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Qty</th>
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Unit</th>
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Unit Price</th>
                <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Net Value</th>
              </tr>
            </thead>
            <tbody>
              {(sapPo.line_items || []).length === 0 ? (
                <tr><td colSpan={6} className="px-3 py-3 text-center text-2xs text-neutral-500">No line items.</td></tr>
              ) : (
                (sapPo.line_items || []).map((li, idx) => (
                  <tr key={li.item_number ?? idx} className={idx % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
                    <td className="px-3 py-2 border-b border-neutral-50 text-neutral-600">{li.item_number}</td>
                    <td className="px-3 py-2 border-b border-neutral-50 text-neutral-800">{li.description || "—"}</td>
                    <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono">{fmt(li.quantity)}</td>
                    <td className="px-3 py-2 border-b border-neutral-50 text-neutral-600">{li.unit || "—"}</td>
                    <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono">{fmt(li.unit_price)}</td>
                    <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono">{fmt(li.net_value)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-100 bg-neutral-25">
            <span className="text-2xs text-neutral-500">{(sapPo.line_items || []).length} line item(s) · live from SAP</span>
            {usedId ? (
              <span className="text-2xs font-semibold text-success-dark">✓ Selected for matching</span>
            ) : (
              <button
                onClick={useForMatch}
                disabled={syncing}
                className="px-3 py-1.5 rounded-base text-2xs font-semibold border cursor-pointer transition-colors disabled:opacity-50 bg-brand-600 text-white border-brand-600 hover:bg-brand-700"
              >
                {syncing ? "Preparing…" : "Use this PO for Matching"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div className="min-w-0">
      <div className="text-neutral-400 uppercase tracking-wide">{label}</div>
      <div className="text-neutral-800 font-medium truncate" title={value || ""}>{value || "—"}</div>
    </div>
  );
}
