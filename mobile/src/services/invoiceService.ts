import apiClient from './api';
import { getToken } from './authService';
import type {
  ExtractionResult,
  InvoiceListResponse,
  InvoiceDetail,
  InvoiceSaveRequest,
  InvoiceListItem,
  UploadResponse,
  BatchUploadResult,
} from '../types';

export interface PickedUpload {
  uri: string;
  name: string;
  mimeType: string;
  file?: File | null;
}

function appendFile(formData: FormData, field: string, f: PickedUpload) {
  if (f.file) {
    // Web: use the native File object directly
    formData.append(field, f.file, f.name);
  } else {
    // Native (iOS/Android): use the { uri, name, type } convention
    formData.append(field, {
      uri: f.uri,
      name: f.name,
      type: f.mimeType,
    } as any);
  }
}

/** Upload ONE file. Returns an ExtractionResult to review, OR — when the file
 *  turns out to contain several invoices — a BatchUploadResult (drafts saved
 *  server-side, review skipped). Callers must handle both (see isBatchResult). */
export async function uploadInvoice(pickedFile: PickedUpload): Promise<UploadResponse> {
  const token = await getToken();
  const formData = new FormData();
  appendFile(formData, 'file', pickedFile);

  const { data } = await apiClient.post<UploadResponse>('/api/invoices/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000, // multi-invoice files are split + re-extracted per invoice
    params: token ? { token } : {},
  });
  return data;
}

/** Upload SEVERAL files (or several scanned pages) at once. Every invoice found
 *  is saved as a DRAFT; images are merged into one document server-side. */
export async function uploadInvoiceBatch(files: PickedUpload[]): Promise<BatchUploadResult> {
  const token = await getToken();
  const formData = new FormData();
  for (const f of files) appendFile(formData, 'files', f);

  const { data } = await apiClient.post<BatchUploadResult>('/api/invoices/upload-batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
    params: token ? { token } : {},
  });
  return data;
}

/** Save extraction result as a new invoice */
export async function saveInvoice(payload: InvoiceSaveRequest): Promise<InvoiceListItem> {
  const token = await getToken();
  const { data } = await apiClient.post<InvoiceListItem>('/api/invoices/save', payload, {
    params: token ? { token } : {},
  });
  return data;
}

/** Get paginated invoice list, optionally filtered by status */
export async function getInvoices(skip = 0, limit = 20, status?: string): Promise<InvoiceListResponse> {
  const params: Record<string, any> = { skip, limit };
  if (status) params.status = status;
  const { data } = await apiClient.get<InvoiceListResponse>('/api/invoices/', { params });
  return data;
}

/** Get single invoice detail */
export async function getInvoice(id: number): Promise<InvoiceDetail> {
  const { data } = await apiClient.get<InvoiceDetail>(`/api/invoices/${id}`);
  return data;
}

/** Update invoice fields + line items */
export async function updateInvoice(id: number, payload: Partial<InvoiceDetail>): Promise<InvoiceDetail> {
  const { data } = await apiClient.put<InvoiceDetail>(`/api/invoices/${id}`, payload);
  return data;
}

/** Transition invoice status */
export async function updateInvoiceStatus(id: number, status: string): Promise<InvoiceDetail> {
  const { data } = await apiClient.patch<InvoiceDetail>(`/api/invoices/${id}/status`, { status });
  return data;
}
