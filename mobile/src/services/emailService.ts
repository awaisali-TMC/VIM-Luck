import apiClient from './api';
import type {
  EmailMessage,
  EmailListResponse,
  EmailConfig,
  ExtractionResult,
} from '../types';

const BASE = '/api/admin/inbox';

/** Get Gmail configuration status */
export async function getInboxConfig(): Promise<EmailConfig> {
  const { data } = await apiClient.get(`${BASE}/config`);
  return data;
}

/** Fetch new emails from Gmail IMAP */
export async function fetchEmailsFromServer(): Promise<{
  fetched: number;
  saved: number;
  skipped: number;
}> {
  const { data } = await apiClient.post(`${BASE}/fetch`);
  return data;
}

/** List emails (paginated) with stats */
export async function listEmails(skip = 0, limit = 20): Promise<EmailListResponse> {
  const { data } = await apiClient.get(BASE, { params: { skip, limit } });
  return data;
}

/** Get single email detail (auto-marks as read) */
export async function getEmail(id: number): Promise<EmailMessage> {
  const { data } = await apiClient.get(`${BASE}/${id}`);
  return data;
}

/** Process an attachment through Document AI + Gemini pipeline */
export async function processAttachment(attachmentId: number): Promise<ExtractionResult> {
  const { data } = await apiClient.post(`${BASE}/attachments/${attachmentId}/process`);
  return data;
}

/** Mark attachment as processed and link to invoice */
export async function markAttachmentProcessed(
  attachmentId: number,
  invoiceId: number,
): Promise<void> {
  await apiClient.patch(`${BASE}/attachments/${attachmentId}/mark-processed`, {
    invoice_id: invoiceId,
  });
}
