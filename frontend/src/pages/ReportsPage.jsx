import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Badge from "../components/common/Badge";
import DataTable from "../components/common/DataTable";
import {
  FilterDropdown,
  DateRangeFilter,
  AmountRangeFilter,
} from "../components/common/FilterControls";
import StatusDonut from "../components/reports/StatusDonut";
import RankBarList from "../components/reports/RankBarList";
import { resolveDateRange } from "../utils/dateRange";
import { STATUS_COLORS } from "../utils/statusColors";
import { tokens } from "../styles/tokens";
import {
  getReportFilters,
  getReportSummary,
  getReportInvoices,
  downloadReportExport,
} from "../services/reportsService";

const PAGE_SIZE = 25;

const fmtInt = (n) => Number(n || 0).toLocaleString();
const fmtMoney = (n) => `PKR ${Math.round(Number(n || 0)).toLocaleString()}`;

export default function ReportsPage() {
  const navigate = useNavigate();

  // Filter option lists (populate the dropdowns).
  const [options, setOptions] = useState(null);

  // Filter state.
  const [dateRange, setDateRange] = useState({ preset: "90", date_from: null, date_to: null });
  const [vendor, setVendor] = useState(null);
  const [supplierId, setSupplierId] = useState(null);
  const [statusSel, setStatusSel] = useState([]);
  const [pendingWith, setPendingWith] = useState(null);
  const [sourceSel, setSourceSel] = useState([]);
  const [amount, setAmount] = useState({ min: "", max: "" });
  const [sapStatus, setSapStatus] = useState(null);
  const [groupBySupplier, setGroupBySupplier] = useState(false);

  // Data.
  const [summary, setSummary] = useState(null);
  const [table, setTable] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [page, setPage] = useState(1);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(true);
  const [exporting, setExporting] = useState(null);

  const { date_from, date_to } = resolveDateRange(dateRange);

  const filters = useMemo(
    () => ({
      date_from,
      date_to,
      vendor,
      supplier_id: supplierId,
      status: statusSel,
      pending_with: pendingWith,
      source: sourceSel,
      amount_min: amount.min,
      amount_max: amount.max,
      sap_status: sapStatus,
    }),
    [date_from, date_to, vendor, supplierId, statusSel, pendingWith, sourceSel, amount.min, amount.max, sapStatus]
  );

  // Load filter options once.
  useEffect(() => {
    getReportFilters().then(setOptions).catch(() => setOptions({}));
  }, []);

  // Fetch summary whenever filters change.
  useEffect(() => {
    let alive = true;
    setSummaryLoading(true);
    getReportSummary(filters)
      .then((d) => alive && setSummary(d))
      .catch(() => {})
      .finally(() => alive && setSummaryLoading(false));
    return () => { alive = false; };
  }, [filters]);

  // Reset to page 1 when the filters or grouping change.
  useEffect(() => { setPage((p) => (p === 1 ? p : 1)); }, [filters, groupBySupplier]);

  // Fetch the invoice table for the current filters + page. Grouped view uses
  // a larger page so suppliers rarely split across page boundaries.
  useEffect(() => {
    let alive = true;
    setTableLoading(true);
    getReportInvoices(
      filters,
      page,
      groupBySupplier ? 200 : PAGE_SIZE,
      groupBySupplier ? "supplier" : "date"
    )
      .then((d) => alive && setTable(d))
      .catch(() => {})
      .finally(() => alive && setTableLoading(false));
    return () => { alive = false; };
  }, [filters, page, groupBySupplier]);

  const anyActive =
    !!vendor || !!supplierId || statusSel.length > 0 || !!pendingWith ||
    sourceSel.length > 0 || amount.min !== "" || amount.max !== "" ||
    !!sapStatus || dateRange.preset !== "90";

  const clearAll = useCallback(() => {
    setVendor(null);
    setSupplierId(null);
    setStatusSel([]);
    setPendingWith(null);
    setSourceSel([]);
    setAmount({ min: "", max: "" });
    setSapStatus(null);
    setDateRange({ preset: "90", date_from: null, date_to: null });
  }, []);

  const exportFile = async (fmt) => {
    setExporting(fmt);
    try {
      // Export mirrors the on-screen view: grouped by supplier when toggled.
      await downloadReportExport(filters, fmt, groupBySupplier ? "supplier" : "date");
    } catch {
      /* ignore */
    } finally {
      setExporting(null);
    }
  };

  // Dropdown option shapes.
  const vendorOpts = (options?.vendors || []).map((v) => ({ value: v.value, label: v.value, count: v.count }));
  const supplierOpts = options?.supplier_accounts || [];
  const statusOpts = (options?.statuses || []).map((s) => ({ ...s, dot: STATUS_COLORS[s.value] }));
  const approverOpts = options?.approvers || [];
  const sourceOpts = options?.sources || [];
  const sapOpts = options?.sap_statuses || [];

  const kpis = summary?.kpis || {};

  // Per-supplier count/subtotal for the grouped table headers (current page).
  const groupStats = useMemo(() => {
    if (!groupBySupplier) return {};
    const m = {};
    for (const it of table.items) {
      const k = it.supplier_name || "Unknown supplier";
      if (!m[k]) m[k] = { count: 0, amount: 0 };
      m[k].count += 1;
      m[k].amount += Number(it.total_amount || 0);
    }
    return m;
  }, [groupBySupplier, table.items]);

  const vendorColumns = [
    { key: "supplier_name", label: "Vendor", render: (v) => v || "—" },
    { key: "count", label: "Invoices", align: "right", render: (v) => <span className="tabular-nums text-neutral-700">{fmtInt(v)}</span> },
    { key: "amount", label: "Total Value", align: "right", render: (v) => <span className="font-mono text-xs font-semibold text-neutral-900 whitespace-nowrap">{fmtMoney(v)}</span> },
  ];

  const invoiceColumns = [
    {
      key: "id", label: "#",
      // A real button, so the invoice opens from the keyboard too (the row
      // click replaced the eye icon).
      render: (v) => (
        <button
          type="button"
          className="text-brand-600 font-semibold cursor-pointer hover:underline whitespace-nowrap bg-transparent border-none p-0"
          onClick={(e) => { e.stopPropagation(); navigate(`/invoices/${v}`); }}
          title="Open invoice"
        >
          #{v}
        </button>
      ),
    },
    {
      key: "invoice_number", label: "Invoice Reference",
      // The scanned document's filename sits under the reference so a row
      // tracks: scanned file → status → SAP document number.
      render: (v, row) => (
        <span className="whitespace-nowrap">
          <span className="font-medium text-neutral-800 block">
            {v || <span className="text-neutral-400 italic font-normal">—</span>}
          </span>
          {row.original_filename && (
            <span className="block text-2xs text-neutral-400 max-w-[190px] truncate" title={row.original_filename}>
              {row.original_filename}
            </span>
          )}
        </span>
      ),
    },
    { key: "supplier_name", label: "Vendor", render: (v) => v || "—" },
    {
      key: "status", label: "Status",
      render: (v, row) => <Badge status={v} label={row.status_label} />,
    },
    {
      key: "pending_with", label: "Pending With",
      render: (v) => v ? <span className="text-2xs text-warning-dark font-medium">{v}</span> : <span className="text-neutral-300">—</span>,
    },
    {
      key: "sap_document_number", label: "SAP Doc #",
      render: (v, row) => v ? (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <span className="font-mono text-xs text-neutral-900" title={row.sap_fiscal_year ? `Fiscal year ${row.sap_fiscal_year}` : undefined}>
            {v}
          </span>
          {row.sap_doc_status && <Badge status={row.sap_doc_status} label={row.sap_status_label} size="xs" />}
        </span>
      ) : (
        <span className="text-neutral-300">—</span>
      ),
    },
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
      render: (_, row) => <span className="text-2xs text-neutral-500">{row.source_label}</span>,
    },
    {
      key: "created_at", label: "Received",
      render: (v) => <span className="text-neutral-500 whitespace-nowrap">{v ? new Date(v).toLocaleDateString() : "—"}</span>,
    },
  ];

  const period = summary?.period;
  const periodText = period
    ? `${new Date(period.from).toLocaleDateString()} – ${new Date(period.to).toLocaleDateString()}`
    : "";

  return (
    <div>
      {/* Filters */}
      <Card
        title="Filters"
        overflowVisible
        subtitle={periodText ? `Reporting period: ${periodText}` : undefined}
        action={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="xs" disabled={exporting} onClick={() => exportFile("csv")}>
              {exporting === "csv" ? "Exporting…" : "⬇ CSV"}
            </Button>
            <Button variant="secondary" size="xs" disabled={exporting} onClick={() => exportFile("xlsx")}>
              {exporting === "xlsx" ? "Exporting…" : "⬇ Excel"}
            </Button>
          </div>
        }
        className="mb-5"
      >
        <div className="flex flex-wrap items-start gap-2.5">
          <FilterDropdown label="Vendor" searchable options={vendorOpts} value={vendor} onChange={setVendor} placeholder="All vendors" />
          <FilterDropdown label="Supplier account" searchable options={supplierOpts} value={supplierId} onChange={setSupplierId} placeholder="All accounts" />
          <FilterDropdown label="Status" multiple options={statusOpts} value={statusSel} onChange={setStatusSel} placeholder="All statuses" />
          <FilterDropdown label="Pending with" options={approverOpts} value={pendingWith} onChange={setPendingWith} placeholder="Anyone" />
          <FilterDropdown label="Source" multiple options={sourceOpts} value={sourceSel} onChange={setSourceSel} placeholder="All sources" />
          <FilterDropdown label="SAP" options={sapOpts} value={sapStatus} onChange={setSapStatus} placeholder="Any" />
          <DateRangeFilter value={dateRange} onChange={setDateRange} />
          <AmountRangeFilter value={amount} onChange={setAmount} />
          {anyActive && (
            <button
              type="button"
              onClick={clearAll}
              className="self-center mt-4 inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-800 bg-transparent border-none cursor-pointer px-1.5 py-1"
            >
              ✕ Clear all
            </button>
          )}
        </div>
      </Card>

      {/* Filtered-set summary strip — scoped to the filters, not a dashboard.
          The status donut below carries the per-status detail. */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 bg-neutral-0 border border-neutral-100 rounded-md shadow-xs px-5 py-3 mb-5">
        {summaryLoading && !summary ? (
          <span className="text-xs text-neutral-400">Loading summary…</span>
        ) : (
          <>
            <span className="text-sm font-bold text-neutral-900">
              {fmtInt(kpis.total_invoices)} invoice{Number(kpis.total_invoices) === 1 ? "" : "s"}
            </span>
            <span className="text-sm font-semibold font-mono text-neutral-900">{fmtMoney(kpis.total_value)}</span>
            {(summary?.by_status || []).map((s) => (
              <span key={s.status} className="inline-flex items-center gap-1.5 text-xs text-neutral-500">
                <span className="w-2 h-2 rounded-sm" style={{ background: STATUS_COLORS[s.status] }} />
                {fmtInt(s.count)} {s.label}
              </span>
            ))}
          </>
        )}
      </div>

      {/* Status breakdown + pending-by-approver */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-5">
        <Card title="Status breakdown" subtitle="Distribution across the filtered set">
          <StatusDonut data={summary?.by_status || []} />
        </Card>
        <Card title="Pending approvals" subtitle="Invoices awaiting each approver role">
          <RankBarList
            items={summary?.pending_by_approver || []}
            accent={tokens.color.status.warning.base}
            empty="No invoices pending approval"
          />
        </Card>
      </div>

      {/* Top vendors */}
      <Card title="Top vendors by value" subtitle="Highest-value vendors in the filtered set" className="mb-5" noPad>
        {(summary?.top_vendors || []).length === 0 ? (
          <div className="py-10 text-center text-xs text-neutral-400">No vendor data for these filters</div>
        ) : (
          <DataTable columns={vendorColumns} data={summary.top_vendors} />
        )}
      </Card>

      {/* Filtered invoices */}
      <Card
        title="Invoices"
        subtitle={`${fmtInt(table.total)} result${table.total !== 1 ? "s" : ""}`}
        action={
          <label className="flex items-center gap-2 text-xs text-neutral-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={groupBySupplier}
              onChange={(e) => setGroupBySupplier(e.target.checked)}
              className="accent-brand-600 cursor-pointer"
            />
            Group by supplier
          </label>
        }
        noPad
      >
        {tableLoading && table.items.length === 0 ? (
          <div className="py-12 text-center text-xs text-neutral-500">Loading invoices…</div>
        ) : table.items.length === 0 ? (
          <div className="py-12 text-center text-xs text-neutral-400">No invoices match these filters</div>
        ) : (
          <>
            <DataTable
              columns={groupBySupplier ? invoiceColumns.filter((c) => c.key !== "supplier_name") : invoiceColumns}
              data={table.items}
              // The whole row opens the invoice, unless text is being selected.
              onRowClick={(row) => {
                if (window.getSelection()?.toString()) return;
                navigate(`/invoices/${row.id}`);
              }}
              groupKey={groupBySupplier ? (row) => row.supplier_name || "Unknown supplier" : undefined}
              renderGroupHeader={
                groupBySupplier
                  ? (key) => {
                      const g = groupStats[key] || { count: 0, amount: 0 };
                      return (
                        <span className="flex items-baseline gap-3">
                          <span className="text-xs font-semibold text-neutral-800">{key}</span>
                          <span className="text-2xs text-neutral-500">
                            {g.count} invoice{g.count !== 1 ? "s" : ""} · {fmtMoney(g.amount)}
                          </span>
                        </span>
                      );
                    }
                  : undefined
              }
            />
            {table.pages > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-neutral-100">
                <span className="text-2xs text-neutral-500">
                  Page {table.page} of {table.pages}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 text-xs rounded-base border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed bg-neutral-0 cursor-pointer"
                  >
                    ‹ Prev
                  </button>
                  {Array.from({ length: Math.min(table.pages, 8) }, (_, i) => i + 1).map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setPage(n)}
                      className={`min-w-[30px] px-2 py-1 text-xs rounded-base border cursor-pointer ${
                        n === table.page
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-neutral-200 bg-neutral-0 text-neutral-600 hover:bg-neutral-50"
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                  <button
                    type="button"
                    disabled={page >= table.pages}
                    onClick={() => setPage((p) => Math.min(table.pages, p + 1))}
                    className="px-2.5 py-1 text-xs rounded-base border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed bg-neutral-0 cursor-pointer"
                  >
                    Next ›
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
