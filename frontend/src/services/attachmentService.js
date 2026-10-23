import api, { getAuthToken } from "./api";

export async function getAttachments(invoiceId) {
  const { data } = await api.get(`/api/invoices/${invoiceId}/attachments`);
  return data;
}

export async function uploadAttachment(invoiceId, file, documentType = "other", description = "", uploadedBy = "", uploadedByRole = "") {
  const form = new FormData();
  form.append("file", file);
  form.append("document_type", documentType);
  form.append("description", description);
  form.append("uploaded_by", uploadedBy);
  form.append("uploaded_by_role", uploadedByRole);
  const { data } = await api.post(`/api/invoices/${invoiceId}/attachments`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteAttachment(attachmentId) {
  await api.delete(`/api/attachments/${attachmentId}`);
}

export function getDownloadUrl(attachmentId) {
  const base = api.defaults.baseURL || "http://localhost:8000";
  // Download links are opened directly by the browser (<a>/<img>), which can't
  // send an Authorization header — pass the token as a query param instead.
  const token = getAuthToken();
  const suffix = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${base}/api/attachments/${attachmentId}/download${suffix}`;
}
