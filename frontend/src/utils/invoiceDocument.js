import { fetchInvoiceDocument } from "../services/invoiceService";

/** Event the in-page viewer (components/common/DocumentViewer, mounted in App.jsx) listens for. */
export const VIEW_DOCUMENT_EVENT = "einv:view-document";

/** Save a Blob as `filename` (a browser download). */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "invoice";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * Show a Blob in `tab` (a window opened during the click). With no tab — the
 * popup was blocked, as it always is in embedded previews — show it in the
 * page's own viewer instead of silently turning "View" into a download.
 */
export function viewBlob(blob, filename, tab) {
  if (!tab) {
    window.dispatchEvent(new CustomEvent(VIEW_DOCUMENT_EVENT, { detail: { blob, filename } }));
    return;
  }
  const url = URL.createObjectURL(blob);
  tab.location.href = url;
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * View (new tab, else the in-page viewer) or download an invoice's
 * originally uploaded file.
 *
 * Call it straight from the click handler: the tab is opened before the
 * fetch, inside the click, or popup blockers stop it. Throws on failure
 * (e.g. 404 when the file is no longer stored); err.message is user-readable.
 */
export async function openInvoiceDocument(invoice, mode) {
  const tab = mode === "view" ? window.open("", "_blank") : null;
  const filename = invoice.original_filename || `invoice-${invoice.id}`;
  try {
    const blob = await fetchInvoiceDocument(invoice.id, { download: mode === "download" });
    if (mode === "view") viewBlob(blob, filename, tab);
    else saveBlob(blob, filename);
  } catch (err) {
    if (tab) tab.close();
    throw err;
  }
}
