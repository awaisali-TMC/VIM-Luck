import { useState, useEffect, useCallback } from "react";
import { getInvoiceApproval, initiateApproval, takeApprovalAction } from "../../services/workflowService";
import Card from "../common/Card";
import Badge from "../common/Badge";
import Button from "../common/Button";
import { useRoleLabel } from "../../config/roleLabels";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function ApprovalProgressCard({ invoiceId, invoiceStatus, currentUser, onStatusChange }) {
  const roleLabel = useRoleLabel();
  const [approvalData, setApprovalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [comments, setComments] = useState("");
  const [error, setError] = useState(null);
  const [showActions, setShowActions] = useState(false);

  const token = currentUser?.token || localStorage.getItem("auth_token");

  const fetchApproval = useCallback(async () => {
    if (!invoiceId) return;
    setLoading(true);
    try {
      const data = await getInvoiceApproval(invoiceId);
      setApprovalData(data);
    } catch {
      setApprovalData(null);
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => { fetchApproval(); }, [fetchApproval]);

  const handleInitiate = async () => {
    setActionLoading(true);
    setError(null);
    try {
      await initiateApproval(invoiceId, token);
      await fetchApproval();
      if (onStatusChange) onStatusChange();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to initiate approval");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAction = async (action) => {
    if (!approvalData?.approval?.id) return;
    setActionLoading(true);
    setError(null);
    try {
      await takeApprovalAction(approvalData.approval.id, action, comments, token);
      setComments("");
      setShowActions(false);
      await fetchApproval();
      if (onStatusChange) onStatusChange();
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to ${action}`);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-neutral-900 mb-3">Approval Workflow</h3>
        <div className="text-center py-4 text-2xs text-neutral-400">Loading...</div>
      </Card>
    );
  }

  // Show initiate button if invoice is validated but no approval yet
  if (invoiceStatus === "validated" && (!approvalData || !approvalData.has_approval)) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-neutral-900 mb-3">Approval Workflow</h3>
        <p className="text-2xs text-neutral-500 mb-3">No approval workflow has been initiated for this invoice.</p>
        <Button size="sm" onClick={handleInitiate} disabled={actionLoading}>
          {actionLoading ? "Initiating..." : "Start Approval Workflow"}
        </Button>
        {error && <p className="text-2xs text-danger-dark mt-2">{error}</p>}
      </Card>
    );
  }

  if (!approvalData?.has_approval) return null;

  const { approval, steps = [] } = approvalData;
  const isInProgress = approval.overall_status === "in_progress";

  // Build a map of step_order → latest action (for showing comments on steps)
  const stepActionMap = {};
  if (approval.actions) {
    for (const a of approval.actions) {
      stepActionMap[a.step_order] = a;
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-neutral-900 m-0">Approval Workflow</h3>
          {approval.workflow_name && (
            <span className="text-2xs text-neutral-500">({approval.workflow_name})</span>
          )}
        </div>
        <Badge status={approval.overall_status} size="xs" />
      </div>

      {/* Steps Progress */}
      <div className="flex items-start gap-0 mb-4">
        {steps.map((step, idx) => {
          const isActive = isInProgress && step.step_order === approval.current_step_order;
          const isDone = step.status === "approved" || step.status === "skipped";
          const isRejected = step.status === "rejected";
          const isReturned = step.status === "returned";

          let dotColor = "bg-neutral-300";
          let lineColor = "bg-neutral-200";
          if (isDone) { dotColor = "bg-emerald-500"; lineColor = "bg-emerald-200"; }
          else if (isRejected) { dotColor = "bg-red-500"; }
          else if (isReturned) { dotColor = "bg-amber-500"; }
          else if (isActive) { dotColor = "bg-blue-500 animate-pulse"; }

          return (
            <div key={step.step_order} className="flex-1 flex flex-col items-center relative">
              {/* Connector line */}
              {idx > 0 && (
                <div className={`absolute top-3 right-1/2 left-0 h-0.5 -translate-y-1/2 ${
                  isDone ? "bg-emerald-200" : "bg-neutral-200"
                }`} style={{ left: "-50%", right: "50%" }} />
              )}
              {/* Dot */}
              <div className={`relative z-10 w-6 h-6 rounded-full ${dotColor} flex items-center justify-center`}>
                {isDone && <span className="text-white text-2xs font-bold">&#10003;</span>}
                {isRejected && <span className="text-white text-2xs font-bold">&#10005;</span>}
                {isReturned && <span className="text-white text-2xs font-bold">&#8617;</span>}
                {isActive && <span className="text-white text-2xs font-bold">{step.step_order}</span>}
                {!isDone && !isRejected && !isReturned && !isActive && (
                  <span className="text-white text-2xs">{step.step_order}</span>
                )}
              </div>
              {/* Label */}
              <div className="text-center mt-1.5">
                <div className={`text-2xs font-semibold ${isActive ? "text-blue-600" : "text-neutral-700"}`}>
                  {step.step_name}
                </div>
                <div className="text-2xs text-neutral-400">{roleLabel(step.approver_role)}</div>
                {step.actor_name && (
                  <div className="text-2xs text-neutral-500 mt-0.5">
                    {step.actor_name} &middot; {timeAgo(step.acted_at)}
                  </div>
                )}
                {(isRejected || isReturned) && stepActionMap[step.step_order]?.comments && (
                  <div className={`text-2xs italic mt-1 px-2 py-1 rounded max-w-[180px] ${
                    isRejected ? "bg-red-50 text-red-600" : "bg-amber-50 text-amber-600"
                  }`}>
                    &ldquo;{stepActionMap[step.step_order].comments}&rdquo;
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Action area — only show if workflow is in progress */}
      {isInProgress && (
        <div className="border-t border-neutral-100 pt-3">
          {!showActions ? (
            <Button size="sm" variant="secondary" onClick={() => setShowActions(true)}>
              Take Action
            </Button>
          ) : (
            <div className="flex flex-col gap-2">
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                placeholder="Add comments (optional)..."
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none resize-none"
                rows={2}
              />
              <div className="flex items-center gap-2">
                <Button size="sm" variant="success" onClick={() => handleAction("approved")} disabled={actionLoading}>
                  {actionLoading ? "..." : "Approve"}
                </Button>
                <Button size="sm" variant="danger" onClick={() => handleAction("rejected")} disabled={actionLoading}>
                  Reject
                </Button>
                <Button size="sm" variant="secondary" onClick={() => handleAction("returned")} disabled={actionLoading}>
                  Return
                </Button>
                <div className="flex-1" />
                <Button size="sm" variant="ghost" onClick={() => setShowActions(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Action history */}
      {approval.actions && approval.actions.length > 0 && (
        <div className="border-t border-neutral-100 pt-3 mt-3">
          <h4 className="text-2xs font-semibold text-neutral-600 mb-2 uppercase">Action History</h4>
          <div className="flex flex-col gap-1.5">
            {approval.actions.map((a) => (
              <div key={a.id} className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2 text-2xs">
                  <Badge status={a.action} size="xs" />
                  <span className="text-neutral-600">
                    Step {a.step_order}: {a.step_name}
                  </span>
                  <span className="text-neutral-500">by {a.approver_name}</span>
                  <span className="text-neutral-400 ml-auto">{timeAgo(a.acted_at)}</span>
                </div>
                {a.comments && (
                  <div className={`ml-8 text-2xs italic px-2 py-1 rounded ${
                    a.action === "rejected"
                      ? "bg-red-50 text-red-600 border-l-2 border-red-400"
                      : a.action === "returned"
                        ? "bg-amber-50 text-amber-600 border-l-2 border-amber-400"
                        : "bg-neutral-50 text-neutral-500 border-l-2 border-neutral-300"
                  }`}>
                    &ldquo;{a.comments}&rdquo;
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <p className="text-2xs text-danger-dark mt-2">{error}</p>}
    </Card>
  );
}
