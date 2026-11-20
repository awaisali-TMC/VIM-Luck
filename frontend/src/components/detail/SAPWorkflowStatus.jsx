import { useState } from "react";
import { refreshSAPWorkflow } from "../../services/sapService";

// SAP approval workflow (Lucky Cement, ZMIR7_PARK → WS90000096): parking started
// it; SAP routes the approvals and posts the invoice itself. This line shows
// where it stands, as last read from ZMIR7_WF_LOG / ZMIR7_ERROR_LOG, and lets
// the user re-read it now instead of waiting for the background poller.
const STATES = {
  INIT: { label: "Workflow not started in SAP", tone: "text-danger-dark", hint: "SAP saved the document but did not start its approval. Unpark it and park again, or check in SAP." },
  BLK: { label: "In SAP approval", tone: "text-warning-dark", hint: "Approvers are working on it in SAP." },
  APP: { label: "Approved in SAP", tone: "text-success-dark" },
  REJ: { label: "Rejected in SAP", tone: "text-danger-dark", hint: "Unpark it to correct and send again." },
};

export default function SAPWorkflowStatus({ invoice, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!invoice?.sap_wf_objkey) return null;

  const status = invoice.sap_wf_status || "";
  const state = STATES[status] || { label: "Approval workflow started — waiting for SAP", tone: "text-neutral-600" };
  const approvedNotPosted = status === "APP" && !invoice.sap_wf_posted_doc;

  const refresh = async () => {
    setBusy(true);
    setError(null);
    try {
      await refreshSAPWorkflow(invoice.id);
      await onChanged?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not read the SAP workflow status");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 pt-2 border-t border-emerald-200 text-2xs">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <span className="text-neutral-500">SAP approval: </span>
          <span className={`font-semibold ${state.tone}`}>{state.label}</span>
          {invoice.sap_wf_posted_doc && (
            <span className="text-success-dark"> &middot; posted as document <strong>{invoice.sap_wf_posted_doc}</strong></span>
          )}
          {approvedNotPosted && !invoice.sap_wf_message && (
            <span className="text-neutral-600"> &middot; waiting for SAP to post it</span>
          )}
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={busy}
          className="text-brand-600 hover:underline bg-transparent border-none cursor-pointer disabled:opacity-50"
        >
          {busy ? "Checking SAP…" : "Refresh from SAP"}
        </button>
      </div>
      {invoice.sap_wf_message && (
        <div className="text-danger-dark mt-1">
          {invoice.sap_wf_status === "APP" ? "SAP posting error" : "SAP message"}: {invoice.sap_wf_message}
        </div>
      )}
      {state.hint && !invoice.sap_wf_message && <div className="text-neutral-500 mt-1">{state.hint}</div>}
      <div className="text-neutral-400 mt-1">
        Workflow key {invoice.sap_wf_objkey}
        {invoice.sap_wf_checked_at && <> &middot; checked {new Date(invoice.sap_wf_checked_at).toLocaleString()}</>}
      </div>
      {error && <div className="text-danger-dark mt-1">{error}</div>}
    </div>
  );
}
