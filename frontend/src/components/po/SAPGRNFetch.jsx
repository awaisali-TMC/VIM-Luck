import { useState, useEffect } from "react";
import { fetchSAPGRN, syncSAPGRN } from "../../services/sapService";

/**
 * Fetch a PO's Goods Received Notes (GRNs) live from SAP (EKBE history) by PO
 * number, show each material document + received quantities, and sync them into
 * the local DB so 3-way matching (PO + GRN vs Invoice) can use them.
 *
 * defaultPoNumber pre-fills the input from the currently-selected PO.
 * onSynced() is called after a successful sync so the parent can refresh.
 */
export default function SAPGRNFetch({ defaultPoNumber = "", onSynced }) {
  const [poNumber, setPoNumber] = useState(defaultPoNumber || "");
  const [loading, setLoading] = useState(false);
  const [grns, setGrns] = useState(null);
  const [error, setError] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState(null);

  // Keep the input in sync with the selected PO until the user fetches/edits.
  useEffect(() => {
    if (defaultPoNumber && grns === null) setPoNumber(defaultPoNumber);
  }, [defaultPoNumber, grns]);

  const handleFetch = async () => {
    const num = poNumber.trim();
    if (!num) return;
    setLoading(true);
    setError(null);
    setGrns(null);
    setSyncMsg(null);
    try {
      const data = await fetchSAPGRN(num);
      setGrns(data.grns || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "SAP GRN fetch failed — check the backend logs.");
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    const num = poNumber.trim();
    if (!num) return;
    setSyncing(true);
    setError(null);
    setSyncMsg(null);
    try {
      const res = await syncSAPGRN(num);
      const parts = [`${res.grns_created} GRN(s) imported`];
      if (res.grns_skipped) parts.push(`${res.grns_skipped} already present`);
      setSyncMsg(parts.join(", ") + ".");
      onSynced?.(res);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "GRN sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  const fmt = (n) => (n != null && n !== "" ? Number(n).toLocaleString() : "—");

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <input
          type="text"
          value={poNumber}
          onChange={(e) => setPoNumber(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleFetch()}
          className="flex-1 text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 transition-colors"
          placeholder="PO number to fetch its GRNs, e.g. 4500005363"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !poNumber.trim()}
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

      {syncMsg && (
        <div className="bg-success-bg border border-success-base rounded-base px-3 py-2">
          <span className="text-2xs text-success-dark font-medium">✓ {syncMsg}</span>
        </div>
      )}

      {/* Fetched GRNs */}
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

          <div className="flex items-center justify-between">
            <span className="text-2xs text-neutral-500">
              {grns.length} GRN(s) · live from SAP
            </span>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="px-3 py-1.5 rounded-base text-2xs font-semibold border cursor-pointer transition-colors disabled:opacity-50 bg-brand-600 text-white border-brand-600 hover:bg-brand-700"
            >
              {syncing ? "Importing…" : "Import GRNs for 3-Way Matching"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
