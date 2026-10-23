# einv Project Handoff — Session Status

> **2026-10-23 — Lucky Cement presales instance created** from VIM-Demo `DEMO` @ `ec9d7f3`
> and deployed to `tmc-presales-pocs` (fake SAP, DEBUG on). `CONTEXT.md` describes it.
> The `DEMO` branch **removed the Non-PO lane**, so the 2026-09-03 note below and every
> Non-PO reference describe code that is no longer in this repo.

> **2026-09-03 — Hilton Pharma instance: Non-PO invoice lane (Phases 1–4) DEPLOYED.**
> Invoices without a purchase order: `/upload/non-po` → GRN/SES check in SAP (hit = hand
> off to the PO flow) → SAP vendor + G/L coding → Non-PO rules → park with G/L account
> lines. PO flow untouched (proved by `backend/test_po_regression.py`). Read CLAUDE.md
> → "Non-PO lane" and CONTEXT.md §6–7; plan + evidence:
> https://claude.ai/code/artifact/5db755fc-d2a3-4b3a-a8b0-ac52f5a0ae32.
> Still open: the first human-witnessed real park in DEV.
>
> Everything below this line predates the Hilton Pharma instance and describes the old
> shared environment (invoice ids, DB counts, mobile parity). `CONTEXT.md` wins.

**Date**: 2026-03-17
**Last session focus**: FBR verification consistency fix, mobile-web parity, DB data cleanup

---

## WHAT WAS DONE IN RECENT SESSIONS

### 1. FBR Verification Fix (COMPLETED)
**Problem**: Extraction page (after upload) showed hardcoded "Tax Payer Status: Active" but after saving, invoice detail showed "NTN Not Found" — inconsistent.

**Root cause**: `frontend/src/pages/ExtractionResultsPage.jsx` had `taxPayerStatus="active"` hardcoded on line 205 instead of calling the real FBR verification API.

**Fix applied**:
- `frontend/src/pages/ExtractionResultsPage.jsx` — Added `useEffect` + `verifyNTN()` call from fbrService to get real FBR status from backend before save
- `frontend/src/components/upload/SupplierInfoCard.jsx` — Added new status styles (`not_found`, `verifying`, `error`), `taxpayerName` prop, default changed from `"active"` to `"verifying"`

### 2. FBR Data Variety (COMPLETED)
**Problem**: All invoices in DB showed "NTN Not Found" — no variety.

**Fix**: Created and ran `backend/update_fbr_data.py` to update 14 invoices with varied FBR verification data:
- `verified_active` (ATL Active — green): IDs 1, 5, 6, 7, 8, 12, 13, 14, 15, 26
- `verified_inactive` (Non-ATL — red): IDs 4, 10, 21
- `needs_review` WHT compliance: IDs 14, 25
- `non_compliant` WHT: IDs 4, 10, 21
- Each updated with `detected_taxes` JSON, `wht_amount`, `gst_amount`, `fbr_taxpayer_name`, `fbr_filing_status`

### 3. Mobile-Web Parity (COMPLETED)
- `mobile/src/components/StatusStepper.tsx` — Changed from 6 steps to 5 steps matching web (Received → Validated → Pending Approval → Approved → ERP Posting)
- `mobile/src/services/calculations.ts` — Updated status transitions to match web, added `STATUS_ACTION_OVERRIDES` for context-aware labels
- `mobile/app/invoice/[id].tsx` — Removed GLCodingCard (hidden on mobile per web), updated FBR badge condition
- `mobile/src/components/FBRBadge.tsx` — Added `verified_active`, `verified_inactive`, `not_found` status configs with proper colors/labels

### 4. DB Cleanup (COMPLETED)
- Deleted 6 duplicate/test invoices: IDs 21, 25, 26, 27, 28, 29
- Current total: 14 invoices in DB

---

## WHAT IS FULLY BUILT (Phase 1 Plan — 100% COMPLETE)

The plan at `.claude/plans/hashed-questing-porcupine.md` is **fully implemented**. All files exist, all DB tables created, all routers registered.

### Part A: RBAC / Internal User Management
- `backend/app/models/internal_user.py` — 8 roles (admin, ap_manager, ap_operator, tax_manager, procurement_manager, auditor, finance_director, department_head)
- `backend/app/routers/internal_auth.py` — Login/logout/me endpoints
- `backend/app/schemas/internal_user.py` — Pydantic schemas
- `frontend/src/services/authService.js` — Auth API service
- `frontend/src/pages/AdminUsersPage.jsx` — User CRUD page
- `frontend/src/pages/LoginPage.jsx` — Real API login (was cosmetic)
- Default admin: `admin@ogdcl.com` / `admin123`

### Part B: Audit Trail
- `backend/app/models/audit_log.py` — AuditLog model
- `backend/app/services/audit_service.py` — `log_audit()` helper
- `backend/app/routers/audit.py` — Query endpoints
- `frontend/src/components/detail/AuditTrailCard.jsx` — Timeline component
- Integrated into `invoices.py` for status changes

### Part C: Multi-Level Approval Workflow
- `backend/app/models/workflow.py` — 4 tables (WorkflowTemplate, WorkflowStep, ApprovalRequest, ApprovalAction)
- `backend/app/services/workflow_engine.py` — Core engine (initiate, process action, match template)
- `backend/app/routers/workflows.py` — Template CRUD
- `backend/app/routers/approvals.py` — Approve/reject/delegate actions
- `backend/app/schemas/workflow.py` — All schemas
- `frontend/src/services/workflowService.js` — API calls
- `frontend/src/pages/MyApprovalsPage.jsx` — Pending approvals queue
- `frontend/src/pages/WorkflowTemplatesPage.jsx` — Template management
- `frontend/src/components/detail/ApprovalProgressCard.jsx` — Progress + action buttons on invoice detail
- Invoice status machine expanded: `validated → pending_approval → approved → posted` (or `rejected`)
- Default workflow template seeded: "General Invoice Approval" (2 steps: AP Manager → Finance Director)

### All Other Built Features
See `## TMC eInvoice — Feature Summary.txt` in project root for the complete list. Key ones:
- Invoice processing (Document AI + Gemini)
- FBR compliance (NTN verification, WHT compliance, tax rules engine)
- Purchase Order matching (2-way, 3-way with GRN/SES)
- Supplier portal with OTP auth
- Duplicate detection
- GL account coding
- Credit/debit notes
- Multi-currency
- Comments & collaboration
- Auto-classification
- Analytics dashboard
- Email inbox (Gmail IMAP)

---

## WHAT IS LEFT TO BUILD

From `## TMC eInvoice — Feature Summary.txt`:

1. **ERP Integration** — SAP/Oracle real-time posting, journal entries, master data sync
2. **Data Encryption** — Encrypt stored files and sensitive DB fields at rest
3. **Audit-Grade Storage** — Immutable document storage with versioning and retention
4. **Live Dashboard Data** — Wire AP/Tax/Auditor dashboards to real analytics (currently mock data)
5. **Notifications** — Email/SMS alerts for status changes and approvals
6. **Bulk Processing** — Upload and process multiple invoices at once
7. **Report Export** — Download dashboards and invoice lists as PDF/Excel
8. **Real SMS OTP** — Replace dev-mode OTP with SMS gateway (Twilio etc.)
9. **Supplier Document Upload** — NTN/STRN certificates, bank letter for verification
10. **Production Deployment** — Docker, HTTPS, secrets management

---

## UNCOMMITTED CHANGES

There are significant uncommitted changes across 38+ files (backend, frontend, mobile). Run `git diff --stat HEAD` to see full list. These include:
- All Phase 1 (RBAC + Audit + Workflow) implementation
- FBR verification fixes
- Mobile-web parity updates
- New backend services (FBR, workflow, audit, auth, analytics, etc.)
- New frontend pages and components
- Mobile app updates

**These should be committed before further work.**

---

## HOW TO RUN

```bash
# Backend (already running on port 8000 usually)
cd backend
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run dev  # port 5173

# Mobile (Expo)
cd mobile
npx expo start --web --port 8085
```

Login: `admin@ogdcl.com` / `admin123` (role: admin)

---

## KEY ARCHITECTURE NOTES

- **Python**: Use `py -3` (not `python` or `python3`) on this machine
- **State-based routing**: No react-router — `activeView` state in `App.jsx` / `SupplierPortal.jsx`
- **Auth**: Internal users use real JWT-like token auth; Supplier users use OTP + session tokens
- **DB**: SQLite at `backend/invoices.db`, auto-created tables via SQLAlchemy
- **FBR**: Local ATL database at `D:/Anas-sb-Project/FBR-Scrapping/fbr_atl_project/atl.db`, live FBR API disabled (`FBR_LIVE_LOOKUP_ENABLED: False`)
- **Design tokens**: `frontend/src/styles/tokens.js`, Tailwind custom classes
- **Memory files**: `C:\Users\awais\.claude\projects\D--Anas-sb-Project-einv\memory\` — has MEMORY.md index
