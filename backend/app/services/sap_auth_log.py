"""SAP authorization log — the evidence to hand to the Basis team.

Every SAP authentication / authorization failure (and every attempt, at INFO)
is written by one logger, ``sap_auth``, to:

- the console (stderr), timestamped, so it shows in the ``start-lan.sh`` output
  even though the app configures no logging of its own, and
- a rotating file, ``settings.SAP_AUTH_LOG_FILE`` (default
  ``logs/sap_auth.log`` under the backend's working directory; empty = no file).
  Admins can also read its tail at ``GET /api/sap/auth-log``.

Covered: the employee login service (``/sap/bc/ztmc_login``, HTTP + Basic auth)
and the RFC calls that run under a SAP user (``ZINI_VERIFY``, the per-user login
test, parking). Each failure line carries a ``kind`` and a ``hint`` saying what
Basis should look at (SU01, SU53, SICF, STRUST, ST22, SM21).

Never logged: any password (the employee's, the Basic-auth one, the RFC one) or
cookies. Only whether a password was set.
"""

import logging
import os
import threading
from collections import deque
from logging.handlers import RotatingFileHandler

from app.config import settings

_lock = threading.Lock()
_configured = False
_file_path: str = ""

# Headers worth showing Basis; set-cookie / authorization are never logged.
_HEADERS = ("content-type", "www-authenticate", "sap-server", "sap-system",
            "sap-client", "sap-perf-fesrec", "server", "x-error", "location")


def auth_logger() -> logging.Logger:
    """The ``sap_auth`` logger, with its handlers attached on first use."""
    global _configured, _file_path
    log = logging.getLogger("sap_auth")
    if _configured:
        return log
    with _lock:
        if _configured:
            return log
        log.setLevel(logging.INFO)
        log.propagate = False          # own handlers; don't double-print via root
        fmt = logging.Formatter("%(asctime)s %(levelname)s [sap-auth] %(message)s")
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        log.addHandler(console)
        path = (settings.SAP_AUTH_LOG_FILE or "").strip()
        if path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                fh = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
                fh.setFormatter(fmt)
                log.addHandler(fh)
                _file_path = os.path.abspath(path)
            except OSError as exc:
                log.warning("Cannot open SAP auth log file %s (%s) — console only", path, exc)
        _configured = True
    return log


def log_file_path() -> str:
    auth_logger()
    return _file_path


def tail(lines: int = 200) -> list[str]:
    """Last ``lines`` lines of the log file ([] when there is no file yet)."""
    path = log_file_path()
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n") for ln in deque(f, maxlen=max(1, min(lines, 2000)))]


def _kv(**fields) -> str:
    return " ".join(f"{k}={v!r}" for k, v in fields.items() if v not in (None, ""))


# ── HTTP: the employee login service ─────────────────────────────────────────

def http_hint(status: int | None, json_body: bool, kind: str = "") -> tuple[str, str]:
    """(kind, hint) for a login-service failure."""
    if kind == "TLS":
        return kind, ("TLS certificate of the login service is not trusted by this server: "
                      "give us the issuing CA (STRUST) and set SAP_LOGIN_API_CA_BUNDLE")
    if kind == "TIMEOUT":
        return kind, "No answer in time: check ICM/web dispatcher load, network route, firewall"
    if kind == "CONNECT":
        return kind, "Could not connect: DNS name, firewall/port, ICM (SMICM) running for HTTPS"
    if status in (401, 403) and not json_body:
        return "BASIC_AUTH_REFUSED", (
            "The HTTP Basic-auth (technical) user was refused before the handler ran: "
            "SU01 (locked/expired/wrong password, user type), SU53 for that user, "
            "S_ICF / S_SERVICE authorization, SICF logon data of ztmc_login")
    if status == 404:
        return "SERVICE_NOT_FOUND", "SICF: service /sap/bc/ztmc_login missing or not activated in this client"
    if status == 500:
        return "SERVER_ERROR", "Handler error: ST22 (ABAP dump) and SM21 at the logged time"
    if status and status >= 502:
        return "GATEWAY_ERROR", "ICM / web dispatcher error: SMICM trace, dev_icm"
    if json_body:
        return "EMPLOYEE_REFUSED", ("The service ran and refused the employee login (see errorCode): "
                                    "check the employee's verification key / user status")
    return "UNEXPECTED_REPLY", "Non-JSON reply: check the SICF handler and ICM trace"


def log_http_failure(*, pernr: str, actor: str, url: str, basic_user: str, basic_pwd_set: bool,
                     status: int | None = None, headers=None, body: str = "",
                     error_code: str = "", message: str = "", exc: Exception | None = None,
                     kind: str = "", json_body: bool = False, elapsed_ms: int | None = None) -> None:
    kind, hint = http_hint(status, json_body, kind)
    hdrs = {}
    if headers is not None:
        hdrs = {h: headers.get(h) for h in _HEADERS if headers.get(h)}
    snippet = (body or "")[:600].replace("\n", " ").replace("\r", " ")
    if "paswrd" in snippet.lower():
        snippet = "<redacted: body echoes the request>"
    auth_logger().warning(
        "LOGIN-SERVICE FAILURE %s",
        _kv(kind=kind, pernr=pernr, vim_user=actor, url=url, basic_user=basic_user or "(none)",
            basic_password_set=basic_pwd_set, http_status=status, elapsed_ms=elapsed_ms,
            error_code=error_code, message=message,
            exception=(f"{type(exc).__name__}: {describe_exception(exc)}" if exc else None),
            headers=hdrs or None, body=snippet or None, hint=hint),
    )


# ── RFC ──────────────────────────────────────────────────────────────────────

_RFC_ATTRS = ("key", "code", "msg_class", "msg_type", "msg_number",
              "msg_v1", "msg_v2", "msg_v3", "msg_v4")


def describe_exception(exc: BaseException) -> str:
    """Message + PyRFC's structured fields + the cause chain, on one line."""
    parts = [(getattr(exc, "message", None) or str(exc) or type(exc).__name__).strip()]
    extra = {a: getattr(exc, a) for a in _RFC_ATTRS
             if getattr(exc, a, None) not in (None, "")}
    if extra:
        parts.append(_kv(**{a: str(v) for a, v in extra.items()}))
    cause, depth = exc.__cause__ or exc.__context__, 0
    while cause is not None and depth < 3:
        parts.append(f"caused by {type(cause).__name__}: {str(cause)[:300]}")
        cause, depth = cause.__cause__ or cause.__context__, depth + 1
    return " | ".join(p.replace("\n", " ") for p in parts if p)


def rfc_hint(exc: BaseException) -> tuple[str, str]:
    text = f"{getattr(exc, 'key', '')} {exc}".upper()
    if "LOGON" in text or "PASSWORD" in text or "LOCKED" in text:
        return "RFC_LOGON_FAILURE", "SU01 for the RFC user: password, lock, validity, user type; SM21 / ST11"
    if "AUTHORI" in text or "S_RFC" in text or "NO RFC" in text:
        return "RFC_AUTHORIZATION_FAILURE", ("S_RFC (function group of the FM) / object auth for the RFC user: "
                                             "SU53 right after the failure, ST01 auth trace")
    if "FU_NOT_FOUND" in text or "FUNCTION_NOT_FOUND" in text or "GETFUNCTIONDESC" in text:
        return "FUNCTION_NOT_FOUND", "Function module missing in this system/client, or not remote-enabled (SE37 attributes)"
    if "COMMUNICATION" in text or "PARTNER" in text or "SAPROUTER" in text or "TIMEOUT" in text:
        return "RFC_COMMUNICATION_FAILURE", "Network/SAProuter/gateway: SMGW, saprouttab, firewall"
    return "RFC_ERROR", "ST22 / SM21 on the SAP side at the logged time"


def log_rfc_failure(context: str, exc: BaseException, *, rfc_user: str = "",
                    actor: str = "", function: str = "", **extra) -> str:
    """Log an RFC failure under a SAP user. Returns the kind (e.g. RFC_LOGON_FAILURE)."""
    kind, hint = rfc_hint(exc)
    auth_logger().warning(
        "RFC FAILURE %s",
        _kv(context=context, kind=kind, function=function, rfc_user=rfc_user or settings.SAP_USER,
            vim_user=actor, ashost=settings.SAP_ASHOST, client=settings.SAP_CLIENT,
            sysnr=settings.SAP_SYSNR, exception=f"{type(exc).__name__}: {describe_exception(exc)}",
            hint=hint, **{k: str(v) for k, v in extra.items()}),
    )
    return kind
