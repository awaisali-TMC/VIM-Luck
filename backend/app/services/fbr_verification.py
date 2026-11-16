"""
FBR Active Taxpayer List (ATL) verification service — IRIS 2.0 integration.

How the Live FBR API works (no login credentials needed)
─────────────────────────────────────────────────────────
FBR's ATL page (https://iris.fbr.gov.pk/public/ATL) is a public Angular SPA.
The Angular frontend embeds a Bearer JWT inside its compiled main.*.js bundle.
We extract that token dynamically and use it to call the hidden REST API at
api.fbr.gov.pk.

Token extraction flow:
  1. GET https://iris.fbr.gov.pk/public/ATL  →  find <script src="main.<hash>.js">
  2. GET https://iris.fbr.gov.pk/main.<hash>.js  (~8 MB Angular bundle)
  3. Regex-extract:
     - authorization_key_verifcation:"<JWT>"   (note: FBR's own typo)
     - base_verification_url:"<URL>"           (auto-detect API URL changes)
  4. POST the API with Bearer <JWT> + payload

Supports:
  - NTN (7-digit + check digit) and CNIC (13-digit) lookups
  - Protocol IDs: Income Tax (1004), Sales Tax (1005), AJK (3001)
  - Local ATL database lookup (7.5M records, sync sqlite3 via run_in_executor)
  - Live FBR IRIS 2.0 API with token auto-refresh on 401
  - Batch verification (multiple NTNs/CNICs in one call)
  - WHT compliance checking (ATL vs non-ATL rates per Section 153)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Identifier Detection & Normalization
# ═══════════════════════════════════════════════════════════════════════════════

def detect_identifier_type(raw: str) -> str:
    """Auto-detect whether the input is an NTN or CNIC.

    - CNIC: 13 digits (with or without dashes, e.g. 42201-5611158-9)
    - NTN:  up to 8 digits (with or without dash check-digit, e.g. 0000091-4)
    """
    stripped = re.sub(r"[\s\-/]", "", raw.strip())
    if stripped.isdigit() and len(stripped) == 13:
        return "CNIC"
    return "NTN"


def normalize_ntn(raw_ntn: str) -> str:
    """Strip dashes/spaces, zero-pad to 7 digits if all-numeric and <=7 chars."""
    cleaned = re.sub(r"[\s\-/]", "", raw_ntn.strip())
    if cleaned.isdigit() and len(cleaned) <= 7:
        cleaned = cleaned.zfill(7)
    return cleaned


def normalize_cnic(raw_cnic: str) -> str:
    """Strip dashes/spaces from CNIC, return 13-digit string."""
    return re.sub(r"[\s\-/]", "", raw_cnic.strip())


def extract_ntn(raw: str) -> Optional[str]:
    """Pull the NTN out of a field that may bundle other tax numbers and labels.

    Vendor invoices often print several identifiers together, e.g.
    'STRN # 3277876177886, NTN # 5433744-3'. We want just the NTN (5433744-3),
    NOT the 13-digit sales-tax registration number (STRN). Returns None when no
    'NTN' label is present, so the caller falls back to raw detection (handles
    a field that is a bare NTN or a CNIC).
    """
    if not raw:
        return None
    # A number explicitly labelled NTN wins (STRN has no 'NTN' substring).
    m = re.search(r"NTN\s*[#:.\-/]?\s*([0-9][0-9\s\-]{4,8}[0-9])", raw, re.IGNORECASE)
    return m.group(1).strip() if m else None


def normalize_identifier(raw: str) -> tuple[str, str]:
    """Detect type and normalize. Returns (normalized_value, identifier_type).

    Tolerates messy fields that bundle several tax numbers by extracting the
    explicitly-labelled NTN first."""
    raw = (raw or "").strip()
    labelled = extract_ntn(raw)
    if labelled:
        return normalize_ntn(labelled), "NTN"
    id_type = detect_identifier_type(raw)
    if id_type == "CNIC":
        return normalize_cnic(raw), "CNIC"
    return normalize_ntn(raw), "NTN"


# ═══════════════════════════════════════════════════════════════════════════════
# Local ATL Database Lookup (read-only sqlite3)
# ═══════════════════════════════════════════════════════════════════════════════

_atl_conn: Optional[sqlite3.Connection] = None


def _get_atl_connection() -> sqlite3.Connection:
    """Lazy singleton read-only connection to the ATL database."""
    global _atl_conn
    if _atl_conn is None:
        db_path = settings.FBR_ATL_DB_PATH
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"ATL database not found: {db_path}")
        _atl_conn = sqlite3.connect(db_path, check_same_thread=False)
        _atl_conn.row_factory = sqlite3.Row
        _atl_conn.execute("PRAGMA query_only = ON")
    return _atl_conn


def _lookup_atl_sync(identifier: str) -> Optional[dict]:
    """Synchronous lookup in the ATL database. Tries multiple formats."""
    conn = _get_atl_connection()
    # Build candidate list: exact, stripped, raw
    candidates = [identifier]
    stripped = re.sub(r"[\s\-/]", "", identifier)
    if stripped != identifier:
        candidates.append(stripped)
    raw = identifier.strip()
    if raw not in candidates:
        candidates.append(raw)

    for candidate in candidates:
        row = conn.execute(
            "SELECT ntn, name, business_name, filing_status, status_date, last_updated "
            "FROM active_taxpayers WHERE ntn = ?",
            (candidate,),
        ).fetchone()
        if row:
            return dict(row)

    # Fallback: strip dashes in SQL to match
    row = conn.execute(
        "SELECT ntn, name, business_name, filing_status, status_date, last_updated "
        "FROM active_taxpayers WHERE REPLACE(REPLACE(ntn, '-', ''), ' ', '') = ?",
        (stripped,),
    ).fetchone()
    return dict(row) if row else None


async def _lookup_atl_pg(normalized: str) -> Optional[dict]:
    """Look up the ATL row in the app database's atl_taxpayers table (the
    weekly-imported copy). Returns None if the table is empty/missing or no
    match — callers then fall back to the sqlite file / live IRIS."""
    try:
        from sqlalchemy import select, or_
        from app.database import async_session
        from app.models.atl_taxpayer import AtlTaxpayer
        digits = re.sub(r"[\s\-/]", "", normalized or "")
        if not digits:
            return None
        # The ATL stores an NTN as its 7-digit base on the Sales-Tax list and
        # as base+check-digit (8 digits) on the Income-Tax list. Match BOTH so
        # a taxpayer on either/both lists is found and all registrations shown.
        candidates = {digits}
        conds = []
        if len(digits) == 8:
            candidates.add(digits[:7])          # drop check digit -> 7-digit base
        if len(digits) == 7:
            conds.append(AtlTaxpayer.ntn.like(f"{digits}_"))  # add 8-digit (+check) form
        conds.insert(0, AtlTaxpayer.ntn.in_(candidates))
        async with async_session() as db:
            res = await db.execute(select(AtlTaxpayer).where(or_(*conds)))
            rows = res.scalars().all()
            if not rows:
                return None
            # A taxpayer can be on the Income Tax list, the Sales Tax list, or
            # both — report which registrations were found.
            lists = sorted({(r.list_type or "").upper() for r in rows if r.list_type})
            active = [r for r in rows if (r.filing_status or "").lower().startswith("active")]
            row = (active or rows)[0]
            return {
                "ntn": row.ntn_display or row.ntn,
                "name": row.name,
                "business_name": row.business_name,
                "filing_status": row.filing_status,
                "status_date": row.status_date,
                "last_updated": row.last_updated,
                "registrations": lists,   # e.g. ["IT","ST"]
            }
    except Exception:
        logger.debug("Postgres ATL lookup unavailable; falling back", exc_info=True)
        return None


async def lookup_atl(identifier: str) -> Optional[dict]:
    """Look up an NTN/CNIC in the ATL. Prefers the app DB's atl_taxpayers table
    (weekly import); falls back to the local sqlite ATL file if present."""
    normalized, _ = normalize_identifier(identifier)
    # 1) app database (Postgres in cloud) — the imported ATL copy
    result = await _lookup_atl_pg(normalized)
    if result:
        return result
    # 2) fall back to the local sqlite ATL file (dev), if configured/present
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _lookup_atl_sync, normalized)
        if not result:
            result = await loop.run_in_executor(None, _lookup_atl_sync, identifier.strip())
    except Exception:
        result = None
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Live FBR IRIS 2.0 API — Token Extraction & API Client
# ═══════════════════════════════════════════════════════════════════════════════

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://iris.fbr.gov.pk",
    "Referer": "https://iris.fbr.gov.pk/",
}

# ── Token cache ──────────────────────────────────────────────────────────────
_cached_token: Optional[str] = None
_token_fetched_at: float = 0
_cached_api_url: Optional[str] = None  # dynamically extracted from bundle


def _invalidate_token_cache():
    """Force re-extraction on next request (called on 401)."""
    global _cached_token, _token_fetched_at, _cached_api_url
    _cached_token = None
    _token_fetched_at = 0
    _cached_api_url = None
    logger.info("FBR token cache invalidated — will re-extract from IRIS bundle.")


def _fetch_bearer_token_sync(force_refresh: bool = False) -> Optional[str]:
    """
    Extract Bearer JWT from the IRIS Angular bundle.

    Steps:
      1. GET the IRIS index page → find <script src="main.<hash>.js">
      2. GET that JS bundle (~8 MB compiled Angular code)
      3. Regex-extract:
         - authorization_key_verifcation:"<JWT>"  (FBR's own typo in the key name)
         - base_verification_url:"<URL>"          (auto-detect API URL changes)

    The token is cached for FBR_TOKEN_CACHE_TTL seconds (default: 1 hour).
    If force_refresh=True, the cache is bypassed.
    """
    global _cached_token, _token_fetched_at, _cached_api_url

    ttl = settings.FBR_TOKEN_CACHE_TTL
    if not force_refresh and _cached_token and (time.time() - _token_fetched_at) < ttl:
        return _cached_token

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    timeout = settings.FBR_REQUEST_TIMEOUT

    try:
        # ── Step 1: Fetch IRIS index page ────────────────────────────────
        logger.info("Fetching IRIS index page to discover JS bundle...")
        idx_resp = session.get(settings.FBR_IRIS_JS_INDEX, timeout=timeout)
        idx_resp.raise_for_status()

        # SELECTOR: The main bundle filename in the HTML.
        # Pattern: <script src="main.<hash>.js" type="module">
        match = re.search(r'src="(main\.[a-f0-9]+\.js)"', idx_resp.text)
        if not match:
            logger.error("Could not find main.*.js bundle reference in IRIS HTML.")
            return None

        bundle_name = match.group(1)
        bundle_url = f"https://iris.fbr.gov.pk/{bundle_name}"

        # ── Step 2: Download the Angular bundle ──────────────────────────
        logger.info("Downloading Angular bundle: %s", bundle_url)
        js_resp = session.get(bundle_url, timeout=90)
        js_resp.raise_for_status()
        js_text = js_resp.text
        logger.info("Bundle downloaded — %d chars.", len(js_text))

        # ── Step 3: Extract the Bearer JWT ───────────────────────────────
        # SELECTOR: FBR uses "authorization_key_verifcation" (their typo).
        token_match = re.search(
            r'authorization_key_verifcation:"([^"]+)"', js_text
        )
        if not token_match:
            logger.error("Bearer token not found in JS bundle.")
            return None

        _cached_token = token_match.group(1)
        _token_fetched_at = time.time()
        logger.info("Bearer token extracted (length=%d).", len(_cached_token))

        # ── Step 3b: Extract API URL (auto-detect changes) ──────────────
        # SELECTOR: base_verification_url in the compiled environment object.
        url_match = re.search(r'base_verification_url:"([^"]+)"', js_text)
        if url_match:
            extracted_url = url_match.group(1)
            if extracted_url != settings.FBR_API_URL:
                logger.warning(
                    "API URL in bundle (%s) differs from config (%s). Using bundle URL.",
                    extracted_url, settings.FBR_API_URL,
                )
            _cached_api_url = extracted_url
        else:
            _cached_api_url = None

        return _cached_token

    except requests.RequestException as exc:
        logger.error("Failed to fetch IRIS bundle: %s", exc)
        return None


def get_effective_api_url() -> str:
    """Return the dynamically extracted URL if available, else the config URL."""
    return _cached_api_url or settings.FBR_API_URL


# ── FBR API response parser ─────────────────────────────────────────────────

# SELECTOR: Map FBR API response field titles to our internal field names.
# If FBR changes the Title strings, update this mapping.
_FBR_FIELD_MAP = {
    "Registration No:": "ntn",
    "Name:": "name",
    "Business Name:": "business_name",
    "Filing Status:": "filing_status",
    "Filing Status Checking Date:": "status_date",
}


def _parse_fbr_response(data: dict, fallback_id: str) -> Optional[dict]:
    """
    Parse the JSON returned by the FBR ATL API.

    Expected shape (outputType "5" = JSON):
    {
      "status_code": 1,
      "response": [
        {"Title": "Registration No:", "Value": "4220156111589"},
        {"Title": "Name:",            "Value": "JOHN DOE"},
        {"Title": "Business Name:",   "Value": "ACME LTD"},
        {"Title": "Filing Status:",   "Value": "Active"},
        {"Title": "Filing Status Checking Date:", "Value": "18-FEB-26"},
        {"Title": "Note:",            "Value": "..."}
      ]
    }

    When no record exists, "response" is a plain string like "No record exists".
    """
    if data.get("status_code") != 1 or "response" not in data:
        logger.warning("FBR API non-success: %s", json.dumps(data)[:300])
        return None

    response = data["response"]
    if isinstance(response, str):
        logger.info("FBR API: no record for %s — %s", fallback_id, response)
        return None

    parsed: dict[str, str] = {}
    for item in response:
        title = item.get("Title", "").strip()
        value = item.get("Value", "").strip()
        if title in _FBR_FIELD_MAP:
            parsed[_FBR_FIELD_MAP[title]] = value

    if not parsed.get("ntn") and not parsed.get("name"):
        return None

    parsed.setdefault("ntn", fallback_id)
    parsed.setdefault("name", "")
    parsed.setdefault("business_name", "")
    parsed.setdefault("filing_status", "Unknown")
    parsed.setdefault("status_date", "")
    return parsed


# ── Core API query function ──────────────────────────────────────────────────

def _query_fbr_api_sync(
    identifier: str,
    identifier_type: str = "NTN",
    protocol_id: Optional[str] = None,
    _is_retry: bool = False,
) -> Optional[dict]:
    """
    Query the live FBR ATL API for a single NTN or CNIC.

    Args:
        identifier:      The NTN (7 digits) or CNIC (13 digits).
        identifier_type: "NTN" or "CNIC".
        protocol_id:     FBR protocol code. Default: Income Tax ATL (1004).
                         Options: 1004 (Income Tax), 1005 (Sales Tax), 3001 (AJK).
        _is_retry:       Internal flag — True when retrying after 401 token refresh.

    Returns:
        Parsed dict with ntn, name, business_name, filing_status, status_date.
        None on failure or "no record".
    """
    if protocol_id is None:
        protocol_id = settings.FBR_PROTOCOL_INCOME_TAX

    token = _fetch_bearer_token_sync()
    if not token:
        return None

    session = requests.Session()
    # SELECTOR: Payload shape expected by the FBR API.
    # protocolId "1004" = Income Tax ATL, outputType "5" = JSON response.
    payload = {
        "protocolId": protocol_id,
        "outputType": "5",
        "identifierType": identifier_type,
        "identifier": identifier.strip(),
        "date": "",
    }
    headers = {
        **_DEFAULT_HEADERS,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json;charset=UTF-8",
    }

    api_url = get_effective_api_url()
    retry_delay = settings.FBR_RETRY_DELAY

    for attempt in range(1, settings.FBR_MAX_RETRIES + 1):
        try:
            logger.info(
                "FBR API: %s=%s protocol=%s (attempt %d/%d) → %s",
                identifier_type, identifier, protocol_id,
                attempt, settings.FBR_MAX_RETRIES, api_url,
            )
            resp = session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=settings.FBR_REQUEST_TIMEOUT,
            )

            # ── Handle 401: token expired, re-extract once ───────────────
            if resp.status_code == 401 and not _is_retry:
                logger.warning("FBR API returned 401 — token likely expired. Re-extracting...")
                _invalidate_token_cache()
                return _query_fbr_api_sync(
                    identifier, identifier_type, protocol_id, _is_retry=True
                )

            resp.raise_for_status()
            data = resp.json()
            return _parse_fbr_response(data, identifier)

        except requests.exceptions.Timeout:
            logger.warning("FBR API timeout on attempt %d.", attempt)
        except requests.exceptions.ConnectionError as exc:
            logger.warning("FBR API connection error on attempt %d: %s", attempt, exc)
        except requests.exceptions.HTTPError as exc:
            logger.error("FBR API HTTP %s on attempt %d.", exc.response.status_code, attempt)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("FBR API response parse failed: %s", exc)
            return None  # no point retrying a parse error

        if attempt < settings.FBR_MAX_RETRIES:
            logger.info("Retrying in %d seconds...", retry_delay)
            time.sleep(retry_delay)

    logger.error(
        "FBR API: all %d attempts failed for %s=%s",
        settings.FBR_MAX_RETRIES, identifier_type, identifier,
    )
    return None


async def live_fbr_lookup(
    identifier: str,
    identifier_type: str = "NTN",
    protocol_id: Optional[str] = None,
) -> Optional[dict]:
    """Async wrapper for live FBR API lookup."""
    if identifier_type == "CNIC":
        normalized = normalize_cnic(identifier)
    else:
        normalized = normalize_ntn(identifier)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _query_fbr_api_sync, normalized, identifier_type, protocol_id
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Verify Function
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_ntn(
    identifier: str,
    check_live: bool = False,
    protocol_id: Optional[str] = None,
) -> dict:
    """
    Verify an NTN or CNIC against the ATL.

    Strategy: local DB first → live API fallback (if enabled & requested).

    Returns dict with: ntn, identifier_type, status, is_active, taxpayer_name,
    business_name, filing_status, status_date, source, verified_at, protocol_id
    """
    normalized, id_type = normalize_identifier(identifier)
    used_protocol = protocol_id or settings.FBR_PROTOCOL_INCOME_TAX
    now = datetime.now(timezone.utc)

    base_result = {
        "ntn": normalized,
        "identifier_type": id_type,
        "protocol_id": used_protocol,
    }

    # ── Try local DB first ───────────────────────────────────────────────
    try:
        result = await lookup_atl(normalized)
    except FileNotFoundError:
        result = None
        if not check_live:
            return {
                **base_result,
                "status": "error",
                "is_active": False,
                "taxpayer_name": None,
                "business_name": None,
                "filing_status": None,
                "status_date": None,
                "source": "local_db",
                "verified_at": now,
                "error": "ATL database not found",
            }

    if result:
        filing = result.get("filing_status", "")
        is_active = filing.lower().startswith("active")
        return {
            **base_result,
            "ntn": result.get("ntn") or normalized,   # prefer the ATL display form
            "status": "verified_active" if is_active else "verified_inactive",
            "is_active": is_active,
            "taxpayer_name": result.get("name"),
            "business_name": result.get("business_name"),
            "filing_status": filing,
            "status_date": result.get("status_date"),
            "registrations": result.get("registrations") or [],
            "source": "local_db",
            "verified_at": now,
        }

    # ── Try live API if enabled ──────────────────────────────────────────
    if check_live and settings.FBR_LIVE_LOOKUP_ENABLED:
        live_result = await live_fbr_lookup(normalized, id_type, protocol_id)
        if live_result:
            filing = live_result.get("filing_status", "")
            is_active = filing.lower().startswith("active")
            return {
                **base_result,
                "status": "verified_active" if is_active else "verified_inactive",
                "is_active": is_active,
                "taxpayer_name": live_result.get("name"),
                "business_name": live_result.get("business_name"),
                "filing_status": filing,
                "status_date": live_result.get("status_date"),
                "source": "live_api",
                "verified_at": now,
            }

    return {
        **base_result,
        "status": "not_found",
        "is_active": False,
        "taxpayer_name": None,
        "business_name": None,
        "filing_status": None,
        "status_date": None,
        "source": "live_api" if (check_live and settings.FBR_LIVE_LOOKUP_ENABLED) else "local_db",
        "verified_at": now,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Batch Verification
# ═══════════════════════════════════════════════════════════════════════════════

async def verify_batch(
    identifiers: list[str],
    check_live: bool = False,
    protocol_id: Optional[str] = None,
) -> list[dict]:
    """
    Verify multiple NTNs/CNICs.

    Processes sequentially with a small delay between live API calls to avoid
    hammering the FBR server. Local DB lookups are fast and don't need delays.
    """
    results = []
    for ident in identifiers:
        result = await verify_ntn(ident, check_live=check_live, protocol_id=protocol_id)
        results.append(result)
        # Add delay between live API calls only
        if check_live and settings.FBR_LIVE_LOOKUP_ENABLED:
            await asyncio.sleep(settings.FBR_BATCH_DELAY)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Token Status (for frontend health indicator)
# ═══════════════════════════════════════════════════════════════════════════════

def get_token_status_sync() -> dict:
    """Return current state of the IRIS token cache."""
    now = time.time()
    ttl = settings.FBR_TOKEN_CACHE_TTL

    if _cached_token:
        age = now - _token_fetched_at
        remaining = max(0, ttl - age)
        return {
            "has_token": True,
            "token_age_seconds": round(age),
            "ttl_remaining_seconds": round(remaining),
            "is_expired": remaining <= 0,
            "api_url": get_effective_api_url(),
            "api_url_source": "bundle" if _cached_api_url else "config",
            "live_lookup_enabled": settings.FBR_LIVE_LOOKUP_ENABLED,
        }

    return {
        "has_token": False,
        "token_age_seconds": None,
        "ttl_remaining_seconds": None,
        "is_expired": True,
        "api_url": settings.FBR_API_URL,
        "api_url_source": "config",
        "live_lookup_enabled": settings.FBR_LIVE_LOOKUP_ENABLED,
    }


async def get_token_status() -> dict:
    """Async wrapper for token status."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_token_status_sync)


async def refresh_token() -> dict:
    """Force re-extraction of the Bearer token from IRIS bundle."""
    _invalidate_token_cache()
    loop = asyncio.get_event_loop()
    token = await loop.run_in_executor(None, _fetch_bearer_token_sync, True)
    status = await get_token_status()
    status["refresh_success"] = token is not None
    return status


# ═══════════════════════════════════════════════════════════════════════════════
# WHT Compliance Check
# ═══════════════════════════════════════════════════════════════════════════════

# Pakistan WHT rate table (Section 153 — common categories)
WHT_RATES = {
    "services": {"atl": 8.0, "non_atl": 16.0},
    "goods_supply": {"atl": 4.5, "non_atl": 9.0},
    "contracts": {"atl": 7.5, "non_atl": 15.0},
    "default": {"atl": 4.0, "non_atl": 8.0},
}

# Rate tolerance for matching (+/- 1 percentage point)
RATE_TOLERANCE = 1.0


def check_wht_compliance(
    detected_taxes: list[dict],
    is_atl_active: bool,
    subtotal_amount: Optional[float] = None,
) -> dict:
    """
    Compare detected WHT rate against expected rate based on ATL status.

    Returns dict with: status, is_supplier_atl, applicable_rate,
    detected_rate, detected_amount, message
    """
    # Find WHT in detected taxes
    wht_entry = None
    for tax in detected_taxes:
        tax_type = (tax.get("tax_type") or "").upper()
        if "WHT" in tax_type or "WITHHOLDING" in tax_type:
            wht_entry = tax
            break

    if not wht_entry:
        return {
            "status": "needs_review",
            "is_supplier_atl": is_atl_active,
            "applicable_rate": None,
            "detected_rate": None,
            "detected_amount": None,
            "message": "No WHT detected on this invoice. Please verify if WHT should be applied.",
        }

    detected_rate = wht_entry.get("rate")
    detected_amount = wht_entry.get("amount")

    # If we have amount and subtotal but no rate, calculate it
    if detected_rate is None and detected_amount and subtotal_amount and subtotal_amount > 0:
        detected_rate = round((detected_amount / subtotal_amount) * 100, 2)

    # Determine which rate category best matches
    atl_key = "atl" if is_atl_active else "non_atl"
    best_category = "default"

    if detected_rate is not None:
        for category, rates in WHT_RATES.items():
            expected = rates[atl_key]
            if abs(detected_rate - expected) <= RATE_TOLERANCE:
                best_category = category
                break

    applicable_rate = WHT_RATES[best_category][atl_key]
    opposite_rate = WHT_RATES[best_category]["non_atl" if is_atl_active else "atl"]

    if detected_rate is None:
        return {
            "status": "needs_review",
            "is_supplier_atl": is_atl_active,
            "applicable_rate": applicable_rate,
            "detected_rate": None,
            "detected_amount": detected_amount,
            "message": f"WHT amount detected but rate could not be determined. "
                       f"Expected rate for {'ATL' if is_atl_active else 'non-ATL'} supplier: {applicable_rate}%.",
        }

    # Check compliance
    if abs(detected_rate - applicable_rate) <= RATE_TOLERANCE:
        return {
            "status": "compliant",
            "is_supplier_atl": is_atl_active,
            "applicable_rate": applicable_rate,
            "detected_rate": detected_rate,
            "detected_amount": detected_amount,
            "message": f"WHT rate {detected_rate}% matches expected {applicable_rate}% "
                       f"for {'ATL active' if is_atl_active else 'non-ATL'} supplier.",
        }

    if abs(detected_rate - opposite_rate) <= RATE_TOLERANCE:
        if is_atl_active:
            return {
                "status": "non_compliant",
                "is_supplier_atl": True,
                "applicable_rate": applicable_rate,
                "detected_rate": detected_rate,
                "detected_amount": detected_amount,
                "message": f"WHT rate {detected_rate}% appears to be the non-ATL rate. "
                           f"Supplier is ATL active — expected rate is {applicable_rate}% (overpaying).",
            }
        else:
            return {
                "status": "non_compliant",
                "is_supplier_atl": False,
                "applicable_rate": applicable_rate,
                "detected_rate": detected_rate,
                "detected_amount": detected_amount,
                "message": f"WHT rate {detected_rate}% appears to be the ATL rate. "
                           f"Supplier is non-ATL — expected rate is {applicable_rate}%. "
                           f"Under-deduction risk — may attract FBR penalty.",
            }

    return {
        "status": "needs_review",
        "is_supplier_atl": is_atl_active,
        "applicable_rate": applicable_rate,
        "detected_rate": detected_rate,
        "detected_amount": detected_amount,
        "message": f"WHT rate {detected_rate}% does not match expected {applicable_rate}% "
                   f"for {'ATL active' if is_atl_active else 'non-ATL'} supplier. Manual review required.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ATL Database Stats
# ═══════════════════════════════════════════════════════════════════════════════

def get_atl_stats_sync() -> dict:
    """Return stats about the ATL database file."""
    db_path = settings.FBR_ATL_DB_PATH
    if not os.path.exists(db_path):
        return {
            "total_records": 0,
            "db_path": db_path,
            "db_size_mb": 0,
            "last_modified": None,
            "status": "not_found",
        }
    try:
        conn = _get_atl_connection()
        count = conn.execute("SELECT COUNT(*) FROM active_taxpayers").fetchone()[0]
        size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)
        mtime = datetime.fromtimestamp(os.path.getmtime(db_path), tz=timezone.utc).isoformat()
        return {
            "total_records": count,
            "db_path": db_path,
            "db_size_mb": size_mb,
            "last_modified": mtime,
            "status": "available",
        }
    except Exception as exc:
        return {
            "total_records": 0,
            "db_path": db_path,
            "db_size_mb": 0,
            "last_modified": None,
            "status": f"error: {exc}",
        }


async def get_atl_stats() -> dict:
    """Async wrapper for ATL stats."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_atl_stats_sync)
