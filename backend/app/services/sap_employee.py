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


def verify_employee_login(user_id: str, password: str, actor: str = "") -> dict:
    """Check an employee ID + password with Lucky's login service.

    Returns {ok, pernr, name, error_code, message, unreachable}. ``unreachable``
    is True when the service could not be asked at all (network, TLS, a non-JSON
    reply), so the caller can tell "wrong password" from "service down".
    ``actor`` (the VIM user) is only for the log. Every attempt goes to the SAP
    auth log (services/sap_auth_log.py); passwords never do.
    """
    import time
    from app.services.sap_auth_log import auth_logger, log_http_failure

    pernr = normalize_pernr(user_id)
    if not pernr or not password:
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "MISSING",
                "message": "Enter your SAP employee ID and password.", "unreachable": False}

    if is_fake():
        r = {**_fake_login(pernr, password), "unreachable": False}
        auth_logger().info("LOGIN-SERVICE %s pernr=%r vim_user=%r error_code=%r (fixture SAP)",
                           "OK" if r["ok"] else "REFUSED", pernr, actor, r["error_code"])
        return r

    import httpx

    url = (settings.SAP_LOGIN_API_URL or "").strip()
    basic_user = settings.SAP_LOGIN_API_USER or settings.SAP_USER
    basic_pwd = settings.SAP_LOGIN_API_PASSWORD or settings.SAP_PASSWD
    ctx = dict(pernr=pernr, actor=actor, url=url, basic_user=basic_user,
               basic_pwd_set=bool(basic_pwd))
    if not url:
        log_http_failure(**ctx, kind="NOT_CONFIGURED", message="SAP_LOGIN_API_URL is empty")
        return {"ok": False, "pernr": pernr, "name": "", "error_code": "NOT_CONFIGURED",
                "message": "SAP_LOGIN_API_URL is not set.", "unreachable": True}
    verify = settings.SAP_LOGIN_API_CA_BUNDLE.strip() or True

    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=settings.SAP_LOGIN_API_TIMEOUT_SECONDS, verify=verify) as client:
            resp = client.post(
                url,
                json={"userId": pernr, "paswrd": password},
                auth=(basic_user, basic_pwd) if basic_user else None,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        text = f"{exc} {exc.__cause__ or ''} {exc.__context__ or ''}".upper()
        kind = ("TLS" if ("CERTIFICATE" in text or "SSL" in text) else
                "TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "CONNECT")
        log_http_failure(**ctx, exc=exc, kind=kind, elapsed_ms=int((time.monotonic() - t0) * 1000))
        return {"ok": False, "pernr": pernr, "name": "", "error_code": kind,
                "message": f"Could not reach the SAP login service ({kind.lower()}: {type(exc).__name__}).",
                "unreachable": True}
    elapsed = int((time.monotonic() - t0) * 1000)

    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        # A 401 with an HTML page here means the Basic-auth (technical) login was
        # refused, not the employee's password.
        log_http_failure(**ctx, status=resp.status_code, headers=resp.headers, body=resp.text,
                         elapsed_ms=elapsed)
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
    if ok:
        auth_logger().info("LOGIN-SERVICE OK pernr=%r name=%r vim_user=%r http_status=%s elapsed_ms=%s",
                           result["pernr"], result["name"], actor, resp.status_code, elapsed)
    else:
        log_http_failure(**ctx, status=resp.status_code, headers=resp.headers, json_body=True,
                         error_code=result["error_code"], message=result["message"],
                         elapsed_ms=elapsed)
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


def check_hierarchy_now(pernr: str, amount, currency: str = "", actor: str = "") -> dict:
    """Open a connection (as the technical user), run the check, close it.
    An RFC failure (logon, S_RFC, missing FM, ...) goes to the SAP auth log, then re-raises."""
    from app.services.sap_auth_log import auth_logger, log_rfc_failure
    from app.services.sap_connector import SAPConnector
    sap = SAPConnector()
    try:
        sap.connect()
        result = check_hierarchy(sap, pernr, amount, currency)
    except Exception as exc:
        log_rfc_failure("hierarchy check", exc, actor=actor, function=settings.SAP_HIERARCHY_RFC,
                        pernr=normalize_pernr(pernr), amount=amount, currency=currency)
        raise
    finally:
        try:
            sap.disconnect()
        except Exception:
            pass
    if not result["ok"]:
        auth_logger().warning(
            "HIERARCHY NOT FOUND function=%r pernr=%r amount=%s currency=%r EV_FLAG=%r ok_flags=%r vim_user=%r",
            settings.SAP_HIERARCHY_RFC, result["pernr"], result["amount"], result["currency"],
            result["flag"], settings.SAP_HIERARCHY_OK_FLAGS, actor)
    return result
