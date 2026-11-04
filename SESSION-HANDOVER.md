# Session handover — 2026-11-04

Handover from Claude Code sessions on this machine (`D:\VIM\VIM-Luck`). Read
`CLAUDE.md` and `CONTEXT.md` first; this file records only what these sessions did and
what is still open. (`HANDOFF.md` is the separate product feature-status doc.)
Newest session first; §1–§5 below are from session 1 and are still accurate.

## 0. Session 2 — 2026-11-04 (onboarding review: run, test, risk scan)

No code changed. The only file changed is this one. The Analytics title fix from
session 1 is still uncommitted and not deployed.

**What was checked (all on this laptop, against the local SQLite DB):**

| Check | Result |
|---|---|
| Toolchain | Python 3.12.10 venv, `pip check` clean; Node 24.22.1; npm deps installed |
| Backend | Starts on :8000 via `.claude\launch.json`. Smoke test: `/health`, internal login, `/me`, `/api/sap/test` (fixture SAP, `RFCSYSID=FAK`), invoices, POs, analytics overview, 90-day volume trend (works on SQLite only, see §4 #1), workflow templates, roles: all 200 |
| Frontend | Starts on :5173. Internal portal renders Analytics with one title and no console errors |
| Offline tests | `test_sap_fake`, `test_line_item_guards`, `test_po_flip`, `test_supplier_vendor_gate`, `test_role_labels`: **all PASS** |
| Live-SAP tests | Not run (`test_po_regression.py`, `test_sap*.py`): there is no SAP system for this instance |
| `npm run build` | **OK.** Warning only: `main` (620 kB) and `supplierService` (523 kB) chunks are over 500 kB |
| `npm run lint` | **20 errors, 5 warnings, all pre-existing, none break the build**: unused vars (ApprovalProgressCard, CreditDebitNoteCard, GLCodingCard, InvoiceClassificationCard, POCreatePage, POListPage, SupplierNotificationsPage), React-compiler `set-state-in-effect` (AuditTrailCard, DuplicateWarningCard, LineItemsTable, AdminEmailInboxPage, ExtractionResultsPage), and `__dirname` in `vite.config.js` (false positive: the ESLint config has no Node globals for that file; Vite shims it) |

**Running the offline tests safely.** Four of the five scripts write rows into
`./invoices.db` in the *current directory*. Run them from a scratch copy so the dev DB
stays clean (they find `app/` themselves; `.env` and the DB are read from the cwd):

```powershell
$s = "$env:TEMP\vim-testrun"; New-Item -ItemType Directory -Force $s | Out-Null
Copy-Item D:\VIM\VIM-Luck\backend\.env, D:\VIM\VIM-Luck\backend\invoices.db $s
cd $s
foreach ($t in "test_sap_fake","test_line_item_guards","test_po_flip","test_supplier_vendor_gate","test_role_labels") { D:\VIM\VIM-Luck\backend\.venv\Scripts\python.exe -X utf8 "D:\VIM\VIM-Luck\backend\$t.py" }
Remove-Item -Recurse -Force $s   # the copy holds the local .env
```

Frontend: `cd D:\VIM\VIM-Luck\frontend; npm run lint; npm run build`.

**New finding: broken access control (most important open issue).**
Proved on a scratch DB copy with a faked supplier principal (same technique as the
existing tests):

- A **supplier** token can `PUT /api/workflow-templates/{id}` with `is_active=0`, which returns 200.
  With no active template, `workflow_engine.py:115` skips approval, so invoices go
  straight to parking. The supplier can also `POST /api/tax-rules` (200) and read
  `/api/audit-logs` and `/api/analytics/*` (200).
- Cause: `workflows.py`, `tax_rules.py`, `gl_accounts.py`, `audit.py` and `analytics.py` are
  mounted with `auth_dep` (internal user **or** supplier) and have no per-route role
  check. Any internal role, `auditor` included, can also change them. The admin pages are
  hidden in the UI, but the API does not enforce it.
- Other `auth_dep` routers (purchase_orders, po_matching, products, currency, fbr,
  comments, agent_invoices) were **not** audited route by route.

**AI / performance risks found in code (not changed):**

- Gemini is called **synchronously inside `async` handlers** (`routers/invoices.py`
  ~448, 463, 519, 582; `routers/inbox.py` ~241). Each extraction blocks the event loop
  for its full duration, and the API is capped at one Cloud Run instance, so one upload
  stalls every other user's requests. `po_flip.py` already uses `anyio.to_thread.run_sync`.
- No explicit request timeout on the Gemini client, and no token-usage logging
  (`usage_metadata` is never read). Cost per invoice cannot be measured.
- `gemini_extract.py` copies one model-reported `overall_confidence` onto **every** field,
  so the per-field confidence in the UI is not per-field.
- Prompts are unversioned module constants, the model id and prompt version are not stored
  with the extraction, and there is no extraction eval set.

## 1. Local environment (set up, working)

| | |
|---|---|
| Python | 3.12.10, installed by winget for this user (`%LOCALAPPDATA%\Programs\Python\Python312`). `py -3` may not be on PATH in old terminals |
| Node.js | 24.22.1 **portable** build at `%LOCALAPPDATA%\Programs\node-v24.22.1-win-x64`, added to user PATH (the MSI needed admin and was cancelled) |
| Backend venv | `backend\.venv`, `requirements.txt` installed |
| Backend config | `backend\.env`, copied from `.env.example`, then: `SAP_ENABLED=true`, `SAP_MODE=fake`, `INITIAL_ADMIN_PASSWORD` and `SUPPLIER_DEMO_OTP` set to local test values (read them from that file). `GEMINI_API_KEY` is **empty**, so AI extraction fails until it is filled in |
| Database | SQLite `backend\invoices.db`: 34 tables, seeded (1 admin user, 8 roles, 15 GL accounts, 10 tax rules, 500 products, default workflow). No invoices, no ATL rows |
| Frontend | `frontend\node_modules` installed |
| Launch config | `.claude\launch.json` with `backend` (:8000) and `frontend` (:5173) entries |

All of the above is git-ignored except `.claude\launch.json`.

Run by hand (two terminals):

```powershell
cd D:\VIM\VIM-Luck\backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
cd D:\VIM\VIM-Luck\frontend; npm run dev
```

- Internal portal http://localhost:5173 (login `admin@tmcltd.com`), supplier portal http://localhost:5173/supplier/
- Check the fixture SAP is active: `GET /api/sap/test` returns `"mode": "fake"` (needs a login token)
- View the DB: VS Code "SQLite Viewer" extension on `backend\invoices.db` (read-only)

## 2. Code change (uncommitted)

**Duplicate "Analytics & Insights" title**: fixed in `frontend/src/pages/AnalyticsDashboard.jsx`.
The title showed twice because `components/layout/Layout.jsx` already renders the page
title in the top bar, and the page added its own `<h2>`. The `<h2>` is removed and the
7D/30D/90D selector is right-aligned. Verified locally: one heading. This is the
**only** change in the working tree. It is not committed and not deployed.

## 3. Deploy: NOT done, blocked

- The user asked to deploy to **https://vim-internal-web-297345409494.asia-south1.run.app/**.
  That is **not** this repo's instance. Inspecting its live bundle showed: brand "TMC eInvoice",
  backend `https://vim-internal-297345409494.asia-south1.run.app`, GCP project number
  `297345409494`. This repo deploys to `lucky-cement-vim-web` in `tmc-presales-pocs`
  (us-central1). Deploying this repo there would replace that app with Lucky Cement code
  and branding, and the backend URL is baked in at build time. It would also break the
  "repo isolation" rule in `CLAUDE.md`.
- **Recommended:** apply the same 3-line fix in vim-internal-web's own source repo (path or
  GitHub name still unknown) and deploy from there.
- **Alternative:** deploy to this repo's own server (`CONTEXT.md` §3). Only the frontend
  changed, so only `lucky-cement-vim-web` needs a rollout.
- **gcloud is not installed.** The winget user-scope install has no installer; the machine-wide
  install was interrupted, and nothing was installed. Deploying needs gcloud plus
  `gcloud auth login` by someone with access to the target project.

## 4. Other Analytics defects found (fixed, then reverted at the user's request)

Not applied; listed so they can be picked up later.

1. **The 90D button breaks the dashboard on Postgres (cloud).** `routers/analytics.py` `volume-trend` uses
   SQLite-only `strftime` for week/month grouping, so it fails. The page loads all its data in one
   `Promise.all`, so one failure leaves every card at 0. `AuditorDashboard` calls week grouping too.
   Fix: `to_char` on Postgres with the format as `literal_column(...)`. A bound parameter
   makes SELECT and GROUP BY different expressions under asyncpg.
2. **Suppliers can read `/api/analytics/*`.** The router is mounted with `auth_dep`, which accepts suppliers,
   so a supplier token sees all suppliers' names and totals. Fix: mount with
   `Depends(get_current_internal_user)`. The mobile app logs in as an internal user, so it is unaffected.
3. **Straight-through rate ignores `parked`.** It counts approved + posted only, but parked is the normal
   end state here.
4. **Status bar colours don't match their badges.** Processing's bar is amber but its badge is purple, so it
   looks like Parked.
5. **Volume trend labels use the full series** while only the last 30 bars are drawn.
6. **Load errors are swallowed** (`console.error` only), so a failure looks like "no data".
7. **Intake Sources labels every non-email source "Upload".** Supplier, po_flip and the rest are mislabelled.
8. **`fmt()` doesn't shorten negative amounts** (credit notes).

Not attempted: "Total Value" sums mixed currencies under a PKR label; Badge gives `parked` and
`pending_approval` the same amber; the KPI grid isn't responsive.

## 5. Next steps (updated in session 2, priority order)

1. **Close the access-control hole (§0).** Gate mutations in `workflows.py`, `tax_rules.py`
   and `gl_accounts.py` with `require_admin` (or the right `require_roles`). Mount `audit.py`
   and `analytics.py` behind `get_current_internal_user` (this also fixes §4 #2). Add a
   standalone test, in the style of `test_supplier_vendor_gate.py`, that expects 403 for a
   supplier. Then audit the remaining `auth_dep` routers route by route.
2. **Take Gemini off the event loop.** Wrap `extract_invoice` / `segment_invoice_pages`
   calls in `anyio.to_thread.run_sync`, set an explicit client timeout, and log
   `usage_metadata` token counts per call.
3. **Fix the 90D analytics on Postgres** (§4 #1): the cloud dashboard shows all zeros.
4. **Deploy the title fix.** Decide the target: vim-internal-web's own repo (preferred) or
   `lucky-cement-vim-web`. Install the Google Cloud CLI (`winget install Google.CloudSDK`,
   needs admin) and run `gcloud auth login`. Commit, then build and deploy following that
   instance's deploy steps.
5. **Extraction quality baseline.** Build a small golden set from `generate_demo_invoices.py`
   PDFs, and store the model id and prompt version with each extraction.

Lower priority: the remaining §4 items, lint cleanup, and code-splitting the two large chunks.
