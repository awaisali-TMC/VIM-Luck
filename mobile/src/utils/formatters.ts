/** Format a number as currency with 2 decimals */
export function fmtAmount(value: number | string | null | undefined): string {
  if (value == null) return '—';
  const num = typeof value === 'string' ? parseFloat(value.replace(/,/g, '')) : value;
  if (isNaN(num)) return '—';
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Format a number with locale grouping */
export function fmtNum(value: number | null | undefined): string {
  if (value == null) return '—';
  return Number(value).toLocaleString();
}

/** Format date string for display */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  // Try parsing ISO or common date formats
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Format file size */
export function fmtFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Confidence tier for color coding */
export function confTier(confidence: number | null | undefined): 'high' | 'medium' | 'low' | null {
  if (confidence == null) return null;
  if (confidence >= 85) return 'high';
  if (confidence >= 60) return 'medium';
  return 'low';
}

/** Supplier field names to filter */
export const SUPPLIER_FIELD_NAMES = new Set([
  'supplier_name',
  'supplier_tax_id',
  'supplier_address',
  'supplier_phone',
]);

/** Preferred display order for invoice fields */
export const FIELD_ORDER = [
  'document_type',
  'invoice_id',
  'invoice_number',
  'invoice_date',
  'due_date',
  'payment_terms',
  'purchase_order',
  'receiver_name',
  'receiver_address',
  'currency',
  'net_amount',
  'subtotal',
  'total_tax_amount',
  'tax_amount',
  'gst_amount',
  'wht_amount',
  'total_amount',
];

/** Human-readable field labels */
export function fieldLabel(fieldName: string): string {
  const labels: Record<string, string> = {
    invoice_number: 'Invoice Number',
    invoice_date: 'Invoice Date',
    due_date: 'Due Date',
    supplier_name: 'Supplier Name',
    supplier_tax_id: 'NTN / Tax ID',
    supplier_address: 'Supplier Address',
    supplier_phone: 'Phone',
    receiver_name: 'Receiver',
    receiver_address: 'Receiver Address',
    currency: 'Currency',
    net_amount: 'Subtotal',
    total_tax_amount: 'Tax Amount',
    tax_amount: 'Tax Amount',
    gst_amount: 'GST Amount',
    wht_amount: 'WHT Amount',
    total_amount: 'Total Amount',
    subtotal: 'Subtotal',
    document_type: 'Document Type',
    payment_terms: 'Payment Terms',
    purchase_order: 'Purchase Order',
  };
  return labels[fieldName] || fieldName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
