import { useCallback, useEffect, useState } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import { getDeliveryCosts } from "../../services/sapService";
import { setDeliveryCosts } from "../../services/invoiceService";

// What Lucky's own MIR7 uses on freight; the user can change it per condition.
const DEFAULT_TAX_CODE = "I0";

/**
 * Planned delivery costs (freight conditions) of the matched PO, live from SAP
 * (EKBZ). Nothing is parked unless it is ticked here; each has its own tax code.
 * The amount is the share of the GRs ticked in the Goods Receipts card, or all
 * that is open when none is ticked.
 *
 * Shown only when "Items to Park" includes planned delivery costs.
 * Props: invoice, taxCodes, editable, onChanged().
 */
export default function DeliveryCostsCard({ invoice, taxCodes = [], editable = false, onChanged }) {
  const [data, setData] = useState(null);       // { costs, chosen, grs_ticked, message }
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const grKey = (invoice?.parking_gr_refs || []).join(",");
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getDeliveryCosts(invoice.id));
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not read planned delivery costs.");
    } finally {
      setLoading(false);
    }
  }, [invoice?.id]);

  useEffect(() => { if (invoice?.id) load(); }, [load, invoice?.id, invoice?.matched_po_id, grKey]);

  const costs = data?.costs || [];
  const chosen = data?.chosen || [];
  const find = (c) => chosen.find((x) => x.po_item === c.po_item && x.cond_type === c.cond_type);
  // Ticked earlier, but no longer open in SAP: keep it visible so it can be removed.
  const gone = data && !data.message
    ? chosen.filter((x) => !costs.some((c) => c.po_item === x.po_item && c.cond_type === x.cond_type)) : [];
  const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 3 }));
  const inputCodes = taxCodes.filter((t) => t.tax_type !== "output");

  const save = async (items) => {
    const before = chosen;
    setData((d) => ({ ...d, chosen: items }));
    setSaving(true);
    setError(null);
    try {
      await setDeliveryCosts(invoice.id, items);
      onChanged?.();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not save the delivery costs.");
      setData((cur) => ({ ...cur, chosen: before }));
    } finally {
      setSaving(false);
    }
  };
  const without = (c) => chosen.filter((x) => !(x.po_item === c.po_item && x.cond_type === c.cond_type));
  const toggle = (c) => save(find(c) ? without(c)
    : [...chosen, { po_item: c.po_item, cond_type: c.cond_type, tax_code: DEFAULT_TAX_CODE }]);
  const setCode = (c, code) => save(chosen.map((x) =>
    x.po_item === c.po_item && x.cond_type === c.cond_type ? { ...x, tax_code: code } : x));

  return (
    <Card
      title="Planned Delivery Costs"
      subtitle="Freight and other conditions on the PO · tick the ones this invoice bills"
      action={<Button variant="ghost" size="xs" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</Button>}
    >
      {error && <div className="mb-3 bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-2xs text-danger-dark">{error}</div>}
      {data?.message && <div className="text-2xs text-neutral-500">{data.message}</div>}
      {!loading && data && !data.message && costs.length === 0 && (
        <div className="text-2xs text-neutral-500">SAP has no open planned delivery cost for this PO.</div>
      )}
      {costs.length > 0 && (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-2xs text-neutral-500 uppercase tracking-wider">
              <th className="text-left py-1.5 px-2 w-8"></th>
              <th className="text-left py-1.5 px-2">Condition</th>
              <th className="text-left py-1.5 px-2">PO item</th>
              <th className="text-left py-1.5 px-2">Vendor</th>
              <th className="text-right py-1.5 px-2">Quantity</th>
              <th className="text-right py-1.5 px-2">Amount</th>
              <th className="text-left py-1.5 px-2">Tax code</th>
            </tr>
          </thead>
          <tbody>
            {costs.map((c) => {
              const sel = find(c);
              return (
                <tr key={`${c.po_item}/${c.cond_type}`} className={`border-t border-neutral-100 ${sel ? "bg-brand-50/40" : ""}`}>
                  <td className="py-1.5 px-2">
                    <input
                      type="checkbox"
                      aria-label={`Park delivery cost ${c.cond_type}`}
                      checked={!!sel}
                      disabled={!editable || saving || (c.other_vendor && !sel)}
                      onChange={() => toggle(c)}
                    />
                  </td>
                  <td className="py-1.5 px-2 font-mono">
                    {c.cond_type}
                    {c.other_vendor && <div className="text-2xs text-danger-dark font-sans">another vendor&apos;s freight</div>}
                    {c.parked > 0 && <div className="text-2xs text-warning-dark font-sans">{fmt(c.parked)} parked</div>}
                    {c.problem && <div className="text-2xs text-danger-dark font-sans">{c.problem}</div>}
                  </td>
                  <td className="py-1.5 px-2">{c.po_item}{c.description ? <span className="text-neutral-500"> · {c.description}</span> : null}</td>
                  <td className="py-1.5 px-2 font-mono">{(c.vendor || "").replace(/^0+/, "") || "—"}</td>
                  <td className="py-1.5 px-2 text-right">{fmt(c.park_quantity)} {c.unit}</td>
                  <td className="py-1.5 px-2 text-right font-mono">{fmt(c.park_amount)}</td>
                  <td className="py-1.5 px-2">
                    {sel ? (
                      <select
                        value={sel.tax_code}
                        disabled={!editable || saving}
                        onChange={(e) => setCode(c, e.target.value)}
                        className="text-xs border border-neutral-200 rounded px-1 py-0.5 max-w-[14rem]"
                        aria-label={`Tax code for ${c.cond_type}`}
                      >
                        {!inputCodes.some((t) => t.code === sel.tax_code) && <option value={sel.tax_code}>{sel.tax_code}</option>}
                        {inputCodes.map((t) => <option key={t.code} value={t.code}>{t.code} — {t.description}</option>)}
                      </select>
                    ) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {gone.map((c) => (
        <div key={`gone-${c.po_item}/${c.cond_type}`} className="mt-2 text-2xs text-danger-dark">
          {c.cond_type} (PO item {c.po_item}) is ticked but has nothing left to invoice in SAP.
          {editable && <button type="button" className="ml-1 underline bg-transparent border-none cursor-pointer" onClick={() => save(without(c))}>Remove</button>}
        </div>
      ))}
      {costs.length > 0 && (
        <div className="mt-2 text-2xs text-neutral-500">
          {data.grs_ticked > 0
            ? `Amounts are for the ${data.grs_ticked} ticked goods receipt(s).`
            : "No goods receipt is ticked: amounts are everything still open on the PO."}
          {" "}Parking is refused if goods, freight and tax exceed the vendor&apos;s invoice total.
          {!editable && <span className="ml-1">(Locked — the invoice is in SAP.)</span>}
        </div>
      )}
    </Card>
  );
}
