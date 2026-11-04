# Session handover — 2026-11-04

Handover from Claude Code sessions on this machine (`D:\VIM\VIM-Luck`). Read
`CLAUDE.md` and `CONTEXT.md` first; this file records only what these sessions did and
what is still open. (`HANDOFF.md` is the separate product feature-status doc.)
Newest session first; §1–§5 below are from session 1 and are still accurate.

## Pulled 2026-11-04: supplier demo OTP moved into the database

`git pull --ff-only --autostash` brought in `9ae16b0` (supplier demo OTP now lives in the
`app_settings` table and is set under **Admin → Suppliers**) and `61d06b2` (`start-lan.sh`).
The uncommitted View/Download work below re-applied cleanly. After the pull, all 6 offline
suites still pass.

- **Local `.env` fixed:** the new config rejects unknown keys, so the old `SUPPLIER_DEMO_OTP=`
  line made the backend fail at startup. It is now **commented out**, keeping its old value in
  the comment. A copy of the pre-pull `.env` is in the session scratchpad only.
- **Local supplier login needs the OTP set once:** `app_settings` is empty, so sign in as admin
  and set it under Admin → Suppliers.
- **On the next deploy:** the cloud DB has no OTP row either, so **supplier login on the demo
  stops working until an admin sets it** there. The `SUPPLIER_DEMO_OTP` env var on
  `lucky-cement-vim-api` is ignored by the new code; it does no harm but could be removed later.
- Local AI extraction still needs `GEMINI_API_KEY` in `backend\.env` (it is empty).

## Latest: invoice document View / Download (client requirement, 2026-11-04)

**Requirement (from the client):** after a user uploads an invoice, they can view and
download that file. **Status: DEPLOYED 2026-11-04** (commit `88504a1`, images `:33e20f0`).

| Deploy record | |
|---|---|
| Bucket | `gs://lucky-cement-vim-uploads` (us-central1, uniform access, public access prevention). `lucky-cement-vim-sa` has `roles/storage.objectUser` on it |
| Cloud Build | `51c22ee0-8b72-4121-89fd-ebc07c721e6d`, SUCCESS in 1m27s |
| API | `lucky-cement-vim-api-00002-wrv`, 100%. Cloud Storage volume `uploads` mounted at `/mnt/uploads`, `UPLOAD_DIR=/mnt/uploads`. Default (gen1) execution environment worked; the log shows "File system has been successfully mounted." |
| Web | `lucky-cement-vim-web-00003-m2m`, 100% |
| Rollback | `gcloud run services update-traffic lucky-cement-vim-api --to-revisions=lucky-cement-vim-api-00001-x8n=100 --region=us-central1 --project=tmc-presales-pocs` and the same for `lucky-cement-vim-web` with `lucky-cement-vim-web-00002-tfv` |
| Verified from outside | `/health` 200; `GET /api/invoices/1/document` with no token → 401; route listed in `/openapi.json`; buttons present in the live bundle |
| **Not yet verified** | A real upload → View/Download on the live site (needs a login), and the file appearing in the bucket: `gcloud storage ls gs://lucky-cement-vim-uploads` |
| Side effects | The pulled OTP change is live too: **supplier login fails until an admin sets the OTP under Admin → Suppliers**. As with every new API revision, the fixture SAP store reset |

Before this, the original upload was saved (`Invoice.stored_filepath`) but nothing served
it: the detail page only showed the file name as text. (Supporting documents already had
their own download in `AttachmentsCard` / `routers/attachments.py`.)

| File | Change |
|---|---|
| `backend/app/services/file_storage.py` | `resolve_stored_file()`: only names `save_uploaded_file()` generates (32 hex chars + extension), looked up inside `UPLOAD_DIR`. `sniff_inline_type()`: type from the file's bytes |
| `backend/app/routers/invoices.py` | `GET /api/invoices/{id}/document` (inline; `?download=true` = attachment), `nosniff`, `no-store`; `document_available` in the detail response |
| `backend/app/schemas/invoice.py` | `document_available: bool` on `InvoiceDetailResponse` |
| `frontend/src/services/invoiceService.js` | `fetchInvoiceDocument()`: fetches as a Blob with the normal auth header (no `?token=` in URLs) |
| `frontend/src/pages/InvoiceDetailPage.jsx` | "View · Download" after the file name in the header, shown only when `document_available`. Errors go to the existing action-error banner. The supplier portal reuses this page |
| `backend/test_invoice_document.py` | New, offline, own temp DB + upload folder: **39/39 pass** |

**Follow-up: "View File" on the review page** (`/results`, and `/supplier/upload/review`, which
uses the same `ExtractionResultsPage.jsx`). A button next to "Raw Output" opens the uploaded file
from browser memory (`URL.createObjectURL` on the dropped `File`), with no server request, so users can
check the extracted fields against the document before saving. It is hidden for email-inbox
reviews, which only carry a `{name, size}` stand-in. If a popup is blocked, it downloads instead.
Checked in the pane with a stubbed upload response (the local Gemini key is empty): the button
renders, and the click opens a `blob:` URL holding the exact PDF. Lint and build unchanged.

**Follow-up 2: Invoice Inbox rows** (internal `InvoiceListPage.jsx`):
- Clicking anywhere on a row opens the invoice. This is skipped while text is selected, so an
  invoice number can still be copied.
- A new **Document** column shows "View · Download", or "—" when there is no file. The two
  buttons stop the click from also opening the row.
- The list API now sets `document_available` per row. `stored_files_available()` checks a page
  of rows with 8 threads, inside `asyncio.to_thread`: on Cloud Run each check is a Cloud Storage
  metadata call, and the event loop must not wait on it. Rows without a valid stored name (e.g.
  PO-flip) skip the check.
- View/Download logic now lives in one helper, `frontend/src/utils/invoiceDocument.js`, used by
  the inbox, the detail page and the review page.
- `test_invoice_document.py` has 7 more list checks (46 total, all pass). Verified in the pane:
  the column renders; View and Download fetch 200 without opening the row; a cell click opens
  `/invoices/1`; the detail-page and review-page links still work.
- **Not covered:** the supplier portal's own list (`HistoryView` in `SupplierPortal.jsx`) is a
  separate component and does not have the column.

**Why the path guard matters:** `/api/invoices/save` stores whatever `stored_filepath` the
client sends. Without the guard, any logged-in user (a supplier included) could point an
invoice at `/proc/self/environ` (the DB URL and API keys live in env vars on Cloud Run) and download it.
The test covers absolute paths, `../`, backslashes, the DB file, `/proc/self/environ`,
`po-flip`, missing files, HTML bytes behind a `.pdf` name, supplier A vs B, and no token (401).

**Checked locally:** the existing 5 offline suites still pass; `npm run build` OK; lint
unchanged (20 old errors, 0 new). In the app: the buttons render and `GET …/document` returns
the exact PDF (`application/pdf`). The Claude browser pane blocks new tabs and won't render
PDFs, so the "View" tab itself was not seen. Check it in Chrome/Edge. The supplier portal
was covered by the test, not clicked through.

**Local test data left behind:** invoice #1 `INV-DOC-0001` (draft) in `backend\invoices.db`,
and its PDF in `backend\uploads\`. Delete it in the app if unwanted.

**Server storage: Cloud Storage bucket (done, see the deploy record above).** Uploads used to go
to the API container's disk, which Cloud Run wipes on every restart or new revision. The steps
that were run:
1. Create a private bucket, e.g. `lucky-cement-vim-uploads` (us-central1, uniform access, public access prevention).
2. Grant `lucky-cement-vim-sa@tmc-presales-pocs.iam.gserviceaccount.com` `roles/storage.objectUser` on it.
3. Commit, build with `cloudbuild.yaml`, deploy **both** services. The API deploy adds a Cloud Storage
   volume mounted at `/mnt/uploads` and sets `UPLOAD_DIR=/mnt/uploads` (may need `--execution-environment=gen2`).
Files uploaded before this are already gone from the server, so older invoices will show no View/Download.

## 0. Session 2 — 2026-11-04 (onboarding review: run, test, risk scan)

No new code was written. The Analytics title fix from session 1 was committed, pushed
and deployed to **this repo's own server** (decision: `lucky-cement-vim-web`, not
vim-internal-web):

| | |
|---|---|
| Commits on `origin/main` | `a5ddde0` title fix, `205c020` this handover (author `ai.engineers1`, set for these commits only; this machine has **no git identity configured**) |
| Cloud Build | `1efb4b6d-6808-4689-b994-004a6c957e81`, SUCCESS in 1m8s. Both images pushed as `:205c020` |
| Rolled out | **web only**: `lucky-cement-vim-web` revision `lucky-cement-vim-web-00002-tfv`, 100% traffic. The backend `lucky-cement-vim-api` was **not** redeployed (no backend change) |
| Rollback | `gcloud run services update-traffic lucky-cement-vim-web --to-revisions=lucky-cement-vim-web-00001-4q6=100 --region=us-central1 --project=tmc-presales-pocs` (previous image `:9f3c063`) |
| Verified | Portal and `/supplier/dashboard` return 200; login page renders, no console errors; live bundle bakes in the `lucky-cement-vim-api-527930147362` URL; "Analytics & Insights" appears once in the bundle (top-bar title only). The signed-in Analytics page was **not** viewed on the live site (needs a real login) |
| Note | The first `/health` call returned 500: Cloud Run said "aborted after waiting too long for an available instance". That was the single API instance cold-starting; the next calls returned 200. Expect it on the first hit after idle |

**"I don't see any changes on Server" (raised after the deploy).** The fix is live on
`lucky-cement-vim-web` (index.html last-modified 2026-11-04 11:33 GMT, `cache-control: no-cache`,
no duplicate `<h2>` in the bundle). **vim-internal-web is untouched**: its index.html is from
2026-10-05 and its bundle still has the duplicate `<h2>`. A fix there is blocked on two things:
- **Source:** there's no local clone, and `awaisali-TMC/VIM-Demo` (the likely source: same
  "TMC eInvoice" brand and the same 2026-10-05 date as `DEMO` @ `ec9d7f3`) returns "Repository
  not found" with this machine's GitHub credentials.
- **GCP:** `shahzaib.moin@tmcltd.com` has no permission on project `297345409494`.
Deploying *this* repo there is still not recommended: it would replace that app with Lucky
Cement code and branding.

**gcloud on this machine:** Google Cloud SDK 592.0.0, unpacked (no admin) to
`%LOCALAPPDATA%\Programs\google-cloud-sdk`. It is **not on PATH**, so call
`& "$env:LOCALAPPDATA\Programs\google-cloud-sdk\bin\gcloud.cmd" …`. It is signed in as
`shahzaib.moin@tmcltd.com`. Six symlinked gsutil docs/test-cert files could not be unpacked
(Windows symlink rights); gcloud doesn't use them. Claude Code's own shell does **not** see
this login (it reports "No credentialed accounts"), so run gcloud from the app's Terminal
panel or your own PowerShell.

**Upload check:** the repo root has no `.gcloudignore`, so `gcloud builds submit` falls back
to `.gitignore`. `gcloud meta list-files-for-upload .` lists 322 files, with no `.env`,
database, venv, `node_modules`, uploads or credentials sheet among them. Re-run it if the
ignore files change.

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

## 3. Deploy: resolved in session 2 (deployed to `lucky-cement-vim-web`, see §0)

Session 1's notes, kept for the record:

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
4. **Title fix: done** for `lucky-cement-vim-web` (§0). If vim-internal-web needs the same
   fix, it has to go in that app's own repo (location still unknown).
   Optionally view the signed-in Analytics page on the live site to confirm by eye.
5. **Extraction quality baseline.** Build a small golden set from `generate_demo_invoices.py`
   PDFs, and store the model id and prompt version with each extraction.

Lower priority: the remaining §4 items, lint cleanup, and code-splitting the two large chunks.
