# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**TMC eInvoice** (internally "einv", legacy name "MEIn") — an Accounts Payable / invoice-management platform. It ingests vendor invoices (web upload, email, supplier portal, or PO-flip), extracts data with AI, runs Pakistan-specific FBR tax compliance checks, matches against purchase orders, routes through multi-level approval workflows, and posts to SAP.

**This repo is the standalone Lucky Cement Limited presales (demo) instance**, created 2026-10-23 as a fresh-history copy of `awaisali-TMC/VIM-Demo`, branch `DEMO` @ `ec9d7f3` (itself descended from the Hilton Pharma codebase). `main` is the only branch, pushed to the private GitHub repo `awaisali-TMC/VIM-Luck` (`origin`); there is no CI trigger — deploys are manual. **Read `CONTEXT.md` first** — it is the authoritative description of the environment (shared presales GCP project `tmc-presales-pocs`), how to deploy, the fake-SAP demo posture, and what is outstanding; it supersedes any inherited doc that mentions other instances.

Three deployable apps live in one repo:
- `backend/` — FastAPI (Python, async SQLAlchemy)
- `frontend/` — React 19 + Vite + Tailwind v4 (serves **two** portals from one build)
- `mobile/` — Expo / React Native (TypeScript, expo-router)

### This instance at a glance

| | |
|---|---|
| GCP project | `tmc-presales-pocs` (number `527930147362`, shared with other presales POCs), region `us-central1` |
| Portal | https://lucky-cement-vim-web-527930147362.us-central1.run.app (supplier portal at `/supplier`) |
| API | https://lucky-cement-vim-api-527930147362.us-central1.run.app |
| Cloud Run services | `lucky-cement-vim-api` (backend), `lucky-cement-vim-web` (frontend) |
| Database | `lucky-cement-vim` on the **shared** Cloud SQL instance `presales-shared-pg` (Postgres 16), user `lucky-cement-vim-app` |
| Posture | **Demo**: `DEBUG=true`, `SAP_ENABLED=true` + `SAP_MODE=fake` (fixture SAP, no real SAP anywhere), ~8.5M `atl_taxpayers` rows loaded |

Full environment table, secrets inventory and outstanding items: `CONTEXT.md`.

## Commands

**The repo is worked on from two machines — check which one you are on.** The commands below are written for the original **Windows** box (`D:\VIM\VIM-Luck`): use `py -3`, not `python`/`python3`. On the **Linux** box (`/home/lcladmin/VIM-Luck`) there is no `py`: use the git-ignored venv, `backend/.venv/bin/python` (e.g. `backend/.venv/bin/python backend/test_sap_fake.py`); Node/npm live in `~/.local/bin`. That box sits behind a Fortinet TLS-inspecting proxy, so export `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` or every Gemini call fails with `CERTIFICATE_VERIFY_FAILED`. `./start-lan.sh` (local helper, not product) starts backend :8000 + frontend :5173 with that set; laptops reach it through an SSH tunnel and the frontend calls `http://localhost:8000` via the git-ignored `frontend/.env.local`.

```powershell
# Backend (from backend/) — runs on :8000
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000   # add --reload for dev
pip install -r requirements.txt                            # deps (no venv is committed)
# Config: copy backend/.env.example to backend/.env. Its defaults are local dev (SQLite, SAP off);
# to reproduce this instance's demo behaviour locally set DEBUG=true, SAP_ENABLED=true, SAP_MODE=fake.

# Frontend (from frontend/) — runs on :5173
npm install
npm run dev          # internal portal at /, supplier portal at /supplier/ (vite middleware serves supplier.html for /supplier/*)
npm run build        # multi-entry Vite build (index.html + supplier.html)
npm run lint         # eslint (flat config in eslint.config.js)

# Mobile (from mobile/)
npx expo start --web --port 8085
```

### Tests

Backend tests are **standalone scripts, not pytest**. Each is a `__main__` entry point that spins up a FastAPI `TestClient` and overrides `get_current_principal` to fake auth. Run one directly:

```powershell
py -3 backend/test_po_flip.py               # PO-flip API (supplier-only endpoints)
py -3 backend/test_supplier_vendor_gate.py  # supplier vendor-name gate
py -3 backend/test_sap_fake.py              # fixture SAP connector: contract + demo path, offline (forces DEBUG/SAP_MODE=fake itself)
py -3 backend/test_line_item_guards.py      # zero-quantity goods lines must not reach SAP, offline
py -3 backend/test_role_labels.py           # role display-name renames, offline; own throwaway DB
py -3 backend/test_invoice_document.py      # original invoice file view/download + path guard, offline; own temp DB + upload dir
py -3 backend/test_duplicate_check.py       # duplicate-invoice key blocks approval/SAP, offline; fake SAP, own throwaway DB
py -3 backend/test_po_regression.py         # PO-lane BASELINE: live SAP validate dry-run (needs SAP env)
```

`test_role_labels.py` defaults to a temp SQLite file; set `ROLE_LABELS_DB=postgresql+asyncpg://…` to run it against a throwaway Postgres 16 (the run that matters — SQLite ignores the `VARCHAR` lengths and unique constraints Postgres enforces). It refuses to start against anything that looks like a real database. Docker recipe: `backend/README-role-labels-test.md`.

**There is no real SAP behind this instance**, so the live scripts only run where an SAP system, the NW RFC SDK and its credentials are available (they were written against OGDCL DEV; `test_po_regression.py` defaults to that system's PO `4500000378`). The live scripts open real RFC connections (validate mode parks and rolls back, so SAP is never changed) and need `SAP_PASSWD` etc. in the environment. Run them from PowerShell, not Git Bash: MSYS rewrites `SAP_SAPROUTER=/H/...` into a Windows path. `test_po_regression.py` writes a normalized transcript to `REG_TRANSCRIPT_OUT`; run it before and after any change near the PO flow and diff the two files.

`backend/drop_nonpo_objects.py` is a one-off that clears the database objects left by the removed Non-PO lane (report-only without `--yes`); it is deliberately not in `run_migrations()`, which runs on every instance at startup. `backend/seed_test_data.py` seeds realistic Pakistani PO/invoice data for manual testing. The other `test_sap*.py` scripts (`test_sap.py`, `test_sap_po*.py`, `test_sap_delivery_probe.py`) are live SAP-connectivity probes and only work on a machine with the NW RFC SDK + network access to the SAP host. There is no frontend/mobile test suite.

## Architecture

### Dual-portal frontend (one build, two entry points)
`vite.config.js` declares two HTML inputs:
- `index.html` → `main.jsx` → `App.jsx` — **internal/admin portal** (staff)
- `supplier.html` → `supplier-main.jsx` → `SupplierApp.jsx` → `SupplierPortal.jsx` — **external supplier portal**

Both portals share an origin and therefore `localStorage`. They must use **separate token keys**: internal = `auth_token`, supplier = `supplier_token`. `frontend/src/services/api.js` picks the key with an exact-path test (`/^\/supplier(\.html)?($|\/)/`) — crossing the keys lets one portal impersonate the other identity type (a real auth-leak bug, commit `7cda57f`), and a looser `includes("supplier")` match once caught the internal `/suppliers` admin route and sent the supplier token to admin endpoints. Do not "simplify" that test.

The browser-tab title uses the customer name "Lucky Cement Limited" (re-branded 2026-10-23 from VIM-Demo's product name "TMC eInvoice"): `frontend/src/config/brand.js` builds "`<page>` · Lucky Cement Limited" for the internal portal, **plus static titles in both HTML entry points** (the supplier portal never sets its title from JS, so `supplier.html`'s "Supplier Portal · Lucky Cement Limited" is all it shows). Title changes touch all three places; `brand.js` is a fixed string (the old shared-build hostname sniffing was removed). The visible UI brand is separate and not yet Lucky Cement: the sidebar (`components/layout/Layout.jsx`) shows the TMC logo + "TMC eInvoice", and the login page shows a "cognivend" wordmark (split across two `<span>`s, so grepping for `cognivend` misses it) with a "Powered By" TMC logo.

### Navigation: both portals use React Router
The **internal portal** is a `<Routes>` tree in `App.jsx` (`/`, `/ap`, `/upload`, `/results`, `/invoices`, `/invoices/:id`, `/po/*`, `/approvals`, the admin pages). Every route is wrapped in `guard(path, element)`, which renders the page only if `canAccessPath(role, path, matrix)` allows it and otherwise redirects to the role's home. In-flight extraction results do **not** live in the URL: `UploadInvoicePage` hands them to `ExtractionContext` (`handleExtractionComplete`), `/results` reads them from there, and `handleSave` builds the `/api/invoices/save` payload from that context. `/results` shares the `/upload` permission key (`pageKey()` in `config/rolePermissions.js`).

The **supplier portal uses React Router** with basename `/supplier` (`supplier-main.jsx`): `/supplier/dashboard`, `/pos`, `/upload(/review)`, `/invoices`, `/invoices/:id`, `/tracker`, `/profile`. Raw entry hits (`/supplier.html`, `/supplier`) normalize to `/supplier/dashboard`. `frontend/nginx.conf` serves `supplier.html` for `/supplier/*` (trailing-slash prefix, so the internal `/suppliers` admin route stays with the internal SPA); a vite middleware in `vite.config.js` mirrors that fallback for dev/preview.

`mobile/` uses expo-router file-based routing under `mobile/app/`.

### Dual-principal auth (`backend/app/security.py`)
Two principal types share the API:
- **Internal users** (`InternalUser`) — email/password login, one of 8 built-in roles (`admin`, `ap_manager`, `ap_operator`, `tax_manager`, `procurement_manager`, `auditor`, `finance_director`, `department_head`). Display names come from a `roles` table (`role_labels()` in `routers/role_permissions.py`), where `ap_operator` is labelled **"Purchaser"** and admins can rename roles or add custom (non-system) ones. Authorization always checks the role **key**, never the label. Page access is a role × page matrix stored in `role_permissions` and mirrored client-side by `canAccessPath()` in `frontend/src/config/rolePermissions.js`.
- **Suppliers** (`SupplierUser`) — OTP login + self-signup, approved by an admin.

Both authenticate by an opaque session token sent as `Authorization: Bearer <token>` (preferred) or `?token=` query param (deprecated, leaks into logs). Key dependencies:
- `get_current_principal` — accepts **either** type; gates shared business endpoints.
- `get_current_internal_user` / `get_current_supplier` — single-type.
- `require_admin` / `require_roles(*roles)` — RBAC factories over internal users.

**Object-level scoping (e.g. a supplier seeing only their own invoices) is enforced inside individual routes, not by these dependencies.**

The token lives on the principal's own row (`internal_users.auth_token` + `token_issued_at`), so a login replaces the previous session. `TOKEN_TTL_HOURS` (default `720` = 30 days; `0` disables expiry) rejects older tokens; rows with a NULL `token_issued_at` predate the feature and are never force-expired.

### Route protection is declared at include-time (`backend/app/main.py`)
Routers are mounted with a dependency that gates *every* route in them:
- **public** (no dep): `auth.router` (supplier OTP/signup), `internal_auth_router` (internal login).
- **admin-only** (`admin_dep`): supplier admin, internal user admin, email inbox.
- **authenticated** (`auth_dep`): everything else (invoices, POs, FBR, workflows, approvals, analytics, SAP, etc.).
- **role-gated at include time**: `reports.router` alone is mounted with `require_roles("admin", "ap_operator")`.

A router in the `auth_dep` tier can still tighten individual routes with their own dependency — `role_permissions` mounts under `auth_dep` but gates its mutations on admin per-route. When adding a router, mount it in the right tier here — the routes themselves often assume the principal already exists.

### Startup lifecycle (`lifespan` in `main.py`)
On boot, in order: write GCP creds (file path locally, base64 `GCP_CREDENTIALS_JSON` in cloud) → `init_db()` (create tables from models) → `run_migrations()` → seed-if-empty (admin user, default workflow template, GL accounts, tax rules, products) → start the product-matching queue worker.

- **`init_db()`** (in `app/database.py`, like `run_migrations()`) calls `Base.metadata.create_all`. Every model module must be imported in `database.py` so its table registers — that's why there's a wall of `# noqa: F401` imports there.
- **`run_migrations()`** is a hand-rolled migration list of idempotent `ALTER TABLE ... ADD COLUMN` statements, **each in its own transaction**. There is no Alembic. To add a column: add the field to the model *and* append an `ADD COLUMN` line to the `migrations` list. Per-statement transactions matter on Postgres (one failed/duplicate statement would otherwise poison the rest); on SQLite each statement auto-commits anyway.
- **Admin bootstrap**: only seeds when `internal_users` is empty, using `INITIAL_ADMIN_EMAIL` (default `admin@tmcltd.com`) and `INITIAL_ADMIN_PASSWORD`. If no password is set, a random one is generated and logged once (printed in full only when `DEBUG=True`).

### AI extraction pipeline
The **active** extraction path is `app/services/gemini_extract.py` — a single Gemini call that returns fields + line items + detected taxes in one pass. It **replaced** the older 3-step Document AI → Gemini-tax → Gemini-line-items pipeline; `document_ai.py` and the per-step `gemini_*` services are legacy/secondary. There is also a parallel **ADK agent** (`app/agents/invoice_agent.py`, an `LlmAgent` with function tools in `tools.py`) that wraps the same services and is exposed via `routers/agent_invoices.py` (and runnable with `adk web app/agents`).

**The model id is one setting, never a literal.** All 7 Gemini call sites — 6 files: the five `gemini_*` services (`gemini_extract.py` has two) plus the ADK agent — pass `model=settings.GEMINI_MODEL`, so `GEMINI_MODEL` in `.env` or as a Cloud Run env var moves every one of them at once, with no rebuild. Default `gemini-3.5-flash`. Do not reintroduce a hard-coded id. An unknown id is not validated at startup — it fails on the first API call — and Google retires ids for new API projects (`gemini-2.5-flash` began 404ing on 2026-08-31). The ADK agent binds `model=` at **import time**, so it needs a process restart (a new Cloud Run revision) to pick up a change; the services read it per call.

**`os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"` is set at the top of `main.py` before any `google.adk` import** — Vertex AI's function-calling schema rejects ADK's auto-generated fields. Don't move or remove it. ADK reads `GOOGLE_API_KEY`; the app bridges `GEMINI_API_KEY` → `GOOGLE_API_KEY` in `invoice_agent.py`.

### Serial product-matching queue (`routers/invoices.py`)
Product matching runs through a single background `asyncio.Queue` worker (`start_matching_queue` / `stop_matching_queue`, wired into lifespan) so Gemini matching calls happen one-at-a-time in FIFO order rather than concurrently. After saving an invoice with `pending_processing` status, the frontend fires `matchProducts(id)` to enqueue it.

### Invoice status state machine
Defined as `VALID_TRANSITIONS` in `routers/invoices.py`. Status PATCH endpoints validate against it:
```
draft → pending_processing → validated → pending_approval → approved → parked → posted
                                  ↘ parked / posted (if no workflow matches)
   parked  = parked in SAP, waiting for a SAP user to post (or reverse) it — the
             normal path on this instance (parked in the fixture SAP, SAP_MODE=fake)
   rejected / exception are recoverable; posted is terminal
```
The two steppers have **diverged** — check the one you're editing rather than assuming: web `frontend/src/components/detail/WorkflowStepper.jsx` renders **4** steps (Received → Validated → Approval → ERP Posting) and folds `parked` into the ERP Posting step by relabelling it, while mobile `StatusStepper.tsx` still renders **5** (Received → Validated → Pending Approval → Approved → ERP Posting) with no `parked` handling. `mobile/src/services/calculations.ts` mirrors the web calculation logic.

### Duplicate invoice check (`services/duplicate_detection.py`)
Lucky Cement's rule: an invoice is a **duplicate** of an *earlier* live invoice (not deleted, not `exception`) with the same **Reference** (invoice number, case/space-insensitive), **PO**, **NTN**, **SAP vendor** and **company code**. Reference and PO must match. NTN, vendor and company code must match wherever both invoices carry them; a value missing on one side is skipped rather than letting a duplicate through. PO, vendor and company code come from the matched PO, falling back to the PO number printed on the invoice. NTNs compare on their 7-digit base, so `5433744-3` = `5433744`.
- **Blocking, server-side (409):** `POST /api/approvals/invoice/{id}/initiate`, every mode of `POST /api/sap/invoices/{id}/post` (so the submit-time dry run catches it), and `PATCH /api/invoices/{id}/status` to `pending_approval`/`approved`/`parked`/`posted`. Saving is never blocked, because the PO is usually unknown at upload.
- **Only earlier invoices count**, so the original is never blocked by a later re-send. To release a copy, delete it or mark the original `exception`.
- The PO's company code is `purchase_orders.company_code`, set on every SAP sync and backfilled at park. POs synced before it existed have none until they're parked.
- The older checks (same number from any supplier; same NTN + amount ±1% + date ±7 days; same amount + date) remain as **advisory** banner warnings. `DuplicateWarningCard` shows the blocking case first.

### FBR tax compliance (Pakistan-specific)
FBR = the Pakistani tax authority. The app verifies supplier NTNs against the **Active Taxpayer List** and computes WHT/GST compliance. Live IRIS API lookup is **disabled by default** (`FBR_LIVE_LOOKUP_ENABLED=False`). ATL lookups (`services/fbr_verification.py`) prefer the app DB's `atl_taxpayers` table (imported on this instance, ~8.5M rows) and fall back to a local SQLite file at `FBR_ATL_DB_PATH` (dev only). `GET /api/fbr/atl-stats` reads **only** the SQLite file, so it reports 0 on every cloud instance — never use it as a health check. The tax-rules engine (`tax_rule.py` + seeded defaults in `main.py`) holds GST/WHT/SED/FED rates with FBR section references.

### SAP integration (`services/sap_connector.py`) — FAKE on this instance (fixture connector, see `SAP_MODE=fake` below)
Platform-split connector, both paths through a SAProuter: on Windows a direct **ctypes binding to `sapnwrfc.dll`**; on Linux (the Docker image) **PyRFC** (`pyrfc.Connection`, needs `libsapnwrfc.so` on `LD_LIBRARY_PATH`). SAP host/credentials come from `SAP_*` settings. Used for PO fetch and invoice posting (`sap_po_service.py`, `sap_invoice_post.py`).

**`settings.SAP_ENABLED` gates all live RFC calls** (checks live in `routers/sap.py`). This instance runs `SAP_ENABLED=true` with `SAP_MODE=fake`, so every call is answered by the in-process fixture connector — no real SAP system is reachable from it, and its image is built `SAP_SDK=off` (no PyRFC). The live connector described here is inherited product code (it was LIVE against OGDCL DEV on the Hilton instance this codebase came from); pointing this instance at a real SAP would need an SDK image build, `DEBUG=false`, `SAP_MODE=live` and real `SAP_*` settings. Connectivity check: `GET /api/sap/test`. **The two connector paths differ where it matters most:** PyRFC (production) **raises** on an unknown BAPI/structure field name, while the Windows ctypes path silently ignores it, so a wrong field works locally and fails only in production. Verify every new field against `DD03L` / `FUPARAREF` on the target system (RFC_READ_TABLE, read-only) before sending it. The SAProuter hop also times out on the first connect now and then and succeeds on retry. (For contrast, on an SAP-less instance — `SAP_ENABLED=false` — parking validation is assumed to pass, parking/posting is *simulated* with a placeholder document number, and the SAP-backed dropdowns fall back to static defaults, so the approval flow still runs end-to-end. Don't mistake that fallback behaviour for this instance's.)

**`SAP_MODE=fake` — the fixture connector (demos and offline tests).** A third `SAPConnector` implementation, `services/sap_connector_fake.py`, answers RFC calls from an in-memory SQLite database whose tables carry SAP's real names (`EKKO`, `EKPO`, `LFA1`, …), seeded from `services/sap_fixtures/*.sql`. It exists because `RFC_READ_TABLE`'s `OPTIONS` rows concatenate into a clause SQLite already understands verbatim (`EBELN = '…' AND LOEKZ = ''`, `NAME1 LIKE 'X%'`, `BEDAT >= '…'` — SAP dates are YYYYMMDD strings, so range comparisons are string comparisons), so the whole read path is one SELECT rather than a hand-rolled evaluator. It holds state: parking `INSERT`s into `RBKP` so a later unpark finds the document, and `BAPI_TRANSACTION_ROLLBACK` genuinely discards, which makes `mode="validate"` non-mutating exactly as against real SAP.

- **Two switches, and confusing them is the usual mistake.** `SAP_ENABLED` decides whether the routers take the SAP path at all; `SAP_MODE` decides which connector answers. A demo needs **`SAP_ENABLED=true` AND `SAP_MODE=fake`** — `SAP_ENABLED=false` short-circuits before the connector and gives you the old placeholder simulation, with no POs to match against.
- **It cannot load in production.** `sap_connector.py` only imports it when `SAP_MODE == "fake" and settings.DEBUG`, and the module itself raises on import when `DEBUG` is false. Both gates are deliberate: a fake connector in production would report parking successes for invoices that were never sent anywhere.
- **Everything it touches is labelled.** `GET /api/sap/test` returns `"mode": "fake"` and reports the host as `in-process fixtures` rather than echoing the live `SAP_ASHOST` — a green run here proves the app's plumbing, not that SAP accepted anything, and a screenshot should not be able to imply otherwise.
- **Fixture identifiers are invented** (PO `4500009001`, vendor `0002000101`, delivery note `DN-2026-00417`), matching SAP's formats but copying no real master data — this data goes on screen in front of customers. PO `4500009002` is scripted to fail park with a blocked-vendor `TYPE: "E"`, so the error path can be demonstrated; add more in `sap_fixtures/scripted.json`.
- Adding a table means adding it to `schema.sql` — an unknown table or column **raises** rather than returning an empty result, because a silent empty table is indistinguishable from "SAP has no such row".
- **To see what was actually parked, set `SAP_FAKE_DB_PATH`.** Empty (the default) keeps the store in memory, so every run starts from the same fixtures; set a path and it becomes a SQLite file you can open in any DB browser *while the app is running* — which is also the most convincing thing to show in a demo, since it is the fixture equivalent of opening SE16 on `RBKP`. It seeds once and then persists across restarts; `rm backend/sap_fake.db` resets it (a stale demo database still holding yesterday's documents is the failure mode to watch for).
  ```powershell
  py -3 backend/sap_se16.py RBKP                              # A = parked, 5 = posted
  py -3 backend/sap_se16.py EKPO -w "EBELN = '4500009001'"    # no args lists tables; --csv exports
  ```
  `sap_se16.py` opens the file read-only (safe mid-demo) and needs no `sqlite3.exe`, which Windows usually lacks. The deployed instance leaves `SAP_FAKE_DB_PATH` empty, so its "SAP" resets on every cold start or new revision while the app DB still says *parked* — that is why `lucky-cement-vim-api` is capped at **one** Cloud Run instance (two would each hold their own SAP). Don't raise that limit.
- **The demo story the fixtures encode**, and the shapes worth showing: `4500009001` goods PO with a goods receipt and freight — parks cleanly; `4700009001` and `4700009002` service POs confirmed by entry sheets `1000009001` / `1000009002` — value-based, no quantity sent; `4500009002` — reaches SAP and is **refused** (vendor blocked); `4500009003` — stopped *before* SAP by the app's own GR-based-IV pre-check, because no goods receipt exists; `4700009003` — its service twin, stopped before SAP because no entry sheet was ever accepted; `4500009004` — partial delivery (18 of 30 received), with two invoices: billing 30 fails the 3-way match (`mismatch`), billing 18 is a `partial_match` and parks; `4500009005` — three packaging items, fully received, for the line-selection story: every invoice line starts checked, so a clean three-line invoice parks; one with a freight line the PO does not carry shows that line as "not on PO", blocks Submit until it is unchecked or deleted, and is refused by name if parked anyway (a parked line must sit on a PO item); and a goods line whose text says "DELIVERY INFO" is just a goods line. `backend/generate_demo_invoices.py` writes matching invoice PDFs (needs `pip install reportlab`, which is deliberately not in `requirements.txt`), plus variations against the original POs that need no fixture data: a price difference (+2.7%, over the 2% tolerance), a quantity difference (22 billed vs 20), a re-sent `HP-2026-0417` (blocked as a duplicate once matched to its PO), a credit note (Classify → Apply turns on the Credit/Debit Note card), a 17% invoice (tax code `I2`), and one with no PO number (find the PO by vendor name in the PO search — the UI only auto-suggests when the invoice has a PO reference). Their dates are spread out so only the re-send trips the duplicate check.
- **The 3-way match screen shows a service PO's confirmation as a GRN, not an SES.** `POST /api/sap/pos/{po}/grn/sync` imports every SAP receipt document (EKBE `VGABE=1`) as a `GoodsReceivedNote`, including the one an accepted entry sheet posts; SES records in the app are only created by hand (`POST /api/purchase-orders/{id}/ses`), so adding one on top double-counts. Parking is unaffected — it reads the sheet number from EKBE-LFBNR (`fetch_service_grn_refs`). This is the original product behaviour, kept deliberately.
- **Building the backend image without the SDK:** `docker build --build-arg SAP_SDK=off … backend`. The licensed NW RFC SDK is git-ignored and pulled from a GCS bucket by the pipeline, so a laptop build has no copy and `COPY nwrfcsdk-linux` fails at build time whatever `SAP_MODE` says. The arg defaults to `on`; **this instance's `cloudbuild.yaml` passes `SAP_SDK=off` and sets `DOCKER_BUILDKIT=1`** — Cloud Build's legacy builder otherwise builds the unused `sap-on` stage too and fails on its `COPY`. An `off` image has no PyRFC: `SAPConnectorPyRFC.__init__` raises a message naming the build arg rather than a bare `ImportError`, and the image is only usable with `SAP_MODE=fake`.
- Covered by `py -3 backend/test_sap_fake.py` (offline, no SAP, no Gemini): the connector contract, WHERE semantics, the invoice BAPIs, the PO and master-data services, both gates, and the full upload → match → park flow over HTTP. Re-runnable against an existing `invoices.db`.

## Conventions & gotchas

- **Config**: pydantic-settings in `app/config.py`, loaded from `backend/.env`. `settings.DEBUG` (default `False`) gates `/docs`, `/redoc`, `/openapi.json` and dev-only secret leakage (e.g. returning OTP codes in responses). **This instance runs `DEBUG=true`** — required by `SAP_MODE=fake`; it is a demo, not a production posture (see `CONTEXT.md` §5).
- **Supplier OTP**: there is no SMS gateway — a fixed, always-valid demo OTP stored in the app DB (`app_settings` row `supplier_demo_otp`, model `models/app_setting.py`, admin-only API `routers/app_settings.py` at `/api/admin/settings/supplier-demo-otp`) is the **only** way a supplier can log in on this instance. Admins set or disable it under **Admin → Suppliers**. It is not an env setting any more; don't put `SUPPLIER_DEMO_OTP` back in `.env` (pydantic-settings rejects unknown dotenv keys, so startup fails) (`CONTEXT.md` §5).
- **Logins**: only the `admin` user is ever seeded (`INITIAL_ADMIN_EMAIL`, default `admin@tmcltd.com`). `ap_manager`, `ap_operator`, `finance_director` and every supplier must be created through the admin UI (**Admin → Users** / **Suppliers**) or `POST /api/admin/users` / `POST /api/admin/suppliers`. Because the seeded default workflow routes **AP Manager → Finance Director**, no invoice can clear approval until those two accounts exist. `content/VIM-PRD-CREDENTIALS.md` (git-ignored) is the credential sheet — infra secrets, the account list and the Secret Manager fetch commands. Any `@ogdcl.com` login you find in an inherited doc or in git history belongs to the OGDCL instance and does not exist here.
- **Operational scripts** (in `backend/`, all `py -3`, all targeting `DATABASE_URL` — so a cloud run needs cloud-sql-proxy): `import_atl.py <file> --type IT|ST` re-imports FBR's Active Taxpayer List from its published multi-sheet Excel workbooks into `atl_taxpayers`, **replacing** the snapshot for that list type. `update_fbr_data.py`, `add_sap_posting_columns.py` and `update_file_paths.py` are one-off maintenance scripts, not part of any pipeline.
- **DB**: SQLite (`sqlite+aiosqlite`) in dev, Postgres-capable (`asyncpg` is a dependency) in prod via `DATABASE_URL`. All DB access is async.
- **CORS**: explicit allowlist in `settings.CORS_ORIGINS` (no wildcard); override per-env via the `CORS_ORIGINS` env var (JSON list).
- **Frontend styling**: Tailwind v4 with custom tokens. Design tokens live in `src/index.css` (CSS theme) and `src/styles/tokens.js` (JS palettes). The display brand comes from `brand.js` (a fixed string — see above).
- **Deployment (manual, no trigger)**: `gcloud builds submit --config=cloudbuild.yaml --project=tmc-presales-pocs --substitutions=_TAG=<short sha>` builds and pushes both images (backend `SAP_SDK=off`; frontend gets `--build-arg API_BASE_URL=<backend URL>`, baked at build time) to `us-central1-docker.pkg.dev/tmc-presales-pocs/presales-lucky-cement-vim`. Cloud Build's identity in this project can push but **not** deploy, so rolling out is a separate `gcloud run deploy <svc> --image=… --region=us-central1` run as yourself for `lucky-cement-vim-api` and `lucky-cement-vim-web`. Image-only deploys keep env vars, secrets, the Cloud SQL attachment and public access. Public access uses the `run.googleapis.com/invoker-iam-disabled` annotation (`--no-invoker-iam-check`). Exact commands, environment table and secrets inventory: `CONTEXT.md` §2–3.
- **The frontend's API URL is baked in at build time**, not read at runtime: `api.js` uses `VITE_API_BASE_URL` (falling back to `http://localhost:8000`), which comes from the git-ignored `frontend/.env.production` that `frontend/Dockerfile` writes from its `API_BASE_URL` build arg. The arg is deliberately **not** named `VITE_*` — Docker ARGs become env vars during `RUN`, Vite prefers env vars over `.env.production`, and an empty `VITE_API_BASE_URL` would silently blank the URL and send the deployed bundle to localhost. Don't rename it. Pointing a build at a different backend means a rebuild, not an env-var change.
- **Repo isolation**: Lucky Cement-specific code stays in this repo. The codebase is VIM-Demo's `DEMO` branch as of 2026-10-05 (Hilton → Martin Dow → product trunk lineage); porting newer work from VIM-Demo or the customer repos is manual and on demand only, and nothing flows the other way.
- **`mobile/` is not deployed by this instance and was skipped by the re-brand**: its `package.json` still carries `start:vim` / `start:martindow` scripts pointing at old shared backends, and the app keeps its own identity. Set `EXPO_PUBLIC_API_URL` to this instance's API before running it (`CONTEXT.md` §7).
- **Legacy deploy files**: `render.yaml` (Render) and `frontend/vercel.json` (Vercel) predate Cloud Run — ignore them.
- **Stale docs**: any doc mentioning GCP project `einvoicing-document-ai-487908`, services `martin-dow-backend`/`martin-dow-dev`, or DB `martindow` on `einv-pg` describes the OLD shared environment — `CONTEXT.md` wins. The Non-PO invoice lane was removed on VIM-Demo's `DEMO` branch, so ignore Non-PO references in inherited docs and comments. `frontend/CODEBASE_INVENTORY.md` predates auth/RBAC and most pages ("Authentication: None", 4 pages) — treat it as historical. `HANDOFF.md` and `## TMC eInvoice — Feature Summary.txt` track feature status and what's left to build. `SESSION-HANDOVER.md` is the running log of what earlier Claude Code sessions did (deploys, local `.env` fixes, open items), newest first — read it after `CONTEXT.md` when picking work back up.
