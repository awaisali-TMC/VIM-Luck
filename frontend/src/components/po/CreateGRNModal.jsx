import { useState, useCallback } from "react";
import { createGRN } from "../../services/purchaseOrderService";
import Modal from "../common/Modal";
import Button from "../common/Button";

export default function CreateGRNModal({ open, onClose, poId, poLineItems, onCreated }) {
  const [form, setForm] = useState({
    grn_number: "",
    grn_date: "",
    received_by: "",
    plant_location: "",
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
        received_quantity: "",
        inspection_status: "accepted",
      }))
    );
    setForm({ grn_number: "", grn_date: "", received_by: "", plant_location: "", notes: "" });
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
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleSubmit = useCallback(async () => {
    if (!form.grn_number.trim()) {
      setError("GRN Number is required.");
      return;
    }

    const filledLines = lineItems.filter((li) => li.received_quantity !== "" && parseFloat(li.received_quantity) > 0);
    if (filledLines.length === 0) {
      setError("At least one line item must have a received quantity.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createGRN(poId, {
        grn_number: form.grn_number,
        grn_date: form.grn_date || null,
        po_id: poId,
        received_by: form.received_by || null,
        plant_location: form.plant_location || null,
        notes: form.notes || null,
        line_items: filledLines.map((li) => ({
          po_line_item_id: li.po_line_item_id,
          received_quantity: parseFloat(li.received_quantity),
          inspection_status: li.inspection_status,
        })),
      });
      setLineItems([]);
      onCreated?.();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to create GRN");
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
      title="Create Goods Received Note (GRN)"
      width={750}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={handleClose}>Cancel</Button>
          <Button variant="primary" size="sm" onClick={handleSubmit} disabled={saving}>
            {saving ? "Creating..." : "Create GRN"}
          </Button>
        </>
      }
    >
      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-4">
          <span className="text-2xs text-danger-dark font-medium">{error}</span>
        </div>
      )}

      {/* GRN Header */}
      <div className="grid grid-cols-2 gap-4 mb-5">
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">GRN Number *</label>
          <input
            type="text"
            value={form.grn_number}
            onChange={(e) => handleFieldChange("grn_number", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
            placeholder="e.g. GRN-QP-5000132924/2025"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">GRN Date</label>
          <input
            type="date"
            value={form.grn_date}
            onChange={(e) => handleFieldChange("grn_date", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Received By</label>
          <input
            type="text"
            value={form.received_by}
            onChange={(e) => handleFieldChange("received_by", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
            placeholder="Name of receiver"
          />
        </div>
        <div>
          <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Plant / Location</label>
          <input
            type="text"
            value={form.plant_location}
            onChange={(e) => handleFieldChange("plant_location", e.target.value)}
            className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
            placeholder="e.g. QP (Quetta Plant)"
          />
        </div>
      </div>

      {/* Line Items */}
      <div className="text-xs font-semibold text-neutral-700 mb-2">Received Quantities</div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left">PO Line Item</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-20">Ordered</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-28">Received Qty *</th>
              <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left w-32">Inspection</th>
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
                    value={li.received_quantity}
                    onChange={(e) => handleLineChange(idx, "received_quantity", e.target.value)}
                    className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400 text-right"
                    placeholder="0"
                    min="0"
                  />
                </td>
                <td className="px-3 py-2 border-b border-neutral-50">
                  <select
                    value={li.inspection_status}
                    onChange={(e) => handleLineChange(idx, "inspection_status", e.target.value)}
                    className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400 bg-white"
                  >
                    <option value="accepted">Accepted</option>
                    <option value="rejected">Rejected</option>
                    <option value="pending">Pending</option>
                  </select>
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
          placeholder="Any remarks about the delivery..."
        />
      </div>
    </Modal>
  );
}
