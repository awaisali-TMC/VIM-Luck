"""SAP employee login and approval-hierarchy check (Lucky Cement).

Two checks run before an invoice can start the SAP parking workflow
(services/sap_workflow.py), whose initiator is the VIM user's SAP employee:

1. **Employee login**: Lucky's ICF service ``/sap/bc/ztmc_login`` (HTTP + Basic
   auth) checks an employee ID (PERNR) + password::

       POST {"userId": "00004007", "paswrd": "..."}
       -> {"success": true,  "code": 200, "errorCode": "OK", "userid": "00004007", "name": "WASEEM QURESHI "}
       -> {"success": false, "code": 401, "errorCode": "INVALID_PASSWORD", "message": "Verification key does not match", ...}

2. **Hierarchy check**: RFC ``ZINI_VERIFY`` (IV_PERNR NUMC8, IV_WAERS optional,
   IV_AMOUNT WRBTR) -> EV_FLAG CHAR1. Which EV_FLAG values mean "a hierarchy
   exists" is not yet confirmed; see settings.SAP_HIERARCHY_OK_FLAGS.

With SAP_MODE=fake (DEBUG only) both are answered from fixtures: the login from
``sap_fixtures/scripted.json`` ("employees"), ZINI_VERIFY by the fake connector.
"""

import logging
from decimal import Decimal, InvalidOperation

from app.config import settings

logger = logging.getLogger(__name__)


def is_fake() -> bool:
    return settings.SAP_MODE == "fake" and settings.DEBUG


def normalize_pernr(user_id: str | None) -> str:
    """SAP personnel numbers are NUMC 8: '4007' -> '00004007'. Anything that
    is not all digits is returned trimmed and upper-cased, unchanged otherwise."""
    uid = (user_id or "").strip()
    return uid.zfill(8) if uid.isdigit() else uid.upper()


# ── 1. Employee login (HTTP) ─────────────────────────────────────────────────

def _fake_login(pernr: str, password: str) -> dict:
    from app.services.sap_connector_fake import _scripts
    emp = (_scripts().get("employees") or {}).get(pernr)
    if emp and emp.get("password") == password:
        return {"ok": True, "pernr": pernr, "name": emp.get("name", ""),
                "error_code": "OK", "message": "Login successful"}
    if emp:
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "INVALID_PASSWORD",
                "message": "Verification key does not match"}
    return {"ok": False, "pernr": pernr, "name": "", "error_code": "USER_NOT_FOUND",
            "message": "Employee not found"}


def verify_employee_login(user_id: str, password: str) -> dict:
    """Check an employee ID + password with Lucky's login service.

    Returns {ok, pernr, name, error_code, message, unreachable}. ``unreachable``
    is True when the service could not be asked at all (network, TLS, a non-JSON
    reply), so the caller can tell "wrong password" from "service down".
    Never logs the password.
    """
    pernr = normalize_pernr(user_id)
    if not pernr or not password:
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "MISSING",
                "message": "Enter your SAP employee ID and password.", "unreachable": False}

    if is_fake():
        return {**_fake_login(pernr, password), "unreachable": False}

    import httpx

    url = (settings.SAP_LOGIN_API_URL or "").strip()
    if not url:
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "NOT_CONFIGURED",
                "message": "SAP_LOGIN_API_URL is not set.", "unreachable": True}
    basic_user = settings.SAP_LOGIN_API_USER or settings.SAP_USER
    basic_pwd = settings.SAP_LOGIN_API_PASSWORD or settings.SAP_PASSWD
    verify = settings.SAP_LOGIN_API_CA_BUNDLE.strip() or True

    try:
        with httpx.Client(timeout=settings.SAP_LOGIN_API_TIMEOUT_SECONDS, verify=verify) as client:
            resp = client.post(
                url,
                json={"userId": pernr, "paswrd": password},
                auth=(basic_user, basic_pwd) if basic_user else None,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.warning("SAP login service unreachable for %s: %s", pernr, exc)
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "UNREACHABLE",
                "message": f"Could not reach the SAP login service ({type(exc).__name__}).",
                "unreachable": True}

    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        # A 401 with an HTML page here means the Basic-auth (technical) login was
        # refused, not the employee's password.
        logger.warning("SAP login service returned HTTP %s with no JSON body for %s",
                       resp.status_code, pernr)
        hint = (" — the service's Basic-auth login (SAP_LOGIN_API_USER) was refused"
                if resp.status_code in (401, 403) else "")
        return {"ok": False, "pernr": pernr, "name": "", "error_code": f"HTTP_{resp.status_code}",
                "message": f"SAP login service answered HTTP {resp.status_code}{hint}.",
                "unreachable": True}

    ok = body.get("success") is True
    result = {
        "ok": ok,
        "pernr": normalize_pernr(body.get("userid")) or pernr if ok else pernr,
        "name": (body.get("name") or "").strip(),
        "error_code": str(body.get("errorCode") or ""),
        "message": str(body.get("message") or ("Login successful" if ok else "SAP login failed")),
        "unreachable": False,
    }
    if not ok:
        logger.info("SAP employee login refused for %s: %s", pernr, result["error_code"])
    return result


# ── 2. Approval-hierarchy check (RFC) ────────────────────────────────────────

def _ok_flags() -> set[str]:
    return {f.strip().upper() for f in (settings.SAP_HIERARCHY_OK_FLAGS or "").split(",") if f.strip()}


def check_hierarchy(sap, pernr: str, amount, currency: str = "") -> dict:
    """Call ZINI_VERIFY on an open connection.

    Returns {ok, flag, pernr, amount, currency, message}.
    """
    pernr = normalize_pernr(pernr)
    try:
        amt = Decimal(str(amount if amount not in (None, "") else 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        amt = Decimal("0.00")
    cur = (currency or "").strip().upper()
    if not (cur.isalpha() and 3 <= len(cur) <= 5):
        cur = ""   # IV_WAERS is optional; don't send OCR text like "RS." as a key

    kwargs = {"IV_PERNR": pernr, "IV_AMOUNT": f"{amt:.2f}", "output_params": ["EV_FLAG"]}
    if cur:
        kwargs["IV_WAERS"] = cur
    result = sap.call(settings.SAP_HIERARCHY_RFC, **kwargs)
    flag = (result.get("EV_FLAG") or "").strip().upper()
    ok = flag in _ok_flags()
    logger.info("%s pernr=%s amount=%s %s -> EV_FLAG=%r (%s)", settings.SAP_HIERARCHY_RFC,
                pernr, amt, cur, flag, "ok" if ok else "no hierarchy")
    return {
        "ok": ok,
        "flag": flag,
        "pernr": pernr,
        "amount": float(amt),
        "currency": cur,
        "message": (f"Approval hierarchy found in SAP for employee {pernr}."
                    if ok else
                    f"No SAP approval hierarchy for employee {pernr} at {amt:,.2f} {cur}".rstrip()
                    + f" ({settings.SAP_HIERARCHY_RFC} returned EV_FLAG '{flag}')."),
    }


def check_hierarchy_now(pernr: str, amount, currency: str = "") -> dict:
    """Open a connection (as the technical user), run the check, close it."""
    from app.services.sap_connector import SAPConnector
    sap = SAPConnector()
    sap.connect()
    try:
        return check_hierarchy(sap, pernr, amount, currency)
    finally:
        try:
            sap.disconnect()
        except Exception:
            pass
