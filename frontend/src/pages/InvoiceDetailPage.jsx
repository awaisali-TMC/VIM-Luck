import { useState, useEffect, useMemo, useRef } from "react";
import { usePermissions } from "../context/PermissionsContext";
import useInvoiceDetail from "../hooks/useInvoiceDetail";
import { updateInvoice, deleteInvoice, deleteInvoiceLineItem, patchInvoiceLineItem, addInvoiceLineItem, setParkingSelection, matchProducts } from "../services/invoiceService";
import { openInvoiceDocument } from "../utils/invoiceDocument";
import { getInvoiceMatches } from "../services/purchaseOrderService";
import { verifyNTN } from "../services/fbrService";
import useFBRVerification from "../hooks/useFBRVerification";
import { getInvoiceApproval } from "../services/workflowService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import KpiCard from "../components/common/KpiCard";
import Spinner from "../components/common/Spinner";
import FBRVerificationBadge from "../components/common/FBRVerificationBadge";
import WorkflowStepper from "../components/detail/WorkflowStepper";
import InvoiceDetailFields from "../components/detail/InvoiceDetailFields";
import SAPPostingCard from "../components/detail/SAPPostingCard";
import WHTComplianceCard from "../components/detail/WHTComplianceCard";
import LineItemsTable from "../components/upload/LineItemsTable";
import SalesTaxCard from "../components/upload/SalesTaxCard";
import POMatchSection from "../components/po/POMatchSection";
import { blockedLineIds, blockedLinesMessage } from "../utils/parkingBlockers";
import ApprovalProgressCard from "../components/detail/ApprovalProgressCard";
import AuditTrailCard from "../components/detail/AuditTrailCard";
import DuplicateWarningCard from "../components/detail/DuplicateWarningCard";
import CommentsCard from "../components/detail/CommentsCard";
import GLCodingCard from "../components/detail/GLCodingCard";
import CreditDebitNoteCard from "../components/detail/CreditDebitNoteCard";
import { useRoleLabel } from "../config/roleLabels";
import InvoiceClassificationCard from "../components/detail/InvoiceClassificationCard";
import MultiCurrencyCard from "../components/detail/MultiCurrencyCard";
import AttachmentsCard from "../components/detail/AttachmentsCard";
import Modal from "../components/common/Modal";
import { listTemplates, initiateApproval } from "../services/workflowService";
import { postInvoiceToSAP, fetchSAPTaxCodes, fetchSAPCurrencies, unparkInvoiceFromSAP, validateInvoiceForSAP, lookupSAPVendor } from "../services/sapService";
import { tokens } from "../styles/tokens";

/**
 * Status-based action configurations.
 * Each status maps to an array of { label, variant, targetStatus }.
 */
const STATUS_ACTIONS = {
  draft: [
    { label: "Submit for Processing", variant: "primary", targetStatus: "pending_processing" },
  ],
  pending_processing: [
    { label: "Validate", variant: "success", targetStatus: "validated" },
  ],
  validated: [
    { label: "Submit for Approval", variant: "primary", targetStatus: "pending_approval" },
  ],
  pending_approval: [],  // approval actions handled by ApprovalProgressCard
  approved: [
    { label: "Flag Exception", variant: "danger", targetStatus: "exception" },
  ],
  rejected: [
    { label: "Resubmit for Approval", variant: "primary", targetStatus: "pending_approval" },
    { label: "Resubmit for Processing", variant: "secondary", targetStatus: "pending_processing" },
    { label: "Flag Exception", variant: "danger", targetStatus: "exception" },
  ],
  exception: [
    { label: "Resubmit for Processing", variant: "primary", targetStatus: "pending_processing" },
    { label: "Validate", variant: "success", targetStatus: "validated" },
  ],
  parked: [],
  posted: [],
};

// Pick the most accurate SAP input tax code for an invoice: match its effective
// tax rate to a code's parsed rate (0% → exempt I0), preferring "standard rate"
// codes on ties. The user can still override in the dropdown.
function pickDefaultTaxCode(invoice, codes) {
  const inputs = (codes || []).filter((c) => c.tax_type === "input");
  if (!inputs.length) return null;
  const subtotal =
    Number(invoice?.subtotal_amount) ||
    (Number(invoice?.total_amount || 0) - Number(invoice?.tax_amount || invoice?.gst_amount || 0)) ||
    0;
  const tax = Number(invoice?.tax_amount || invoice?.gst_amount || 0);
  const rate = subtotal > 0 ? (tax / subtotal) * 100 : 0;

  if (!tax || rate < 0.5) {
    return inputs.find((c) => c.code === "I0")?.code
      || inputs.find((c) => c.rate === 0)?.code
      || inputs[0].code;
  }
  let best = null;
  let bestDiff = Infinity;
  for (const c of inputs) {
    if (c.rate == null) continue;
    const diff = Math.abs(c.rate - rate);
    const standard = /standard rate/i.test(c.description || "");
    if (diff < bestDiff - 0.01 || (Math.abs(diff - bestDiff) <= 0.01 && standard)) {
      best = c;
      bestDiff = diff;
    }
  }
  if (best && bestDiff <= 1.5) return best.code;
  return inputs.find((c) => c.code === "GJ")?.code || inputs.find((c) => c.code === "I0")?.code || inputs[0].code;
}

function buildTaxSummary(invoice) {
  if (!invoice) return [];
  const rows = [];
  const cur = invoice.currency || "PKR";
  const fmt = (v) => `${cur} ${Number(v).toLocaleString()}`;

  if (invoice.subtotal_amount != null)
    rows.push({ label: "Subtotal", value: fmt(invoice.subtotal_amount) });
  if (invoice.gst_amount != null)
    rows.push({ label: "GST", value: fmt(invoice.gst_amount) });
  if (invoice.wht_amount != null)
    rows.push({ label: "WHT", value: fmt(invoice.wht_amount) });
  if (invoice.tax_amount != null)
    rows.push({ label: "Tax", value: fmt(invoice.tax_amount) });
  if (invoice.total_amount != null)
    rows.push({ label: "Total", value: fmt(invoice.total_amount), isTotal: true });

  return rows;
}

/**
 * Selection-aware totals: when only SOME line items are selected for parking,
 * Subtotal / Tax / Total are recomputed from the selected lines. Tax uses the
 * SAP tax code's rate (matches what gets parked — the header tax belongs to
 * the full document and goes stale when quantities are edited); proportional
 * scaling of the header tax is only a fallback when no rate is known. With all
 * lines selected the full document summary is shown unchanged.
 */
function buildSelectedTaxSummary(invoice, selectedIds, derivedRate) {
  if (!invoice) return [];
  const lines = invoice.line_items || [];
  const allSel = !selectedIds || lines.length === 0 || lines.every((li) => selectedIds.has(li.id));
  const fullTax = Number(invoice.tax_amount || invoice.gst_amount || 0);
  // Nothing special (all selected, invoice has its own tax) → detailed summary.
  if (allSel && !(fullTax <= 0 && derivedRate)) return buildTaxSummary(invoice);

  const cur = invoice.currency || "PKR";
  const fmt = (v) => `${cur} ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const fullNet = lines.reduce((s, li) => s + Number(li.amount || 0), 0) || Number(invoice.subtotal_amount || 0);
  const selNet = allSel ? fullNet : lines.filter((li) => selectedIds.has(li.id)).reduce((s, li) => s + Number(li.amount || 0), 0);

  let tax = 0;
  let taxLabel = "Tax";
  if (!allSel && derivedRate) {
    tax = Math.round(selNet * (derivedRate / 100) * 100) / 100;
    taxLabel = `Tax (${derivedRate}% — ${invoice.sap_tax_code || "SAP code"})`;
  } else if (fullTax > 0) {
    tax = fullNet > 0 ? Math.round(fullTax * (selNet / fullNet) * 100) / 100 : 0;
  } else if (derivedRate) {
    tax = Math.round(selNet * (derivedRate / 100) * 100) / 100;
    taxLabel = `Tax (${derivedRate}% — from SAP code)`;
  }
  return [
    { label: allSel ? "Subtotal" : "Subtotal (selected)", value: fmt(selNet) },
    { label: taxLabel, value: fmt(tax), isTax: true },
    { label: allSel ? "Total" : "Total (selected)", value: fmt(selNet + tax), isTotal: true },
  ];
}

export default function InvoiceDetailPage({ invoiceId, onBack, currentUser }) {
  const roleLabel = useRoleLabel();
  const {
    invoice,
    loading,
    error,
    saving,
    changeStatus,
    refetch,
  } = useInvoiceDetail(invoiceId);
  // No batch "edit mode" anymore — fields & line items are inline-editable and
  // autosave. `editing` is kept false so the existing !editing view guards pass.
  const editing = false;

  // ── FBR ATL detail for this supplier (rich: name, business, IT/ST lists) ──
  const [fbrInfo, setFbrInfo] = useState(null);
  const [fbrLoading, setFbrLoading] = useState(false);
  const [fbrExpanded, setFbrExpanded] = useState(false);
  const loadFbr = () => {
    const ntn = (invoice?.supplier_ntn || "").trim();
    if (!ntn) { setFbrInfo(null); return; }
    setFbrLoading(true);
    verifyNTN(ntn)
      .then((r) => setFbrInfo(r))
      .catch(() => setFbrInfo(null))
      .finally(() => setFbrLoading(false));
  };
  useEffect(() => { loadFbr(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [invoice?.id, invoice?.supplier_ntn]);

  // ── ERP (SAP vendor master) registration for this supplier ──
  const [erpStatus, setErpStatus] = useState("verifying"); // verifying|registered|not_registered|error
  const [erpVendorNo, setErpVendorNo] = useState(null);
  useEffect(() => {
    const ntn = (invoice?.supplier_ntn || "").trim();
    const name = (invoice?.supplier_name || "").trim();
    if (!ntn && !name) { setErpStatus("not_registered"); return; }
    setErpStatus("verifying");
    lookupSAPVendor({ ntn, name })
      .then((r) => { setErpStatus(r.registered ? "registered" : "not_registered"); setErpVendorNo(r.vendor_number || null); })
      .catch(() => setErpStatus("error"));
  }, [invoice?.id, invoice?.supplier_ntn, invoice?.supplier_name]);

  // ── Per-line selection + match status (item-level parking control) ──
  const [matchStatusById, setMatchStatusById] = useState(null); // {lineId: 'matched'|'unmatched'}
  const [poLineCount, setPoLineCount] = useState(0); // PO items in the latest match result
  const [selectedLineIds, setSelectedLineIds] = useState(null); // Set<lineId>

  // Changes when a line is added or removed (a bare length would miss a delete
  // followed by an add), so the effects below re-run for exactly that.
  const lineIdKey = (invoice?.line_items || []).map((li) => li.id).join(",");

  // Load the latest PO match result → per-line match status (on PO / not on PO)
  // and how many items the PO has. Selection is separate, below.
  useEffect(() => {
    const lines = invoice?.line_items || [];
    if (!invoice || lines.length === 0) { setMatchStatusById(null); setPoLineCount(0); return; }
    let cancelled = false;
    getInvoiceMatches(invoice.id)
      .then((data) => {
        if (cancelled) return;
        const results = Array.isArray(data) ? data : data?.matches || [];
        const result = results.find((r) => r.po_id === invoice.matched_po_id) || results[0];
        const statusMap = {};
        let poItems = 0; // every PO line appears once in line_matches, paired or not
        for (const lm of result?.line_matches || []) {
          if (lm.po_line_item_id != null) poItems += 1;
          if (lm.invoice_line_item_id != null) {
            statusMap[lm.invoice_line_item_id] = lm.po_line_item_id != null ? "matched" : "unmatched";
          }
        }
        const hasData = Object.keys(statusMap).length > 0;
        // Once there is match data, a line the match does not mention has no PO item either.
        if (hasData) for (const li of lines) if (!(li.id in statusMap)) statusMap[li.id] = "unmatched";
        setMatchStatusById(hasData ? statusMap : null);
        setPoLineCount(hasData ? poItems : 0);
      })
      .catch(() => {
        if (cancelled) return;
        setMatchStatusById(null);
        setPoLineCount(0);
      });
    return () => { cancelled = true; };
  }, [invoice?.id, invoice?.matched_po_id, lineIdKey]);

  // Which lines are selected for parking. Every line starts selected: a line the
  // PO does not carry is flagged (see blockedIds) rather than quietly left out.
  // The selection saved at submit-for-approval wins on first sight of an invoice,
  // so every approver sees the same lines. After that the user's own toggles are
  // kept; a line that disappears drops out and a new line starts selected.
  const knownLineIds = useRef({ invoiceId: null, ids: new Set() });
  useEffect(() => {
    const lines = invoice?.line_items || [];
    if (!invoice || lines.length === 0) {
      knownLineIds.current = { invoiceId: invoice?.id ?? null, ids: new Set() };
      setSelectedLineIds(null);
      return;
    }
    const ids = lines.map((li) => li.id);
    const known = knownLineIds.current;
    if (known.invoiceId !== invoice.id || known.ids.size === 0) {
      const saved = (invoice.parking_line_item_ids || []).filter((id) => ids.includes(id));
      setSelectedLineIds(new Set(saved.length ? saved : ids));
    } else {
      setSelectedLineIds((prev) => new Set(ids.filter((id) => !known.ids.has(id) || prev?.has(id))));
    }
    knownLineIds.current = { invoiceId: invoice.id, ids: new Set(ids) };
  }, [invoice?.id, lineIdKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSelectLine = (id) =>
    setSelectedLineIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const toggleSelectAllLines = (checked) => {
    const lines = invoice?.line_items || [];
    setSelectedLineIds(checked ? new Set(lines.map((li) => li.id)) : new Set());
  };
  const selectedLineIdArray = () => (selectedLineIds ? Array.from(selectedLineIds) : null);

  const handleDeleteLineItem = async (lineId) => {
    if (!window.confirm("Permanently delete this line item from the invoice? This cannot be undone.")) return;
    try {
      await deleteInvoiceLineItem(invoice.id, lineId);
      await refetch();
    } catch (err) {
      window.alert(err.response?.data?.detail || "Failed to delete line item.");
    }
  };

  // ── Inline editing (no Edit mode) — fields & lines autosave ──
  const INLINE_FIELD_KEYS = [
    "invoice_number", "invoice_date", "due_date", "currency", "document_type",
    "po_reference", "supplier_name", "supplier_address", "supplier_ntn",
    "receiver_name", "receiver_address", "subtotal_amount", "tax_amount",
    "gst_amount", "wht_amount", "total_amount", "bank_iban",
  ];
  const [inlineFields, setInlineFields] = useState({});
  useEffect(() => {
    if (!invoice) return;
    const seed = {};
    for (const k of INLINE_FIELD_KEYS) {
      seed[k] = invoice[k] ?? (["subtotal_amount", "tax_amount", "gst_amount", "wht_amount", "total_amount"].includes(k) ? null : "");
    }
    setInlineFields(seed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoice?.id]);

  const handleInlineFieldChange = (field, value) =>
    setInlineFields((prev) => ({ ...prev, [field]: value }));

  const handleInlineFieldSave = async (field, value) => {
    if (invoice?.[field] === value) return; // unchanged
    try {
      await updateInvoice(invoice.id, { [field]: value });
      await refetch();
    } catch (err) {
      setValidateError(err.response?.data?.detail || "Failed to save field.");
    }
  };

  const handleLineSave = async (lineId, patch) => {
    try {
      await patchInvoiceLineItem(invoice.id, lineId, patch);
      await refetch();
    } catch (err) {
      setValidateError(err.response?.data?.detail || "Failed to save line item.");
    }
  };

  // "+ Add line" is hidden for now — kept for easy re-enable (pass as
  // onAddLineItem to LineItemsTable below).
  // eslint-disable-next-line no-unused-vars
  const handleAddLine = async () => {
    try {
      await addInvoiceLineItem(invoice.id);
      await refetch();
    } catch (err) {
      setValidateError(err.response?.data?.detail || "Failed to add line item.");
    }
  };

  const { verifyResult, verifyError, verify: verifyFBR } = useFBRVerification();

  // Deep-link scroll: /invoices/{id}#comments (e.g. from a mention notification)
  // scrolls to the comment section once the page has rendered. Read the hash
  // from window.location (not useLocation) so this component also works inside
  // the supplier portal, which has no react-router context.
  const commentsRef = useRef(null);
  useEffect(() => {
    if (loading || !invoice) return;
    if (window.location.hash === "#comments") {
      // small delay so the cards above have rendered and taken their height
      const t = setTimeout(() => {
        commentsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 350);
      return () => clearTimeout(t);
    }
  }, [loading, invoice?.id]);

  // Fetch pending approval info (with all steps)
  const [pendingApproval, setPendingApproval] = useState(null);
  const [approvalSteps, setApprovalSteps] = useState([]);
  useEffect(() => {
    if (!invoice) {
      setPendingApproval(null);
      setApprovalSteps([]);
      return;
    }
    getInvoiceApproval(invoice.id).then((data) => {
      if (data?.has_approval && data.approval) {
        const step = data.steps?.find((s) => s.step_order === data.approval.current_step_order);
        setPendingApproval({
          stepName: step?.step_name || data.approval.current_step_name,
          role: roleLabel(step?.approver_role || data.approval.current_step_role),
          stepOrder: data.approval.current_step_order,
          totalSteps: data.approval.total_steps,
          workflowName: data.approval.workflow_name,
          overallStatus: data.approval.overall_status,
        });
        setApprovalSteps(data.steps || []);
      } else if (invoice.status === "pending_approval") {
        // No workflow initiated yet — show generic pending info
        setPendingApproval({
          stepName: "Awaiting Workflow",
          role: "approver",
          stepOrder: 1,
          totalSteps: 0,
          workflowName: "",
          overallStatus: "pending",
        });
        setApprovalSteps([]);
      }
    }).catch(() => {});
  }, [invoice?.id, invoice?.status]);

  // Approval confirmation modal state
  const [showApprovalConfirm, setShowApprovalConfirm] = useState(false);
  const [workflowSteps, setWorkflowSteps] = useState([]);
  const [workflowName, setWorkflowName] = useState("");
  const [workflowBlocked, setWorkflowBlocked] = useState(null); // reason string when no workflow matches
  const [sapValidationError, setSapValidationError] = useState(null); // SAP dry-run error(s) at submit time
  const [validatingSap, setValidatingSap] = useState(false);
  const [submittingApproval, setSubmittingApproval] = useState(false);

  /** Does this active template actually match the invoice (same rules as the
   *  backend engine: currency, amount range, invoice type)? */
  const templateMatches = (t) => {
    if (!t.is_active) return false;
    if (t.currency && invoice?.currency && t.currency !== invoice.currency) return false;
    const amt = Number(invoice?.total_amount || 0);
    if (t.min_amount != null && amt < t.min_amount) return false;
    if (t.max_amount != null && t.max_amount > 0 && amt > t.max_amount) return false;
    if (t.invoice_type && t.invoice_type !== "all" && invoice?.document_type &&
        t.invoice_type !== invoice.document_type) return false;
    return true;
  };

  const handleSubmitForApproval = async () => {
    if (blockedMessage) {
      // Applies to every role (only parkers run the SAP dry run below).
      lineItemsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (!sapParkingComplete) {
      // Surface inline errors on the SAP Parking card and scroll to it.
      setShowSapErrors(true);
      sapCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setWorkflowBlocked(null);
    setWorkflowName("");
    setWorkflowSteps([]);
    setSapValidationError(null);

    // Pre-flight the SAP park (dry run) so parking errors — duplicate check,
    // missing entry sheet, dates, tax — surface NOW, before the approval chain,
    // instead of after Finance Director approves. Only parkers (Purchaser /
    // Admin) can run the dry run; other submitters skip it (someone else parks).
    if (canParkToSAP) {
      setValidatingSap(true);
      try {
        const res = await validateInvoiceForSAP(invoice.id, selectedLineIdArray());
        if (!res.ok) {
          setSapValidationError(res.message || "SAP validation failed.");
        }
      } catch (err) {
        const detail = err.response?.data?.detail;
        setSapValidationError(
          typeof detail === "string" ? detail : detail?.message || "SAP validation failed — see server logs."
        );
      } finally {
        setValidatingSap(false);
      }
    }

    // Find a workflow template that MATCHES this invoice — no match = blocked.
    try {
      const templates = await listTemplates();
      const list = Array.isArray(templates) ? templates : templates?.templates || [];
      const match = list.find(templateMatches);
      if (match) {
        setWorkflowName(match.name);
        setWorkflowSteps((match.steps || []).sort((a, b) => a.step_order - b.step_order));
      } else {
        const actives = list.filter((t) => t.is_active);
        setWorkflowBlocked(
          actives.length === 0
            ? "No active approval workflow is configured. An admin must create one in Admin → Workflows before this invoice can be submitted."
            : `No active workflow matches this invoice (currency ${invoice?.currency || "PKR"}, amount ${Number(invoice?.total_amount || 0).toLocaleString()}). Adjust a workflow template's currency/amount range in Admin → Workflows.`
        );
      }
    } catch {
      setWorkflowBlocked("Could not load workflow templates — check the backend and try again.");
    }
    setShowApprovalConfirm(true);
  };

  // Validate = the human sign-off that the AI-extracted data has been reviewed.
  // Enforce that the essentials are present before letting it through, so
  // "Validated" is a real checkpoint rather than a blind click.
  const [validateError, setValidateError] = useState(null);
  const handleValidate = () => {
    const missing = [];
    if (!invoice?.invoice_number?.trim()) missing.push("Invoice #");
    if (!invoice?.invoice_date) missing.push("Invoice Date");
    if (!invoice?.supplier_name?.trim()) missing.push("Supplier Name");
    if (!(Number(invoice?.total_amount) > 0)) missing.push("Total Amount");
    if (missing.length) {
      setValidateError(
        `Cannot validate — these fields are required: ${missing.join(", ")}. ` +
        "Fill them in above, then Validate."
      );
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    setValidateError(null);
    changeStatus("validated");
  };

  const confirmApproval = async () => {
    setSubmittingApproval(true);
    try {
      const token = currentUser?.token || localStorage.getItem("auth_token");
      // Lock in the line-item selection so it carries through the workflow and
      // every approver sees the same lines (and the parked amount matches).
      try { await setParkingSelection(invoice.id, selectedLineIdArray() || []); } catch { /* non-fatal */ }
      await initiateApproval(invoice.id, token);
      setShowApprovalConfirm(false);
      await refetch();
    } catch (err) {
      setShowApprovalConfirm(false);
      alert(err.response?.data?.detail || "Failed to initiate approval workflow");
    } finally {
      setSubmittingApproval(false);
    }
  };

  // ── SAP Posting state ──
  const [showSAPPostConfirm, setShowSAPPostConfirm] = useState(false);
  const [sapPosting, setSapPosting] = useState(false);
  const [sapPostResult, setSapPostResult] = useState(null);
  const [sapPostError, setSapPostError] = useState(null);
  const [taxCodes, setTaxCodes] = useState([]);
  const [taxCodesLoading, setTaxCodesLoading] = useState(false);
  const [currencies, setCurrencies] = useState([]);
  // Inline SAP-parking validation: shown after a blocked submit-for-approval.
  const [showSapErrors, setShowSapErrors] = useState(false);
  const sapCardRef = useRef(null);
  const lineItemsRef = useRef(null);
  // Live values reported by the SAP Parking card (validated synchronously,
  // since the backend save lags behind the inputs).
  const [liveSap, setLiveSap] = useState(null);
  const handleSapValues = useMemo(() => (v) => setLiveSap(v), []);
  // Optimistic local selection so the dropdown reflects a pick instantly,
  // before the save round-trips back. Reset when switching invoices.
  const [pickedTaxCode, setPickedTaxCode] = useState(null);
  useEffect(() => { setPickedTaxCode(null); }, [invoiceId]);

  // Fetch the cached SAP tax codes once the invoice is loaded, so the
  // Financial Details dropdown (and later the Park modal) can use them.
  useEffect(() => {
    if (!invoice || taxCodes.length > 0) return;
    setTaxCodesLoading(true);
    fetchSAPTaxCodes()
      .then((data) => setTaxCodes(data.tax_codes || []))
      .catch(() => { /* keep the free-text fallback */ })
      .finally(() => setTaxCodesLoading(false));
  }, [invoice, taxCodes.length]);

  // Fetch the cached SAP currency list once the invoice is loaded.
  useEffect(() => {
    if (!invoice || currencies.length > 0) return;
    fetchSAPCurrencies()
      .then((data) => setCurrencies(data.currencies || []))
      .catch(() => { /* fall back to invoice currency + PKR */ });
  }, [invoice, currencies.length]);

  // The AI-suggested code for this invoice's tax rate, and the effective code
  // shown in the dropdown (saved code wins, else AI suggestion).
  const aiSuggestedTaxCode = useMemo(
    () => (taxCodes.length ? pickDefaultTaxCode(invoice, taxCodes) : null),
    [invoice, taxCodes]
  );
  // Optimistic pick wins, then the saved code, then the AI suggestion.
  const effectiveTaxCode = pickedTaxCode ?? invoice?.sap_tax_code ?? aiSuggestedTaxCode ?? "";

  // Reflect the choice instantly, then persist on the invoice in the background.
  const handleTaxCodeChange = (code) => {
    if (!code) return;
    setPickedTaxCode(code);
    updateInvoice(invoiceId, { sap_tax_code: code })
      .then(() => refetch())
      .catch(() => { /* non-fatal — optimistic selection stays */ });
  };

  // Persist any SAP-posting field (layout / posting date / header text / fx).
  const handleSapFieldSave = (patch) => {
    updateInvoice(invoiceId, patch)
      .then(() => refetch())
      .catch(() => { /* non-fatal */ });
  };

  // ── Unpark / delete ──
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const handleUnpark = async () => {
    if (!window.confirm(
      `Unpark from SAP?\n\nThis deletes SAP document ${invoice.sap_document_number}/${invoice.sap_fiscal_year} ` +
      `and then removes this invoice from your list.`
    )) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await unparkInvoiceFromSAP(invoice.id);
      onBack();  // invoice is now soft-deleted — return to the list
    } catch (err) {
      const detail = err.response?.data?.detail;
      setActionError(typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail || "Failed to unpark from SAP");
    } finally {
      setActionBusy(false);
    }
  };

  // ── Original uploaded document: view in a new tab / download ──
  const [docBusy, setDocBusy] = useState(null); // "view" | "download" | null

  const handleDocument = async (mode) => {
    setDocBusy(mode);
    setActionError(null);
    try {
      await openInvoiceDocument(invoice, mode);
    } catch (err) {
      setActionError(err.message || "Could not open the invoice document.");
    } finally {
      setDocBusy(null);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Delete this invoice? It will be removed from your list.")) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await deleteInvoice(invoice.id);
      onBack();
    } catch (err) {
      setActionError(err.response?.data?.detail || err.message || "Failed to delete invoice");
    } finally {
      setActionBusy(false);
    }
  };

  // Whether this user can change the invoice comes from the admin-editable
  // permission matrix: level "edit" on the Invoice Inbox page. "view" users
  // (reviewers brought in via @mention — dept heads, auditor, etc.) are
  // read-only + can only comment.
  const { canEdit: canEditByPermission, role: currentRole } = usePermissions();
  // Only purchasers (ap_operator) and admins may park to SAP (mirrors the backend guard).
  const canParkToSAP = currentRole === "admin" || currentRole === "ap_operator";
  const canEditInvoice = canEditByPermission("/invoices");
  // Suppliers viewing their own invoice: no edit rights, but a DRAFT (e.g.
  // just created from a PO) needs their explicit "Submit for Processing"
  // before it reaches the AP inbox. Backend enforces ownership + transition.
  const isSupplierViewer = currentUser?.role === "supplier";
  const supplierCanSubmit = isSupplierViewer && invoice?.status === "draft";

  // SAP parking fields are editable only during review — locked once the
  // invoice is submitted for approval (pending_approval) and beyond.
  const sapFieldsEditable =
    canEditInvoice && !!invoice && ["draft", "pending_processing", "validated", "rejected", "exception"].includes(invoice.status);

  // Chosen document currency drives whether an exchange rate is required.
  const currencyVal = (liveSap ? liveSap.currency : (invoice?.sap_currency || invoice?.currency)) || "PKR";
  const foreignCurrency = !!invoice && currencyVal !== (invoice.base_currency || "PKR");
  // Validate against the card's LIVE input values (reported via onValuesChange).
  // Before the card reports, fall back to saved values / defaults so we don't
  // flag anything prematurely. An input the user emptied is caught immediately.
  const sapFieldErrors = {};
  if (invoice) {
    const layoutVal   = liveSap ? liveSap.layout       : (invoice.sap_layout ?? "goods");
    const postingVal  = liveSap ? liveSap.postingDate  : (invoice.sap_posting_date ?? "2025-05-20");
    const baselineVal = liveSap ? liveSap.baselineDate : (invoice.sap_baseline_date ?? "2025-05-20");
    const headerVal   = liveSap ? liveSap.headerText   : (invoice.sap_header_text ?? `einv-${invoice.invoice_number || invoice.id}`);
    const itemVal     = liveSap ? liveSap.itemText     : (invoice.sap_item_text ?? (invoice.invoice_number || `einv-${invoice.id}`));
    const fxVal       = liveSap ? liveSap.exchangeRate : invoice.exchange_rate;
    const blank = (v) => !String(v ?? "").trim();
    if (!(invoice.sap_tax_code || effectiveTaxCode)) sapFieldErrors.taxCode = "Select a SAP tax code.";
    if (blank(layoutVal)) sapFieldErrors.layout = "Choose a layout.";
    if (blank(currencyVal)) sapFieldErrors.currency = "Select a currency.";
    if (blank(postingVal)) sapFieldErrors.postingDate = "Enter a posting date.";
    if (blank(baselineVal)) sapFieldErrors.baselineDate = "Enter a baseline date.";
    if (blank(headerVal)) sapFieldErrors.headerText = "Enter header text.";
    if (blank(itemVal)) sapFieldErrors.itemText = "Enter item text.";
    if (foreignCurrency && blank(fxVal)) sapFieldErrors.exchangeRate = "Exchange rate is required for foreign currency.";
  }
  const sapParkingComplete = !!invoice && Object.keys(sapFieldErrors).length === 0;

  // A selected line with no PO item cannot be parked: the SAP payload only has
  // PO-linked rows, and the backend refuses it. Flag it here, before the user
  // submits, instead of letting the park fail after approval.
  const blockedIds = useMemo(
    () => blockedLineIds(
      invoice?.line_items, selectedLineIds, matchStatusById, poLineCount,
      liveSap ? liveSap.layout : (invoice?.sap_layout ?? "goods")
    ),
    [invoice?.line_items, selectedLineIds, matchStatusById, poLineCount, liveSap, invoice?.sap_layout]
  );
  const blockedMessage = blockedIds.size ? blockedLinesMessage(invoice?.line_items, blockedIds) : null;

  // Auto-fill sensible defaults for any parking field that was never set, so the
  // shown values are actually saved. Only fills NULL fields — a value the user
  // explicitly cleared ("") stays empty and will block approval until re-entered.
  useEffect(() => {
    if (!invoice || !sapFieldsEditable) return;
    const patch = {};
    if (invoice.sap_layout == null) patch.sap_layout = "goods";
    if (invoice.sap_posting_date == null) patch.sap_posting_date = "2025-05-20";
    if (invoice.sap_baseline_date == null) patch.sap_baseline_date = "2025-05-20";
    if (invoice.sap_header_text == null) patch.sap_header_text = `einv-${invoice.invoice_number || invoice.id}`;
    if (invoice.sap_item_text == null) patch.sap_item_text = invoice.invoice_number || `einv-${invoice.id}`;
    if (invoice.sap_currency == null) patch.sap_currency = invoice.currency || "PKR";
    if (invoice.sap_tax_code == null && aiSuggestedTaxCode) patch.sap_tax_code = aiSuggestedTaxCode;
    if (Object.keys(patch).length === 0) return;
    updateInvoice(invoiceId, patch).then(() => refetch()).catch(() => { /* non-fatal */ });
  }, [invoice, sapFieldsEditable, aiSuggestedTaxCode, invoiceId, refetch]);

  // Parking is only allowed once the invoice has completed approval — you can't
  // send it to SAP before it's approved. Not yet sent to SAP.
  const sapEligible = invoice && invoice?.status === "approved" && !invoice?.sap_document_number;
  // Actually parkable only once a PO is matched (line items are built from PO items).
  const canPostToSAP = sapEligible && invoice?.matched_po_id;

  const handlePostToSAP = async () => {
    setSapPosting(true);
    setSapPostError(null);
    setSapPostResult(null);
    try {
      const result = await postInvoiceToSAP(invoice.id, {
        mode: "park",
        // All values come from what was set on the invoice before approval.
        taxCode: invoice.sap_tax_code || effectiveTaxCode || "I0",
        postingDate: invoice.sap_posting_date || "2025-05-20",
        headerText: invoice.sap_header_text || null,
        exchangeRate: invoice.exchange_rate || null,
        layout: invoice.sap_layout || "goods",
        lineItemIds: selectedLineIdArray(),
      });
      setSapPostResult(result);
      setShowSAPPostConfirm(false);
      await refetch();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const base = typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail || "Failed to park invoice in SAP";
      // An approved invoice is locked: the way back to editing its lines is Flag Exception.
      const hint = invoice.status === "approved" && typeof detail === "string" && detail.includes("Uncheck or delete")
        ? " This invoice is approved, so use Flag Exception to edit its lines first."
        : "";
      setSapPostError(base + hint);
    } finally {
      setSapPosting(false);
    }
  };

  // --- Loading state ---
  if (loading) {
    return (
      <Card>
        <Spinner text="Loading invoice..." subtext="Fetching invoice details" />
      </Card>
    );
  }

  // --- Error state ---
  if (error && !invoice) {
    return (
      <Card>
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-3">
          <div className="font-semibold text-xs text-danger-dark mb-1">
            Failed to Load Invoice
          </div>
          <div className="text-2xs text-danger-dark mb-3">{error}</div>
          <Button variant="secondary" size="sm" onClick={onBack}>
            &larr; Back to List
          </Button>
        </div>
      </Card>
    );
  }

  if (!invoice) return null;

  const actions = STATUS_ACTIONS[invoice.status] || [];
  // Inline-editable while pre-approval, the user has edit rights, and it's not
  // in SAP. Locks automatically once approved/parked/posted.
  const editable =
    canEditInvoice &&
    !invoice.sap_document_number &&
    ["draft", "pending_processing", "validated", "rejected", "exception"].includes(invoice.status);

  return (
    <div className="flex flex-col gap-5">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>
            &larr; Back
          </Button>
          <div>
            <h2 className="text-xl font-bold text-neutral-900 m-0">
              {invoice.invoice_number || `Invoice #${invoice.id}`}
            </h2>
            <span className="text-2xs text-neutral-500">
              {invoice.original_filename}
              {invoice.created_at && (
                <> &middot; {new Date(invoice.created_at).toLocaleDateString()}</>
              )}
              {invoice.document_available && (
                <>
                  {" "}&middot;{" "}
                  <button
                    type="button"
                    className="text-brand-600 hover:text-brand-800 hover:underline bg-transparent border-none p-0 cursor-pointer disabled:opacity-50 disabled:cursor-wait"
                    onClick={() => handleDocument("view")}
                    disabled={!!docBusy}
                    title="Open the uploaded invoice in a new tab"
                  >
                    {docBusy === "view" ? "Opening…" : "View"}
                  </button>
                  {" "}&middot;{" "}
                  <button
                    type="button"
                    className="text-brand-600 hover:text-brand-800 hover:underline bg-transparent border-none p-0 cursor-pointer disabled:opacity-50 disabled:cursor-wait"
                    onClick={() => handleDocument("download")}
                    disabled={!!docBusy}
                    title="Download the uploaded invoice file"
                  >
                    {docBusy === "download" ? "Downloading…" : "Download"}
                  </button>
                </>
              )}
            </span>
          </div>
          <Badge status={invoice.status} />
          {invoice.supplier_ntn && (
            // Header shows just the compact pill (single line, so it aligns with
            // the status Badge); the full FBR detail lives in the Vendor
            // Verification card below.
            <FBRVerificationBadge
              status={fbrInfo?.status || invoice.fbr_verification_status}
            />
          )}
        </div>

        <div className="flex items-center gap-2">
          {!canEditInvoice && !supplierCanSubmit && (
            <span className="text-2xs text-neutral-400 italic">View only — you can comment below</span>
          )}

          {/* Supplier: submit their own draft (e.g. created from a PO) into the
              AP pipeline. Until then the draft is invisible to AP staff. */}
          {supplierCanSubmit && (
            <Button
              variant="primary"
              size="sm"
              onClick={async () => {
                await changeStatus("pending_processing");
                matchProducts(invoiceId).catch(() => {});
              }}
              disabled={saving}
              title="Send this invoice to Accounts Payable for processing"
            >
              {saving ? "Submitting…" : "Submit for Processing"}
            </Button>
          )}
          {/* FBR verify/re-verify lives on the Vendor Verification card below —
              no duplicate button in the header. */}
          {/* No Edit button — fields & line items are edited inline (autosave).
              A subtle hint tells the operator the page is directly editable. */}
          {editable && (
            <span className="text-2xs text-neutral-400 italic">Fields save as you edit</span>
          )}

          {/* Status transition actions */}
          {!editing && canEditInvoice &&
            actions.map((action) => (
              <Button
                key={action.targetStatus}
                variant={action.variant}
                size="sm"
                onClick={() =>
                  action.targetStatus === "pending_approval"
                    ? handleSubmitForApproval()
                    : action.targetStatus === "validated"
                    ? handleValidate()
                    : changeStatus(action.targetStatus)
                }
                title={action.targetStatus === "validated"
                  ? "Confirm you've reviewed the extracted data — checks that required fields are present."
                  : action.targetStatus === "pending_approval" && blockedMessage
                  ? "Some selected lines are not on the PO. Uncheck or delete them first."
                  : undefined}
                disabled={saving || (action.targetStatus === "pending_approval" && (validatingSap || !!blockedMessage))}
              >
                {action.targetStatus === "pending_approval" && validatingSap
                  ? "Validating with SAP…"
                  : action.label}
              </Button>
            ))}

          {/* Park to SAP — shown for validated/approved invoices not yet in SAP.
              Disabled (with a reason) until a PO is matched, so it stays visible
              rather than silently disappearing. */}
          {!editing && canEditInvoice && sapEligible && canParkToSAP && (
            <span title={!canPostToSAP ? "Match this invoice to a purchase order first (PO Match section below) to enable parking." : undefined}>
              <Button
                variant="success"
                size="sm"
                onClick={() => { setSapPostError(null); setShowSAPPostConfirm(true); }}
                disabled={sapPosting || !canPostToSAP}
              >
                {sapPosting ? "Parking..." : "Park to SAP"}
              </Button>
            </span>
          )}

          {/* Unpark from SAP — for parked invoices. Deletes the SAP doc, then
              soft-deletes here. (Posted docs must be reversed in SAP, not here.) */}
          {!editing && canEditInvoice && invoice.sap_document_number && invoice.sap_doc_status !== "posted" && (
            <Button variant="danger" size="sm" onClick={handleUnpark} disabled={actionBusy}>
              {actionBusy ? "Unparking..." : "Unpark from SAP"}
            </Button>
          )}

          {/* Delete — only for invoices not yet in SAP. Parked/posted can't be
              deleted here; they must be unparked/reversed in SAP first. */}
          {!editing && canEditInvoice && !invoice.sap_document_number && (
            <Button variant="ghost" size="sm" onClick={handleDelete} disabled={actionBusy}>
              {actionBusy ? "Deleting..." : "Delete"}
            </Button>
          )}
        </div>
      </div>

      {/* ── Unpark / delete error ── */}
      {actionError && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-2.5 flex items-center justify-between">
          <span className="text-2xs text-danger-dark font-medium">{actionError}</span>
          <button className="text-neutral-400 hover:text-neutral-600 text-sm" onClick={() => setActionError(null)}>&times;</button>
        </div>
      )}

      {/* ── Inline error banner ── */}
      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-2.5">
          <span className="text-2xs text-danger-dark font-medium">{error}</span>
        </div>
      )}

      {validateError && (
        <div className="bg-warning-bg border border-warning-base rounded-base px-4 py-2.5 flex items-center justify-between">
          <span className="text-2xs text-warning-dark font-medium">{validateError}</span>
          <button onClick={() => setValidateError(null)} className="text-warning-dark bg-transparent border-none cursor-pointer text-sm">&#10005;</button>
        </div>
      )}

      {/* ── SAP Post Success Banner ── */}
      {sapPostResult && (
        <div className="bg-success-bg border border-success-base rounded-base px-4 py-3 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-success-dark">
              {sapPostResult.sap_doc_status === "posted" ? "Invoice Posted to SAP Successfully" : "Invoice Parked in SAP Successfully"}
            </div>
            <div className="text-2xs text-success-dark mt-0.5">
              SAP Document: <strong>{sapPostResult.sap_document_number}</strong> / {sapPostResult.sap_fiscal_year}
              {sapPostResult.company_code && <> &middot; Company: {sapPostResult.company_code}</>}
              {sapPostResult.sap_doc_status !== "posted" && <> &middot; awaiting posting in SAP (MIR7)</>}
            </div>
          </div>
          <button className="text-neutral-400 hover:text-neutral-600 text-sm" onClick={() => setSapPostResult(null)}>&times;</button>
        </div>
      )}

      {/* ── SAP Post Error Banner — only when the Park modal is closed
           (while it's open, the error shows inside the modal instead) ── */}
      {sapPostError && !showSAPPostConfirm && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-3 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-danger-dark">Failed to Park in SAP</div>
            <div className="text-2xs text-danger-dark mt-0.5">{sapPostError}</div>
          </div>
          <button className="text-neutral-400 hover:text-neutral-600 text-sm" onClick={() => setSapPostError(null)}>&times;</button>
        </div>
      )}

      {/* ── SAP Posting Info (for already posted) ── */}
      {invoice.sap_document_number && !sapPostResult && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-md px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-emerald-600 text-base">&#9989;</span>
            <div>
              <div className="text-xs font-semibold text-emerald-800">
                {invoice.sap_doc_status === "posted" ? "Posted to SAP" : "Parked in SAP"} &mdash; Document {invoice.sap_document_number}/{invoice.sap_fiscal_year}
                {invoice.sap_doc_status !== "posted" && <span className="font-normal"> (awaiting posting in SAP)</span>}
              </div>
              <div className="text-2xs text-emerald-600 mt-0.5">
                {invoice.sap_company_code && <>Company Code: {invoice.sap_company_code} &middot; </>}
                {invoice.sap_posted_at && <>Sent: {new Date(invoice.sap_posted_at).toLocaleString()}</>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Duplicate Warning ── */}
      <DuplicateWarningCard
        invoiceId={invoice.id}
        refreshKey={`${invoice.matched_po_id}|${invoice.invoice_number}|${invoice.supplier_ntn}|${invoice.po_reference}`}
      />

      {/* ── Workflow Stepper ── */}
      <WorkflowStepper currentStatus={invoice.status} />

      {/* ── Review warnings (e.g. supplier vendor-name mismatch) — informational,
             they never change the invoice status ── */}
      {Array.isArray(invoice.warnings) && invoice.warnings.length > 0 && (
        <div className="bg-warning-bg border border-warning-light rounded-md px-4 py-3.5">
          <div className="flex items-start gap-3">
            <svg
              className="w-[18px] h-[18px] text-warning-dark flex-shrink-0 mt-0.5"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-warning-dark mb-1">
                Review needed — check before approving
              </div>
              <ul className="m-0 pl-0 list-none flex flex-col gap-1">
                {invoice.warnings.map((w, i) => (
                  <li key={i} className="text-2xs text-warning-text leading-relaxed">{w}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Pending Approval Info — full workflow chain */}
      {pendingApproval && (pendingApproval.overallStatus === "in_progress" || pendingApproval.overallStatus === "pending" || invoice.status === "pending_approval") && (
        <div className="bg-amber-50 border border-amber-200 rounded-md px-4 py-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-amber-600 text-lg">&#9203;</span>
            <div className="text-xs font-semibold text-amber-800">
              Approval Pending &middot; {pendingApproval.workflowName || "Workflow"}
            </div>
          </div>
          {approvalSteps.length > 0 && (
            <div className="flex items-center gap-0 ml-1">
              {approvalSteps.map((step, i) => {
                const isCurrent = step.step_order === pendingApproval.stepOrder;
                const isDone = step.status === "approved" || step.status === "skipped";
                const isRejected = step.status === "rejected";
                return (
                  <div key={step.step_order} className="flex items-center">
                    <div className={`flex items-center gap-2 px-3 py-2 rounded-md border text-2xs ${
                      isCurrent
                        ? "bg-amber-100 border-amber-300 text-amber-900 font-semibold"
                        : isDone
                          ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                          : isRejected
                            ? "bg-red-50 border-red-200 text-red-700"
                            : "bg-neutral-50 border-neutral-200 text-neutral-400"
                    }`}>
                      <span className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-2xs font-bold ${
                        isDone ? "bg-emerald-500" : isRejected ? "bg-red-500" : isCurrent ? "bg-amber-500" : "bg-neutral-300"
                      }`}>
                        {isDone ? "✓" : isRejected ? "✕" : step.step_order}
                      </span>
                      <div>
                        <div>{step.step_name}</div>
                        <div className={`text-2xs ${isCurrent ? "text-amber-600" : isDone ? "text-emerald-500" : "text-neutral-400"}`}>
                          {isCurrent && <span className="font-semibold">Pending from </span>}
                          <span>{roleLabel(step.approver_role)}</span>
                          {isDone && step.actor_name && <> &middot; {step.actor_name}</>}
                        </div>
                      </div>
                    </div>
                    {i < approvalSteps.length - 1 && (
                      <div className={`w-6 h-0.5 ${isDone ? "bg-emerald-400" : "bg-neutral-200"}`} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Invoice Classification — editors only (it triggers a re-classify action) */}
      {!editing && canEditInvoice && (
        <InvoiceClassificationCard
          invoiceId={invoice.id}
          currentDocType={invoice.document_type}
          onClassified={() => refetch()}
        />
      )}

      {/* ── KPI Summary Row ── */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Total Amount"
          value={
            invoice.total_amount != null
              ? `${invoice.currency || "PKR"} ${Number(invoice.total_amount).toLocaleString()}`
              : "---"
          }
          sub={
            invoice.subtotal_amount != null
              ? `Subtotal: ${invoice.currency || "PKR"} ${Number(invoice.subtotal_amount).toLocaleString()}`
              : undefined
          }
          accentColor={tokens.color.brand[500]}
          icon="&#128176;"
        />
        <KpiCard
          label="AI Confidence"
          value={
            invoice.overall_confidence != null
              ? `${Math.round(invoice.overall_confidence)}%`
              : "---"
          }
          sub="Overall extraction accuracy"
          accentColor={tokens.color.status.success.base}
          icon="&#127919;"
        />
        <KpiCard
          label="Document Type"
          value={invoice.document_type || "Invoice"}
          sub={`${invoice.page_count || 1} page${(invoice.page_count || 1) !== 1 ? "s" : ""}`}
          accentColor={tokens.color.status.info.base}
          icon="&#128203;"
        />
        <KpiCard
          label="Invoice Date"
          value={invoice.invoice_date || "---"}
          sub={invoice.due_date ? `Due: ${invoice.due_date}` : undefined}
          accentColor={tokens.color.status.posted.base}
          icon="&#128197;"
        />
      </div>

      {/* ── Vendor Verification: FBR tax-payer status + SAP ERP registration ── */}
      <Card title="Vendor Verification" subtitle={invoice.supplier_name || "Supplier compliance checks"}>
        <div className="flex flex-wrap items-start gap-8">
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">Tax Payer Status (FBR)</div>
            {invoice.supplier_ntn ? (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  {/* Click the badge to expand/collapse the FBR details */}
                  <button
                    type="button"
                    onClick={() => fbrInfo && setFbrExpanded((v) => !v)}
                    className="inline-flex items-center gap-1 bg-transparent border-none p-0 cursor-pointer"
                    title={fbrInfo ? "Click for FBR details" : undefined}
                  >
                    <FBRVerificationBadge
                      status={fbrInfo?.status || invoice.fbr_verification_status || "not_verified"}
                      source={fbrInfo?.source}
                    />
                    {fbrInfo && fbrInfo.status !== "not_found" && (
                      <span className="text-neutral-400 text-[10px]">{fbrExpanded ? "▲" : "▼"}</span>
                    )}
                  </button>
                  {!fbrLoading && (
                    <Button variant="ghost" size="xs" onClick={() => { loadFbr(); verifyFBR(invoice.id); }}>
                      Re-verify
                    </Button>
                  )}
                  {fbrLoading && <span className="text-2xs text-neutral-400">Verifying…</span>}
                </div>
                {fbrInfo && fbrInfo.status !== "not_found" && fbrExpanded && (
                  <div className="text-2xs text-neutral-600 flex flex-col gap-0.5">
                    <div><span className="text-neutral-400">NTN:</span> <span className="font-mono">{fbrInfo.ntn || invoice.supplier_ntn}</span></div>
                    {fbrInfo.taxpayer_name && <div><span className="text-neutral-400">Name:</span> {fbrInfo.taxpayer_name}</div>}
                    {fbrInfo.business_name && fbrInfo.business_name !== fbrInfo.taxpayer_name && (
                      <div><span className="text-neutral-400">Business:</span> {fbrInfo.business_name}</div>
                    )}
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="text-neutral-400">Registered:</span>
                      {(fbrInfo.registrations || []).length ? (
                        fbrInfo.registrations.map((r) => (
                          <span key={r} className="inline-flex items-center gap-1 text-[10px] font-semibold text-success-dark bg-success-bg border border-success-base px-1.5 py-0.5 rounded">
                            {r === "IT" ? "Income Tax" : r === "ST" ? "Sales Tax" : r}
                          </span>
                        ))
                      ) : <span className="text-neutral-400">—</span>}
                    </div>
                    <div className="text-neutral-400 mt-0.5">Source: {fbrInfo.source === "local_db" ? "FBR ATL" : fbrInfo.source === "live_api" ? "FBR Live" : fbrInfo.source}</div>
                  </div>
                )}
                {fbrInfo && fbrInfo.status === "not_found" && (
                  <div className="text-2xs text-warning-dark">NTN not on the Active Taxpayer List.</div>
                )}
              </div>
            ) : (
              <span className="text-2xs text-neutral-400 italic">No supplier NTN to verify</span>
            )}
          </div>
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">ERP Registration (SAP)</div>
            {(() => {
              const map = {
                registered: { cls: "bg-success-bg border-success-base text-success-dark", dot: "bg-success-base", label: "Registered" },
                not_registered: { cls: "bg-warning-bg border-warning-base text-warning-dark", dot: "bg-warning-base", label: "Not Registered" },
                verifying: { cls: "bg-info-bg border-info-base text-info-dark", dot: "bg-info-base", label: "Checking…" },
                error: { cls: "bg-neutral-50 border-neutral-200 text-neutral-500", dot: "bg-neutral-400", label: "Unavailable" },
              };
              const s = map[erpStatus] || map.error;
              return (
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-2xs font-semibold border ${s.cls}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
                  {s.label}
                  {erpStatus === "registered" && erpVendorNo && <span className="font-mono opacity-70 ml-1">#{erpVendorNo}</span>}
                </span>
              );
            })()}
          </div>
        </div>
      </Card>

      {/* ── Two-Column: Fields + Line Items ── */}
      {/* The Fields card drives the row height. The Line Items card is absolutely
          positioned so its (possibly long) list never stretches the row; it fills
          the Fields card's height and scrolls inside — so neither side shows a
          band of white space, however many lines there are. */}
      <div className="grid grid-cols-2 gap-5 items-stretch">
        <InvoiceDetailFields
          invoice={invoice}
          editing={editable}
          editFields={inlineFields}
          onFieldChange={handleInlineFieldChange}
          onFieldBlur={handleInlineFieldSave}
        />
        {/* "+ Add line" is hidden for now (operators shouldn't add lines that
            aren't on the vendor's document) — re-enable by passing
            onAddLineItem={handleAddLine}. */}
        <div ref={lineItemsRef} className="relative">
        <div className="absolute inset-0">
        <LineItemsTable
          lineItems={invoice.line_items || []}
          taxSummary={buildSelectedTaxSummary(
            invoice,
            selectedLineIds,
            // Rate of the tax code that will actually be used when parking —
            // partial selections compute their tax from it (see builder above).
            (() => {
              const code = invoice.sap_tax_code || effectiveTaxCode;
              return code ? (taxCodes.find((c) => c.code === code)?.rate ?? null) : null;
            })()
          )}
          editable={editable}
          onLineSave={editable ? handleLineSave : undefined}
          selectable={invoice.status !== "draft"}
          selectionLocked={!editable}
          selectedIds={selectedLineIds}
          onToggleSelect={toggleSelectLine}
          onToggleSelectAll={toggleSelectAllLines}
          onDeleteLineItem={editable ? handleDeleteLineItem : undefined}
          matchStatusById={matchStatusById}
          blockedIds={blockedIds}
          blockedMessage={blockedMessage}
        />
        </div>
        </div>
      </div>

      {/* Sales Tax — extracted figures only; SAP tax code lives in SAP Parking */}
      <SalesTaxCard
        alwaysShow
        fields={[
          invoice.tax_amount != null && { field_name: "total_tax_amount", value: invoice.tax_amount, label: "Tax Amount" },
          invoice.gst_amount != null && { field_name: "total_tax_amount", value: invoice.gst_amount, label: "GST Amount" },
          invoice.subtotal_amount != null && { field_name: "net_amount", value: invoice.subtotal_amount, label: "Subtotal" },
          invoice.total_amount != null && { field_name: "total_amount", value: invoice.total_amount, label: "Total Amount" },
        ].filter(Boolean)}
        lineItems={invoice.line_items || []}
      />

      {/* SAP Parking parameters — editable during review, locked at approval */}
      {!editing && (
        <div ref={sapCardRef}>
          <SAPPostingCard
            key={invoice.id}
            invoice={invoice}
            editable={sapFieldsEditable}
            onSave={handleSapFieldSave}
            foreignCurrency={foreignCurrency}
            currencies={currencies}
            errors={showSapErrors ? sapFieldErrors : {}}
            taxCodes={taxCodes}
            taxCode={effectiveTaxCode}
            aiSuggestedTaxCode={aiSuggestedTaxCode}
            onTaxCodeChange={handleTaxCodeChange}
            taxCodesLoading={taxCodesLoading}
            onValuesChange={handleSapValues}
          />
        </div>
      )}

      {/* Credit/Debit Note Info */}
      <CreditDebitNoteCard invoice={invoice} />

      {/* Multi-Currency */}
      <MultiCurrencyCard invoice={invoice} />

      {/* GL Account Coding — hidden for now
      {!editing && invoice.status !== "draft" && (
        <GLCodingCard
          invoiceId={invoice.id}
          lineItems={invoice.line_items || []}
          currentUser={currentUser}
        />
      )} */}

      {/* WHT Compliance */}
      {(verifyResult?.wht_compliance || invoice.wht_compliance_status) && (
        <WHTComplianceCard
          whtCompliance={verifyResult?.wht_compliance}
          fbrStatus={verifyResult?.fbr_verification?.status || invoice.fbr_verification_status}
          invoice={invoice}
        />
      )}

      {/* FBR verify error */}
      {verifyError && (
        <div className="bg-warning-bg border border-warning-base rounded-base px-4 py-2.5">
          <span className="text-2xs text-warning-dark font-medium">FBR Verification: {verifyError}</span>
        </div>
      )}

      {/* PO Matching Section — reviewers see results read-only (no run/match). */}
      {!editing && (
        <POMatchSection
          invoiceId={invoice.id}
          poReference={invoice.po_reference}
          onMatched={refetch}
          readOnly={!canEditInvoice}
        />
      )}

      {/* Approval Workflow Progress */}
      {!editing && (
        <ApprovalProgressCard
          invoiceId={invoice.id}
          invoiceStatus={invoice.status}
          currentUser={currentUser}
          onStatusChange={() => {
            refetch();
          }}
        />
      )}

      {/* Comments & Notes */}
      {!editing && (
        <div ref={commentsRef} id="comments">
          <CommentsCard entityType="invoice" entityId={invoice.id} currentUser={currentUser} />
        </div>
      )}

      {/* Supporting Documents */}
      {!editing && (
        <AttachmentsCard invoiceId={invoice.id} currentUser={currentUser} />
      )}

      {/* Audit Trail */}
      {!editing && (
        <AuditTrailCard entityType="invoice" entityId={invoice.id} />
      )}

      {/* SAP Posting Confirmation Modal */}
      <Modal
        open={showSAPPostConfirm}
        title="Park Invoice to SAP"
        onClose={() => setShowSAPPostConfirm(false)}
      >
        <div className="flex flex-col gap-4">
          <div className="text-xs text-neutral-600">
            <>This will <strong>park</strong> a vendor invoice in SAP (MIR7 — held, no accounting until a SAP user posts it) linked to PO <strong>{invoice.po_reference || `#${invoice.matched_po_id}`}</strong>.</>
          </div>

          <div className="bg-neutral-25 border border-neutral-100 rounded-md p-4 text-2xs space-y-2">
            <div className="flex justify-between">
              <span className="text-neutral-500">Invoice Number</span>
              <span className="font-medium text-neutral-800">{invoice.invoice_number || `INV-${invoice.id}`}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Vendor</span>
              <span className="font-medium text-neutral-800">{invoice.supplier_name || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Total Amount</span>
              <span className="font-semibold text-neutral-900">{invoice.currency || "PKR"} {Number(invoice.total_amount || 0).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Tax Amount</span>
              <span className="font-medium text-neutral-800">{invoice.currency || "PKR"} {Number(invoice.tax_amount || invoice.gst_amount || 0).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-neutral-500">Line Items</span>
              <span className="font-medium text-neutral-800">{(invoice.line_items || []).length}</span>
            </div>
          </div>

          {/* Read-only review of the SAP parking values set before approval */}
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
              SAP Posting Details
            </div>
            <div className="bg-neutral-25 border border-neutral-100 rounded-md p-4 text-2xs space-y-2">
              <div className="flex justify-between">
                <span className="text-neutral-500">Items to Park</span>
                <span className="font-medium text-neutral-800">
                  {{ goods: "Goods/service items", delivery: "Planned delivery costs", both: "Goods/service items + planned delivery costs" }[invoice.sap_layout || "goods"]}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Tax Code</span>
                <span className="font-medium text-neutral-800">
                  {(() => {
                    const code = invoice.sap_tax_code || effectiveTaxCode;
                    const desc = taxCodes.find((c) => c.code === code)?.description;
                    return code ? `${code}${desc ? ` — ${desc}` : ""}` : "—";
                  })()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Currency</span>
                <span className="font-medium text-neutral-800">{invoice.sap_currency || invoice.currency || "PKR"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Posting Date</span>
                <span className="font-medium text-neutral-800">{invoice.sap_posting_date || "2025-05-20"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Baseline Date</span>
                <span className="font-medium text-neutral-800">{invoice.sap_baseline_date || "2025-05-20"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Header Text</span>
                <span className="font-medium text-neutral-800">{invoice.sap_header_text || `einv-${invoice.invoice_number || invoice.id}`}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Item Text</span>
                <span className="font-medium text-neutral-800">{invoice.sap_item_text || (invoice.invoice_number || `einv-${invoice.id}`)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Exchange Rate</span>
                <span className="font-medium text-neutral-800">{invoice.exchange_rate ?? "—"}</span>
              </div>
            </div>
            <span className="text-2xs text-neutral-400 mt-1 block">
              These were set during review. To change them, edit before the invoice is submitted for approval.
            </span>
          </div>

          {sapPostError && (
            <div className="bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-2xs text-danger-dark">
              {sapPostError}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" onClick={() => setShowSAPPostConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="success"
              size="sm"
              onClick={handlePostToSAP}
              disabled={sapPosting || !sapParkingComplete}
            >
              {sapPosting ? "Parking in SAP..." : "Confirm & Park"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Approval Confirmation Modal */}
      <Modal
        open={showApprovalConfirm}
        title="Submit for Approval"
        onClose={() => setShowApprovalConfirm(false)}
      >
        <div className="flex flex-col gap-4">
          <div className="text-xs text-neutral-600">
            This invoice will be sent through the following approval workflow:
          </div>

          {/* No matching workflow — submission is blocked */}
          {workflowBlocked && (
            <div className="bg-danger-bg border border-danger-base rounded-md px-3 py-2.5 text-2xs text-danger-dark">
              <strong>Cannot submit:</strong> {workflowBlocked}
            </div>
          )}

          {sapValidationError && (
            <div className="bg-danger-bg border border-danger-base rounded-md px-3 py-2.5 text-2xs text-danger-dark">
              <strong>SAP validation failed — fix before submitting:</strong>
              <div className="mt-1">{sapValidationError}</div>
              <div className="mt-1 opacity-70">This invoice would fail when parking to SAP. Resolve it now so it doesn&apos;t error after approval.</div>
            </div>
          )}

          {canParkToSAP && !sapValidationError && !workflowBlocked && (
            <div className="bg-success-bg border border-success-base rounded-md px-3 py-2 text-2xs text-success-dark">
              ✓ SAP validation passed — this invoice will park cleanly after approval.
            </div>
          )}

          {workflowName && (
            <div className="text-sm font-semibold text-neutral-800">{workflowName}</div>
          )}

          {workflowSteps.length > 0 && (
            <div className="flex flex-col gap-2">
              {workflowSteps.map((step, i) => (
                <div key={step.id || i} className="flex items-center gap-3 bg-neutral-25 border border-neutral-100 rounded-md px-4 py-3">
                  <span className="w-6 h-6 rounded-full bg-brand-600 text-white text-2xs font-bold flex items-center justify-center flex-shrink-0">
                    {step.step_order}
                  </span>
                  <div className="flex-1">
                    <div className="text-xs font-semibold text-neutral-800">{step.step_name}</div>
                    <div className="text-2xs text-neutral-500">
                      {roleLabel(step.approver_role)}
                      {step.sla_hours && <> &middot; SLA: {step.sla_hours}h</>}
                    </div>
                  </div>
                  {i < workflowSteps.length - 1 && (
                    <span className="text-neutral-300 text-xs">&rarr;</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {workflowSteps.length > 0 && (
            <div className="bg-info-bg border border-info-base rounded-md px-3 py-2 text-2xs text-info-dark">
              The invoice will first go to <strong>{roleLabel(workflowSteps[0]?.approver_role)}</strong> for review{workflowSteps[1] && (
                <>, then to <strong>{roleLabel(workflowSteps[1]?.approver_role)}</strong> for final approval</>
              )}.
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" size="sm" onClick={() => setShowApprovalConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={confirmApproval}
              disabled={submittingApproval || !!workflowBlocked || !!sapValidationError || workflowSteps.length === 0}
            >
              {submittingApproval ? "Submitting..." : "Confirm & Submit"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
