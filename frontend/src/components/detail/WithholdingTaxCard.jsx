import { useCallback, useEffect, useState } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import { getInvoiceWHT } from "../../services/sapService";
import { setInvoiceWHT } from "../../services/invoiceService";

/**
 * Lucky Cement (observation G) — withholding tax.
 *
 * Shows the vendor's WHT types/codes from its BP in SAP (LFBW, rate from
 * T059Z) with an estimate on the invoice's net amount. The user can tick which
 * of the vendor's OWN types apply to this invoice (Lucky has one code per
 * type); those are then sent as WITHTAXDATA. Without a change nothing is sent.
 *
 * Props: invoice, editable, onChanged().
 */
export default function WithholdingTaxCard({ invoice, editable = false, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);     // Set of ticked WHT types while editing
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getInvoiceWHT(invoice.id));
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not read the vendor's withholding tax.");
    } finally {
      setLoading(false);
    }
  }, [invoice?.id]);

  useEffect(() => { if (invoice?.id) load(); }, [load, invoice?.id, invoice?.matched_po_id]);

  const bpRows = data?.vendor_wht || [];        // only these may be chosen
  const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 }));
  const cur = invoice?.currency || "PKR";
  const override = data?.override;
  const rows = override || bpRows;

  const startEdit = () => setDraft(new Set(
    rows.filter((r) => bpRows.some((b) => b.wht_type === r.wht_type)).map((r) => r.wht_type)));
  const draftItems = () => bpRows.filter((r) => draft.has(r.wht_type))
    .map((r) => ({ wht_type: r.wht_type, wht_code: r.wht_code || r.wht_type }));
  const save = async (items) => {
    setSaving(true);
    setError(null);
    try {
      await setInvoiceWHT(invoice.id, items);
      setDraft(null);
      await load();
      onChanged?.();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Could not save the withholding tax.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      title="Withholding Tax"
      subtitle={data?.vendor_number
        ? `Vendor ${data.vendor_number} · company code ${data.company_code} · from the vendor's BP in SAP`
        : "From the vendor's BP in SAP"}
      action={
        <div className="flex items-center gap-2">
          {editable && !draft && bpRows.length > 0 && <Button variant="secondary" size="xs" onClick={startEdit}>Change</Button>}
          {editable && override && !draft && (
            <Button variant="ghost" size="xs" onClick={() => save([])} disabled={saving}>Use vendor BP</Button>
          )}
          <Button variant="ghost" size="xs" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</Button>
        </div>
      }
    >
      {error && <div className="mb-3 bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-2xs text-danger-dark">{error}</div>}
      {data?.message && <div className="text-2xs text-neutral-500">{data.message}</div>}
      {!loading && data && !data.message && rows.length === 0 && (
        <div className="text-2xs text-neutral-500">No withholding tax maintained for this vendor in SAP.</div>
      )}

      {rows.length > 0 && !draft && (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-2xs text-neutral-500 uppercase tracking-wider">
              <th className="text-left py-1.5 px-2">WHT type</th>
              <th className="text-left py-1.5 px-2">WHT code</th>
              <th className="text-left py-1.5 px-2">Description</th>
              <th className="text-right py-1.5 px-2">Rate</th>
              <th className="text-right py-1.5 px-2">Est. WHT ({cur})</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.wht_type}/${r.wht_code}`} className="border-t border-neutral-100">
                <td className="py-1.5 px-2 font-mono">{r.wht_type}</td>
                <td className="py-1.5 px-2 font-mono">{r.wht_code || "—"}</td>
                <td className="py-1.5 px-2">
                  {r.name || "—"}
                  {r.in_bp === false && <span className="ml-1 text-danger-dark">(not in the vendor's BP — SAP parking is blocked)</span>}
                  {r.subject === false && <span className="ml-1 text-neutral-400">(not subject)</span>}
                </td>
                <td className="py-1.5 px-2 text-right">{r.rate == null ? "—" : `${fmt(r.rate)}%`}</td>
                <td className="py-1.5 px-2 text-right font-mono">{fmt(r.estimate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {draft && (
        <div className="flex flex-col gap-2 text-xs">
          <div className="text-2xs text-neutral-500">Tick the vendor's WHT types that apply to this invoice.</div>
          {bpRows.map((r) => (
            <label key={r.wht_type} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={draft.has(r.wht_type)}
                onChange={() => {
                  const next = new Set(draft);
                  if (next.has(r.wht_type)) next.delete(r.wht_type); else next.add(r.wht_type);
                  setDraft(next);
                }}
              />
              <span className="font-mono w-8">{r.wht_type}</span>
              <span>{r.name || "—"}{r.rate == null ? "" : ` · ${fmt(r.rate)}%`}</span>
            </label>
          ))}
          {draft.size === 0 && <div className="text-2xs text-danger-dark">Tick at least one, or use the vendor BP.</div>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="xs" type="button" onClick={() => setDraft(null)} disabled={saving}>Cancel</Button>
            <Button variant="primary" size="xs" type="button" onClick={() => save(draftItems())} disabled={saving || draft.size === 0}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}

      {data && !data.message && (
        <div className="mt-2 text-2xs text-neutral-500">
          {override
            ? "Changed for this invoice — sent to SAP (WITHTAXDATA) when parking."
            : "Vendor BP — nothing is sent; SAP decides from the vendor's BP when parking."}
          {" "}Estimate on the net amount {fmt(data.base)}; SAP calculates the actual amount.
          {!editable && <span className="ml-1">(Locked — the invoice is in SAP.)</span>}
        </div>
      )}
    </Card>
  );
}
