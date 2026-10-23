# MEIn Frontend — Codebase Inventory

## 1. Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React | 19.2.0 |
| Build Tool | Vite | 7.3.1 |
| Styling | Tailwind CSS | 4.2.0 |
| HTTP Client | Axios | 1.13.5 |
| File Upload | react-dropzone | 15.0.0 |
| State Management | React useState/useCallback (no external library) | — |
| Routing | Manual view switching in App.jsx (no React Router) | — |
| Authentication | None | — |

---

## 2. Project Structure

```
src/
├── main.jsx                          # Entry point — renders <App />
├── App.jsx                           # Root shell: sidebar, navigation, global state
├── index.css                         # Tailwind theme tokens (brand, neutral, status colors)
│
├── services/
│   ├── api.js                        # Axios instance (baseURL, 60s timeout)
│   └── invoiceService.js             # All API call functions (6 endpoints)
│
├── styles/
│   └── tokens.js                     # JS design tokens (colors, status palettes)
│
├── hooks/
│   ├── useInvoiceUpload.js           # Upload workflow state machine (not used by App)
│   └── useInvoiceDetail.js           # Detail page: fetch, edit, save, status transitions
│
├── pages/
│   ├── UploadInvoicePage.jsx         # File upload + Document AI processing
│   ├── ExtractionResultsPage.jsx     # Review extracted data before saving
│   ├── InvoiceListPage.jsx           # Paginated table of saved invoices
│   └── InvoiceDetailPage.jsx         # Single invoice view/edit/workflow
│
├── components/
│   ├── common/                       # Reusable UI primitives
│   │   ├── Badge.jsx                 # Status pill (19 status configs)
│   │   ├── Button.jsx                # 5 variants, 3 sizes
│   │   ├── Card.jsx                  # Container with optional header
│   │   ├── ConfidenceIcon.jsx        # Colored confidence dot + tooltip
│   │   ├── ConfidenceLabel.jsx       # Label with confidence underline + tooltip
│   │   ├── KpiCard.jsx               # Metric card with accent border
│   │   └── Spinner.jsx               # Loading spinner with message
│   │
│   ├── upload/                       # Extraction flow components
│   │   ├── UploadZone.jsx            # Drag-and-drop file input
│   │   ├── FilePreview.jsx           # File metadata display (unused currently)
│   │   ├── ExtractedFields.jsx       # Simple field table (unused — replaced by InvoiceInfoCard)
│   │   ├── ExtractionKPIs.jsx        # 4-card KPI grid (confidence, type, fields, time)
│   │   ├── SupplierInfoCard.jsx      # Supplier fields + Tax Payer / ERP status
│   │   ├── InvoiceInfoCard.jsx       # Invoice header fields in sorted grid
│   │   ├── LineItemsTable.jsx        # Editable line items with auto-calc Rate
│   │   ├── SalesTaxCard.jsx          # Tax amount, %, subtotal, total
│   │   ├── WorkflowActions.jsx       # Discard / Save Draft / Submit buttons
│   │   ├── WarningsBanner.jsx        # Collapsible warnings list
│   │   ├── RawOutputViewer.jsx       # Full-screen 2-tab viewer (Fields, OCR) — ACTIVE
│   │   └── RawOutputDrawer.jsx       # Old 4-tab drawer — DEPRECATED, not imported
│   │
│   └── detail/                       # Invoice detail page components
│       ├── InvoiceDetailFields.jsx   # Grouped field table with inline editing
│       └── WorkflowStepper.jsx       # 4-step status progression bar
```

---

## 3. Screens & Navigation

There is **no React Router**. Navigation is handled by `activeView` state in `App.jsx`.

| View Key | Page Component | How User Gets Here |
|----------|---------------|-------------------|
| `"upload"` | `UploadInvoicePage` | Default view, sidebar "Upload Invoice" link, or after discarding results |
| `"results"` | `ExtractionResultsPage` | Automatically after successful Document AI extraction |
| `"list"` | `InvoiceListPage` | Sidebar "Invoices" link, or after successful save |
| `"detail"` | `InvoiceDetailPage` | Clicking a row in InvoiceListPage |

**Navigation flow:**
```
Upload ──extract──▶ Results ──save──▶ List ──click row──▶ Detail
  ▲                   │                 ▲                    │
  └───── discard ─────┘                 └──── back button ───┘
```

**Sidebar:** Fixed left sidebar with logo "MEIn", two nav items (Upload Invoice, Invoices), collapsible toggle, and user info footer showing logged-in user "Anas Wahab".

---

## 4. State Management

**No external state library.** All state lives in React hooks.

### Global State (App.jsx)

| State Variable | Type | Purpose |
|---------------|------|---------|
| `activeView` | string | Current page: "upload" / "results" / "list" / "detail" |
| `sidebarCollapsed` | boolean | Sidebar expand/collapse |
| `selectedInvoiceId` | number | Invoice ID for detail view |
| `extractionFile` | File | Uploaded file object |
| `extractionResult` | object | Document AI extraction response |
| `savedInvoice` | object | Invoice after save |
| `resultsState` | string | "extracted" / "saving" / "saved" / "error" |
| `resultsError` | string | Save error message |
| `lineItemOverrides` | object | User edits to line items `{"rowIdx-colKey": value}` |

### Hook: useInvoiceDetail (Detail page)

| State Variable | Type | Purpose |
|---------------|------|---------|
| `invoice` | object | Loaded invoice from API |
| `loading` | boolean | Fetch in progress |
| `error` | string | Error message |
| `editing` | boolean | Edit mode toggle |
| `editFields` | object | Cloned field values for editing |
| `editLineItems` | array | Cloned line items for editing |
| `saving` | boolean | Save in progress |

### Hook: useInvoiceUpload (not used by App)

Alternative upload workflow hook — manages state machine: idle → extracting → extracted → saving → saved.

---

## 5. API Endpoints

Base URL: `VITE_API_BASE_URL` env var or `http://localhost:8000` (60s timeout).

### Endpoints Called by Frontend

| Method | Path | Service Function | Called From | Purpose |
|--------|------|-----------------|-------------|---------|
| POST | `/api/invoices/upload` | `uploadInvoice(file)` | UploadInvoicePage | Upload file → Document AI extraction |
| POST | `/api/invoices/save` | `saveInvoice(data)` | App.handleSave | Save extraction result as invoice |
| GET | `/api/invoices/` | `getInvoices(skip, limit)` | InvoiceListPage | Paginated invoice list |
| GET | `/api/invoices/{id}` | `getInvoice(id)` | useInvoiceDetail | Fetch single invoice |
| PUT | `/api/invoices/{id}` | `updateInvoice(id, data)` | useInvoiceDetail | Update invoice fields + line items |
| PATCH | `/api/invoices/{id}/status` | `updateInvoiceStatus(id, status)` | useInvoiceDetail | Transition invoice status |

### Key Data Shapes

**ExtractionResult (from upload):**
```
{ fields[], line_items[], overall_confidence, document_type,
  page_count, processing_time_ms, warnings[], original_filename,
  stored_filepath, raw_document_ai }
```

**InvoiceSaveRequest (to save):**
```
{ invoice_number, invoice_date, due_date, currency, supplier_name,
  supplier_address, supplier_ntn, receiver_name, receiver_address,
  subtotal_amount, tax_amount, total_amount, gst_amount, wht_amount,
  po_reference, bank_iban, document_type, overall_confidence,
  field_confidences, warnings[], processing_time_ms, original_filename,
  stored_filepath, mime_type, file_size_bytes, page_count, status,
  line_items[] }
```

**InvoiceDetailResponse (from get/update):**
```
{ id, original_filename, stored_filepath, mime_type, file_size_bytes,
  page_count, invoice_number, invoice_date, due_date, currency,
  supplier_name, supplier_address, supplier_ntn, receiver_name,
  receiver_address, subtotal_amount, tax_amount, total_amount,
  gst_amount, wht_amount, po_reference, bank_iban, document_type,
  overall_confidence, field_confidences, warnings[], processing_time_ms,
  status, created_at, updated_at, line_items[] }
```

**Invoice Status State Machine:**
```
draft → pending_processing → validated → posted
                ↕                ↕
             exception ◄────────┘
```

---

## 6. Authentication

**None.** There is no authentication, authorization, or user management. The sidebar hardcodes "Anas Wahab" as the user. All API endpoints are open.

---

## 7. Component Dependency Map

```
App.jsx
├── UploadInvoicePage
│   ├── Card, Badge, Button
│   └── UploadZone (react-dropzone)
│
├── ExtractionResultsPage
│   ├── Card, Badge, Button
│   ├── ExtractionKPIs → KpiCard
│   ├── SupplierInfoCard → ConfidenceLabel
│   ├── InvoiceInfoCard → ConfidenceLabel
│   ├── LineItemsTable → Card (EditableCell inline)
│   ├── SalesTaxCard → Card, ConfidenceLabel
│   ├── WorkflowActions → Card, Button
│   └── RawOutputViewer (full-screen overlay)
│
├── InvoiceListPage
│   ├── Card, Badge
│   └── (table built inline)
│
└── InvoiceDetailPage
    ├── Card, Badge, Button, KpiCard, Spinner
    ├── WorkflowStepper
    ├── InvoiceDetailFields → Card
    ├── LineItemsTable → Card
    └── SalesTaxCard → Card, ConfidenceLabel
```

---

## 8. Unused / Deprecated Files

| File | Status | Notes |
|------|--------|-------|
| `RawOutputDrawer.jsx` | Deprecated | Replaced by RawOutputViewer.jsx, not imported anywhere |
| `ExtractedFields.jsx` | Unused | Replaced by InvoiceInfoCard.jsx |
| `FilePreview.jsx` | Unused | Upload page uses inline processing view instead |
| `WarningsBanner.jsx` | Unused | Only imported by FilePreview which is unused |
| `useInvoiceUpload.js` | Unused | App.jsx manages upload state directly instead |

---

## 9. Key Business Logic in Frontend

**Rate auto-calculation (3 locations):**
- `App.jsx` → `handleExtractionComplete`: Overwrites unit_price = amount / qty on extraction
- `LineItemsTable.jsx` → `handleCommit`: Recalculates when user edits qty or amount
- `useInvoiceDetail.js` → `handleLineItemChange`: Same recalculation on detail page

**Default line item creation:**
- `App.jsx` → `handleExtractionComplete`: If Document AI returns no line items, creates one with qty=1, amount=total_amount, description="N/A"

**Tax deduplication fix:**
- Backend `document_ai.py`: If total_tax_amount == total_amount, sets total_tax_amount to 0

**Sales Tax % derivation (SalesTaxCard.jsx):**
- Priority 1: net_amount / subtotal from fields
- Priority 2: Sum of line item amounts
- Priority 3: total_amount - tax_amount (derived)

**Field mapping:**
- Supplier fields (supplier_name, supplier_tax_id, supplier_address, supplier_phone) → SupplierInfoCard
- All other fields → InvoiceInfoCard
- Fields sorted by FIELD_ORDER constant
- Amount fields formatted with 2 decimal places
