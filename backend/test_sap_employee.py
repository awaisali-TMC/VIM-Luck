"""SAP employee login + approval-hierarchy check (Lucky Cement), offline.

What it proves, on the fixture SAP (no SAP, no network, no Gemini):
- the login service client: the request it sends (8-digit PERNR, Basic auth,
  JSON body), both documented replies, a non-JSON 401 and a network error —
  against an in-process mock transport, so nothing leaves the machine;
- with the feature off, GET /employee-login says so and parking is unchanged;
- POST /employee-login stores the PERNR + encrypted password on a success, and
  changes nothing on a wrong password; GET re-checks the stored login;
- ZINI_VERIFY (fake): EV_FLAG 'X' -> ok, '' -> no hierarchy, per-amount limit;
- with the check on, the submit dry run reports a missing hierarchy and a park
  is refused (422) with nothing parked in SAP; with a hierarchy it parks.

Uses its own throwaway SQLite database, recreated on every run.

    py -3 backend/test_sap_employee.py
"""

import json
import logging
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(__file__))

SCRATCH = os.path.join(tempfile.gettempdir(), "sap_employee_test.db")
if os.path.exists(SCRATCH):
    os.remove(SCRATCH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{SCRATCH}"
os.environ["DEBUG"] = "true"
os.environ["SAP_MODE"] = "fake"
os.environ["GEMINI_API_KEY"] = ""
AUTH_LOG = os.path.join(tempfile.gettempdir(), "sap_employee_test_auth.log")
for _f in (AUTH_LOG,):
    if os.path.exists(_f):
        os.remove(_f)
os.environ["SAP_AUTH_LOG_FILE"] = AUTH_LOG

from app.config import settings  # noqa: E402

settings.DEBUG = True
settings.SAP_MODE = "fake"
settings.SAP_ENABLED = True
settings.SAP_FAKE_DB_PATH = ""
settings.SAP_WORKFLOW_ENABLED = False
settings.SAP_WF_POLL_SECONDS = 0
settings.SAP_EMPLOYEE_LOGIN_ENABLED = False
settings.SAP_HIERARCHY_CHECK_ENABLED = False

import httpx  # noqa: E402
from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.main as main  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models.internal_user import InternalUser  # noqa: E402
from app.security import get_current_principal, get_current_internal_user, Principal  # noqa: E402
from app.services import sap_connector_fake as fake  # noqa: E402
from app.services import sap_employee  # noqa: E402
from app.services.sap_credentials import decrypt_sap_password  # noqa: E402

PO = "4500009001"
LINE = {"description": "Split AC Unit 1.5 Ton Inverter", "quantity": 20, "unit": "ST",
        "unit_price": 185000, "amount": 3700000}
_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}" + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


# ── 1. Login service client, against a mock transport ───────────────────────

def test_login_client():
    print("\nUNIT: login service client (mock HTTP, live mode)")
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        seen["body"] = json.loads(request.content)
        if seen["body"]["paswrd"] == "123":
            return httpx.Response(200, json={"success": True, "code": 200, "errorCode": "OK",
                                              "message": "Login successful", "userid": "00004007",
                                              "name": "WASEEM QURESHI "})
        if seen["body"]["paswrd"] == "basic-refused":
            return httpx.Response(401, text="<html>Logon failed</html>")
        if seen["body"]["paswrd"] == "down":
            raise httpx.ConnectError("no route", request=request)
        if seen["body"]["paswrd"] == "tls":
            raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate", request=request)
        return httpx.Response(401, json={"success": False, "code": 401, "errorCode": "INVALID_PASSWORD",
                                         "message": "Verification key does not match",
                                         "userid": "", "name": ""})

    real_client = httpx.Client

    def mock_client(*a, **kw):
        kw.pop("verify", None)
        return real_client(*a, transport=httpx.MockTransport(handler), **kw)

    saved = (settings.SAP_MODE, settings.SAP_LOGIN_API_USER, settings.SAP_LOGIN_API_PASSWORD)
    settings.SAP_MODE = "live"
    settings.SAP_LOGIN_API_USER, settings.SAP_LOGIN_API_PASSWORD = "TMC_VIM", "tech-secret"
    httpx.Client = mock_client
    try:
        r = sap_employee.verify_employee_login("4007", "123")
        expect("success -> ok, name trimmed", r["ok"] and r["name"] == "WASEEM QURESHI", r)
        expect("userId sent as the 8-digit PERNR", seen["body"] == {"userId": "00004007", "paswrd": "123"}, seen["body"])
        expect("Basic auth with the technical user", seen["auth"].startswith("Basic "), seen["auth"])
        expect("posted to SAP_LOGIN_API_URL", seen["url"] == settings.SAP_LOGIN_API_URL, seen["url"])

        r = sap_employee.verify_employee_login("00004007", "wrong")
        expect("wrong password -> not ok, INVALID_PASSWORD, not 'unreachable'",
               not r["ok"] and r["error_code"] == "INVALID_PASSWORD" and not r["unreachable"], r)

        r = sap_employee.verify_employee_login("00004007", "basic-refused")
        expect("non-JSON 401 -> unreachable, names the Basic-auth login",
               not r["ok"] and r["unreachable"] and "SAP_LOGIN_API_USER" in r["message"], r)

        r = sap_employee.verify_employee_login("00004007", "down")
        expect("network error -> unreachable", not r["ok"] and r["unreachable"], r)

        r = sap_employee.verify_employee_login("00004007", "tls", actor="1:admin@test")
        expect("TLS error -> error_code TLS", r["error_code"] == "TLS", r)
    finally:
        httpx.Client = real_client
        settings.SAP_MODE, settings.SAP_LOGIN_API_USER, settings.SAP_LOGIN_API_PASSWORD = saved

    expect("PERNR padding", sap_employee.normalize_pernr(" 4007 ") == "00004007")


def _log_text():
    for h in logging.getLogger("sap_auth").handlers:
        h.flush()
    return open(AUTH_LOG, encoding="utf-8").read() if os.path.exists(AUTH_LOG) else ""


def test_auth_log():
    print("\nUNIT: SAP authorization log (for Basis)")
    from app.services.sap_auth_log import log_rfc_failure
    text = _log_text()
    expect("log file written", bool(text), AUTH_LOG)
    expect("successful login logged at INFO with the name", "LOGIN-SERVICE OK" in text and "WASEEM QURESHI" in text)
    expect("wrong password -> EMPLOYEE_REFUSED + errorCode",
           "kind='EMPLOYEE_REFUSED'" in text and "INVALID_PASSWORD" in text)
    expect("HTML 401 -> BASIC_AUTH_REFUSED with an SU01/SU53 hint",
           "kind='BASIC_AUTH_REFUSED'" in text and "SU53" in text)
    expect("network -> CONNECT, certificate -> TLS (STRUST hint)",
           "kind='CONNECT'" in text and "kind='TLS'" in text and "STRUST" in text)
    expect("logs the technical user name and the VIM user",
           "basic_user='TMC_VIM'" in text and "vim_user='1:admin@test'" in text)
    for secret in ("tech-secret", "'123'", "basic-refused", "paswrd\": "):
        expect(f"no password in the log ({secret})", secret not in text)

    class FakeRfcError(Exception):
        key = "RFC_AUTHORIZATION_FAILURE"
        message = "User TMC_VIM has no RFC authorization for function module ZINI_VERIFY"
        msg_class, msg_number = "00", "001"

    kind = log_rfc_failure("hierarchy check", FakeRfcError(), actor="1:admin@test",
                           function="ZINI_VERIFY", pernr="00009001")
    text = _log_text()
    expect("RFC auth failure classified", kind == "RFC_AUTHORIZATION_FAILURE", kind)
    expect("RFC line carries key, message class, function and S_RFC hint",
           "RFC FAILURE" in text and "msg_class='00'" in text and "function='ZINI_VERIFY'" in text
           and "S_RFC" in text)

    class Logon(Exception):
        key = "RFC_LOGON_FAILURE"
    expect("RFC logon failure classified",
           log_rfc_failure("x", Logon("Name or password is incorrect")) == "RFC_LOGON_FAILURE")


# ── 2. ZINI_VERIFY on the fixture connector ──────────────────────────────────

def test_hierarchy_unit():
    print("\nUNIT: ZINI_VERIFY (fixture)")
    ok = sap_employee.check_hierarchy_now("9001", 5_000_000, "PKR")
    expect("employee with a hierarchy -> ok, EV_FLAG X", ok["ok"] and ok["flag"] == "X", ok)
    no = sap_employee.check_hierarchy_now("00009099", 10, "PKR")
    expect("employee without one -> not ok, EV_FLAG ''", not no["ok"] and no["flag"] == "", no)
    expect("message names the employee and the RFC", "00009099" in no["message"] and "ZINI_VERIFY" in no["message"], no)
    expect("under the amount limit -> ok", sap_employee.check_hierarchy_now("00009002", 100000, "PKR")["ok"])
    expect("over the amount limit -> not ok", not sap_employee.check_hierarchy_now("00009002", 100000.01, "PKR")["ok"])


# ── 3. Over HTTP ─────────────────────────────────────────────────────────────

_po_id = None


def _new_invoice(client):
    global _po_id
    if _po_id is None:
        r = client.post(f"/api/sap/pos/{PO}/sync")
        _po_id = r.json().get("po_id") or r.json().get("id")
    r = client.post("/api/invoices/save", json={
        "original_filename": "emp.pdf", "stored_filepath": "demo/emp", "mime_type": "application/pdf",
        "invoice_number": f"EMP-{uuid.uuid4().hex[:8].upper()}", "invoice_date": "2026-03-12",
        "currency": "PKR", "document_type": "invoice", "status": "validated",
        "source_type": "upload", "po_reference": PO, "supplier_ntn": "0912345-6",
        "subtotal_amount": 3700000, "tax_amount": 0, "total_amount": 3700000,
        "line_items": [dict(LINE)],
    })
    inv_id = r.json()["id"]
    m = client.post(f"/api/po-matching/invoices/{inv_id}/match", json={"po_id": _po_id})
    expect(f"match invoice {inv_id} -> 200 (got {m.status_code})", m.status_code == 200, m.text[:160])
    return inv_id


def _post(client, inv_id, mode):
    return client.post(f"/api/sap/invoices/{inv_id}/post",
                       json={"mode": mode, "tax_code": "I1", "layout": "goods", "posting_date": "20260312"})


def _rbkp_count():
    return fake._store().execute("SELECT count(*) AS n FROM RBKP").fetchone()["n"]


def _stored_user():
    import asyncio
    from app.database import async_session

    async def run():
        async with async_session() as db:
            return (await db.execute(select(InternalUser).where(InternalUser.id == 1))).scalar_one()
    return asyncio.run(run())


def test_http(client):
    print("\nHTTP: feature off")
    s = client.get("/api/sap/employee-login").json()
    expect("GET says disabled", s["enabled"] is False, s)
    expect("hierarchy-check says disabled", client.post("/api/sap/hierarchy-check", json={"amount": 1}).json() == {"enabled": False})
    expect("sign-in refused while off", client.post("/api/sap/employee-login",
                                                    json={"user_id": "9001", "password": "demo123"}).status_code == 400)
    inv = _new_invoice(client)
    expect("park works with no SAP login at all", _post(client, inv, "park").status_code == 200)

    settings.SAP_EMPLOYEE_LOGIN_ENABLED = True
    settings.SAP_HIERARCHY_CHECK_ENABLED = True

    print("\nHTTP: sign in")
    s = client.get("/api/sap/employee-login").json()
    expect("enabled, not signed in yet", s["enabled"] and not s["signed_in"], s)
    r = client.post("/api/sap/employee-login", json={"user_id": "9099", "password": "nope"})
    expect("wrong password -> 401", r.status_code == 401, r.text)
    expect("...and nothing stored", not _stored_user().sap_username)

    inv = _new_invoice(client)
    r = _post(client, inv, "validate")
    expect("dry run without a SAP login -> 422 asking to sign in",
           r.status_code == 422 and "Sign in" in r.json()["detail"], r.text)

    r = client.post("/api/sap/employee-login", json={"user_id": "9099", "password": "demo123"})
    expect("right password -> 200 signed in", r.status_code == 200 and r.json()["signed_in"], r.text)
    u = _stored_user()
    expect("PERNR stored 8-digit", u.sap_username == "00009099", u.sap_username)
    expect("password stored encrypted", u.sap_password_enc and u.sap_password_enc != "demo123"
           and decrypt_sap_password(u.sap_password_enc) == "demo123")
    s = client.get("/api/sap/employee-login").json()
    expect("GET re-checks the stored login -> signed in with name",
           s["signed_in"] and s["name"] == "DEMO NO HIERARCHY", s)

    print("\nHTTP: hierarchy gate")
    r = client.post("/api/sap/hierarchy-check", json={"amount": 3700000, "currency": "PKR"}).json()
    expect("review-screen check -> no hierarchy", r["enabled"] and r["ok"] is False, r)
    r = _post(client, inv, "validate")
    expect("submit dry run -> ok false with the reason",
           r.status_code == 200 and r.json()["ok"] is False and "No SAP approval hierarchy" in r.json()["message"], r.text)
    before = _rbkp_count()
    r = _post(client, inv, "park")
    expect("park refused -> 422", r.status_code == 422, r.text)
    expect("...nothing parked in SAP", _rbkp_count() == before)

    client.post("/api/sap/employee-login", json={"user_id": "00009001", "password": "demo123"})
    expect("switching employee replaces the stored ID", _stored_user().sap_username == "00009001")
    r = client.post("/api/sap/hierarchy-check", json={"amount": 3700000, "currency": "Rs."}).json()
    expect("with a hierarchy -> ok (junk currency dropped)", r["ok"] is True and r["currency"] == "", r)
    expect("dry run passes", _post(client, inv, "validate").json()["ok"] is True)
    r = _post(client, inv, "park")
    expect("park goes through -> 200", r.status_code == 200, r.text[:200])
    expect("...one document parked", _rbkp_count() == before + 1)

    client.post("/api/sap/employee-login", json={"user_id": "00009002", "password": "demo123"})
    inv = _new_invoice(client)
    r = _post(client, inv, "park")
    expect("amount over the employee's limit -> 422", r.status_code == 422, r.text[:200])
    expect("...and logged as HIERARCHY NOT FOUND", "HIERARCHY NOT FOUND" in _log_text()
           and "pernr='00009002'" in _log_text())

    r = client.get("/api/sap/auth-log?lines=50")
    expect("admin reads the log tail over HTTP", r.status_code == 200 and len(r.json()["lines"]) > 0, r.text[:200])


if __name__ == "__main__":
    test_login_client()
    test_hierarchy_unit()
    test_auth_log()

    async def _real_admin(db=Depends(get_db)):
        # The real row, in the request's own session, so a sign-in persists.
        return (await db.execute(select(InternalUser).where(InternalUser.id == 1))).scalar_one()

    main.app.dependency_overrides[get_current_principal] = lambda: Principal(
        kind="internal", id=1, role="admin")
    main.app.dependency_overrides[get_current_internal_user] = _real_admin

    with TestClient(main.app) as client:
        test_http(client)

    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        sys.exit(1)
    print("RESULT: ALL SAP EMPLOYEE TESTS PASSED")
    print("=" * 60)
