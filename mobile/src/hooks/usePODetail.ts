import { useState, useCallback, useEffect } from 'react';
import {
  getPurchaseOrder,
  updatePurchaseOrder,
  updatePOStatus,
} from '../services/purchaseOrderService';
import type { PurchaseOrderDetail, POLineItem } from '../types';

export default function usePODetail(poId: number) {
  const [po, setPO] = useState<PurchaseOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState<Record<string, any>>({});
  const [editLineItems, setEditLineItems] = useState<POLineItem[]>([]);
  const [saving, setSaving] = useState(false);

  const fetchPO = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getPurchaseOrder(poId);
      setPO(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load PO');
    } finally {
      setLoading(false);
    }
  }, [poId]);

  useEffect(() => {
    fetchPO();
  }, [fetchPO]);

  const startEditing = useCallback(() => {
    if (!po) return;
    setEditing(true);
    setEditFields({
      vendor_name: po.vendor_name,
      vendor_ntn: po.vendor_ntn || '',
      po_date: po.po_date || '',
      po_type: po.po_type,
      currency: po.currency,
      notes: po.notes || '',
    });
    setEditLineItems(po.line_items.map((li) => ({ ...li })));
  }, [po]);

  const cancelEditing = useCallback(() => {
    setEditing(false);
    setEditFields({});
    setEditLineItems([]);
  }, []);

  const handleFieldChange = useCallback((field: string, value: any) => {
    setEditFields((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleLineItemChange = useCallback(
    (index: number, field: string, value: any) => {
      setEditLineItems((prev) => {
        const updated = [...prev];
        const item = { ...updated[index], [field]: value };
        // Auto-calculate amount
        if (field === 'quantity' || field === 'unit_price') {
          const qty = field === 'quantity' ? Number(value) : Number(item.quantity);
          const price = field === 'unit_price' ? Number(value) : Number(item.unit_price);
          if (!isNaN(qty) && !isNaN(price)) {
            item.amount = qty * price;
          }
        }
        updated[index] = item;
        return updated;
      });
    },
    [],
  );

  const addLineItem = useCallback(() => {
    setEditLineItems((prev) => [
      ...prev,
      { description: '', quantity: 1, unit_price: 0, amount: 0 },
    ]);
  }, []);

  const removeLineItem = useCallback((index: number) => {
    setEditLineItems((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const saveEdits = useCallback(async () => {
    if (!po) return;
    try {
      setSaving(true);
      const payload = {
        ...editFields,
        line_items: editLineItems.map((li) => ({
          id: li.id,
          description: li.description,
          quantity: li.quantity,
          unit: li.unit || undefined,
          unit_price: li.unit_price,
          amount: li.amount ?? undefined,
        })),
      };
      const updated = await updatePurchaseOrder(po.id, payload);
      // Refresh full detail
      await fetchPO();
      setEditing(false);
    } catch (err: any) {
      throw new Error(err.response?.data?.detail || err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }, [po, editFields, editLineItems, fetchPO]);

  const changeStatus = useCallback(
    async (newStatus: string) => {
      if (!po) return;
      const updated = await updatePOStatus(po.id, newStatus);
      await fetchPO();
    },
    [po, fetchPO],
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
    fetchPO,
  };
}
