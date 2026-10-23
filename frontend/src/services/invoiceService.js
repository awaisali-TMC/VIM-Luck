import api from "./api";

// `extra` = optional multipart fields sent alongside the file. Empty today.
export async function uploadInvoice(file, extra = {}) {
  const formData = new FormData();
  formData.append("file", file);
  for (const [k, v] of Object.entries(extra)) if (v != null) formData.append(k, v);
  const response = await api.post("/api/invoices/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    // AI extraction of a multi-page PDF can take minutes, and a multi-invoice
    // file is split + re-extracted per invoice — align with the backend's
    // 900s Cloud Run request timeout.
    timeout: 890000,
  });
  return response.data;
}

export async function uploadInvoiceBatch(files, extra = {}) {
  // Upload several files at once. Every invoice found (multi-invoice PDFs are
  // split) is saved as a DRAFT; returns { batch, invoice_count, invoices, errors }.
  const formData = new FormData();
  for (const f of files) formData.append("files", f);
  for (const [k, v] of Object.entries(extra)) if (v != null) formData.append(k, v);
  const response = await api.post("/api/invoices/upload-batch", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 890000,
  });
  return response.data;
}

export async function saveInvoice(invoiceData) {
  const response = await api.post("/api/invoices/save", invoiceData);
  return response.data;
}

export async function getInvoices(skip = 0, limit = 20) {
  const response = await api.get("/api/invoices/", { params: { skip, limit } });
  return response.data;
}

export async function getInvoice(id) {
  const response = await api.get(`/api/invoices/${id}`);
  return response.data;
}

export async function updateInvoice(id, data) {
  const response = await api.put(`/api/invoices/${id}`, data);
  return response.data;
}

export async function updateInvoiceStatus(id, status) {
  const response = await api.patch(`/api/invoices/${id}/status`, { status });
  return response.data;
}

export async function matchProducts(id) {
  const response = await api.post(`/api/invoices/${id}/match-products`);
  return response.data;
}

export async function deleteInvoice(id) {
  // Soft-delete. Backend rejects (409) if the invoice is parked/posted in SAP.
  const response = await api.delete(`/api/invoices/${id}`);
  return response.data;
}

export async function deleteInvoiceLineItem(invoiceId, lineItemId) {
  // Permanently remove one line item (e.g. a line not on the PO) so the rest
  // of the invoice can be parked. Recomputes subtotal/total server-side.
  const response = await api.delete(`/api/invoices/${invoiceId}/line-items/${lineItemId}`);
  return response.data;
}

export async function patchInvoiceLineItem(invoiceId, lineItemId, patch) {
  // In-place update of one line item (inline editing). Keeps the line id so the
  // PO match survives; recomputes amount + invoice totals server-side.
  const response = await api.patch(`/api/invoices/${invoiceId}/line-items/${lineItemId}`, patch);
  return response.data;
}

export async function addInvoiceLineItem(invoiceId) {
  // Append a blank line item for inline editing; returns its new id.
  const response = await api.post(`/api/invoices/${invoiceId}/line-items`);
  return response.data;
}

export async function setParkingSelection(invoiceId, lineItemIds) {
  // Persist which line items are selected for parking (locked at submit).
  const response = await api.put(`/api/invoices/${invoiceId}/parking-selection`, { line_item_ids: lineItemIds });
  return response.data;
}
