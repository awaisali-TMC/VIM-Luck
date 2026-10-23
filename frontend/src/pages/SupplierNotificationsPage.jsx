import { useState, useEffect } from "react";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import api from "../services/api";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

const STATUS_EVENTS = {
  draft: { icon: "📝", text: "Invoice created as draft", color: "#94A3B8" },
  pending_processing: { icon: "⏳", text: "Submitted for AI processing", color: "#F59E0B" },
  validated: { icon: "✅", text: "AI validation complete", color: "#3B82F6" },
  pending_approval: { icon: "🔄", text: "Sent for approval", color: "#8B5CF6" },
  approved: { icon: "✅", text: "Invoice approved", color: "#10B981" },
  rejected: { icon: "❌", text: "Invoice rejected", color: "#EF4444" },
  exception: { icon: "⚠️", text: "Exception flagged — action needed", color: "#EF4444" },
  posted: { icon: "📮", text: "Posted to ERP system", color: "#059669" },
};

export default function SupplierNotificationsPage({ user, onViewInvoice }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get("/api/invoices/", { params: { skip: 0, limit: 50 } });
        setInvoices(data.data.invoices || []);
      } catch {
        setInvoices([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Generate notification-style events from invoice statuses
  const events = invoices.map((inv) => {
    const evt = STATUS_EVENTS[inv.status] || STATUS_EVENTS.draft;
    return {
      id: inv.id,
      invoiceNumber: inv.invoice_number || `#${inv.id}`,
      supplierName: inv.supplier_name,
      amount: inv.total_amount,
      currency: inv.currency || "PKR",
      status: inv.status,
      icon: evt.icon,
      text: evt.text,
      color: evt.color,
      date: inv.created_at,
    };
  });

  // Separate by action needed
  const actionNeeded = events.filter((e) => ["exception", "rejected"].includes(e.status));
  const inProgress = events.filter((e) => ["pending_processing", "validated", "pending_approval"].includes(e.status));
  const completed = events.filter((e) => ["approved", "posted"].includes(e.status));

  return (
    <div className="flex flex-col gap-5">
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-danger-bg border border-danger-base rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">&#9888;</span>
            <span className="text-xs font-bold text-danger-dark">Action Needed</span>
          </div>
          <div className="text-2xl font-bold text-danger-dark">{actionNeeded.length}</div>
          <div className="text-2xs text-danger-dark opacity-70">Invoices requiring your attention</div>
        </div>
        <div className="bg-warning-bg border border-warning-base rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">&#128260;</span>
            <span className="text-xs font-bold text-warning-dark">In Progress</span>
          </div>
          <div className="text-2xl font-bold text-warning-dark">{inProgress.length}</div>
          <div className="text-2xs text-warning-dark opacity-70">Being processed or awaiting approval</div>
        </div>
        <div className="bg-success-bg border border-success-base rounded-lg p-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">&#9989;</span>
            <span className="text-xs font-bold text-success-dark">Completed</span>
          </div>
          <div className="text-2xl font-bold text-success-dark">{completed.length}</div>
          <div className="text-2xs text-success-dark opacity-70">Approved or posted</div>
        </div>
      </div>

      {/* Action needed section */}
      {actionNeeded.length > 0 && (
        <Card>
          <h3 className="text-xs font-bold text-danger-dark mb-3 flex items-center gap-2">
            <span>&#9888;</span> Action Required
          </h3>
          {actionNeeded.map((evt) => (
            <div
              key={evt.id}
              onClick={() => onViewInvoice && onViewInvoice(evt.id)}
              className="flex items-center gap-4 p-3 mb-2 bg-danger-bg/50 border border-danger-base/30 rounded-lg cursor-pointer hover:bg-danger-bg transition-colors"
            >
              <span className="text-lg">{evt.icon}</span>
              <div className="flex-1">
                <div className="text-xs font-semibold text-neutral-900">
                  {evt.invoiceNumber} — {evt.text}
                </div>
                <div className="text-2xs text-neutral-500 mt-0.5">
                  {evt.supplierName || "Unknown"} &middot;{" "}
                  {evt.currency} {Number(evt.amount || 0).toLocaleString()} &middot;{" "}
                  {timeAgo(evt.date)}
                </div>
              </div>
              <Badge status={evt.status} size="xs" />
            </div>
          ))}
        </Card>
      )}

      {/* All invoices timeline */}
      <Card>
        <h3 className="text-xs font-bold text-neutral-800 mb-3">Invoice Status Tracker</h3>
        {loading ? (
          <div className="text-center py-8 text-2xs text-neutral-400">Loading...</div>
        ) : events.length === 0 ? (
          <div className="text-center py-8 text-2xs text-neutral-400">No invoices yet</div>
        ) : (
          <div className="flex flex-col">
            {events.map((evt, i) => (
              <div
                key={evt.id}
                onClick={() => onViewInvoice && onViewInvoice(evt.id)}
                className="flex items-start gap-3 py-3 cursor-pointer hover:bg-neutral-25 rounded-lg px-2 transition-colors"
              >
                {/* Timeline dot + line */}
                <div className="flex flex-col items-center flex-shrink-0">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: evt.color }}
                  />
                  {i < events.length - 1 && (
                    <div className="w-px h-8 bg-neutral-200 mt-1" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-neutral-800">
                      {evt.invoiceNumber}
                    </span>
                    <Badge status={evt.status} size="xs" />
                    <span className="text-2xs text-neutral-400 ml-auto">{timeAgo(evt.date)}</span>
                  </div>
                  <div className="text-2xs text-neutral-500 mt-0.5">{evt.text}</div>
                  <div className="text-2xs text-neutral-400 mt-0.5">
                    {evt.currency} {Number(evt.amount || 0).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
