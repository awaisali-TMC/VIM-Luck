import { useState, useEffect, useCallback } from "react";
import {
  getInvoice,
  updateInvoice,
  updateInvoiceStatus,
} from "../services/invoiceService";

/** Returns true when the invoice has line items but none have been matched yet. */
function isMatchingPending(inv) {
  if (!inv || inv.status === "draft") return false;
  if (!inv.line_items?.length) return false;
  return !inv.line_items.some((li) => li.matched_product_code);
}

/**
 * State management hook for Invoice Detail page.
 * Handles: data fetching, edit mode (fields + line items), saving edits, status transitions.
 * Auto-polls every 3 s while product matching is still running in the background.
 */
export default function useInvoiceDetail(invoiceId) {
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState({});
  const [editLineItems, setEditLineItems] = useState([]);
  const [saving, setSaving] = useState(false);

  // Load invoice on mount or when id changes
  useEffect(() => {
    if (!invoiceId) return;
    setLoading(true);
    setError(null);
    getInvoice(invoiceId)
      .then((data) => {
        setInvoice(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(
          err.response?.data?.detail || err.message || "Failed to load invoice"
        );
        setLoading(false);
      });
  }, [invoiceId]);

  // Poll every 3 s while product matching is still running
  useEffect(() => {
    if (!invoice || !isMatchingPending(invoice)) return;
    const id = setInterval(() => {
      getInvoice(invoiceId)
        .then((data) => setInvoice(data))
        .catch(() => {});
    }, 3000);
    return () => clearInterval(id);
  }, [invoice, invoiceId]);

  const startEditing = useCallback(() => {
    if (!invoice) return;
    setEditFields({
      invoice_number: invoice.invoice_number || "",
      invoice_date: invoice.invoice_date || "",
      due_date: invoice.due_date || "",
      currency: invoice.currency || "PKR",
      supplier_name: invoice.supplier_name || "",
      supplier_address: invoice.supplier_address || "",
      supplier_ntn: invoice.supplier_ntn || "",
      receiver_name: invoice.receiver_name || "",
      receiver_address: invoice.receiver_address || "",
      subtotal_amount: invoice.subtotal_amount,
      tax_amount: invoice.tax_amount,
      total_amount: invoice.total_amount,
      gst_amount: invoice.gst_amount,
      wht_amount: invoice.wht_amount,
      po_reference: invoice.po_reference || "",
      bank_iban: invoice.bank_iban || "",
      document_type: invoice.document_type || "",
    });
    // Seed line items for editing (clone to avoid mutating original).
    // Quantity and unit_price are independent inputs; amount is derived
    // (qty × price). Seed unit_price from the stored value, falling back to
    // amount ÷ qty only when it's missing.
    setEditLineItems(
      (invoice.line_items || []).map((li) => {
        const qty = parseFloat(li.quantity);
        const amount = parseFloat(li.amount);
        const unitPrice =
          li.unit_price != null
            ? li.unit_price
            : qty && amount
            ? Math.round((amount / qty) * 100) / 100
            : null;
        return {
          id: li.id,
          description: li.description || "",
          quantity: li.quantity,
          unit: li.unit || "",
          unit_price: unitPrice,
          amount: li.amount,
        };
      })
    );
    setEditing(true);
  }, [invoice]);

  const cancelEditing = useCallback(() => {
    setEditing(false);
    setEditFields({});
    setEditLineItems([]);
  }, []);

  const handleFieldChange = useCallback((field, value) => {
    setEditFields((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleLineItemChange = useCallback((index, field, value) => {
    setEditLineItems((prev) => {
      const updated = [...prev];
      const item = { ...updated[index], [field]: value };

      // Quantity and unit_price are INDEPENDENT — changing one never changes
      // the other. Amount is the derived value: amount = qty × unit_price.
      if (field === "quantity" || field === "unit_price") {
        const qty = parseFloat(field === "quantity" ? value : item.quantity);
        const price = parseFloat(field === "unit_price" ? value : item.unit_price);
        if (!isNaN(qty) && !isNaN(price)) {
          item.amount = Math.round(qty * price * 100) / 100;
        }
      }

      updated[index] = item;
      return updated;
    });
  }, []);

  const addLineItem = useCallback(() => {
    setEditLineItems((prev) => [
      ...prev,
      { id: null, description: "", quantity: null, unit: "", unit_price: null, amount: null },
    ]);
  }, []);

  const removeLineItem = useCallback((index) => {
    setEditLineItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const saveEdits = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...editFields,
        line_items: editLineItems.map((li) => ({
          description: li.description || null,
          quantity: li.quantity,
          unit: li.unit || null,
          unit_price: li.unit_price,
          amount: li.amount,
        })),
      };
      const updated = await updateInvoice(invoiceId, payload);
      setInvoice(updated);
      setEditing(false);
      setEditFields({});
      setEditLineItems([]);
    } catch (err) {
      setError(
        err.response?.data?.detail || err.message || "Failed to save changes"
      );
    } finally {
      setSaving(false);
    }
  }, [invoiceId, editFields, editLineItems]);

  const changeStatus = useCallback(
    async (newStatus) => {
      setSaving(true);
      setError(null);
      try {
        const updated = await updateInvoiceStatus(invoiceId, newStatus);
        setInvoice(updated);
      } catch (err) {
        setError(
          err.response?.data?.detail ||
            err.message ||
            "Failed to change status"
        );
      } finally {
        setSaving(false);
      }
    },
    [invoiceId]
  );

  const refetch = useCallback(async () => {
    if (!invoiceId) return;
    try {
      const data = await getInvoice(invoiceId);
      setInvoice(data);
    } catch { /* keep existing invoice on refetch failure */ }
  }, [invoiceId]);

  return {
    invoice,
    loading,
    error,
    editing,
    editFields,
    editLineItems,
    saving,
    matchingPending: isMatchingPending(invoice),
    startEditing,
    cancelEditing,
    handleFieldChange,
    handleLineItemChange,
    addLineItem,
    removeLineItem,
    saveEdits,
    changeStatus,
    refetch,
  };
}
