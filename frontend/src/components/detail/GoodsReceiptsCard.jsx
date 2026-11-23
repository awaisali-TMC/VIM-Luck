import { useCallback, useEffect, useState } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import { getOpenGRs } from "../../services/sapService";
import { setParkingGRs } from "../../services/invoiceService";

/**
 * Lucky Cement (observation F) — GR-wise parking.
 *
 * Lists the matched PO's goods receipts that are not yet fully invoiced (live
 * from SAP EKBE) with a checkbox each. The ticked GRs are saved on the invoice
 * (parking_gr_refs); parking then sends one item per ticked GR, referencing it.
 * With nothing ticked, parking picks the latest GR per PO item as before.
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

  useEffect(() => { load(); }, [load]);

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

  const grs = data?.grs || [];
  // Selected open quantity per PO item, to compare with what the invoice bills.
  const selectedByItem = {};
  for (const g of grs) {
    if (selected.has(g.gr_key)) selectedByItem[g.po_item] = (selectedByItem[g.po_item] || 0) + g.open_qty;
  }
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
        <div className="text-2xs text-neutral-500">No open goods receipts on this PO in SAP.</div>
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
                  <td className="py-1.5 px-2 font-mono">{g.gr_doc}/{String(g.gr_item).replace(/^0+/, "")} <span className="text-neutral-400">{g.gr_year}</span></td>
                  <td className="py-1.5 px-2">{fmtDate(g.posting_date)}</td>
                  <td className="py-1.5 px-2">{g.po_item}{g.description ? <span className="text-neutral-500"> · {g.description}</span> : null}</td>
                  <td className="py-1.5 px-2 text-right">{fmtNum(g.received)} {g.unit}</td>
                  <td className="py-1.5 px-2 text-right">{fmtNum(g.invoiced)}</td>
                  <td className="py-1.5 px-2 text-right font-semibold">{fmtNum(g.open_qty)} {g.unit}</td>
                  <td className="py-1.5 px-2 text-right font-mono">{fmtNum(g.open_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 text-2xs text-neutral-500">
            {selected.size === 0
              ? "No GR ticked — parking uses the latest goods receipt for each PO item."
              : <>Selected: {Object.entries(selectedByItem).map(([item, q]) => `item ${item}: ${fmtNum(q)}`).join(" · ")}.
                  {" "}The ticked GRs must add up to the quantity the invoice bills for each item.</>}
            {!editable && <span className="ml-1">(Locked — the invoice is in SAP.)</span>}
          </div>
        </>
      )}
    </Card>
  );
}
