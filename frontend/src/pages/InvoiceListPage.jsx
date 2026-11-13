import { useState, useEffect, useMemo, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { getInvoices } from "../services/invoiceService";
import { getInvoiceApproval } from "../services/workflowService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import KpiCard from "../components/common/KpiCard";
import TabBar from "../components/common/TabBar";
import FilterBar from "../components/common/FilterBar";
import DataTable from "../components/common/DataTable";
import ConfidenceMeter from "../components/common/ConfidenceMeter";
import Modal from "../components/common/Modal";
import { tokens } from "../styles/tokens";
import { openInvoiceDocument } from "../utils/invoiceDocument";

const DOC_LINK =
  "text-brand-600 hover:text-brand-800 hover:underline bg-transparent border-none p-0 cursor-pointer disabled:opacity-50 disabled:cursor-wait";

export default function InvoiceListPage({ onViewInvoice, onUpload }) {
  // Freshly uploaded drafts (batch upload) arrive via router state — highlight them.
  const location = useLocation();
  const [newIds, setNewIds] = useState(() => new Set(location.state?.newInvoiceIds || []));

  // Per-row View / Download of the uploaded file.
  const [docBusy, setDocBusy] = useState(null); // { id, mode } while a fetch runs
  const [docError, setDocError] = useState(null);
  const handleDocument = async (row, mode) => {
    setDocBusy({ id: row.id, mode });
    setDocError(null);
    try {
      await openInvoiceDocument(row, mode);
    } catch (err) {
      setDocError(`${row.invoice_number || `Invoice #${row.id}`}: ${err.message || "could not open the document."}`);
    } finally {
      setDocBusy(null);
    }
  };
  const uploadErrors = location.state?.uploadErrors || [];
  const [invoices, setInvoices] = useState([]);
  const [, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");  // specific status, on top of the tabs
  const [dateFrom, setDateFrom] = useState("");              // created-date range (yyyy-mm-dd)
  const [dateTo, setDateTo] = useState("");
  const [sortDir, setSortDir] = useState("desc");            // by created date: desc = newest first
  const [page, setPage] = useState(1);
  const [approvalInfo, setApprovalInfo] = useState({}); // { invoiceId: { stepName, role } }
  const perPage = 10;

  // Fetch approval info for pending_approval invoices
  const fetchApprovalInfo = useCallback(async (invoiceList) => {
    const pending = invoiceList.filter((inv) => inv.status === "pending_approval");
    if (!pending.length) return;
    const info = {};
    await Promise.all(
      pending.map(async (inv) => {
        try {
          const data = await getInvoiceApproval(inv.id);
          if (data?.has_approval && data.approval) {
            const currentStep = data.steps?.find(
              (s) => s.step_order === data.approval.current_step_order
            );
            info[inv.id] = {
              stepName: currentStep?.step_name || data.approval.current_step_name,
              role: currentStep?.approver_role || data.approval.current_step_role,
              stepOrder: data.approval.current_step_order,
              totalSteps: data.approval.total_steps,
            };
          }
        } catch { /* ignore */ }
      })
    );
    setApprovalInfo((prev) => ({ ...prev, ...info }));
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const data = await getInvoices(0, 100);
        setInvoices(data.invoices);
        setTotal(data.total);
        fetchApprovalInfo(data.invoices);
      } catch {
        // API not available yet
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [fetchApprovalInfo]);

  // Status counts for KPIs and tabs
  const statusCounts = useMemo(() => {
    const counts = { all: invoices.length, review: 0, approval: 0, posted: 0, exception: 0 };
    for (const inv of invoices) {
      if (["pending_processing", "draft"].includes(inv.status)) counts.review++;
      if (inv.status === "pending_approval") counts.approval++;
      if (["posted", "parked"].includes(inv.status)) counts.posted++;
      if (inv.status === "exception") counts.exception++;
    }
    return counts;
  }, [invoices]);

  // Filtered by tab
  const tabFiltered = useMemo(() => {
    if (tab === "all") return invoices;
    if (tab === "review") return invoices.filter((inv) => ["pending_processing", "draft"].includes(inv.status));
    if (tab === "approval") return invoices.filter((inv) => inv.status === "pending_approval");
    if (tab === "posted") return invoices.filter((inv) => ["posted", "parked"].includes(inv.status));
    if (tab === "exception") return invoices.filter((inv) => inv.status === "exception");
    return invoices;
  }, [invoices, tab]);

  // Filtered by search + status + created-date range, then sorted by created date
  const filtered = useMemo(() => {
    let list = tabFiltered;

    if (statusFilter !== "all") {
      list = list.filter((inv) => inv.status === statusFilter);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (inv) =>
          (inv.invoice_number || "").toLowerCase().includes(q) ||
          (inv.supplier_name || "").toLowerCase().includes(q) ||
          (inv.original_filename || "").toLowerCase().includes(q) ||
          String(inv.id).includes(q)
      );
    }

    if (dateFrom) {
      const from = new Date(dateFrom);
      list = list.filter((inv) => inv.created_at && new Date(inv.created_at) >= from);
    }
    if (dateTo) {
      const to = new Date(dateTo);
      to.setHours(23, 59, 59, 999);  // include the whole "to" day
      list = list.filter((inv) => inv.created_at && new Date(inv.created_at) <= to);
    }

    return [...list].sort((a, b) => {
      const da = a.created_at ? new Date(a.created_at).getTime() : 0;
      const db = b.created_at ? new Date(b.created_at).getTime() : 0;
      return sortDir === "asc" ? da - db : db - da;
    });
  }, [tabFiltered, statusFilter, search, dateFrom, dateTo, sortDir]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  // Reset page on any filter/sort change
  useEffect(() => { setPage(1); }, [tab, search, statusFilter, dateFrom, dateTo, sortDir]);

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8 text-xs text-neutral-500">Loading invoices...</div>
      </Card>
    );
  }

  if (invoices.length === 0) {
    return (
      <Card>
        <div className="text-center py-12">
          <div className="text-[40px] mb-3">&#128203;</div>
          <div className="text-sm font-semibold text-neutral-800 mb-1">No invoices yet</div>
          <div className="text-xs text-neutral-500 mb-4">Upload your first invoice to get started</div>
          <Button variant="primary" size="sm" onClick={onUpload}>
            &#128228; Upload Invoice
          </Button>
        </div>
      </Card>
    );
  }

  const columns = [
    {
      key: "id", label: "#",
      render: (v, row) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          {/* New rows are marked by the green row tint + this dot — a text pill
              wraps and breaks the narrow column, so keep the marker tiny. */}
          {newIds.has(row.id) && (
            <span
              className="w-2 h-2 rounded-full bg-success-base flex-shrink-0"
              title="Just uploaded"
            />
          )}
          {/* A real button, so the invoice can still be opened from the
              keyboard now that the row click replaced the eye icon. */}
          <button
            type="button"
            className="text-brand-600 font-semibold cursor-pointer hover:underline bg-transparent border-none p-0"
            onClick={(e) => { e.stopPropagation(); onViewInvoice?.(row.id); }}
            title="Open invoice"
          >
            #{v}
          </button>
        </span>
      ),
    },
    {
      key: "invoice_number", label: "Invoice Reference",
      // Plain, selectable text (not a link) so the reference can be copied;
      // open the invoice via the # link or the eye button instead.
      render: (v, row) => (
        <span
          className="font-medium text-neutral-800 whitespace-nowrap"
          title={row.original_filename || undefined}
        >
          {v || <span className="text-neutral-400 italic font-normal">—</span>}
        </span>
      ),
    },
    { key: "supplier_name", label: "Vendor", render: (v) => v || "—" },
    {
      key: "total_amount", label: "Amount", align: "right",
      render: (v, row) => (
        <span className={`font-semibold font-mono text-xs whitespace-nowrap ${Number(v) < 0 ? "text-danger-dark" : "text-neutral-900"}`}>
          {v != null ? `${row.currency || "PKR"} ${Math.abs(Number(v)).toLocaleString()}` : "—"}
        </span>
      ),
    },
    {
      key: "source_type", label: "Source",
      render: (v) => {
        const sourceMap = {
          web_upload: { label: "Web", icon: "🌐", bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700" },
          mobile_upload: { label: "Mobile", icon: "📱", bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700" },
          email: { label: "Email", icon: "📬", bg: "bg-indigo-50", border: "border-indigo-200", text: "text-indigo-700" },
          supplier: { label: "Supplier", icon: "🏢", bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700" },
          po_flip: { label: "From PO", icon: "📋", bg: "bg-cyan-50", border: "border-cyan-200", text: "text-cyan-700" },
          upload: { label: "Upload", icon: "📤", bg: "bg-neutral-50", border: "border-neutral-200", text: "text-neutral-600" },
        };
        const s = sourceMap[v] || sourceMap.upload;
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold ${s.bg} ${s.border} ${s.text} border`}>
            {s.icon} {s.label}
          </span>
        );
      },
    },
    {
      key: "overall_confidence", label: "AI Conf.",
      render: (v) => v != null ? <ConfidenceMeter value={Math.round(v)} /> : <span className="text-neutral-400">—</span>,
    },
    {
      key: "status", label: "Status",
      render: (v, row) => (
        <div>
          <Badge status={v} />
          {v === "pending_approval" && approvalInfo[row.id] && (
            <div className="text-2xs text-neutral-500 mt-0.5 leading-tight">
              Step {approvalInfo[row.id].stepOrder}/{approvalInfo[row.id].totalSteps}: {approvalInfo[row.id].stepName}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "created_at", label: "Created",
      render: (v) => <span className="text-neutral-500 whitespace-nowrap">{v ? new Date(v).toLocaleDateString() : "—"}</span>,
    },
    {
      key: "document_available", label: "Document",
      render: (available, row) => {
        if (!available) {
          return <span className="text-neutral-400" title="No uploaded file for this invoice">—</span>;
        }
        const busy = docBusy?.id === row.id ? docBusy.mode : null;
        // stopPropagation: these act on the file, not the row (which opens the invoice).
        return (
          <span className="whitespace-nowrap text-2xs" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className={DOC_LINK}
              disabled={!!busy}
              onClick={() => handleDocument(row, "view")}
              title="Open the uploaded invoice in a new tab"
            >
              {busy === "view" ? "Opening…" : "View"}
            </button>
            <span className="text-neutral-300 mx-1.5">&middot;</span>
            <button
              type="button"
              className={DOC_LINK}
              disabled={!!busy}
              onClick={() => handleDocument(row, "download")}
              title="Download the uploaded invoice file"
            >
              {busy === "download" ? "Downloading…" : "Download"}
            </button>
          </span>
        );
      },
    },
  ];

  return (
    <div>
      {/* Just-uploaded banner (batch upload landed here) */}
      {newIds.size > 0 && (
        <div className="bg-success-bg border border-success-base rounded-base px-4 py-2.5 mb-4 flex items-center justify-between">
          <span className="text-2xs text-success-dark font-medium">
            {newIds.size} invoice{newIds.size !== 1 ? "s" : ""} just uploaded as draft{newIds.size !== 1 ? "s" : ""} — highlighted below. Open each to review, then Validate.
            {uploadErrors.length > 0 && (
              <span className="text-danger-dark ml-2">
                {uploadErrors.length} file{uploadErrors.length !== 1 ? "s" : ""} failed: {uploadErrors.map((e) => e.file).join(", ")}
              </span>
            )}
          </span>
          <button onClick={() => setNewIds(new Set())} className="text-success-dark bg-transparent border-none cursor-pointer text-sm">&#10005;</button>
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KpiCard size="lg" label="Total Invoices" value={String(statusCounts.all)} sub="All time" accentColor={tokens.color.brand[500]} icon="📄" />
        <KpiCard size="lg" label="Needs Review" value={String(statusCounts.review)} sub="Draft & pending" accentColor={tokens.color.status.warning.base} icon="👁" />
        <KpiCard size="lg" label="In Approval" value={String(statusCounts.approval)} sub="Pending approval" accentColor={tokens.color.status.pending.base} icon="⏳" />
        <KpiCard size="lg" label="Posted" value={String(statusCounts.posted)} sub={statusCounts.all > 0 ? `${((statusCounts.posted / statusCounts.all) * 100).toFixed(1)}% of total` : "0%"} accentColor={tokens.color.status.success.base} icon="✓" />
        <KpiCard size="lg" label="Exceptions" value={String(statusCounts.exception)} sub="Needs attention" accentColor={tokens.color.status.danger.base} icon="⚠" />
      </div>

      {/* Main Table Card */}
      <Card
        title="Invoice Inbox"
        action={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="xs">&#8595; Export</Button>
            <Button variant="primary" size="xs" onClick={onUpload}>
              &#128228; Upload Invoice
            </Button>
          </div>
        }
        noPad
      >
        <div className="px-5 pt-3">
          <TabBar
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "all", label: "All Invoices", count: statusCounts.all },
              { key: "review", label: "Needs Review", count: statusCounts.review },
              { key: "approval", label: "In Approval", count: statusCounts.approval },
              { key: "exception", label: "Exceptions", count: statusCounts.exception },
              { key: "posted", label: "Posted", count: statusCounts.posted },
            ]}
          />
          <FilterBar
            filters={[
              { type: "search", placeholder: "Search invoice #, vendor, filename...", value: search, onChange: (e) => setSearch(e.target.value) },
              {
                type: "select", value: statusFilter, title: "Filter by status",
                onChange: (e) => setStatusFilter(e.target.value),
                options: [
                  { value: "all", label: "All statuses" },
                  { value: "draft", label: "Draft" },
                  { value: "pending_processing", label: "Processing" },
                  { value: "validated", label: "Validated" },
                  { value: "pending_approval", label: "Pending Approval" },
                  { value: "approved", label: "Approved" },
                  { value: "parked", label: "Parked" },
                  { value: "posted", label: "Posted" },
                  { value: "rejected", label: "Rejected" },
                  { value: "exception", label: "Exception" },
                ],
              },
              { type: "date", value: dateFrom, title: "Created from", onChange: (e) => setDateFrom(e.target.value) },
              { type: "date", value: dateTo, title: "Created to", onChange: (e) => setDateTo(e.target.value) },
              {
                type: "select", value: sortDir, title: "Sort by created date",
                onChange: (e) => setSortDir(e.target.value),
                options: [
                  { value: "desc", label: "Newest first" },
                  { value: "asc", label: "Oldest first" },
                ],
              },
            ]}
          />
        </div>
        {docError && (
          <div className="mx-5 mb-3 bg-danger-bg border border-danger-base rounded-base px-4 py-2.5 flex items-center justify-between">
            <span className="text-2xs text-danger-dark font-medium">{docError}</span>
            <button className="text-neutral-400 hover:text-neutral-600 bg-transparent border-none cursor-pointer text-sm" onClick={() => setDocError(null)}>&times;</button>
          </div>
        )}
        <DataTable
          columns={columns}
          data={paginated}
          // Clicking anywhere on a row opens the invoice, unless the user is
          // selecting text (e.g. copying an invoice number).
          onRowClick={(row) => {
            if (window.getSelection()?.toString()) return;
            onViewInvoice?.(row.id);
          }}
          rowClassName={(row) => (newIds.has(row.id) ? "bg-success-bg/60" : null)}
        />
        <div className="flex items-center justify-between px-5 py-3 text-2xs text-neutral-500">
          <span>Showing {paginated.length} of {filtered.length} invoices</span>
          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1).slice(0, 8).map((p) => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={`w-7 h-7 rounded-base border text-[11px] font-semibold cursor-pointer transition-colors ${
                  p === page
                    ? "border-brand-600 bg-brand-600 text-white"
                    : "border-neutral-200 bg-neutral-0 text-neutral-600 hover:bg-neutral-50"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
