import { useCallback, useEffect, useState } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import { getOpenGRs } from "../../services/sapService";
import { clearSrnList, setParkingGRs } from "../../services/invoiceService";

/**
 * Lucky Cement (observation F) — GR-wise parking.
 *
 * Lists the matched PO's goods receipts that are not yet fully invoiced (live
 * from SAP EKBE) with a checkbox each. The ticked GRs are saved on the invoice
 * (parking_gr_refs); parking then sends one item per ticked GR, referencing it.
 * With nothing ticked, parking picks the latest GR per PO item, and refuses when
 * the invoice bills more than that GR.
 * When all open GRs of a PO item add up to the billed quantity (data.suggested)
 * and nothing was chosen yet, they are ticked and saved automatically.
 *
 * Props: invoice, editable (false once the invoice is in SAP), onChanged().
 */
export default function GoodsReceiptsCard({ invoice, editable = false, onChanged }) {
  const [data, setData] = useState(null);       // { po_number, grs, selected, message }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState(() => new Set(invoice?.parking_gr_refs || []));

  const load = useCallback(async () => {
    if (!invoice?.matched_po_id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getOpenGRs(invoice.id);
      setData(res);
      setSelected(new Set(res.selected || []));
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not read goods receipts from SAP.");
    } finally {
      setLoading(false);
    }
  }, [invoice?.id, invoice?.matched_po_id]);

  const srnKey = (invoice?.srn_list || []).map((r) => r.number).join(",");
  useEffect(() => { load(); }, [load, srnKey]);

  // Nothing chosen yet and the backend has a suggestion: tick and save it once.
  useEffect(() => {
    if (!editable || !data || data.chosen || !data.suggested?.length) return;
    const keys = data.suggested;
    setData((d) => ({ ...d, chosen: true }));
    setSelected(new Set(keys));
    setSaving(true);
    setParkingGRs(invoice.id, keys)
      .then(() => onChanged?.())
      .catch((err) => {
        const d = err.response?.data?.detail;
        setError(typeof d === "string" ? d : "Could not save the selection.");
        setSelected(new Set());
      })
      .finally(() => setSaving(false));
  }, [data, editable, invoice?.id, onChanged]);

  if (!invoice?.matched_po_id) return null;

  const toggle = async (key) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    setSelected(next);
    setSaving(true);
    setError(null);
    try {
      await setParkingGRs(invoice.id, [...next]);
      onChanged?.();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not save the selection.");
      setSelected(selected);                    // roll back
    } finally {
      setSaving(false);
    }
  };

  // The suggestion differs from what is ticked (a GRN summary that came later).
  const useSuggested = async () => {
    const keys = data.suggested;
    setSaving(true);
    setError(null);
    try {
      await setParkingGRs(invoice.id, keys);
      setSelected(new Set(keys));
      onChanged?.();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not save the selection.");
    } finally {
      setSaving(false);
    }
  };
  const forgetSrns = async () => {
    try {
      await clearSrnList(invoice.id);
      onChanged?.();
      load();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not remove the SRNs.");
    }
  };

  const grs = data?.grs || [];
  const closed = data?.closed || [];
  // Selected open quantity per PO item, to compare with what the invoice bills.
  const selectedByItem = {};
  for (const g of grs) {
    if (selected.has(g.gr_key)) selectedByItem[g.po_item] = (selectedByItem[g.po_item] || 0) + g.open_qty;
  }
  const isSuggested = data?.suggested?.length > 0 && data.suggested.length === selected.size
    && data.suggested.every((k) => selected.has(k));
  const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(6, 8)}.${d.slice(4, 6)}.${d.slice(0, 4)}` : d || "—");
  const fmtNum = (n) => Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });

  return (
    <Card
      title="Goods Receipts"
      subtitle={`Open GRs on PO ${data?.po_number || "—"} · tick the GRs this invoice parks against`}
      action={<Button variant="ghost" size="xs" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</Button>}
    >
      {error && (
        <div className="mb-3 bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-2xs text-danger-dark">{error}</div>
      )}
      {data?.message && !grs.length && <div className="text-2xs text-neutral-500">{data.message}</div>}
      {!loading && data && !grs.length && !data.message && (
        <div className="text-2xs text-neutral-500">
          {closed.length > 0
            ? "No open goods receipts: every GR on this PO is already invoiced or reversed in SAP."
            : data.ekbe_rows === 0
            ? "SAP has no goods receipt or invoice history for this PO."
            : "SAP has history for this PO, but no goods receipt of movement type 101 or 103."}
          {!closed.length && (data.unused || []).length > 0 && (
            <span> Found: {data.unused.map((u) => `${u.count} × event ${u.vgabe || "—"}${u.bwart ? `, movement ${u.bwart}` : ""}`).join(" · ")}.</span>
          )}
        </div>
      )}
      {closed.length > 0 && (
        <details className="mb-2 mt-1 text-2xs text-neutral-500">
          <summary className="cursor-pointer">Closed goods receipts ({closed.length})</summary>
          {closed.map((g) => (
            <div key={g.gr_key} className="py-0.5">
              <span className="font-mono">{g.gr_doc}/{String(g.gr_item).replace(/^0+/, "")} {g.gr_year}</span>
              {" · "}item {g.po_item} · received {fmtNum(g.received)} {g.unit} · invoiced {fmtNum(g.invoiced)} · <strong>{g.reason}</strong>
              {(g.moves || []).length > 0 && (
                <span> ({g.moves.map((m) => `${m.bwart} ${m.qty > 0 ? "+" : ""}${fmtNum(m.qty)}`).join(", ")})</span>
              )}
            </div>
          ))}
        </details>
      )}
      {data?.srn_count > 0 && (
        <div className={`mb-2 text-2xs rounded-md px-3 py-2 border ${data.srn_problems?.length
          ? "bg-warning-bg border-warning-base text-warning-dark" : "bg-success-bg border-success-base text-success-dark"}`}>
          GRN summary attached to the invoice: {data.srn_count} SRN(s){data.srn_problems?.length ? "." : ", all open in SAP."}
          {editable && (
            <button type="button" className="ml-2 underline bg-transparent border-none cursor-pointer" onClick={forgetSrns}>Remove the SRNs</button>
          )}
          {(data.srn_problems || []).map((p) => <div key={p}>{p}</div>)}
        </div>
      )}
      {grs.length > 0 && (
        <>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="text-2xs text-neutral-500 uppercase tracking-wider">
                <th className="text-left py-1.5 px-2 w-8"></th>
                <th className="text-left py-1.5 px-2">GR document</th>
                <th className="text-left py-1.5 px-2">Posted</th>
                <th className="text-left py-1.5 px-2">PO item</th>
                <th className="text-right py-1.5 px-2">Received</th>
                <th className="text-right py-1.5 px-2">Invoiced</th>
                <th className="text-right py-1.5 px-2">Open qty</th>
                <th className="text-right py-1.5 px-2">Open amount</th>
              </tr>
            </thead>
            <tbody>
              {grs.map((g) => (
                <tr key={g.gr_key} className={`border-t border-neutral-100 ${selected.has(g.gr_key) ? "bg-brand-50/40" : ""}`}>
                  <td className="py-1.5 px-2">
                    <input
                      type="checkbox"
                      aria-label={`Park against GR ${g.gr_doc} item ${g.gr_item}`}
                      checked={selected.has(g.gr_key)}
                      disabled={!editable || saving}
                      onChange={() => toggle(g.gr_key)}
                    />
                  </td>
                  <td className="py-1.5 px-2 font-mono">
                    {g.gr_doc}/{String(g.gr_item).replace(/^0+/, "")} <span className="text-neutral-400">{g.gr_year}</span>
                    {(g.srn || []).some((d) => d !== g.gr_doc) && <div className="text-2xs text-neutral-500">SRN {g.srn.join(", ")}</div>}
                  </td>
                  <td className="py-1.5 px-2">{fmtDate(g.posting_date)}</td>
                  <td className="py-1.5 px-2">{g.po_item}{g.description ? <span className="text-neutral-500"> · {g.description}</span> : null}</td>
                  <td className="py-1.5 px-2 text-right">{fmtNum(g.received)} {g.unit}</td>
                  <td className="py-1.5 px-2 text-right">
                    {fmtNum(g.invoiced)}
                    {g.parked > 0 && (
                      <div className="text-2xs text-warning-dark" title={`Parked invoice ${(g.parked_docs || []).join(", ")}`}>
                        {fmtNum(g.parked)} parked
                      </div>
                    )}
                  </td>
                  <td className="py-1.5 px-2 text-right font-semibold">{fmtNum(g.open_qty)} {g.unit}</td>
                  <td className="py-1.5 px-2 text-right font-mono">{fmtNum(g.open_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {editable && data.suggested?.length > 0 && !isSuggested && (
            <div className="mt-2 text-2xs text-warning-dark">
              {data.suggested.length} receipt(s) {data.srn_count > 0 ? "of the GRN summary " : ""}add up to the billed quantity.
              <button type="button" className="ml-1 underline bg-transparent border-none cursor-pointer" disabled={saving} onClick={useSuggested}>Tick them</button>
            </div>
          )}
          {editable && data.why_not && selected.size === 0 && (
            <div className="mt-2 text-2xs text-warning-dark">Not ticked automatically: {data.why_not}</div>
          )}
          <div className="mt-2 text-2xs text-neutral-500">
            {selected.size === 0
              ? "No GR ticked — parking uses the latest goods receipt for each PO item, and is refused if the invoice bills more than that receipt."
              : <>Selected: {Object.entries(selectedByItem).map(([item, q]) => `item ${item}: ${fmtNum(q)}`).join(" · ")}.
                  {" "}The ticked GRs must add up to the quantity the invoice bills for each item.</>}
            {isSuggested && <span className="ml-1">Ticked automatically: {data.srn_count > 0 ? "the SRNs of the attached GRN summary" : "all open GRs"} add up to the billed quantity.</span>}
            {!editable && <span className="ml-1">(Locked — the invoice is in SAP.)</span>}
          </div>
        </>
      )}
    </Card>
  );
}
