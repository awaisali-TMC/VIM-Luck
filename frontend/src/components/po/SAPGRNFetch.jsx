import { useState, useEffect, useRef, useCallback } from "react";
import { fetchSAPGRN } from "../../services/sapService";
import { searchPurchaseOrders } from "../../services/purchaseOrderService";

/**
 * Fetch a PO's Goods Received Notes (GRNs) live from SAP (EKBE history).
 *
 * The PO field has the same type-ahead suggestions as the main PO search
 * (local DB autocomplete). It is seeded from the selected PO ONCE and then left
 * alone — typing a different PO sticks and is never overwritten on re-render.
 * Picking a suggestion (or Enter / the Fetch button) fetches that PO's GRNs.
 */
export default function SAPGRNFetch({ defaultPoNumber = "", onPoSelected }) {
  const [query, setQuery] = useState(defaultPoNumber || "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(false);
  const [grns, setGrns] = useState(null);
  const [error, setError] = useState(null);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);
  const seededRef = useRef(false);

  // Seed the field from the selected PO ONCE; after that the user's input is
  // authoritative — a different PO they type is never replaced on re-render.
  useEffect(() => {
    if (!seededRef.current && defaultPoNumber) {
      setQuery(defaultPoNumber);
      seededRef.current = true;
    }
  }, [defaultPoNumber]);

  // Close the suggestions dropdown on an outside click.
  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const runSearch = useCallback((value) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value.trim() || value.trim().length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await searchPurchaseOrders(value);
        setResults(data || []);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
        setOpen(true);
      }
    }, 300);
  }, []);

  const doFetch = useCallback(async (num) => {
    const n = (num || "").trim();
    if (!n) return;
    setOpen(false);
    setLoading(true);
    setError(null);
    setGrns(null);
    try {
      const data = await fetchSAPGRN(n);
      setGrns(data.grns || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "SAP GRN fetch failed — check the backend logs.");
    } finally {
      setLoading(false);
    }
  }, []);

  const selectPO = (po) => {
    setQuery(po.po_number);
    setResults([]);
    setOpen(false);
    onPoSelected?.(po);   // also select this PO for matching (enables Run Match)
    doFetch(po.po_number);
  };

  // When a number is typed and fetched (not picked from the list), resolve it to
  // a local PO so it also becomes the match PO. Exact po_number match preferred.
  const resolveAndSelect = useCallback(async (num) => {
    const n = (num || "").trim();
    if (!n || !onPoSelected) return;
    try {
      const data = await searchPurchaseOrders(n);
      const exact = (data || []).find((p) => String(p.po_number) === n) || (data || [])[0];
      if (exact) onPoSelected(exact);
    } catch { /* not resolvable locally — leave the match PO as-is */ }
  }, [onPoSelected]);

  const handleFetchClick = () => {
    doFetch(query);
    resolveAndSelect(query);
  };

  const fmt = (n) => (n != null && n !== "" ? Number(n).toLocaleString() : "—");

  return (
    <div ref={wrapperRef} className="flex flex-col gap-3">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => runSearch(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleFetchClick(); } }}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 transition-colors"
            placeholder="Search by PO number, e.g. 4500005363"
          />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-3 h-3 border-2 border-brand-400 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {open && results.length > 0 && (
            <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-neutral-0 border border-neutral-200 rounded-base shadow-lg max-h-60 overflow-y-auto">
              {results.map((po) => (
                <button
                  key={po.id}
                  onClick={() => selectPO(po)}
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
            </div>
          )}
        </div>
        <button
          onClick={handleFetchClick}
          disabled={loading || !query.trim()}
          className="px-3 py-2 rounded-base text-2xs font-semibold border cursor-pointer transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed bg-brand-600 text-white border-brand-600 hover:bg-brand-700"
        >
          {loading ? "Fetching…" : "Fetch GRNs from SAP"}
        </button>
      </div>

      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2">
          <span className="text-2xs text-danger-dark font-medium">{error}</span>
        </div>
      )}

      {grns !== null && grns.length === 0 && !loading && (
        <div className="text-2xs text-neutral-500 px-1">No goods receipts found in SAP for this PO.</div>
      )}

      {grns && grns.length > 0 && (
        <>
          {grns.map((g) => (
            <div key={`${g.grn_number}-${g.grn_year}`} className="border border-neutral-200 rounded-base overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 bg-neutral-25 border-b border-neutral-100">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-neutral-900">{g.grn_number}</span>
                  <span className="text-2xs text-neutral-500">Doc year {g.grn_year}</span>
                  {g.plant && <span className="text-2xs text-neutral-500">Plant {g.plant}</span>}
                </div>
                <span className="text-2xs text-neutral-600">{g.grn_date || "—"}</span>
              </div>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-neutral-25">
                    <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">PO Item</th>
                    <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Material</th>
                    <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Received Qty</th>
                    <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Movement</th>
                  </tr>
                </thead>
                <tbody>
                  {g.line_items.map((li, idx) => (
                    <tr key={li.po_item ?? idx} className={idx % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
                      <td className="px-3 py-2 border-b border-neutral-50 text-neutral-600">{li.po_item}</td>
                      <td className="px-3 py-2 border-b border-neutral-50 text-neutral-600">{li.material_number || "—"}</td>
                      <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono">{fmt(li.received_quantity)}</td>
                      <td className="px-3 py-2 border-b border-neutral-50 text-neutral-500">{(li.movement_types || []).join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          <span className="text-2xs text-neutral-500">{grns.length} GRN(s) · live from SAP</span>
        </>
      )}
    </div>
  );
}
