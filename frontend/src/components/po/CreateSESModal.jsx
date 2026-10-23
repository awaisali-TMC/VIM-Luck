import { useState, useCallback } from "react";
import { createSES } from "../../services/purchaseOrderService";
import Modal from "../common/Modal";
import Button from "../common/Button";

export default function CreateSESModal({ open, onClose, poId, poLineItems, onCreated }) {
  const [form, setForm] = useState({
    ses_number: "",
    ses_date: "",
    service_period_from: "",
    service_period_to: "",
    notes: "",
  });
  const [lineItems, setLineItems] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Initialize line items from PO when modal opens
  const handleOpen = useCallback(() => {
    setLineItems(
      poLineItems.map((li) => ({
        po_line_item_id: li.id,
        description: li.description,
        ordered_qty: li.quantity,
        ordered_amount: li.amount,
        completed_quantity: "",
        completed_amount: "",
      }))
    );
    setForm({ ses_number: "", ses_date: "", service_period_from: "", service_period_to: "", notes: "" });
    setError(null);
  }, [poLineItems]);

  // Init on open
  if (open && lineItems.length === 0 && poLineItems.length > 0) {
    handleOpen();
  }

  const handleFieldChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleLineChange = (index, field, value) => {
    setLineItems((prev) => {
      const updated = [...prev];
      const item = { ...updated[index], [field]: value };
      // Auto-calc completed_amount from quantity if unit_price available
      if (field === "completed_quantity") {
        const poLine = poLineItems.find((li) => li.id === item.po_line_item_id);
        if (poLine?.unit_price) {
          item.completed_amount = Math.round(parseFloat(value || 0) * poLine.unit_price * 100) / 100;
        }
      }
      updated[index] = item;
      return updated;
    });
  };

  const handleSubmit = useCallback(async () => {
    if (!form.ses_number.trim()) {
      setError("SES Number is required.");
      return;
    }

    const filledLines = lineItems.filter((li) => li.completed_quantity !== "" && parseFloat(li.completed_quantity) > 0);
    if (filledLines.length === 0) {
      setError("At least one line item must have a completed quantity.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createSES(poId, {
        ses_number: form.ses_number,
        ses_date: form.ses_date || null,
        po_id: poId,
        service_period_from: form.service_period_from || null,
        service_period_to: form.service_period_to || null,
        notes: form.notes || null,
        line_items: filledLines.map((li) => ({
          po_line_item_id: li.po_line_item_id,
          completed_quantity: parseFloat(li.completed_quantity),
          completed_amount: li.completed_amount ? parseFloat(li.completed_amount) : null,
        })),
      });
      setLineItems([]);
      onCreated?.();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to create SES");
    } finally {
      setSaving(false);
    }
  }, [form, lineItems, poId, onCreated]);

  const handleClose = () => {
    setLineItems([]);
    setError(null);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Create Service Entry Sheet (SES)"
      width={750}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={handleClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={handleSubmit} disabled={saving}>
            {saving ? "Creating..." : "Create SES"}
          </Button>
        </>
      }
    >
      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-4">
          <span className="text-2xs text-danger-dark font-medium">{error}</span>
        </div>
      )}

      {/* SES Header */}
      <div className="grid grid-cols-2 gap-4 mb-5">
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">SES Number *</label>
          <input
            type="text"
            value={form.ses_number}
            onChange={(e) => handleFieldChange("ses_number", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
            placeholder="e.g. SES-1000070334"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">SES Date</label>
          <input
            type="date"
            value={form.ses_date}
            onChange={(e) => handleFieldChange("ses_date", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Service Period From</label>
          <input
            type="date"
            value={form.service_period_from}
            onChange={(e) => handleFieldChange("service_period_from", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Service Period To</label>
          <input
            type="date"
            value={form.service_period_to}
            onChange={(e) => handleFieldChange("service_period_to", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
          />
        </div>
      </div>

      {/* Line Items */}
      <div className="text-xs font-semibold text-neutral-700 mb-2">Completed Services</div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left">PO Line Item</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-20">Ordered</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-28">Completed Qty *</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-28">Amount</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((li, idx) => (
              <tr key={idx} className={idx % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
                <td className="px-3 py-2 border-b border-neutral-50 text-neutral-800">
                  <span className="text-neutral-400 mr-1">#{idx + 1}</span> {li.description || "N/A"}
                </td>
                <td className="px-3 py-2 border-b border-neutral-50 text-right text-neutral-600 font-mono">
                  {li.ordered_qty}
                </td>
                <td className="px-3 py-2 border-b border-neutral-50">
                  <input
                    type="number"
                    value={li.completed_quantity}
                    onChange={(e) => handleLineChange(idx, "completed_quantity", e.target.value)}
                    className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400 text-right"
                    placeholder="0"
                    min="0"
                  />
                </td>
                <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono text-neutral-700">
                  {li.completed_amount ? Number(li.completed_amount).toLocaleString() : "\u2014"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Notes */}
      <div className="mt-4">
        <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Notes</label>
        <textarea
          value={form.notes}
          onChange={(e) => handleFieldChange("notes", e.target.value)}
          className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 resize-none"
          rows={2}
          placeholder="Any remarks about the service completion..."
        />
      </div>
    </Modal>
  );
}
