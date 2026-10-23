import apiClient from './api';
import { getToken } from './authService';

// ─── Types ──────────────────────────────────────────────────────

export interface StatusCounts {
  draft?: number;
  pending_processing?: number;
  validated?: number;
  pending_approval?: number;
  approved?: number;
  posted?: number;
  exception?: number;
  rejected?: number;
  [key: string]: number | undefined;
}

export interface AnalyticsOverview {
  total_invoices: number;
  total_amount: number;
  avg_confidence: number;
  exception_count: number;
  pending_count: number;
  approved_count: number;
  posted_count: number;
  draft_count: number;
  validated_count: number;
  rejected_count: number;
  status_counts: StatusCounts;
  exception_rate: number;
  straight_through_rate: number;
}

export interface StatusBreakdown {
  status: string;
  count: number;
}

export interface VolumeTrend {
  date: string;
  count: number;
}

export interface SupplierSummary {
  supplier_name: string;
  count: number;
  total_amount: number;
}

export interface TaxSummary {
  total_gst: number;
  total_wht: number;
  total_tax: number;
  invoice_count: number;
}

// ─── API Calls ──────────────────────────────────────────────────

/** Get overview KPIs — maps backend status_counts to flat fields */
export async function getAnalyticsOverview(days = 30): Promise<AnalyticsOverview> {
  const { data } = await apiClient.get('/api/analytics/overview', {
    params: { days },
  });
  const sc: StatusCounts = data.status_counts || {};
  return {
    total_invoices: data.total_invoices ?? 0,
    total_amount: data.total_amount ?? 0,
    avg_confidence: data.avg_confidence ?? 0,
    draft_count: sc.draft ?? 0,
    validated_count: sc.validated ?? 0,
    pending_count: (sc.pending_processing ?? 0) + (sc.pending_approval ?? 0),
    approved_count: sc.approved ?? 0,
    posted_count: sc.posted ?? 0,
    exception_count: sc.exception ?? 0,
    rejected_count: sc.rejected ?? 0,
    status_counts: sc,
    exception_rate: data.exception_rate ?? 0,
    straight_through_rate: data.straight_through_rate ?? 0,
  };
}

/** Get invoice count by status */
export async function getStatusBreakdown(days = 30): Promise<StatusBreakdown[]> {
  const { data } = await apiClient.get('/api/analytics/by-status', {
    params: { days },
  });
  return data;
}

/** Get daily volume trend */
export async function getVolumeTrend(days = 30): Promise<VolumeTrend[]> {
  const { data } = await apiClient.get('/api/analytics/volume-trend', {
    params: { days },
  });
  return data;
}

/** Get top suppliers */
export async function getTopSuppliers(days = 30, limit = 5): Promise<SupplierSummary[]> {
  const { data } = await apiClient.get('/api/analytics/by-supplier', {
    params: { days, limit },
  });
  return data;
}

/** Get tax summary */
export async function getTaxSummary(days = 30): Promise<TaxSummary> {
  const { data } = await apiClient.get('/api/analytics/tax-summary', {
    params: { days },
  });
  return data;
}

/** Get audit logs for a specific entity */
export async function getEntityAuditLogs(entityType: string, entityId: number): Promise<any[]> {
  try {
    const { data } = await apiClient.get(`/api/audit-logs/entity/${entityType}/${entityId}`);
    return data;
  } catch {
    return [];
  }
}

/** Get invoice comments */
export async function getInvoiceComments(invoiceId: number): Promise<any[]> {
  try {
    const token = await getToken();
    const { data } = await apiClient.get(`/api/invoices/${invoiceId}/comments`, {
      params: token ? { token } : {},
    });
    return data;
  } catch {
    return [];
  }
}

/** Add a comment to an invoice */
export async function addInvoiceComment(invoiceId: number, text: string): Promise<any> {
  const token = await getToken();
  const { data } = await apiClient.post(`/api/invoices/${invoiceId}/comments`, {
    text,
  }, {
    params: token ? { token } : {},
  });
  return data;
}

/** Get invoice classification */
export async function classifyInvoice(invoiceId: number): Promise<any> {
  const { data } = await apiClient.get(`/api/invoices/${invoiceId}/classify`);
  return data;
}

/** Check for duplicate invoices */
export async function checkDuplicates(invoiceId: number): Promise<any> {
  try {
    const { data } = await apiClient.get(`/api/invoices/${invoiceId}/duplicates`);
    return data;
  } catch {
    return null;
  }
}
