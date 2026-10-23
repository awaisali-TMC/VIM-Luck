# VIM Lucky Cement — Full Project Context

This repository is the **complete, standalone codebase for the Lucky Cement Limited
presales (demo) instance** of TMC eInvoice (VIM). Read this file first, then `CLAUDE.md`
for codebase conventions. Last updated: 2026-10-23.

---

## 1. What this is and where it came from

- TMC eInvoice is an AP/invoice platform: vendors submit invoices (web upload, email,
  supplier portal, PO-flip), AI extracts the data (Gemini), FBR tax compliance is
  checked against the Active Taxpayer List, invoices are matched 2-way/3-way against
  purchase orders, routed through approval workflows, and parked/posted to SAP —
  **against a fixture ("fake") SAP on this instance** (§5). No real SAP is involved.
- Created 2026-10-23 as a fresh-history copy of `awaisali-TMC/VIM-Demo`, branch
  **`DEMO` @ `ec9d7f3`** (2026-10-05). `DEMO` was the latest branch: 23 commits ahead
  of VIM-Demo's `main`, 0 behind. It carries the fixture SAP connector, the SDK-optional
  backend image, the "Purchaser" role rename and line-selection parking, and it has
  **no Non-PO lane** (removed on `DEMO`; ignore Non-PO references in inherited docs).
- Re-branded to "Lucky Cement Limited" (browser titles + demo invoice bill-to).
- **Git**: `main` is the only branch, pushed to the private GitHub repo
  `awaisali-TMC/VIM-Luck` (`origin`). There is no CI trigger; deploys are manual (§3).
- **Isolation rule**: Lucky Cement-specific code stays HERE. Porting from VIM-Demo or
  the other customer repos is manual and on demand; nothing flows back.

## 2. Environment (shared presales GCP project)

Unlike the production customer instances (one GCP project each), this POC lives in
the **shared presales project** next to the other presales VIM/Satori demos, and
follows their `<cust>-vim-*` naming.

| Item | Value |
|---|---|
| GCP project | `tmc-presales-pocs` (name "TMC Presales POCs", number `527930147362`), org `401466922363` |
| Region | `us-central1` |
| Portal | https://lucky-cement-vim-web-527930147362.us-central1.run.app |
| Supplier portal | same host + `/supplier` |
| API | https://lucky-cement-vim-api-527930147362.us-central1.run.app |
| Cloud Run services | `lucky-cement-vim-api` (backend, 1CPU/1Gi, timeout 900s, **max 1 instance** — see §5), `lucky-cement-vim-web` (frontend, 1CPU/512Mi, max 4) |
| Cloud SQL | **shared** instance `presales-shared-pg` (Postgres 16, db-g1-small, us-central1-c, backups on) — other POCs' databases live on it too |
| Database / user | `lucky-cement-vim` / `lucky-cement-vim-app` |
| Artifact Registry | `us-central1-docker.pkg.dev/tmc-presales-pocs/presales-lucky-cement-vim` (`lucky-cement-vim-api`, `lucky-cement-vim-web`) |
| Service account | `lucky-cement-vim-sa@tmc-presales-pocs.iam.gserviceaccount.com` (runtime for both services) — `roles/cloudsql.client` + `secretAccessor` on its own secrets only, no keys |
| Secrets | `lucky-cement-vim-database-url`, `lucky-cement-vim-db` (DB user password), `lucky-cement-vim-gemini-api-key` (API key "lucky-cement gemini", restricted to `generativelanguage.googleapis.com`), `lucky-cement-vim-initial-admin-password` (first-boot seed only — **stale**, see §6), `lucky-cement-vim-supplier-demo-otp` |
| Public access | `run.googleapis.com/invoker-iam-disabled` annotation (`--no-invoker-iam-check`), same as the other presales services |

**Secrets/credentials are NOT in this repo.** The local sheet is
`content/VIM-PRD-CREDENTIALS.md` (git-ignored). Two different sources of truth:

- **Application logins live in the database** (`lucky-cement-vim.internal_users` /
  `supplier_users`, PBKDF2 hashes — a password cannot be read back, only checked or
  reset). Changes made in the app (Admin → Users → Reset Password) exist only there.
- **Infra secrets and the supplier demo OTP live in Secret Manager**:

```powershell
gcloud secrets versions access latest --secret=lucky-cement-vim-supplier-demo-otp --project=tmc-presales-pocs
```

The FBR ATL dataset (`atl_taxpayers`, 8,499,758 rows: IT 8,304,107 + ST 195,651) was
copied server-side on 2026-10-23 from the `ibrahim-fibers-vim` database on the same
instance (Cloud SQL CSV export → GCS → CSV import, `id` column left out so the
sequence stays valid for later `import_atl.py` runs). Counts verified after import;
the temporary transfer bucket was deleted.

## 3. Deploying (manual)

Cloud Build's identity in this project (`527930147362-compute@…`) can push images but
cannot deploy to Cloud Run, so build and rollout are two steps. From the repo root:

```powershell
$tag = git rev-parse --short HEAD
gcloud builds submit --config=cloudbuild.yaml --project=tmc-presales-pocs --substitutions=_TAG=$tag
$repo = "us-central1-docker.pkg.dev/tmc-presales-pocs/presales-lucky-cement-vim"
gcloud run deploy lucky-cement-vim-api --image="$repo/lucky-cement-vim-api:$tag" --region=us-central1 --project=tmc-presales-pocs
gcloud run deploy lucky-cement-vim-web --image="$repo/lucky-cement-vim-web:$tag" --region=us-central1 --project=tmc-presales-pocs
```

Image-only deploys keep every env var, secret, the Cloud SQL attachment, scaling and
public access. `cloudbuild.yaml` builds the backend with `--build-arg SAP_SDK=off`
under BuildKit (`DOCKER_BUILDKIT=1` — the legacy builder also builds the unused
`sap-on` stage and fails on its `COPY` of the absent SDK) and the frontend with
`API_BASE_URL` = the API URL above, **baked into the bundle at build time**.

Backend runtime configuration (set once at creation; change with
`gcloud run services update lucky-cement-vim-api --update-env-vars=…`):

| Env var | Value |
|---|---|
| `DEBUG` | `true` (required by `SAP_MODE=fake`; §5) |
| `SAP_ENABLED` / `SAP_MODE` | `true` / `fake` |
| `GEMINI_MODEL` | `gemini-3.5-flash` |
| `INITIAL_ADMIN_EMAIL` | `admin@tmcltd.com` |
| `CORS_ORIGINS` | both portal URLs (`…-527930147362.us-central1.run.app` and `…-wwmrdyz2sa-uc.a.run.app`) |
| `DATABASE_URL`, `GEMINI_API_KEY`, `INITIAL_ADMIN_PASSWORD`, `SUPPLIER_DEMO_OTP` | from the secrets in §2 |

## 4. No SAP SDK

The backend image is built without the licensed NW RFC SDK and without PyRFC
(`SAP_SDK=off`). It can only run with `SAP_MODE=fake`; a live RFC call would fail
with a message naming the build arg.

## 5. Demo posture — fake SAP, DEBUG on

- **`SAP_ENABLED=true` + `SAP_MODE=fake`**: PO/vendor/tax-code lookups, parking and
  posting are answered by `services/sap_connector_fake.py` from the fixtures in
  `services/sap_fixtures/` (invented POs `4500009001`–`4500009005`, `4700009001`–
  `4700009003`, vendors `00020001xx`). The demo story and failure cases each fixture
  encodes are listed in CLAUDE.md → "SAP_MODE=fake". `GET /api/sap/test` reports
  `"mode": "fake"`.
- **The fixture store is in memory** (`SAP_FAKE_DB_PATH` empty). It resets whenever the
  backend instance restarts (cold start after ~15 min idle, or a new revision), so a
  document parked before a restart is gone from "SAP" although the app DB still says
  *parked*. That is why the backend is capped at **one** instance: with two, each
  would hold its own SAP. For a long demo, warm the app up and run the flow in one go.
- **`DEBUG=true`** — the fake connector refuses to import otherwise. Consequences on
  this public URL: `/docs`, `/redoc` and `/openapi.json` are served, and dev-only
  detail such as supplier OTP codes is returned in API responses. Acceptable for a
  presales demo with invented data; **never** load real Lucky Cement data here.
- **Supplier login**: no SMS gateway; the `lucky-cement-vim-supplier-demo-otp` secret
  is a fixed, always-valid OTP for any verified supplier mobile.

## 6. Application knowledge (digest — details in CLAUDE.md)

- **Dual portal, one build**: `index.html` = internal portal, `supplier.html` =
  supplier portal. Separate localStorage token keys (`auth_token` vs `supplier_token`)
  — never "simplify" that split; it was a real auth-leak bug.
- **Brand** is "Lucky Cement Limited" in `frontend/src/config/brand.js` and both HTML
  entry points. The sidebar/login still show the TMC logo + "TMC eInvoice" wordmark.
- **Logins**: `admin@tmcltd.com` was seeded on first boot from the
  `lucky-cement-vim-initial-admin-password` secret, but its password was **reset in the
  app on 2026-10-23 06:47 UTC** (Admin → Users → Reset Password), so the database is
  now the only source of truth and the secret no longer works. The secret is only read
  when `internal_users` is empty. The seeded workflow
  "General Invoice Approval" routes AP Manager → Finance Director; those two users
  were created 2026-10-23: `apmanager@tmcltd.com` (`ap_manager`) and
  `financedir@tmcltd.com` (`finance_director`), both department Finance. Their
  passwords are only in `content/VIM-PRD-CREDENTIALS.md` (not in Secret Manager).
  One demo supplier exists: **TechServ Solutions (Pvt) Ltd**, SAP vendor `0002000105`,
  NTN `3456789-2`, placeholder mobile `03000000105`, logging in with the demo OTP. It
  owns fixture POs `4500009005` (packaging, line-selection story) and `4700009002`
  (service). A supplier's first "My POs" load is empty on a fresh database and kicks
  a background SAP sync; the POs appear on the next load (or "Refresh from SAP").
- **FBR ATL**: lookups hit the `atl_taxpayers` table (~8.5M rows). `GET /api/fbr/atl-stats`
  reads a local sqlite file and reports 0 on every cloud instance — not a health check.
- **Extraction**: single Gemini call (`gemini_extract.py`), model from `GEMINI_MODEL`,
  key from this instance's own restricted API key.
- **Demo invoices**: `py -3 backend/generate_demo_invoices.py` (needs
  `pip install reportlab`) writes PDFs billed to Lucky Cement Limited that match the
  fixture POs.

## 7. Outstanding

1. **Lucky Cement logo/branding art** — the UI still ships the TMC logo. Swap when
   assets are supplied.
2. **Demo users** — admin, AP Manager, Finance Director and supplier TechServ exist.
   No Purchaser (ex-AP Operator) by decision; other fixture vendors have no supplier
   login.
3. **Mobile app** (`mobile/`) untouched — still carries its own identity and stale URLs;
   set `EXPO_PUBLIC_API_URL` to this instance's API if a mobile demo is needed.
4. **Real SAP** — if this POC ever needs Lucky Cement's SAP: build the backend with the
   SDK (`SAP_SDK=on`, SDK tarball in a bucket), set `DEBUG=false`, `SAP_MODE=live`,
   the `SAP_*` connection env vars and a `sap-passwd` secret, and check egress (a
   SAProuter that filters source IPs needs a static egress IP via VPC connector + NAT).
