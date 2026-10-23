import { useState, useEffect, useCallback } from "react";
import {
  getPurchaseOrder,
  updatePurchaseOrder,
  updatePOStatus,
} from "../services/purchaseOrderService";

/**
 * State management hook for PO Detail page.
 * Handles: data fetching, edit mode (fields + line items), saving edits, status transitions.
 */
export default function usePODetail(poId) {
  const [po, setPO] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState({});
  const [editLineItems, setEditLineItems] = useState([]);
  const [saving, setSaving] = useState(false);

  // Load PO on mount or when id changes
  const loadPO = useCallback(async () => {
    if (!poId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getPurchaseOrder(poId);
      setPO(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to load purchase order");
    } finally {
      setLoading(false);
    }
  }, [poId]);

  useEffect(() => {
    loadPO();
  }, [loadPO]);

  const startEditing = useCallback(() => {
    if (!po) return;
    setEditFields({
      po_number: po.po_number || "",
      vendor_name: po.vendor_name || "",
      vendor_ntn: po.vendor_ntn || "",
      po_date: po.po_date || "",
      po_type: po.po_type || "local",
      currency: po.currency || "PKR",
      notes: po.notes || "",
    });
    setEditLineItems(
      (po.line_items || []).map((li) => ({
        id: li.id,
        item_number: li.item_number,
        description: li.description || "",
        quantity: li.quantity,
        unit: li.unit || "",
        unit_price: li.unit_price,
        amount: li.amount,
      }))
    );
    setEditing(true);
  }, [po]);

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
      if (field === "quantity" || field === "unit_price") {
        const qty = field === "quantity" ? parseFloat(value) : parseFloat(item.quantity);
        const price = field === "unit_price" ? parseFloat(value) : parseFloat(item.unit_price);
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
      { id: null, item_number: prev.length + 1, description: "", quantity: null, unit: "", unit_price: null, amount: null },
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
          id: li.id,
          item_number: li.item_number,
          description: li.description || null,
          quantity: li.quantity,
          unit: li.unit || null,
          unit_price: li.unit_price,
          amount: li.amount,
        })),
      };
      const updated = await updatePurchaseOrder(poId, payload);
      setPO(updated);
      setEditing(false);
      setEditFields({});
      setEditLineItems([]);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }, [poId, editFields, editLineItems]);

  const changeStatus = useCallback(
    async (newStatus) => {
      setSaving(true);
      setError(null);
      try {
        const updated = await updatePOStatus(poId, newStatus);
        setPO(updated);
      } catch (err) {
        setError(err.response?.data?.detail || err.message || "Failed to change status");
      } finally {
        setSaving(false);
      }
    },
    [poId]
  );

  return {
    po,
    loading,
    error,
    editing,
    editFields,
    editLineItems,
    saving,
    startEditing,
    cancelEditing,
    handleFieldChange,
    handleLineItemChange,
    addLineItem,
    removeLineItem,
    saveEdits,
    changeStatus,
    refreshPO: loadPO,
  };
}
