import api from "./api";

const BASE = "/api/admin/inbox";

export async function getInboxConfig() {
  const response = await api.get(`${BASE}/config`);
  return response.data;
}

export async function fetchEmailsFromServer() {
  const response = await api.post(`${BASE}/fetch`);
  return response.data;
}

export async function listEmails(skip = 0, limit = 50) {
  const response = await api.get(`${BASE}/`, { params: { skip, limit } });
  return response.data;
}

export async function getEmail(id) {
  const response = await api.get(`${BASE}/${id}`);
  return response.data;
}

export async function processAttachment(attachmentId) {
  const response = await api.post(`${BASE}/attachments/${attachmentId}/process`);
  return response.data;
}

export async function markAttachmentProcessed(attachmentId, invoiceId = null) {
  const response = await api.patch(`${BASE}/attachments/${attachmentId}/mark-processed`, {
    invoice_id: invoiceId,
  });
  return response.data;
}
