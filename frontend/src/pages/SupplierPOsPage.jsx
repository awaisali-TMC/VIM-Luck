import { useState, useEffect } from "react";
import api from "../services/api";
import { getFlippablePOs, flipPOToInvoice, refreshSupplierPOs } from "../services/purchaseOrderService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import Modal from "../components/common/Modal";

function fmtCurrency(amount, currency = "PKR") {
  if (amount == null) return "---";
  return `${currency} ${Number(amount).toLocaleString()}`;
}

function fmtDate(s) {
  if (!s) return "---";
  try {
    return new Date(s).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
  } catch {
    return s;
  }
}

const PO_STATUS_MAP = {
  open: { label: "Open", color: "bg-blue-50 text-blue-700 border-blue-200" },
  draft: { label: "Draft", color: "bg-neutral-50 text-neutral-600 border-neutral-200" },
  partially_received: { label: "Partial", color: "bg-amber-50 text-amber-700 border-amber-200" },
  fully_received: { label: "Received", color: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  closed: { label: "Closed", color: "bg-neutral-100 text-neutral-500 border-neutral-300" },
  cancelled: { label: "Cancelled", color: "bg-red-50 text-red-600 border-red-200" },
};

function POStatusBadge({ status }) {
  const s = PO_STATUS_MAP[status] || PO_STATUS_MAP.open;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-semibold border ${s.color}`}>
      {s.label}
    </span>
  );
}

/* ── Create Invoice from PO modal ────────────────────────────────────────── */
function CreateInvoiceModal({ po, defaultGstRate, onClose, onCreated }) {
  const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(today);
  const [gstRate, setGstRate] = useState(defaultGstRate);
  const [qty, setQty] = useState({}); // po_line_item_id -> quantity
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Fresh form each time the dialog opens for a PO; GST defaults to the
  // configured FBR standard rate.
  useEffect(() => {
    if (po) {
      setInvoiceNumber("");
      setInvoiceDate(new Date().toLocaleDateString("en-CA"));
      setGstRate(defaultGstRate);
      setQty({});
      setError("");
    }
  }, [po, defaultGstRate]);

  const lines = po?.line_items || [];
  const effQty = (li) => {
    const v = qty[li.id];
    return v === undefined || v === "" ? Number(li.quantity || 0) : Number(v);
  };
  const subtotal = lines.reduce((s, li) => s + effQty(li) * Number(li.unit_price || 0), 0);
  const gst = subtotal * (Number(gstRate) || 0) / 100;

  const fmt = (n) => `${po?.currency || "PKR"} ${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

  const handleCreate = async () => {
    if (!invoiceNumber.trim()) {
      setError("Enter your invoice number — the number on your own tax invoice.");
      return;
    }
    if (!invoiceDate) {
      setError("Enter the invoice date.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      const line_overrides = Object.entries(qty)
        .filter(([, v]) => v !== "" && v !== undefined)
        .map(([id, v]) => ({ po_line_item_id: Number(id), quantity: Number(v) }));
      const res = await flipPOToInvoice(po.id, {
        invoice_number: invoiceNumber.trim(),
        invoice_date: invoiceDate,
        gst_rate_pct: Number(gstRate) || 0,
        line_overrides,
      });
      onCreated?.(res.invoice_id);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not create the invoice.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full h-9 border border-neutral-200 rounded-md px-3 text-xs text-neutral-800 outline-none focus:border-brand-400 bg-neutral-25 box-border";

  return (
    <Modal
      open={!!po}
      onClose={onClose}
      title={po ? `Create Invoice from PO ${po.po_number}` : ""}
      width={640}
    >
      {po && (
        <div className="flex flex-col gap-4">
          {error && (
            <div className="bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-xs text-danger-dark">{error}</div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-1">
              <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Your Invoice # *</label>
              <input className={inputCls} type="text" placeholder="e.g. INV-2026-014" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} autoFocus />
            </div>
            <div>
              <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Invoice Date *</label>
              <input className={inputCls} type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
            </div>
            <div>
              <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">GST %</label>
              <input className={inputCls} type="number" min="0" max="100" value={gstRate} onChange={(e) => setGstRate(e.target.value)} />
            </div>
          </div>

          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">
              Items — adjust quantity for partial delivery, set 0 to skip a line
            </div>
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-neutral-25">
                  <th className="px-3 py-2 text-left text-2xs font-semibold text-neutral-500">Description</th>
                  <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500 w-24">Qty</th>
                  <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500">Rate</th>
                  <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500">Amount</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((li) => (
                  <tr key={li.id} className="border-t border-neutral-50">
                    <td className="px-3 py-2 text-neutral-800">{li.description}</td>
                    <td className="px-3 py-2 text-right">
                      <input
                        className="w-20 h-8 border border-neutral-200 rounded px-2 text-xs text-right outline-none focus:border-brand-400"
                        type="number"
                        min="0"
                        max={li.quantity ?? undefined}
                        value={qty[li.id] !== undefined ? qty[li.id] : (li.quantity ?? "")}
                        onChange={(e) => setQty((m) => ({ ...m, [li.id]: e.target.value }))}
                      />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-neutral-600">
                      {li.unit_price != null ? Number(li.unit_price).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-neutral-800">
                      {(effQty(li) * Number(li.unit_price || 0)).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-neutral-200">
                  <td colSpan={3} className="px-3 py-1.5 text-right text-neutral-500">Subtotal</td>
                  <td className="px-3 py-1.5 text-right font-mono text-neutral-800">{fmt(subtotal)}</td>
                </tr>
                <tr>
                  <td colSpan={3} className="px-3 py-1.5 text-right text-neutral-500">GST ({gstRate || 0}%)</td>
                  <td className="px-3 py-1.5 text-right font-mono text-neutral-800">{fmt(gst)}</td>
                </tr>
                <tr className="bg-neutral-25">
                  <td colSpan={3} className="px-3 py-2 text-right font-semibold text-neutral-700">Total</td>
                  <td className="px-3 py-2 text-right font-mono font-bold text-neutral-900">{fmt(subtotal + gst)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="bg-info-bg border border-info-light rounded-md px-3 py-2 text-2xs text-info-dark">
            After creating, open the invoice to attach your tax-invoice document and submit it for processing.
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-neutral-100">
            <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>Cancel</Button>
            <Button variant="primary" size="sm" onClick={handleCreate} disabled={submitting}>
              {submitting ? "Creating…" : "Create Invoice"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function SupplierPOsPage({ onInvoiceCreated }) {
  const [pos, setPOs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [selectedPO, setSelectedPO] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [invoicePO, setInvoicePO] = useState(null); // PO being invoiced
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");
  // Default GST % for the Create Invoice dialog — from the FBR Tax Rules
  // engine (GST-STD), so a government rate change is an admin edit, not a
  // deploy. Falls back to 18 if no rule is configured.
  const [defaultGstRate, setDefaultGstRate] = useState(18);

  useEffect(() => {
    (async () => {
      try {
        // Instant local list; the backend refreshes from SAP in the background.
        const data = await getFlippablePOs();
        setPOs(data || []);
      } catch {
        setPOs([]);
      } finally {
        setLoading(false);
      }
    })();

    (async () => {
      try {
        const res = await api.get("/api/tax-rules", { params: { tax_type: "gst", active_only: true } });
        const rules = res.data?.rules || [];
        const std = rules.find((r) => r.rule_code === "GST-STD") || rules[0];
        if (std?.rate != null) setDefaultGstRate(Number(std.rate));
      } catch {
        /* keep the fallback default */
      }
    })();
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshError("");
    try {
      // Waits for the SAP sync, then returns the fresh list.
      const data = await refreshSupplierPOs();
      setPOs(data || []);
    } catch {
      setRefreshError("Could not refresh from SAP — showing the last known list.");
    } finally {
      setRefreshing(false);
    }
  };

  const handleViewPO = (po) => {
    setSelectedPO(po);
    setShowDetail(true);
  };

  const startInvoice = (po) => {
    setShowDetail(false);
    setInvoicePO(po);
  };

  // Client-side filtering: status pills + free-text search over PO number
  // and line-item descriptions.
  const filteredPOs = pos.filter((po) => {
    if (statusFilter !== "all" && po.status !== statusFilter) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      po.po_number?.toLowerCase().includes(q) ||
      (po.line_items || []).some((li) => li.description?.toLowerCase().includes(q))
    );
  });

  const STATUS_FILTERS = [
    { key: "all", label: "All" },
    { key: "open", label: "Open" },
    { key: "partially_received", label: "Partial" },
    { key: "fully_received", label: "Received" },
  ];
  const countFor = (key) => (key === "all" ? pos.length : pos.filter((p) => p.status === key).length);

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white border border-neutral-100 rounded-lg px-5 py-4">
          <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Total POs</div>
          <div className="text-2xl font-bold text-neutral-900">{pos.length}</div>
        </div>
        <div className="bg-white border border-neutral-100 rounded-lg px-5 py-4">
          <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Open POs</div>
          <div className="text-2xl font-bold text-blue-600">
            {pos.filter((p) => p.status === "open").length}
          </div>
        </div>
        <div className="bg-white border border-neutral-100 rounded-lg px-5 py-4">
          <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Ready for Invoice</div>
          <div className="text-2xl font-bold text-emerald-600">
            {pos.filter((p) => ["open", "partially_received", "fully_received"].includes(p.status)).length}
          </div>
        </div>
      </div>

      {/* PO List */}
      <Card
        title="Purchase Orders"
        subtitle={refreshError || undefined}
        action={
          <Button variant="secondary" size="xs" onClick={handleRefresh} disabled={refreshing || loading}>
            {refreshing ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                </svg>
                Refreshing from SAP…
              </>
            ) : (
              <>⟳ Refresh from SAP</>
            )}
          </Button>
        }
        noPad
      >
        {/* Toolbar: status filter pills + search */}
        <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-neutral-100">
          <div className="flex bg-neutral-50 border border-neutral-100 rounded-lg p-0.5 gap-0.5">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setStatusFilter(f.key)}
                className={`text-xs font-semibold px-3 py-1.5 rounded-md cursor-pointer border-none transition-all ${
                  statusFilter === f.key
                    ? "bg-white text-neutral-900 shadow-xs"
                    : "bg-transparent text-neutral-500 hover:text-neutral-700"
                }`}
              >
                {f.label}
                <span className="ml-1.5 text-[10px] font-bold px-1.5 py-px rounded-full bg-neutral-100 text-neutral-500">
                  {countFor(f.key)}
                </span>
              </button>
            ))}
          </div>
          <input
            type="text"
            placeholder="Search PO number or item…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-xs border border-neutral-200 rounded-lg px-3 py-2 outline-none focus:border-emerald-400 bg-neutral-50 w-56"
          />
        </div>

        {loading ? (
          <div className="text-center py-12 text-xs text-neutral-400">Loading purchase orders...</div>
        ) : pos.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-[40px] mb-3">📋</div>
            <div className="text-sm font-semibold text-neutral-700">No purchase orders yet</div>
            <div className="text-xs text-neutral-400 mt-1">Purchase orders assigned to you will appear here</div>
          </div>
        ) : filteredPOs.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-sm font-semibold text-neutral-700">No POs match</div>
            <div className="text-xs text-neutral-400 mt-1">Try a different status or search term</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-neutral-25 border-b border-neutral-100">
                  {["SR#", "PO Number", "Date", "Amount", "Type", "Status", ""].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {filteredPOs.map((po, idx) => (
                  <tr key={po.id} className="hover:bg-neutral-25 transition-colors">
                    <td className="px-4 py-3 text-neutral-400">{idx + 1}</td>
                    <td className="px-4 py-3 font-mono font-semibold text-brand-600">{po.po_number}</td>
                    <td className="px-4 py-3 text-neutral-500">{fmtDate(po.po_date)}</td>
                    <td className="px-4 py-3 font-semibold text-neutral-800">{fmtCurrency(po.total_amount, po.currency)}</td>
                    <td className="px-4 py-3 text-neutral-500 capitalize">{(po.po_type || "local").replace(/_/g, " ")}</td>
                    <td className="px-4 py-3"><POStatusBadge status={po.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="secondary" size="xs" onClick={() => handleViewPO(po)}>
                          View
                        </Button>
                        {["open", "partially_received", "fully_received"].includes(po.status) && (
                          <Button variant="primary" size="xs" onClick={() => startInvoice(po)}>
                            Create Invoice
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* PO Detail Modal */}
      <Modal
        open={showDetail}
        title={selectedPO ? `PO: ${selectedPO.po_number}` : "Purchase Order"}
        onClose={() => setShowDetail(false)}
        width={700}
      >
        {selectedPO ? (
          <div className="flex flex-col gap-4">
            {/* PO Header */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">PO Number</div>
                <div className="text-xs font-semibold text-neutral-800">{selectedPO.po_number}</div>
              </div>
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">PO Date</div>
                <div className="text-xs text-neutral-700">{fmtDate(selectedPO.po_date)}</div>
              </div>
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">Status</div>
                <POStatusBadge status={selectedPO.status} />
              </div>
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">Vendor</div>
                <div className="text-xs text-neutral-700">{selectedPO.vendor_name}</div>
              </div>
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">Total Amount</div>
                <div className="text-xs font-semibold text-neutral-900">{fmtCurrency(selectedPO.total_amount, selectedPO.currency)}</div>
              </div>
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase">Type</div>
                <div className="text-xs text-neutral-700 capitalize">{(selectedPO.po_type || "local").replace(/_/g, " ")}</div>
              </div>
            </div>

            {/* Line Items */}
            {selectedPO.line_items && selectedPO.line_items.length > 0 && (
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">Line Items</div>
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="bg-neutral-25">
                      <th className="px-3 py-2 text-left text-2xs font-semibold text-neutral-500">#</th>
                      <th className="px-3 py-2 text-left text-2xs font-semibold text-neutral-500">Description</th>
                      <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500">Qty</th>
                      <th className="px-3 py-2 text-left text-2xs font-semibold text-neutral-500">Unit</th>
                      <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500">Rate</th>
                      <th className="px-3 py-2 text-right text-2xs font-semibold text-neutral-500">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedPO.line_items.map((li, i) => (
                      <tr key={li.id || i} className="border-t border-neutral-50">
                        <td className="px-3 py-2 text-neutral-400">{li.item_number || i + 1}</td>
                        <td className="px-3 py-2 text-neutral-800">{li.description}</td>
                        <td className="px-3 py-2 text-right text-neutral-600">{li.quantity}</td>
                        <td className="px-3 py-2 text-neutral-500">{li.unit || "---"}</td>
                        <td className="px-3 py-2 text-right font-mono text-neutral-600">
                          {li.unit_price != null ? Number(li.unit_price).toLocaleString() : "---"}
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-semibold text-neutral-800">
                          {li.amount != null ? Number(li.amount).toLocaleString() : "---"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-neutral-200 bg-neutral-25">
                      <td colSpan={5} className="px-3 py-2 text-right font-semibold text-neutral-600">Total</td>
                      <td className="px-3 py-2 text-right font-bold font-mono text-neutral-900">
                        {selectedPO.currency || "PKR"} {Number(selectedPO.total_amount || 0).toLocaleString()}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}

            {selectedPO.notes && (
              <div>
                <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Notes</div>
                <div className="text-xs text-neutral-600 bg-neutral-25 rounded-md px-3 py-2">{selectedPO.notes}</div>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-2 border-t border-neutral-100">
              <Button variant="secondary" size="sm" onClick={() => setShowDetail(false)}>
                Close
              </Button>
              {["open", "partially_received", "fully_received"].includes(selectedPO.status) && (
                <Button variant="primary" size="sm" onClick={() => startInvoice(selectedPO)}>
                  Create Invoice from this PO
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-xs text-neutral-400">Failed to load PO</div>
        )}
      </Modal>

      {/* Create Invoice from PO */}
      <CreateInvoiceModal
        po={invoicePO}
        defaultGstRate={defaultGstRate}
        onClose={() => setInvoicePO(null)}
        onCreated={(invoiceId) => {
          setInvoicePO(null);
          onInvoiceCreated?.(invoiceId);
        }}
      />
    </div>
  );
}
