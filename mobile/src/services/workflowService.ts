import apiClient from './api';
import { getToken } from './authService';

// ─── Types ──────────────────────────────────────────────────────

export interface ApprovalAction {
  id: number;
  step_order: number;
  step_name: string;
  approver_id: number | null;
  approver_name: string;
  action: string; // approved, rejected, returned, delegated, skipped
  comments: string | null;
  acted_at: string;
}

export interface ApprovalRequest {
  id: number;
  invoice_id: number;
  workflow_template_id: number;
  current_step_order: number;
  overall_status: string; // pending, in_progress, approved, rejected, cancelled
  initiated_at: string;
  completed_at: string | null;
  actions: ApprovalAction[];
  template_name?: string;
  steps?: WorkflowStep[];
}

export interface WorkflowStep {
  id: number;
  template_id: number;
  step_order: number;
  step_name: string;
  approver_role: string | null;
  approver_user_id: number | null;
  department: string | null;
  is_required: number;
  auto_approve_below: number | null;
  sla_hours: number;
}

export interface PendingApproval {
  approval_request: ApprovalRequest;
  invoice_id: number;
  invoice_number: string | null;
  supplier_name: string | null;
  total_amount: number | null;
  currency: string;
  step_name: string;
  waiting_since: string;
  sla_hours: number;
}

// ─── API Calls ──────────────────────────────────────────────────

/** Get pending approvals for current user */
export async function getPendingApprovals(): Promise<PendingApproval[]> {
  const token = await getToken();
  const { data } = await apiClient.get('/api/approvals/pending', {
    params: { token },
  });
  return data;
}

/** Get approval status for a specific invoice */
export async function getInvoiceApproval(invoiceId: number): Promise<ApprovalRequest | null> {
  try {
    const { data } = await apiClient.get(`/api/approvals/invoice/${invoiceId}`);
    return data;
  } catch {
    return null;
  }
}

/** Initiate approval workflow for an invoice */
export async function initiateApproval(invoiceId: number): Promise<ApprovalRequest | null> {
  const token = await getToken();
  const { data } = await apiClient.post(`/api/approvals/invoice/${invoiceId}/initiate`, null, {
    params: { token },
  });
  return data;
}

/** Perform an approval action (approve/reject/return/delegate) */
export async function performApprovalAction(
  requestId: number,
  action: 'approved' | 'rejected' | 'returned' | 'delegated',
  comments?: string,
): Promise<ApprovalAction> {
  const token = await getToken();
  const { data } = await apiClient.post(`/api/approvals/${requestId}/action`, {
    action,
    comments: comments || null,
  }, {
    params: { token },
  });
  return data;
}

/** Get approval history */
export async function getApprovalHistory(skip = 0, limit = 20): Promise<ApprovalRequest[]> {
  const token = await getToken();
  const { data } = await apiClient.get('/api/approvals/history', {
    params: { token, skip, limit },
  });
  return data;
}
