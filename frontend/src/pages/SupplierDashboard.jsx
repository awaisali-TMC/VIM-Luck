import { useState, useEffect } from "react";
import { getInvoices } from "../services/invoiceService";
import KpiCard from "../components/common/KpiCard";
import Badge from "../components/common/Badge";
import { tokens } from "../styles/tokens";

const STATUS_LABELS = {
  draft: "Received",
  pending_processing: "Under Review",
  validated: "Approved",
  posted: "ERP Posted",
  exception: "Requires Action",
};

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-full bg-brand-50 flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
        </svg>
      </div>
      <p className="text-sm font-semibold text-neutral-700 mb-1">No invoices submitted yet</p>
      <p className="text-xs text-neutral-400">Upload your first invoice to get started</p>
    </div>
  );
}

function StatusTimeline({ status }) {
  const steps = [
    { key: "draft", label: "Received" },
    { key: "pending_processing", label: "Under Review" },
    { key: "validated", label: "Approved" },
    { key: "posted", label: "ERP Posted" },
  ];

  const isException = status === "exception";
  const currentIdx = isException ? 1 : steps.findIndex((s) => s.key === status);

  return (
    <div className="flex items-center gap-0">
      {steps.map((step, i) => {
        const isDone = !isException && i <= currentIdx;
        const isCurrent = !isException && i === currentIdx;
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold transition-colors ${
                  isDone
                    ? isCurrent
                      ? "bg-brand-500 text-white"
                      : "bg-success-base text-white"
                    : "bg-neutral-200 text-neutral-400"
                }`}
              >
                {isDone && !isCurrent ? "✓" : i + 1}
              </div>
              <span className={`text-[9px] mt-1 whitespace-nowrap font-medium ${isDone ? "text-neutral-700" : "text-neutral-400"}`}>
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className={`w-8 h-px mb-4 mx-0.5 ${i < currentIdx && !isException ? "bg-success-base" : "bg-neutral-200"}`} />
            )}
          </div>
        );
      })}
      {isException && (
        <div className="ml-3 flex flex-col items-center">
          <div className="w-5 h-5 rounded-full bg-danger-base flex items-center justify-center text-white text-[10px] font-bold">!</div>
          <span className="text-[9px] mt-1 text-danger-dark font-medium">Action Needed</span>
        </div>
      )}
    </div>
  );
}

export default function SupplierDashboard({ user, onUpload, onViewInvoice }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await getInvoices(0, 100);
        setInvoices(data.invoices || []);
      } catch {
        setInvoices([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const counts = invoices.reduce(
    (acc, inv) => {
      acc.total++;
      if (inv.status === "draft" || inv.status === "pending_processing") acc.pending++;
      if (inv.status === "validated" || inv.status === "posted") acc.approved++;
      if (inv.status === "exception") acc.exception++;
      return acc;
    },
    { total: 0, pending: 0, approved: 0, exception: 0 }
  );

  const totalValue = invoices.reduce((sum, inv) => sum + (inv.total_amount || 0), 0);

  const fmt = (n) =>
    n >= 1_000_000
      ? `PKR ${(n / 1_000_000).toFixed(1)}M`
      : n >= 1_000
      ? `PKR ${(n / 1_000).toFixed(0)}K`
      : `PKR ${n.toFixed(0)}`;

  const fmtDate = (s) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return s;
    }
  };

  return (
    <div>
      {/* Welcome banner */}
      <div
        className="rounded-lg px-6 py-5 mb-6 flex items-center justify-between"
        style={{
          background: "linear-gradient(135deg, #1a1d27 0%, #2f35cc 100%)",
        }}
      >
        <div>
          <h2 className="text-xl font-bold text-white mb-1">
            Welcome back, {user?.name || "Supplier"}
          </h2>
          <p className="text-sm text-blue-200 opacity-80">
            Track your invoice submissions and payment status in real time.
          </p>
        </div>
        <button
          onClick={onUpload}
          className="flex items-center gap-2 bg-white text-brand-700 text-sm font-semibold px-5 py-2.5 rounded-lg shadow-sm hover:bg-brand-50 transition-colors cursor-pointer border-none"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          Upload Invoice
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard
          size="lg"
          label="Total Submitted"
          value={String(counts.total)}
          sub={`${fmt(totalValue)} total value`}
          accentColor={tokens.color.brand[500]}
          icon="📄"
        />
        <KpiCard
          size="lg"
          label="Under Review"
          value={String(counts.pending)}
          sub="Being processed"
          accentColor={tokens.color.status.info.base}
          icon="🔍"
        />
        <KpiCard
          size="lg"
          label="Approved"
          value={String(counts.approved)}
          sub="Validated & posted"
          accentColor={tokens.color.status.success.base}
          icon="✓"
        />
        <KpiCard
          size="lg"
          label="Requires Action"
          value={String(counts.exception)}
          sub={counts.exception > 0 ? "Needs your attention" : "All clear"}
          accentColor={counts.exception > 0 ? tokens.color.status.danger.base : tokens.color.status.success.base}
          icon="⚠"
        />
      </div>

      {/* Recent Submissions */}
      <div className="bg-neutral-0 border border-neutral-100 rounded-lg shadow-xs">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900">My Submissions</h3>
            <p className="text-xs text-neutral-400 mt-0.5">All invoices you have submitted</p>
          </div>
          <button
            onClick={onUpload}
            className="flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100 px-3 py-1.5 rounded-md cursor-pointer border-none transition-colors"
          >
            + New Invoice
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <svg className="w-6 h-6 text-brand-400 animate-spin" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
        ) : invoices.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-neutral-25 border-b border-neutral-100">
                  {["Invoice #", "Supplier", "Date", "Amount", "Status", "Progress", ""].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {invoices.map((inv) => (
                  <tr
                    key={inv.id}
                    className="hover:bg-neutral-25 transition-colors group"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-neutral-800 whitespace-nowrap">
                      {inv.invoice_number || `#${inv.id}`}
                    </td>
                    <td className="px-4 py-3 text-neutral-600 max-w-[160px] truncate">
                      {inv.supplier_name || "—"}
                    </td>
                    <td className="px-4 py-3 text-neutral-500 whitespace-nowrap">
                      {fmtDate(inv.invoice_date || inv.created_at)}
                    </td>
                    <td className="px-4 py-3 font-semibold text-neutral-800 whitespace-nowrap">
                      {inv.total_amount != null
                        ? `PKR ${Number(inv.total_amount).toLocaleString()}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <Badge status={inv.status} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusTimeline status={inv.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => onViewInvoice(inv.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-brand-600 hover:text-brand-700 font-semibold text-xs bg-brand-50 hover:bg-brand-100 px-3 py-1 rounded cursor-pointer border-none"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Help section */}
      {!loading && invoices.length > 0 && counts.exception > 0 && (
        <div className="mt-4 bg-danger-bg border border-danger-light rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-lg mt-0.5">⚠️</span>
          <div>
            <p className="text-sm font-semibold text-danger-dark mb-0.5">
              {counts.exception} invoice{counts.exception > 1 ? "s require" : " requires"} your attention
            </p>
            <p className="text-xs text-danger-dark opacity-70">
              One or more invoices have exceptions that need to be resolved. Please review the details and contact your AP team if needed.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
