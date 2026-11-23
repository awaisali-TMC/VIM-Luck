import api from "./api";

const BASE = "/api/sap";

export async function testSAPConnection() {
  const response = await api.get(`${BASE}/test`);
  return response.data;
}

export async function fetchSAPPOs(maxRows = 100, companyCode = null) {
  const params = { max_rows: maxRows };
  if (companyCode) params.company_code = companyCode;
  const response = await api.get(`${BASE}/pos`, { params });
  return response.data;
}

export async function fetchSAPPODetail(poNumber) {
  const response = await api.get(`${BASE}/pos/${poNumber}`);
  return response.data;
}

export async function syncSAPPO(poNumber) {
  const response = await api.post(`${BASE}/pos/${poNumber}/sync`);
  return response.data;
}

export async function getOpenGRs(invoiceId) {
  // Open (not fully invoiced) goods receipts of the invoice's matched PO, live from SAP.
  const response = await api.get(`${BASE}/invoices/${invoiceId}/open-grs`);
  return response.data;
}

export async function fetchSAPTaxCodes(companyCode = null) {
  const params = companyCode ? { company_code: companyCode } : {};
  const response = await api.get(`${BASE}/tax-codes`, { params });
  return response.data;
}

export async function fetchSAPCurrencies() {
  // Served from the local sap_currencies cache (lazy-synced from SAP TCURT).
  const response = await api.get(`${BASE}/currencies`);
  return response.data;
}

export async function fetchSAPGRN(poNumber) {
  const response = await api.get(`${BASE}/pos/${poNumber}/grn`);
  return response.data;
}

export async function syncSAPGRN(poNumber) {
  const response = await api.post(`${BASE}/pos/${poNumber}/grn/sync`);
  return response.data;
}

export async function syncAllSAPPOs(maxRows = 100, companyCode = null) {
  const params = { max_rows: maxRows };
  if (companyCode) params.company_code = companyCode;
  const response = await api.post(`${BASE}/pos/sync-all`, null, { params });
  return response.data;
}

export async function unparkInvoiceFromSAP(invoiceId) {
  // Deletes the parked SAP document, then the backend soft-deletes the invoice.
  const response = await api.post(`${BASE}/invoices/${invoiceId}/unpark`);
  return response.data;
}

export async function refreshSAPWorkflow(invoiceId) {
  // Reads the SAP approval-workflow status (ZMIR7_WF_LOG) now; returns
  // { status, sap_wf_status, sap_wf_label, sap_wf_posted_doc, sap_wf_message, sap_wf_checked_at }.
  const response = await api.post(`${BASE}/invoices/${invoiceId}/workflow/refresh`);
  return response.data;
}

export async function postInvoiceToSAP(invoiceId, options = {}) {
  const response = await api.post(`${BASE}/invoices/${invoiceId}/post`, {
    mode: options.mode || "park",   // "park" (MIR7, held) | "post" (MIRO, final)
    company_code: options.companyCode || null,
    posting_date: options.postingDate || null,
    tax_code: options.taxCode || "I0",
    header_text: options.headerText || null,
    exchange_rate: options.exchangeRate || null,
    layout: options.layout || "goods",  // "goods" | "delivery" | "both" — SAP item-selection layout
    line_item_ids: options.lineItemIds || null,  // if set, park only these invoice lines
  }, {
    // Live SAP: park + workflow event + commit over the SAProuter can outlast the
    // 60s default. A client timeout does NOT stop the server, so the invoice
    // would park anyway while the page reported a failure.
    timeout: 180000,
  });
  return response.data;
}

/**
 * Dry-run the SAP park to pre-validate an invoice (duplicate check, entry
 * sheet, dates, tax) WITHOUT creating a document. Used at submit-for-approval
 * time so parking errors surface before the approval chain, not after.
 * Returns { ok, message, sap_return }.
 */
export async function lookupSAPVendor({ ntn = "", name = "" } = {}) {
  // Is this supplier registered as a vendor in SAP (LFA1)? Drives ERP Registration.
  const response = await api.get(`${BASE}/vendor-lookup`, { params: { ntn, name } });
  return response.data;
}

export async function validateInvoiceForSAP(invoiceId, lineItemIds = null) {
  const response = await api.post(`${BASE}/invoices/${invoiceId}/post`, {
    mode: "validate",
    line_item_ids: lineItemIds || null,
  });
  return response.data;
}

// ── SAP employee login + approval-hierarchy check (Lucky Cement) ──
// { enabled, hierarchy_check_enabled, signed_in, pernr, name, message, unreachable, mode }
export async function getSAPEmployeeLogin() {
  const response = await api.get(`${BASE}/employee-login`);
  return response.data;
}

export async function signInSAPEmployee(userId, password) {
  const response = await api.post(`${BASE}/employee-login`, { user_id: userId, password });
  return response.data;
}

// ZINI_VERIFY for the signed-in employee: { enabled, ok, flag, pernr, amount, currency, message }
export async function checkSAPHierarchy(amount, currency) {
  const response = await api.post(`${BASE}/hierarchy-check`, { amount, currency: currency || null });
  return response.data;
}
