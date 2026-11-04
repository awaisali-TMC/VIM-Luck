import { fetchInvoiceDocument } from "../services/invoiceService";

/**
 * Show a Blob in `tab` (a window opened during the click), or save it as
 * `filename` when there is no tab (a download, or a blocked popup).
 */
export function showOrSaveBlob(blob, filename, tab) {
  const url = URL.createObjectURL(blob);
  if (tab) {
    tab.location.href = url;
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "invoice";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * View (new tab) or download an invoice's originally uploaded file.
 *
 * Call it straight from the click handler: the tab is opened before the
 * fetch, inside the click, or popup blockers stop it. Throws on failure
 * (e.g. 404 when the file is no longer stored); err.message is user-readable.
 */
export async function openInvoiceDocument(invoice, mode) {
  const tab = mode === "view" ? window.open("", "_blank") : null;
  try {
    const blob = await fetchInvoiceDocument(invoice.id, { download: mode === "download" });
    showOrSaveBlob(blob, invoice.original_filename || `invoice-${invoice.id}`, tab);
  } catch (err) {
    if (tab) tab.close();
    throw err;
  }
}
