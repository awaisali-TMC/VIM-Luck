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
 * With goods on the same invoice (layout "both") the amount is the share of the
 * GRs ticked in the Goods Receipts card, or all that is open when none is ticked.
 * Freight on its own invoice (layout "delivery") has its own SRN choice here.
 *
 * Shown only when "Items to Park" includes planned delivery costs.
 * Props: invoice, layout, taxCodes, editable, onChanged().
 */
export default function DeliveryCostsCard({ invoice, layout, taxCodes = [], editable = false, onChanged }) {
  const [data, setData] = useState(null);       // { costs, chosen, grs_ticked, message }
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const alone = layout === "delivery";
  const grKey = `${(invoice?.parking_gr_refs || []).join(",")}|${invoice?.sap_layout}`;
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
  // SRNs (goods receipts) of a freight-only invoice; none listed = SAP can't split it.
  const bySrn = (c) => alone && (c.grs || []).length > 0;
  const free = (c) => c.grs.filter((g) => !g.taken_by);
  const change = (c, patch) => save(chosen.map((x) =>
    x.po_item === c.po_item && x.cond_type === c.cond_type ? { ...x, ...patch } : x));
  // Ticking a condition takes the SRNs of the attached GRN summary, else every SRN
  // no other invoice bills; the user corrects the rest.
  const preset = (c) => {
    const listed = free(c).filter((g) => g.listed);
    return (listed.length ? listed : free(c)).map((g) => g.gr_key);
  };
  const toggle = (c) => save(find(c) ? without(c) : [...chosen, {
    po_item: c.po_item, cond_type: c.cond_type, tax_code: DEFAULT_TAX_CODE,
    ...(bySrn(c) ? { gr_keys: preset(c) } : {}),
  }]);
  const setCode = (c, code) => change(c, { tax_code: code });
  const srnTicked = (c, g) => (find(c)?.gr_keys || []).includes(g.gr_key);
  const toggleSrn = (c, g) => {
    const keys = find(c)?.gr_keys || [];
    change(c, { gr_keys: srnTicked(c, g) ? keys.filter((k) => k !== g.gr_key) : [...keys, g.gr_key] });
  };
  const sum = (c, field) => c.grs.filter((g) => srnTicked(c, g)).reduce((t, g) => t + g[field], 0);
  const amountOf = (c) => (bySrn(c) && find(c)?.gr_keys ? sum(c, "amount") : c.park_amount);
  const qtyOf = (c) => (bySrn(c) && find(c)?.gr_keys ? sum(c, "quantity") : c.park_quantity);
  const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(6, 8)}.${d.slice(4, 6)}.${d.slice(0, 4)}` : d || "—");
  const rateOf = (code) => Number(taxCodes.find((t) => t.code === code)?.rate || 0);
  const total = costs.filter(find).reduce((t, c) => t + (amountOf(c) || 0) * (1 + rateOf(find(c).tax_code) / 100), 0);
  const billed = Number(invoice?.total_amount || 0);

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
                  <td className="py-1.5 px-2 text-right">{fmt(qtyOf(c))} {c.unit}</td>
                  <td className="py-1.5 px-2 text-right font-mono">{fmt(amountOf(c))}</td>
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
      {alone && costs.filter((c) => find(c) && bySrn(c) && find(c).gr_keys).map((c) => (
        <div key={`srn-${c.po_item}/${c.cond_type}`} className="mt-3 text-xs">
          <div className="text-2xs text-neutral-500 mb-1">SRNs whose {c.cond_type} this invoice bills</div>
          {c.grs.map((g) => (
            <label key={g.gr_key} className="flex items-center gap-2 py-0.5">
              <input
                type="checkbox"
                checked={srnTicked(c, g)}
                disabled={!editable || saving || (!!g.taken_by && !srnTicked(c, g))}
                onChange={() => toggleSrn(c, g)}
                aria-label={`Freight of SRN ${g.srn.join(", ")}`}
              />
              <span className="font-mono">{g.srn.join(", ")}</span>
              <span className="text-neutral-500">{fmtDate(g.posting_date)} · {fmt(g.quantity)} {c.unit}</span>
              <span className="font-mono ml-auto">{fmt(g.amount)}</span>
              {g.taken_by && <span className="text-2xs text-danger-dark">on invoice {g.taken_by.invoice_number} (#{g.taken_by.id})</span>}
            </label>
          ))}
        </div>
      ))}
      {alone && total > 0 && billed > 0 && (
        <div className={`mt-2 text-xs ${Math.abs(total - billed) > 1 ? "text-danger-dark" : "text-success-dark"}`}>
          Ticked freight with tax {fmt(total)} · vendor&apos;s invoice {fmt(billed)}
          {Math.abs(total - billed) > 1 ? ": they must be equal to park." : "."}
        </div>
      )}
      {gone.map((c) => (
        <div key={`gone-${c.po_item}/${c.cond_type}`} className="mt-2 text-2xs text-danger-dark">
          {c.cond_type} (PO item {c.po_item}) is ticked but has nothing left to invoice in SAP.
          {editable && <button type="button" className="ml-1 underline bg-transparent border-none cursor-pointer" onClick={() => save(without(c))}>Remove</button>}
        </div>
      ))}
      {costs.length > 0 && (
        <div className="mt-2 text-2xs text-neutral-500">
          {alone
            ? "Freight on its own invoice: no goods are parked with it."
            : data.grs_ticked > 0
            ? `Amounts are for the ${data.grs_ticked} ticked goods receipt(s).`
            : "No goods receipt is ticked: amounts are everything still open on the PO."}
          {!alone && " Parking is refused if goods, freight and tax exceed the vendor's invoice total."}
          {!editable && <span className="ml-1">(Locked — the invoice is in SAP.)</span>}
        </div>
      )}
    </Card>
  );
}
