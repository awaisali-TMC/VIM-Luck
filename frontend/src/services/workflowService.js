import api from "./api";

// ── Workflow Templates ───────────────────────────────────────────────────────

export async function listTemplates() {
  const response = await api.get("/api/workflow-templates");
  return response.data;
}

export async function createTemplate(data) {
  const response = await api.post("/api/workflow-templates", data);
  return response.data;
}

export async function getTemplate(id) {
  const response = await api.get(`/api/workflow-templates/${id}`);
  return response.data;
}

export async function updateTemplate(id, data) {
  const response = await api.put(`/api/workflow-templates/${id}`, data);
  return response.data;
}

export async function deleteTemplate(id) {
  const response = await api.delete(`/api/workflow-templates/${id}`);
  return response.data;
}

// ── Steps ────────────────────────────────────────────────────────────────────

export async function addStep(templateId, data) {
  const response = await api.post(`/api/workflow-templates/${templateId}/steps`, data);
  return response.data;
}

export async function updateStep(templateId, stepId, data) {
  const response = await api.put(`/api/workflow-templates/${templateId}/steps/${stepId}`, data);
  return response.data;
}

export async function deleteStep(templateId, stepId) {
  const response = await api.delete(`/api/workflow-templates/${templateId}/steps/${stepId}`);
  return response.data;
}

export async function reorderSteps(templateId, stepIds) {
  const response = await api.post(`/api/workflow-templates/${templateId}/steps/reorder`, {
    step_ids: stepIds,
  });
  return response.data;
}

// ── Approvals ────────────────────────────────────────────────────────────────

export async function getPendingApprovals(token) {
  const response = await api.get("/api/approvals/pending", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function getInvoiceApproval(invoiceId) {
  const response = await api.get(`/api/approvals/invoice/${invoiceId}`);
  return response.data;
}

export async function initiateApproval(invoiceId, token) {
  const response = await api.post(`/api/approvals/invoice/${invoiceId}/initiate`, null, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function takeApprovalAction(requestId, action, comments, token, delegatedToId) {
  const body = { action, comments: comments || null, delegated_to_id: delegatedToId || null };
  const response = await api.post(`/api/approvals/${requestId}/action`, body, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function getApprovalHistory({ skip = 0, limit = 20, status } = {}) {
  const params = { skip, limit };
  if (status) params.status = status;
  const response = await api.get("/api/approvals/history", { params });
  return response.data;
}

// ── Audit Logs ───────────────────────────────────────────────────────────────

export async function getAuditLogs({ entity_type, entity_id, action, skip = 0, limit = 50 } = {}) {
  const params = { skip, limit };
  if (entity_type) params.entity_type = entity_type;
  if (entity_id) params.entity_id = entity_id;
  if (action) params.action = action;
  const response = await api.get("/api/audit-logs", { params });
  return response.data;
}

export async function getEntityAuditLogs(entityType, entityId) {
  const response = await api.get(`/api/audit-logs/entity/${entityType}/${entityId}`);
  return response.data;
}
