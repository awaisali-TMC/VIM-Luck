import { useState, useEffect, useCallback } from "react";
import { getPendingApprovals, takeApprovalAction, getApprovalHistory } from "../services/workflowService";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Badge from "../components/common/Badge";
import KpiCard from "../components/common/KpiCard";
import Modal from "../components/common/Modal";

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

function formatCurrency(amount, currency = "PKR") {
  if (amount == null) return "—";
  return `${currency} ${Number(amount).toLocaleString()}`;
}

export default function MyApprovalsPage({ currentUser, onViewInvoice }) {
  const [tab, setTab] = useState("pending");
  const [pending, setPending] = useState([]);
  const [history, setHistory] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [actionModal, setActionModal] = useState(null); // { approval, action }
  const [comments, setComments] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const token = currentUser?.token || localStorage.getItem("auth_token");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "pending") {
        const data = await getPendingApprovals(token);
        setPending(data.approvals || []);
        setCounts(data.counts || {});
      } else {
        const statusFilter = tab === "all" ? undefined : tab;
        const data = await getApprovalHistory({ status: statusFilter, limit: 50 });
        setHistory(data.history || []);
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, [tab, token]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleAction = async (action) => {
    if (!actionModal) return;
    setActionLoading(true);
    setError(null);
    try {
      await takeApprovalAction(actionModal.approval.id, action, comments, token);
      const invoiceId = actionModal.approval.invoice_id;
      setActionModal(null);
      setComments("");
      if (onViewInvoice && invoiceId) {
        onViewInvoice(invoiceId);
      } else {
        fetchData();
      }
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${action}`);
    } finally {
      setActionLoading(false);
    }
  };

  const tabs = [
    { key: "pending", label: "Pending", count: counts.pending },
    { key: "approved", label: "Approved" },
    { key: "rejected", label: "Rejected" },
    { key: "all", label: "All History" },
  ];

  const items = tab === "pending" ? pending : history;

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <KpiCard
          label="Pending (Mine)"
          value={counts.pending || 0}
          icon="⏳"
          accentColor="#F59E0B"
        />
        <KpiCard
          label="Approved Today"
          value={counts.approved_today || 0}
          icon="✅"
          accentColor="#10B981"
        />
        <KpiCard
          label="Rejected Today"
          value={counts.rejected_today || 0}
          icon="❌"
          accentColor="#EF4444"
        />
      </div>

      {/* Tabs */}
      <Card>
        <div className="flex items-center gap-1 border-b border-neutral-100 mb-4">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer bg-transparent ${
                tab === t.key
                  ? "border-brand-500 text-brand-600"
                  : "border-transparent text-neutral-500 hover:text-neutral-700"
              }`}
            >
              {t.label}
              {t.count != null && (
                <span className="ml-1.5 bg-danger-base text-white text-2xs font-bold px-1.5 py-px rounded-full">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {error && (
          <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-3 text-2xs text-danger-dark">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-8 text-xs text-neutral-500">Loading...</div>
        ) : items.length === 0 ? (
          <div className="text-center py-8 text-xs text-neutral-400">
            {tab === "pending" ? "No pending approvals" : "No history found"}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-neutral-100">
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Invoice</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Supplier</th>
                  <th className="text-right py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Amount</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Step</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Status</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">When</th>
                  {tab === "pending" && (
                    <th className="text-right py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-neutral-50 hover:bg-neutral-25 transition-colors cursor-pointer"
                    onClick={() => onViewInvoice && onViewInvoice(item.invoice_id)}
                  >
                    <td className="py-2.5 px-3 font-medium text-brand-600">
                      {item.invoice_number || `#${item.invoice_id}`}
                    </td>
                    <td className="py-2.5 px-3 text-neutral-700">{item.supplier_name || "—"}</td>
                    <td className="py-2.5 px-3 text-right font-medium text-neutral-900">
                      {formatCurrency(item.total_amount, item.currency)}
                    </td>
                    <td className="py-2.5 px-3 text-neutral-600">
                      {item.current_step_name || `Step ${item.current_step_order}/${item.total_steps}`}
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge status={item.overall_status} size="xs" />
                    </td>
                    <td className="py-2.5 px-3 text-neutral-400">
                      {timeAgo(item.initiated_at)}
                    </td>
                    {tab === "pending" && (
                      <td className="py-2.5 px-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="success"
                            size="xs"
                            onClick={() => { setActionModal({ approval: item, action: "approved" }); setComments(""); }}
                          >
                            Approve
                          </Button>
                          <Button
                            variant="danger"
                            size="xs"
                            onClick={() => { setActionModal({ approval: item, action: "rejected" }); setComments(""); }}
                          >
                            Reject
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Action Modal */}
      {actionModal && (
        <Modal
          open={true}
          title={`${actionModal.action === "approved" ? "Approve" : "Reject"} — ${
            actionModal.approval.invoice_number || `Invoice #${actionModal.approval.invoice_id}`
          }`}
          onClose={() => setActionModal(null)}
        >
          <div className="flex flex-col gap-3">
            <div className="text-xs text-neutral-600">
              <strong>Supplier:</strong> {actionModal.approval.supplier_name || "—"}<br />
              <strong>Amount:</strong> {formatCurrency(actionModal.approval.total_amount, actionModal.approval.currency)}<br />
              <strong>Step:</strong> {actionModal.approval.current_step_name || `Step ${actionModal.approval.current_step_order}`}
            </div>
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">Comments</label>
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none resize-none"
                rows={3}
                placeholder={`Reason for ${actionModal.action === "approved" ? "approval" : "rejection"}...`}
              />
            </div>
            {error && <p className="text-2xs text-danger-dark">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setActionModal(null)}>Cancel</Button>
              <Button
                variant={actionModal.action === "approved" ? "success" : "danger"}
                size="sm"
                onClick={() => handleAction(actionModal.action)}
                disabled={actionLoading}
              >
                {actionLoading
                  ? "Processing..."
                  : actionModal.action === "approved"
                  ? "Confirm Approve"
                  : "Confirm Reject"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
