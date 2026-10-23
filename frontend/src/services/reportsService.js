import api from "./api";

// FastAPI expects repeated query keys (status=a&status=b), so serialize arrays
// without index brackets.
const arrayParams = { indexes: null };

/** Turn the page's filter state into a flat query-param object. */
function toParams(f = {}) {
  const p = {};
  if (f.date_from) p.date_from = f.date_from;
  if (f.date_to) p.date_to = f.date_to;
  if (f.days) p.days = f.days;
  if (f.vendor) p.vendor = f.vendor;
  if (f.supplier_id) p.supplier_id = f.supplier_id;
  if (f.status?.length) p.status = f.status;
  if (f.pending_with) p.pending_with = f.pending_with;
  if (f.source?.length) p.source = f.source;
  if (f.amount_min !== "" && f.amount_min != null) p.amount_min = f.amount_min;
  if (f.amount_max !== "" && f.amount_max != null) p.amount_max = f.amount_max;
  if (f.sap_status) p.sap_status = f.sap_status;
  return p;
}

export async function getReportFilters() {
  const r = await api.get("/api/reports/filters");
  return r.data;
}

export async function getReportSummary(filters) {
  const r = await api.get("/api/reports/summary", {
    params: toParams(filters),
    paramsSerializer: arrayParams,
  });
  return r.data;
}

export async function getReportInvoices(filters, page = 1, pageSize = 25, sort = "date") {
  const r = await api.get("/api/reports/invoices", {
    params: { ...toParams(filters), page, page_size: pageSize, sort },
    paramsSerializer: arrayParams,
  });
  return r.data;
}

/** Fetch the export as a Blob and trigger a browser download. */
export async function downloadReportExport(filters, fmt = "csv", sort = "date") {
  const r = await api.get("/api/reports/export", {
    params: { ...toParams(filters), fmt, sort },
    paramsSerializer: arrayParams,
    responseType: "blob",
  });
  const stamp = new Date().toISOString().slice(0, 10);
  const url = window.URL.createObjectURL(new Blob([r.data]));
  const a = document.createElement("a");
  a.href = url;
  a.download = `invoice-report-${stamp}.${fmt === "xlsx" ? "xlsx" : "csv"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
