import { useState, useCallback, useEffect } from 'react';
import { getPurchaseOrders } from '../services/purchaseOrderService';
import type { PurchaseOrder } from '../types';

const PAGE_SIZE = 20;

export default function usePurchaseOrders(statusFilter?: string) {
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const fetchPage = useCallback(
    async (pageNum: number, isRefresh = false) => {
      try {
        if (isRefresh) setRefreshing(true);
        else setLoading(true);
        setError(null);

        const data = await getPurchaseOrders(
          pageNum * PAGE_SIZE,
          PAGE_SIZE,
          statusFilter,
        );
        setOrders(data.purchase_orders);
        setTotal(data.total);
        setPage(pageNum);
      } catch (err: any) {
        setError(err.response?.data?.detail || err.message || 'Failed to load purchase orders');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [statusFilter],
  );

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
    orders,
    total,
    loading,
    refreshing,
    error,
    refresh,
    loadMore,
    hasMore: (page + 1) * PAGE_SIZE < total,
  };
}
