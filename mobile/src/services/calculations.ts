import type { ExtractedLineItem, ExtractedField } from '../types';

/** Calculate rate = amount / qty, rounded to 2 decimals */
export function calculateRate(amount: number, qty: number): number {
  if (!qty || qty === 0) return 0;
  return Math.round((amount / qty) * 100) / 100;
}

/** Recalculate unit_price for all line items */
export function applyRateToLineItems(items: ExtractedLineItem[]): ExtractedLineItem[] {
  return items.map((li) => {
    const qty = li.quantity ? parseFloat(String(li.quantity)) : 0;
    const amount = li.amount ? parseFloat(String(li.amount)) : 0;
    return {
      ...li,
      unit_price: qty && amount ? calculateRate(amount, qty) : li.unit_price,
    };
  });
}

/** Create a default line item when Document AI returns none */
export function createDefaultLineItem(totalAmount: number): ExtractedLineItem {
  return {
    description: 'N/A',
    quantity: 1,
    unit: null,
    unit_price: totalAmount || 0,
    amount: totalAmount || 0,
  };
}

/** If total_tax_amount == total_amount, set tax to 0 (Document AI misread) */
export function normalizeTax(taxAmount: number, totalAmount: number): number {
  if (taxAmount === totalAmount) return 0;
  return taxAmount;
}

/** Extract total_amount from fields array */
export function getFieldValue(fields: ExtractedField[], fieldName: string): string | undefined {
  return fields.find((f) => f.field_name === fieldName)?.value;
}

/** Process extraction result: apply default line item + rate recalculation */
export function processExtractionResult(result: any): any {
  let lineItems = result.line_items || [];

  // Create default line item if none returned
  if (lineItems.length === 0) {
    const totalRaw = getFieldValue(result.fields || [], 'total_amount');
    const totalAmount = totalRaw ? parseFloat(String(totalRaw).replace(/,/g, '')) : 0;
    lineItems = [createDefaultLineItem(totalAmount)];
  }

  // Recalculate rate for all line items
  lineItems = applyRateToLineItems(lineItems);

  return { ...result, line_items: lineItems };
}

// ─── Status Machine ─────────────────────────────────────────────

const STATUS_TRANSITIONS: Record<string, string[]> = {
  draft: ['pending_processing'],
  pending_processing: ['validated', 'exception'],
  validated: ['pending_approval', 'posted', 'exception'],
  pending_approval: [],  // approval actions handled by ApprovalProgressCard
  approved: ['posted', 'exception'],
  rejected: ['pending_approval', 'pending_processing', 'exception'],
  exception: ['pending_processing', 'validated'],
  posted: [],
};

export interface StatusTransition {
  status: string;
  label: string;
  variant: 'primary' | 'secondary' | 'danger';
}

const TRANSITION_CONFIG: Record<string, { label: string; variant: 'primary' | 'secondary' | 'danger' }> = {
  pending_processing: { label: 'Submit for Processing', variant: 'primary' },
  validated: { label: 'Mark Validated', variant: 'primary' },
  pending_approval: { label: 'Submit for Approval', variant: 'primary' },
  approved: { label: 'Approve', variant: 'primary' },
  rejected: { label: 'Reject', variant: 'danger' },
  posted: { label: 'Post to ERP', variant: 'primary' },
  exception: { label: 'Flag Exception', variant: 'danger' },
  draft: { label: 'Revert to Draft', variant: 'secondary' },
};

// Context-aware label/variant overrides per current status (matches web STATUS_ACTIONS)
const STATUS_ACTION_OVERRIDES: Record<string, Record<string, { label: string; variant: 'primary' | 'secondary' | 'danger' }>> = {
  pending_processing: {
    validated: { label: 'Mark Validated', variant: 'primary' },
    exception: { label: 'Flag Exception', variant: 'danger' },
  },
  validated: {
    pending_approval: { label: 'Submit for Approval', variant: 'primary' },
    posted: { label: 'Post to ERP', variant: 'primary' },
    exception: { label: 'Flag Exception', variant: 'danger' },
  },
  approved: {
    posted: { label: 'Post to ERP', variant: 'primary' },
    exception: { label: 'Flag Exception', variant: 'danger' },
  },
  rejected: {
    pending_approval: { label: 'Resubmit for Approval', variant: 'primary' },
    pending_processing: { label: 'Resubmit for Processing', variant: 'secondary' },
    exception: { label: 'Flag Exception', variant: 'danger' },
  },
  exception: {
    pending_processing: { label: 'Resubmit for Processing', variant: 'primary' },
    validated: { label: 'Mark Validated', variant: 'primary' },
  },
};

export function getAvailableTransitions(currentStatus: string): StatusTransition[] {
  const statuses = STATUS_TRANSITIONS[currentStatus] || [];
  const overrides = STATUS_ACTION_OVERRIDES[currentStatus] || {};
  return statuses.map((s) => ({
    status: s,
    label: overrides[s]?.label || TRANSITION_CONFIG[s]?.label || s,
    variant: overrides[s]?.variant || TRANSITION_CONFIG[s]?.variant || 'secondary',
  }));
}

export function getStatusLabel(status: string): string {
  // Labels mirror the web Badge (STATUS_CONFIG) so the two apps read identically.
  const labels: Record<string, string> = {
    draft: 'Draft',
    pending: 'Pending',
    pending_processing: 'Processing',
    matching: 'In Matching',
    validated: 'Validated',
    submitted: 'Submitted',
    pending_approval: 'Pending Approval',
    approved: 'Approved',
    parked: 'Parked',
    posted: 'ERP Posting',
    exception: 'Exception',
    rejected: 'Rejected',
  };
  return labels[status] || status;
}

export function getStatusAction(targetStatus: string): string {
  const actions: Record<string, string> = {
    pending_processing: 'Submit for Processing',
    validated: 'Mark Validated',
    pending_approval: 'Submit for Approval',
    approved: 'Approve',
    rejected: 'Reject',
    posted: 'Post to ERP',
    exception: 'Flag Exception',
    draft: 'Revert to Draft',
  };
  return actions[targetStatus] || targetStatus;
}
