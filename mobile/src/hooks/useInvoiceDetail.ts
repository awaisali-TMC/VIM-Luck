import { useState, useCallback, useEffect } from 'react';
import { getInvoice, updateInvoice, updateInvoiceStatus } from '../services/invoiceService';
import { calculateRate } from '../services/calculations';
import type { InvoiceDetail, LineItem } from '../types';

export default function useInvoiceDetail(invoiceId: number) {
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState<Record<string, any>>({});
  const [editLineItems, setEditLineItems] = useState<LineItem[]>([]);
  const [saving, setSaving] = useState(false);

  const fetchInvoice = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getInvoice(invoiceId);
      setInvoice(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load invoice');
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    fetchInvoice();
  }, [fetchInvoice]);

  const startEditing = useCallback(() => {
    if (!invoice) return;
    setEditFields({
      invoice_number: invoice.invoice_number || '',
      invoice_date: invoice.invoice_date || '',
      due_date: invoice.due_date || '',
      currency: invoice.currency || 'PKR',
      supplier_name: invoice.supplier_name || '',
      supplier_address: invoice.supplier_address || '',
      supplier_ntn: invoice.supplier_ntn || '',
      receiver_name: invoice.receiver_name || '',
      receiver_address: invoice.receiver_address || '',
      subtotal_amount: invoice.subtotal_amount,
      tax_amount: invoice.tax_amount,
      total_amount: invoice.total_amount,
    });
    setEditLineItems(
      (invoice.line_items || []).map((li) => {
        const qty = li.quantity ? parseFloat(String(li.quantity)) : 0;
        const amt = li.amount ? parseFloat(String(li.amount)) : 0;
        return {
          ...li,
          unit_price: qty && amt ? calculateRate(amt, qty) : li.unit_price,
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

  const handleFieldChange = useCallback((field: string, value: any) => {
    setEditFields((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleLineItemChange = useCallback((index: number, field: string, value: number | string | null) => {
    setEditLineItems((prev) => {
      const updated = [...prev];
      const item = { ...updated[index], [field]: value };
      // Auto-calculate rate
      if (field === 'quantity' || field === 'amount') {
        const qty = field === 'quantity' ? Number(value) : Number(item.quantity);
        const amount = field === 'amount' ? Number(value) : Number(item.amount);
        if (qty && amount) {
          item.unit_price = calculateRate(amount, qty);
        }
      }
      updated[index] = item;
      return updated;
    });
  }, []);

  const saveEdits = useCallback(async () => {
    if (!invoice) return;
    try {
      setSaving(true);
      const data = await updateInvoice(invoice.id, {
        ...editFields,
        line_items: editLineItems,
      } as any);
      setInvoice(data);
      setEditing(false);
      setEditFields({});
      setEditLineItems([]);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }, [invoice, editFields, editLineItems]);

  const changeStatus = useCallback(async (newStatus: string) => {
    if (!invoice) return;
    try {
      setSaving(true);
      const data = await updateInvoiceStatus(invoice.id, newStatus);
      setInvoice(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Status change failed');
    } finally {
      setSaving(false);
    }
  }, [invoice]);

  return {
    invoice,
    loading,
    error,
    editing,
    editFields,
    editLineItems,
    saving,
    fetchInvoice,
    startEditing,
    cancelEditing,
    handleFieldChange,
    handleLineItemChange,
    saveEdits,
    changeStatus,
  };
}
