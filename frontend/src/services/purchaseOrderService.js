import api from "./api";

// ── Purchase Order CRUD ─────────────────────────────

export async function createPurchaseOrder(data) {
  const response = await api.post("/api/purchase-orders/", data);
  return response.data;
}

export async function uploadPurchaseOrder(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post("/api/purchase-orders/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function getPurchaseOrders(skip = 0, limit = 20, params = {}) {
  const response = await api.get("/api/purchase-orders/", {
    params: { skip, limit, ...params },
  });
  return response.data;
}

export async function searchPurchaseOrders(q) {
  const response = await api.get("/api/purchase-orders/search", { params: { q } });
  return response.data;
}

export async function getPurchaseOrder(id) {
  const response = await api.get(`/api/purchase-orders/${id}`);
  return response.data;
}

export async function updatePurchaseOrder(id, data) {
  const response = await api.put(`/api/purchase-orders/${id}`, data);
  return response.data;
}

export async function updatePOStatus(id, status) {
  const response = await api.patch(`/api/purchase-orders/${id}/status`, { status });
  return response.data;
}

export async function deletePurchaseOrder(id) {
  const response = await api.delete(`/api/purchase-orders/${id}`);
  return response.data;
}

// ── GRN ─────────────────────────────────────────────

export async function createGRN(poId, data) {
  const response = await api.post(`/api/purchase-orders/${poId}/grn`, data);
  return response.data;
}

export async function getGRNs(poId) {
  const response = await api.get(`/api/purchase-orders/${poId}/grns`);
  return response.data;
}

// ── SES ─────────────────────────────────────────────

export async function createSES(poId, data) {
  const response = await api.post(`/api/purchase-orders/${poId}/ses`, data);
  return response.data;
}

export async function getSESRecords(poId) {
  const response = await api.get(`/api/purchase-orders/${poId}/ses`);
  return response.data;
}

// ── PO Flip (supplier invoice-from-PO) ──────────────

export async function getFlippablePOs() {
  const response = await api.get("/api/po-flip/open-pos");
  return response.data;
}

/** Manual "Refresh from SAP" — waits for the sync and returns the fresh list.
    Can take a while when many new POs need syncing (one RFC per new PO). */
export async function refreshSupplierPOs() {
  const response = await api.post("/api/po-flip/refresh", {}, { timeout: 120000 });
  return response.data;
}

export async function flipPOToInvoice(poId, payload = {}) {
  const response = await api.post(`/api/po-flip/${poId}/create-invoice`, payload);
  return response.data;
}

// ── PO Matching ─────────────────────────────────────

export async function triggerPOMatch(invoiceId, poId, matchType = "2-way", tolerance = null) {
  const response = await api.post(`/api/po-matching/invoices/${invoiceId}/match`, {
    po_id: poId,
    match_type: matchType,
    tolerance,
  });
  return response.data;
}

export async function getInvoiceMatches(invoiceId) {
  const response = await api.get(`/api/po-matching/invoices/${invoiceId}/matches`);
  return response.data;
}

export async function getMatchResult(matchId) {
  const response = await api.get(`/api/po-matching/results/${matchId}`);
  return response.data;
}

export async function deleteMatchResult(matchId) {
  const response = await api.delete(`/api/po-matching/results/${matchId}`);
  return response.data;
}

export async function autoSuggestPO(invoiceId) {
  const response = await api.post(`/api/po-matching/invoices/${invoiceId}/auto-suggest`);
  return response.data;
}
