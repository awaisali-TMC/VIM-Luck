import apiClient from './api';
import type {
  PurchaseOrder,
  PurchaseOrderDetail,
  POListResponse,
  POLineItem,
  GoodsReceivedNote,
  GRNLineItem,
  ServiceEntrySheet,
  SESLineItem,
  POMatchResult,
  POSuggestion,
} from '../types';

// ─── Purchase Order CRUD ─────────────────────────────────────────

export async function getPurchaseOrders(
  skip = 0,
  limit = 20,
  status?: string,
  search?: string,
): Promise<POListResponse> {
  const params: Record<string, any> = { skip, limit };
  if (status) params.status = status;
  if (search) params.search = search;
  const { data } = await apiClient.get('/api/purchase-orders/', { params });
  return data;
}

export async function getPurchaseOrder(id: number): Promise<PurchaseOrderDetail> {
  const { data } = await apiClient.get(`/api/purchase-orders/${id}`);
  return data;
}

export async function searchPurchaseOrders(q: string): Promise<PurchaseOrder[]> {
  const { data } = await apiClient.get('/api/purchase-orders/search', { params: { q } });
  return data;
}

export interface POCreatePayload {
  po_number: string;
  vendor_name: string;
  vendor_ntn?: string;
  po_date?: string;
  po_type?: string;
  currency?: string;
  notes?: string;
  line_items: Array<{
    description: string;
    quantity: number;
    unit?: string;
    unit_price: number;
    amount?: number;
  }>;
}

export async function createPurchaseOrder(payload: POCreatePayload): Promise<PurchaseOrder> {
  const { data } = await apiClient.post('/api/purchase-orders/', payload);
  return data;
}

export async function updatePurchaseOrder(
  id: number,
  payload: Partial<POCreatePayload>,
): Promise<PurchaseOrder> {
  const { data } = await apiClient.put(`/api/purchase-orders/${id}`, payload);
  return data;
}

export async function updatePOStatus(id: number, status: string): Promise<PurchaseOrder> {
  const { data } = await apiClient.patch(`/api/purchase-orders/${id}/status`, { status });
  return data;
}

export async function deletePurchaseOrder(id: number): Promise<void> {
  await apiClient.delete(`/api/purchase-orders/${id}`);
}

// ─── GRN (Goods Received Notes) ─────────────────────────────────

export interface GRNCreatePayload {
  grn_number: string;
  grn_date?: string;
  received_by?: string;
  plant_location?: string;
  notes?: string;
  line_items: Array<{
    po_line_item_id: number;
    received_quantity: number;
    inspection_status?: string;
  }>;
}

export async function createGRN(poId: number, payload: GRNCreatePayload): Promise<GoodsReceivedNote> {
  const { data } = await apiClient.post(`/api/purchase-orders/${poId}/grn`, payload);
  return data;
}

export async function getGRNs(poId: number): Promise<GoodsReceivedNote[]> {
  const { data } = await apiClient.get(`/api/purchase-orders/${poId}/grns`);
  return data;
}

// ─── SES (Service Entry Sheets) ──────────────────────────────────

export interface SESCreatePayload {
  ses_number: string;
  ses_date?: string;
  service_period_from?: string;
  service_period_to?: string;
  notes?: string;
  line_items: Array<{
    po_line_item_id: number;
    completed_quantity: number;
    completed_amount?: number;
  }>;
}

export async function createSES(poId: number, payload: SESCreatePayload): Promise<ServiceEntrySheet> {
  const { data } = await apiClient.post(`/api/purchase-orders/${poId}/ses`, payload);
  return data;
}

export async function getSESRecords(poId: number): Promise<ServiceEntrySheet[]> {
  const { data } = await apiClient.get(`/api/purchase-orders/${poId}/ses`);
  return data;
}

// ─── PO Matching ─────────────────────────────────────────────────

export async function triggerPOMatch(
  invoiceId: number,
  poId: number,
  matchType: string = '2-way',
): Promise<POMatchResult> {
  const { data } = await apiClient.post(`/api/po-matching/invoices/${invoiceId}/match`, {
    po_id: poId,
    match_type: matchType,
  });
  return data;
}

export async function getInvoiceMatches(invoiceId: number): Promise<POMatchResult[]> {
  const { data } = await apiClient.get(`/api/po-matching/invoices/${invoiceId}/matches`);
  return data;
}

export async function getMatchResult(matchId: number): Promise<POMatchResult> {
  const { data } = await apiClient.get(`/api/po-matching/results/${matchId}`);
  return data;
}

export async function deleteMatchResult(matchId: number): Promise<void> {
  await apiClient.delete(`/api/po-matching/results/${matchId}`);
}

export async function autoSuggestPO(invoiceId: number): Promise<POSuggestion[]> {
  const { data } = await apiClient.post(`/api/po-matching/invoices/${invoiceId}/auto-suggest`);
  return Array.isArray(data) ? data : data.suggestions || [];
}
