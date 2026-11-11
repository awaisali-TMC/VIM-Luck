import json
from pathlib import Path

from pydantic_settings import BaseSettings

# Absolute path to backend/.env (config.py lives at backend/app/config.py), so the
# file is loaded no matter what working directory the process is started from.
# A relative "env_file" is resolved against the CWD: launched outside backend/, the
# app would silently ignore .env and fall back to the defaults below — e.g. talking
# to the wrong SAP system instead of the one configured here.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # Debug / development toggles. Keep DEBUG=False in production — it gates
    # dev-only conveniences that leak secrets (e.g. returning OTP codes in API
    # responses). Override via env DEBUG=true for local development.
    DEBUG: bool = False

    # Session token lifetime (hours). A token older than this is rejected and
    # the user must log in again. Set 0 to disable expiry. Tokens issued before
    # this feature existed (NULL token_issued_at) are not force-expired.
    TOKEN_TTL_HOURS: int = 720  # 30 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./invoices.db"

    # Google Document AI
    GCP_PROJECT_ID: str = ""
    GCP_LOCATION: str = "us"
    DOCAI_PROCESSOR_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = "./service-account-key.json"
    # Base64-encoded service account JSON — used in cloud deployments (Render, etc.)
    # If set, takes priority over GOOGLE_APPLICATION_CREDENTIALS file path
    GCP_CREDENTIALS_JSON: str = ""

    # Gemini AI
    GEMINI_API_KEY: str = ""
    # ONE switch for every Gemini call site (extraction, segmentation, PO extract, tax,
    # line items, product matching, ADK agent). Override per instance with the
    # GEMINI_MODEL env var on the Cloud Run service — no rebuild needed. Google retires
    # model ids for new API projects (gemini-2.5-flash -> 404 on 2026-08-31).
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 20
    # Whether uploaded INVOICE files are persisted to disk. True on a real server
    # (files land in UPLOAD_DIR/<uploader>/, see services/file_storage.py). Set
    # False on Cloud Run so uploads are extracted but NOT saved to the Storage
    # bucket — there is no file to view/download for cloud-uploaded invoices.
    SAVE_UPLOADS: bool = True

    # Gmail IMAP (for email invoice inbox)
    GMAIL_ADDRESS: str = ""
    GMAIL_APP_PASSWORD: str = ""
    GMAIL_IMAP_HOST: str = "imap.gmail.com"
    GMAIL_IMAP_PORT: int = 993
    GMAIL_FETCH_FOLDER: str = "INBOX"
    GMAIL_MAX_FETCH: int = 50

    # FBR Active Taxpayer List — IRIS 2.0 integration
    FBR_ATL_DB_PATH: str = "D:/Anas-sb-Project/FBR-Scrapping/fbr_atl_project/atl.db"
    FBR_API_URL: str = "https://api.fbr.gov.pk/iris2ovs/v1/getdata"
    FBR_IRIS_JS_INDEX: str = "https://iris.fbr.gov.pk/public/ATL"
    FBR_LIVE_LOOKUP_ENABLED: bool = False
    FBR_REQUEST_TIMEOUT: int = 30
    FBR_MAX_RETRIES: int = 3
    FBR_RETRY_DELAY: int = 2          # seconds between retries
    FBR_TOKEN_CACHE_TTL: int = 3600   # seconds to cache extracted JWT (1 hour)
    FBR_BATCH_DELAY: float = 0.5      # seconds between batch API calls
    FBR_USER_ID: str = ""
    FBR_PASSWORD: str = ""
    # FBR Protocol IDs (service codes for different ATL lists)
    FBR_PROTOCOL_INCOME_TAX: str = "1004"
    FBR_PROTOCOL_SALES_TAX: str = "1005"
    FBR_PROTOCOL_AJK: str = "3001"

    # SAP RFC Connection
    # SAP_ENABLED gates all live SAP RFC calls. Set False on instances that have
    # no SAP landscape yet (e.g. the Martin Dow demo): parking VALIDATION is
    # then assumed to pass, parking/posting is SIMULATED (a placeholder document
    # number is stamped), and the SAP-backed dropdowns fall back to static
    # defaults — so the approval flow works end-to-end without a real SAP.
    SAP_ENABLED: bool = True
    # SAP_MODE picks the connector implementation, and is NOT the same switch as
    # SAP_ENABLED above:
    #   "live"  the real RFC connector (ctypes on Windows, PyRFC on Linux)
    #   "fake"  an in-process connector backed by fixture data — for local demos
    #           and offline tests. Requires DEBUG=True; the module refuses to
    #           import otherwise, so it can never load in production.
    # A demo needs SAP_ENABLED=true AND SAP_MODE=fake: enabled so the routers take
    # the real code path and actually reach the connector, fake so the connector
    # is the fixture one. SAP_ENABLED=false bypasses the connector entirely and
    # gives you the old placeholder simulation instead.
    SAP_MODE: str = "live"
    # Where the fake connector keeps its fixture database.
    #   ""        in memory — rebuilt on every process start, so demos repeat
    #             identically and nothing leaks between runs (the default)
    #   <path>    a SQLite file you can open in any DB browser while the app
    #             runs, to see for yourself what was parked. Seeded on first
    #             use; afterwards it persists across restarts. Delete the file
    #             to reset. Only consulted when SAP_MODE=fake.
    SAP_FAKE_DB_PATH: str = ""
    SAP_NWRFC_SDK_PATH: str = "C:\\nwrfcsdk"
    SAP_ASHOST: str = "10.50.210.212"
    SAP_SYSNR: str = "00"
    SAP_CLIENT: str = "400"
    SAP_USER: str = ""
    SAP_PASSWD: str = ""
    SAP_SYSID: str = "523"
    SAP_SAPROUTER: str = "/H/103.111.160.96"
    # Key used to encrypt per-user SAP passwords at rest (internal_users.
    # sap_password_enc). A urlsafe-base64 Fernet key, or any string (it is then
    # hashed into one). If empty, a fixed derived key is used with a warning —
    # set a real value in production. Changing it makes stored SAP passwords
    # undecryptable (users must re-enter them). See services/sap_credentials.py.
    SAP_CRED_KEY: str = ""

    # CORS — explicit allowlist (no wildcard). Override via env CORS_ORIGINS
    # (JSON list) to add/replace origins per environment.
    CORS_ORIGINS: list[str] = [
        "https://einv-frontend-656805782370.asia-south1.run.app",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8081",
    ]

    # Initial admin bootstrap (only used when internal_users table is empty).
    # Leave INITIAL_ADMIN_PASSWORD unset in real deployments to force a random,
    # logged-once password instead of a weak default.
    INITIAL_ADMIN_EMAIL: str = "admin@tmcltd.com"
    INITIAL_ADMIN_PASSWORD: str = ""

    # The fixed supplier demo OTP is NOT an env setting: it lives in the app DB
    # (app_settings.supplier_demo_otp) and admins set it under Admin → Suppliers.
    # See routers/app_settings.py.


    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}


settings = Settings()
