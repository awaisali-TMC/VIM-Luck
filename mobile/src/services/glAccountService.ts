import apiClient from './api';
import type { GLAccount, GLAssignment } from '../types';

const BASE = '/api/gl-accounts';

/** List GL accounts with optional filters */
export async function getGLAccounts(
  skip = 0,
  limit = 100,
  category?: string,
  search?: string,
): Promise<{ accounts: GLAccount[]; total: number }> {
  const params: Record<string, any> = { skip, limit };
  if (category) params.category = category;
  if (search) params.search = search;
  const { data } = await apiClient.get(BASE, { params });
  return data;
}

/** Create a new GL account */
export async function createGLAccount(payload: {
  code: string;
  name: string;
  category?: string;
  parent_code?: string;
  company_code?: string;
  cost_center?: string;
  description?: string;
}): Promise<GLAccount> {
  const { data } = await apiClient.post(BASE, payload);
  return data;
}

/** Get all GL assignments for an invoice */
export async function getGLAssignments(invoiceId: number): Promise<GLAssignment[]> {
  const { data } = await apiClient.get(`${BASE}/assignments/${invoiceId}`);
  return data;
}

/** Create a GL assignment */
export async function createGLAssignment(payload: {
  invoice_id: number;
  line_item_id?: number | null;
  gl_code: string;
  amount?: number | null;
  cost_center?: string | null;
  assignment_type?: string;
}): Promise<GLAssignment> {
  const { data } = await apiClient.post(`${BASE}/assignments`, payload);
  return data;
}

/** Delete a GL assignment */
export async function deleteGLAssignment(assignmentId: number): Promise<void> {
  await apiClient.delete(`${BASE}/assignments/${assignmentId}`);
}
