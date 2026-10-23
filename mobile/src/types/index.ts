// ─── Invoice Status ─────────────────────────────────────────────
export type InvoiceStatus =
  | 'draft'
  | 'pending_processing'
  | 'validated'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'posted'
  | 'exception';

// ─── Extraction Types (from Document AI) ────────────────────────
export interface ExtractedField {
  label: string;
  value: string;
  field_name: string;
  confidence: number; // 0-100
}

export interface ExtractedLineItem {
  description: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  amount: number | null;
  description_confidence?: number | null;
  quantity_confidence?: number | null;
  unit_price_confidence?: number | null;
  amount_confidence?: number | null;
}

export interface ExtractionResult {
  fields: ExtractedField[];
  line_items: ExtractedLineItem[];
  overall_confidence: number;
  document_type: string | null;
  page_count: number;
  processing_time_ms: number;
  warnings: string[];
  original_filename: string;
  stored_filepath: string;
  raw_document_ai?: any;
}

/** A file containing several invoices (or a multi-file/multi-page batch) is
 *  split & saved as DRAFTS server-side — the review screen is skipped and the
 *  app lands on the inbox with these highlighted. Returned by /upload (when it
 *  detects multiple invoices) and always by /upload-batch. */
export interface BatchDraftSummary {
  id: number;
  invoice_number: string | null;
  supplier_name: string | null;
  total_amount: number | null;
  currency: string | null;
}

export interface BatchUploadResult {
  batch: true;
  invoice_count: number;
  invoices: BatchDraftSummary[];
  errors?: { file: string; error: string }[];
}

/** /upload returns either a single ExtractionResult (review it) or, when the
 *  file holds several invoices, a BatchUploadResult (drafts saved). */
export type UploadResponse = ExtractionResult | BatchUploadResult;

export function isBatchResult(r: UploadResponse | BatchUploadResult): r is BatchUploadResult {
  return (r as BatchUploadResult)?.batch === true;
}

// ─── Invoice Types (saved in DB) ────────────────────────────────
export interface LineItem {
  id?: number;
  description: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  amount: number | null;
  ai_description?: string | null;
  ai_quantity?: number | null;
  ai_unit?: string | null;
  ai_unit_price?: number | null;
  ai_amount?: number | null;
  description_confidence?: number | null;
  quantity_confidence?: number | null;
  unit_price_confidence?: number | null;
  amount_confidence?: number | null;
  user_modified?: boolean;
}

export interface InvoiceListItem {
  id: number;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  supplier_name: string | null;
  total_amount: number | null;
  overall_confidence: number | null;
  status: InvoiceStatus;
  document_type: string | null;
  original_filename: string;
  created_at: string;
  line_items: LineItem[];
}

export interface InvoiceDetail {
  id: number;
  original_filename: string;
  stored_filepath: string;
  mime_type: string;
  file_size_bytes: number | null;
  page_count: number | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  supplier_name: string | null;
  supplier_address: string | null;
  supplier_ntn: string | null;
  receiver_name: string | null;
  receiver_address: string | null;
  subtotal_amount: number | null;
  tax_amount: number | null;
  total_amount: number | null;
  gst_amount: number | null;
  wht_amount: number | null;
  po_reference: string | null;
  bank_iban: string | null;
  document_type: string | null;
  overall_confidence: number | null;
  field_confidences: Record<string, number> | null;
  warnings: string[] | null;
  processing_time_ms: number | null;
  status: InvoiceStatus;
  created_at: string;
  updated_at: string | null;
  line_items: LineItem[];
  // FBR verification
  fbr_verification_status?: string | null;
  fbr_taxpayer_name?: string | null;
  fbr_filing_status?: string | null;
  wht_compliance_status?: string | null;
  // Credit/Debit notes
  linked_invoice_id?: number | null;
  credit_debit_reason?: string | null;
  original_invoice_number?: string | null;
  // Multi-currency
  base_currency?: string;
  exchange_rate?: number | null;
  base_total_amount?: number | null;
}

// ─── API Response Wrappers ──────────────────────────────────────
export interface InvoiceListResponse {
  invoices: InvoiceListItem[];
  total: number;
}

export interface InvoiceSaveRequest {
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  currency?: string;
  supplier_name?: string | null;
  supplier_address?: string | null;
  supplier_ntn?: string | null;
  receiver_name?: string | null;
  receiver_address?: string | null;
  subtotal_amount?: number | null;
  tax_amount?: number | null;
  total_amount?: number | null;
  gst_amount?: number | null;
  wht_amount?: number | null;
  po_reference?: string | null;
  bank_iban?: string | null;
  document_type?: string | null;
  overall_confidence?: number | null;
  field_confidences?: Record<string, number> | null;
  warnings?: string[] | null;
  processing_time_ms?: number | null;
  original_filename: string;
  stored_filepath: string;
  mime_type?: string;
  file_size_bytes?: number | null;
  page_count?: number | null;
  status?: string;
  line_items: LineItem[];
}

// ─── UI Helpers ─────────────────────────────────────────────────
export interface LineItemOverrides {
  [key: string]: number | string; // "rowIdx-colKey": value
}

// ─── Purchase Order Types ────────────────────────────────────────
export type POStatus =
  | 'draft'
  | 'open'
  | 'partially_received'
  | 'fully_received'
  | 'closed'
  | 'cancelled';

export type POType = 'local' | 'foreign' | 'contract';

export type MatchStatus = 'full_match' | 'partial_match' | 'mismatch' | 'unmatched';

export interface POLineItem {
  id?: number;
  po_id?: number;
  item_number?: number;
  description: string;
  quantity: number;
  unit?: string | null;
  unit_price: number;
  amount?: number | null;
}

export interface GRNLineItem {
  id?: number;
  grn_id?: number;
  po_line_item_id: number;
  received_quantity: number;
  inspection_status?: string;
}

export interface GoodsReceivedNote {
  id: number;
  grn_number: string;
  grn_date?: string | null;
  po_id: number;
  received_by?: string | null;
  plant_location?: string | null;
  notes?: string | null;
  created_at: string;
  line_items: GRNLineItem[];
}

export interface SESLineItem {
  id?: number;
  ses_id?: number;
  po_line_item_id: number;
  completed_quantity: number;
  completed_amount?: number | null;
}

export interface ServiceEntrySheet {
  id: number;
  ses_number: string;
  ses_date?: string | null;
  po_id: number;
  service_period_from?: string | null;
  service_period_to?: string | null;
  notes?: string | null;
  created_at: string;
  line_items: SESLineItem[];
}

export interface PurchaseOrder {
  id: number;
  po_number: string;
  vendor_name: string;
  vendor_ntn?: string | null;
  po_date?: string | null;
  po_type: POType;
  total_amount: number | null;
  currency: string;
  status: POStatus;
  notes?: string | null;
  source_type?: string;
  original_filename?: string | null;
  stored_filepath?: string | null;
  created_at: string;
  updated_at?: string | null;
  line_items: POLineItem[];
}

export interface PurchaseOrderDetail extends PurchaseOrder {
  grns: GoodsReceivedNote[];
  ses_records: ServiceEntrySheet[];
}

export interface POListResponse {
  purchase_orders: PurchaseOrder[];
  total: number;
}

// ─── PO Matching Types ──────────────────────────────────────────
export interface POLineMatchDetail {
  id: number;
  match_result_id: number;
  invoice_line_item_id?: number | null;
  po_line_item_id?: number | null;
  match_status: MatchStatus;
  quantity_match: boolean;
  price_match: boolean;
  quantity_diff?: number | null;
  quantity_diff_pct?: number | null;
  price_diff?: number | null;
  price_diff_pct?: number | null;
  grn_received_qty?: number | null;
  ses_completed_qty?: number | null;
  reasoning?: string | null;
  invoice_line_description?: string | null;
  invoice_line_qty?: number | null;
  invoice_line_price?: number | null;
  invoice_line_amount?: number | null;
  po_line_description?: string | null;
  po_line_qty?: number | null;
  po_line_price?: number | null;
  po_line_amount?: number | null;
}

export interface POMatchResult {
  id: number;
  invoice_id: number;
  po_id: number;
  match_status: MatchStatus;
  match_type: string;
  overall_score: number;
  total_amount_diff?: number | null;
  total_amount_diff_pct?: number | null;
  notes?: string | null;
  created_at: string;
  po_number?: string;
  line_matches: POLineMatchDetail[];
}

export interface POSuggestion {
  po_id: number;
  po_number: string;
  vendor_name: string;
  total_amount: number | null;
  confidence: number;
}

// ─── Email Inbox Types ──────────────────────────────────────────
export type EmailStatus = 'unread' | 'read' | 'processed';

export interface EmailAttachment {
  id: number;
  email_id: number;
  filename: string;
  content_type: string;
  file_size: number;
  stored_filepath?: string | null;
  processed: boolean;
  invoice_id?: number | null;
}

export interface EmailMessage {
  id: number;
  message_uid: string;
  from_address: string;
  subject: string;
  body_text?: string | null;
  received_at: string;
  fetched_at: string;
  status: EmailStatus;
  has_attachments: boolean;
  attachments?: EmailAttachment[];
}

export interface EmailListResponse {
  emails: EmailMessage[];
  total: number;
  unread: number;
  with_attachments: number;
  processed: number;
}

export interface EmailConfig {
  gmail_address: string | null;
  configured: boolean;
}

// ─── GL Coding Types ────────────────────────────────────────────
export interface GLAccount {
  id: number;
  code: string;
  name: string;
  category?: string | null;
  parent_code?: string | null;
  company_code?: string | null;
  cost_center?: string | null;
  is_active: number;
  description?: string | null;
  created_at: string;
}

export interface GLAssignment {
  id: number;
  invoice_id: number;
  line_item_id?: number | null;
  gl_account_id: number;
  gl_code: string;
  gl_name: string;
  amount?: number | null;
  cost_center?: string | null;
  assignment_type: string;
  confidence?: number | null;
  assigned_by_id?: number | null;
  assigned_by_name?: string | null;
  created_at: string;
}
