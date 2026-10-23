import { useState, useCallback, useEffect } from 'react';
import { getInvoices } from '../services/invoiceService';
import type { InvoiceListItem } from '../types';

const PAGE_SIZE = 20;

export default function useInvoices(statusFilter?: string) {
  const [invoices, setInvoices] = useState<InvoiceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const fetchPage = useCallback(async (pageNum: number, isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const data = await getInvoices(pageNum * PAGE_SIZE, PAGE_SIZE, statusFilter);
      setInvoices(data.invoices);
      setTotal(data.total);
      setPage(pageNum);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load invoices');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  const refresh = useCallback(() => fetchPage(0, true), [fetchPage]);

  const loadMore = useCallback(() => {
    if ((page + 1) * PAGE_SIZE < total) {
      fetchPage(page + 1);
    }
  }, [page, total, fetchPage]);

  useEffect(() => {
    fetchPage(0);
  }, [fetchPage]);

  return {
    invoices,
    total,
    loading,
    refreshing,
    error,
    refresh,
    loadMore,
    hasMore: (page + 1) * PAGE_SIZE < total,
  };
}
