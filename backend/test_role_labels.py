"""Role display names: the rename path, its blast radius, and its guards.

Covers the change that made every role name come from the `roles` table
(`role_labels()` in routers/role_permissions.py) and defaulted ap_operator to
"Purchaser": that a rename reaches every screen, that it changes ONE column of
ONE row and nothing else, and that authorization keeps working off the role
KEY afterwards.

Offline: no SAP, no Gemini, no network. Runs against its own throwaway
database and refuses to start against anything that looks like a real one.

    py -3 backend/test_role_labels.py                     # SQLite (default)
    ROLE_LABELS_DB=postgresql+asyncpg://postgres:pw@127.0.0.1:55432/roletest \
        py -3 backend/test_role_labels.py                 # Postgres 16

Postgres is the one that matters: it enforces VARCHAR lengths and unique
constraints that SQLite silently ignores, and it is what the cloud runs.
See README-role-labels-test.md.
"""

import asyncio
import csv
import hashlib
import io
import os
import secrets
import sys
import tempfile
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

# ── Database selection — must happen before app.config is imported, because
# app/database.py builds the engine at import time and backend/.env would
# otherwise win. Assignment, not setdefault: an inherited DATABASE_URL from a
# cloud-sql-proxy shell must NOT be honoured. ──────────────────────────────────
SCRATCH = os.path.join(tempfile.gettempdir(), "role_labels_test.db")
URL = os.environ.get("ROLE_LABELS_DB", f"sqlite+aiosqlite:///{SCRATCH}")


def _refuse(why: str):
    print(f"\nREFUSING TO RUN: {why}\n  ROLE_LABELS_DB={URL}")
    sys.exit(2)


_low = URL.lower()
if _low.startswith("sqlite"):
    # A local file: only the file it points at matters (the repo path itself may
    # well contain a customer name).
    if "invoices.db" in os.path.basename(_low) or "sap_fake" in os.path.basename(_low):
        _refuse("that is a working database, not a scratch one")
elif _low.startswith("postgresql"):
    for _bad in ("/cloudsql/", "cloudsql", ".run.app", "amazonaws", "azure", "neon.tech",
                 "supabase", "prod", "hilton", "mcml", "ogdcl", "lucky"):
        if _bad in _low:
            _refuse(f"the server address contains {_bad!r} — this suite only runs against a throwaway database")
    if not ("@127.0.0.1:" in _low or "@localhost:" in _low):
        _refuse("the Postgres host must be loopback")
    if ":5432/" in _low:
        _refuse("port 5432 is the default a proxy would use — run the test container on another port (e.g. 55432)")
    if not _low.rstrip("/").endswith("/roletest"):
        _refuse("the Postgres database must be named 'roletest'")
else:
    _refuse("unsupported database URL")

os.environ["DATABASE_URL"] = URL
os.environ["DEBUG"] = "true"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GCP_CREDENTIALS_JSON"] = ""

from fastapi.testclient import TestClient                                  # noqa: E402
from sqlalchemy import select, text                                        # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import settings                                            # noqa: E402

if settings.DATABASE_URL != URL:
    _refuse(f"settings.DATABASE_URL is {settings.DATABASE_URL!r}, not the scratch URL — .env won")
settings.SAP_ENABLED = False           # nothing may leave this machine
settings.FBR_LIVE_LOOKUP_ENABLED = False

import app.main as app_main                                                # noqa: E402
import app.routers.reports as reports_router                               # noqa: E402
from app.models.internal_user import InternalUser                          # noqa: E402
from app.models.invoice import Invoice                                     # noqa: E402
from app.models.role import Role                                           # noqa: E402
from app.models.role_permission import RolePermission                      # noqa: E402
from app.models.supplier import SupplierUser                               # noqa: E402
from app.models.workflow import ApprovalRequest, WorkflowStep, WorkflowTemplate  # noqa: E402
from app.services.workflow_engine import can_user_act_on_step              # noqa: E402

# Labels used by the tests. None of these strings exist in the codebase, so a
# test asserting them cannot accidentally pass against the pre-change code.
NEW_LABEL = "Zebra Purchasing Lead"
SECOND_LABEL = "Buying Desk"

TABLES = ["roles", "role_permissions", "internal_users", "workflow_steps",
          "workflow_templates", "invoices", "approval_requests", "rbac_seeded_pages"]

_failures = []


def expect(label, cond, extra=None):
    print(f"  [{'PASS' if cond else '**FAIL**'}] {label}"
          + (f"  ({extra})" if (extra is not None and not cond) else ""))
    if not cond:
        _failures.append(label)


def warn(label, cond, extra=None):
    """Known pre-existing issue: report, never fail the run."""
    print(f"  [{'ok  ' if cond else 'WARN'}] {label}" + (f"  ({extra})" if extra else ""))


# ── DB access, on its own engine and loop so it never fights the TestClient ──

def db_run(coro_fn):
    async def _wrap():
        eng = create_async_engine(URL)
        Session = async_sessionmaker(eng, expire_on_commit=False)
        try:
            async with Session() as session:
                return await coro_fn(session)
        finally:
            await eng.dispose()
    return asyncio.run(_wrap())


def snapshot():
    """{table: (row_count, sha256 of its rows)} — the blast-radius evidence."""
    async def _go(s):
        out = {}
        for table in TABLES:
            try:
                rows = (await s.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all()
            except Exception:
                continue
            digest = hashlib.sha256("|".join(repr(tuple(r)) for r in rows).encode()).hexdigest()
            out[table] = (len(rows), digest)
        return out
    return db_run(_go)


def roles_now():
    return db_run(lambda s: _roles(s))


async def _roles(s):
    rows = (await s.execute(select(Role.key, Role.label, Role.is_system, Role.description))).all()
    return {r[0]: {"label": r[1], "is_system": r[2], "description": r[3]} for r in rows}


def seed(objects):
    async def _go(s):
        for obj in objects:
            s.add(obj)
        await s.commit()
        return [getattr(o, "id", None) for o in objects]
    return db_run(_go)


def assert_scratch_is_empty():
    """Last line of defence: a real instance has data; a scratch DB does not.

    Runs before the app boots, because the lifespan seeds an admin user."""
    async def _go(s):
        out = {}
        for table in ("invoices", "internal_users"):
            try:
                out[table] = (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
            except Exception:
                out[table] = 0
        return out
    counts = db_run(_go)
    if any(v for v in counts.values()):
        _refuse(f"this database is not empty ({counts}) — it may be a real one")


# ── Fixtures ────────────────────────────────────────────────────────────────

def make_user(role, email=None):
    token = secrets.token_hex(16)
    user = InternalUser(
        email=email or f"{role}-{uuid.uuid4().hex[:6]}@test.local",
        display_name=f"Test {role}", password_hash="x", role=role, is_active=1,
        auth_token=token, token_issued_at=datetime.now(timezone.utc),
    )
    seed([user])
    return {"Authorization": f"Bearer {token}"}


def make_supplier():
    token = secrets.token_hex(16)
    sup = SupplierUser(name="Test Supplier", company_name="Test Co",
                       mobile=f"03{uuid.uuid4().int % 10**9:09d}", status="verified",
                       auth_token=token, token_issued_at=datetime.now(timezone.utc))
    seed([sup])
    return {"Authorization": f"Bearer {token}"}


def seed_roles(labels):
    """Put rows in `roles` BEFORE any endpoint runs — the production shape:
    a database that was seeded by an earlier release."""
    seed([Role(key=k, label=v, is_system=1) for k, v in labels.items()])


def seed_invoice_awaiting(role_key):
    """An invoice sitting on a workflow step owned by `role_key`, which is what
    the Reports 'pending with' column reads."""
    inv = Invoice(original_filename="t.pdf", stored_filepath="t", mime_type="application/pdf",
                  invoice_number=f"RL-{uuid.uuid4().hex[:8]}", invoice_date="2026-09-01",
                  supplier_name="Karachi Office Supplies", currency="PKR",
                  total_amount=1250, subtotal_amount=1250, tax_amount=0,
                  status="pending_approval", source_type="upload")
    tpl = WorkflowTemplate(name="Test flow", is_active=1)
    seed([inv, tpl])
    step = WorkflowStep(template_id=tpl.id, step_order=1, step_name="Review", approver_role=role_key)
    req = ApprovalRequest(invoice_id=inv.id, workflow_template_id=tpl.id,
                          current_step_order=1, overall_status="in_progress", total_steps=1)
    seed([step, req])
    return inv.id, step


# ═══════════════════════════════════════════════════════════════════════════
# Group A — bootstrap and the production-shaped case
# ═══════════════════════════════════════════════════════════════════════════

def test_bootstrap(client, admin):
    print("\nA. Bootstrap")
    from app.routers.role_permissions import SYSTEM_ROLES

    roles = client.get("/api/roles", headers=admin).json()["roles"]
    got = {r["key"]: r["label"] for r in roles}
    expect("a fresh database seeds exactly the built-in roles", got == dict(SYSTEM_ROLES), got)
    expect("ap_operator defaults to Purchaser", got.get("ap_operator") == "Purchaser", got.get("ap_operator"))
    expect("every seeded role is marked as a system role", all(r["is_system"] == 1 for r in roles))

    pages = {p["key"]: p["label"] for p in client.get("/api/role-permissions", headers=admin).json()["pages"]}
    expect("the dashboard page is named Purchaser Dashboard",
           pages.get("/ap") == "Purchaser Dashboard", pages.get("/ap"))


def test_existing_db_labels_survive(client, admin):
    """The deploy case: a database seeded by an earlier release keeps its names."""
    print("\nA. An existing database keeps its own labels")
    before = roles_now()
    client.get("/api/roles", headers=admin)                  # would re-seed if the guard broke
    client.get("/api/role-permissions", headers=admin)
    after = roles_now()
    expect("reading roles does not rewrite stored labels", before == after,
           {k: (before.get(k, {}).get("label"), after.get(k, {}).get("label"))
            for k in after if before.get(k) != after.get(k)})
    expect("the stored label still wins over the code default",
           after["ap_operator"]["label"] == NEW_LABEL, after["ap_operator"]["label"])


# ═══════════════════════════════════════════════════════════════════════════
# Group B — a rename reaches every screen
# ═══════════════════════════════════════════════════════════════════════════

def test_rename_propagates(client, admin, invoice_id):
    print("\nB. A rename reaches every screen")
    r = client.patch("/api/roles/ap_operator", json={"label": NEW_LABEL}, headers=admin)
    expect("an admin can rename a role", r.status_code == 200, r.text[:160])
    expect("the role key is untouched by a rename", r.json().get("key") == "ap_operator", r.text[:160])

    filters = client.get("/api/reports/filters", headers=admin).json()
    approvers = {a["value"]: a["label"] for a in filters.get("approvers", [])}
    expect("Reports 'pending with' filter uses the new name",
           approvers.get("ap_operator") == NEW_LABEL, approvers)

    summary = client.get("/api/reports/summary?days=90", headers=admin).json()
    pend = {p["role"]: p["label"] for p in summary.get("pending_by_approver", [])}
    expect("the Reports summary uses the new name", pend.get("ap_operator") == NEW_LABEL, pend)

    table = client.get("/api/reports/invoices?days=90", headers=admin).json()
    row = next((i for i in table.get("items", []) if i["id"] == invoice_id), None)
    expect("the Reports table 'Pending With' uses the new name",
           row and row.get("pending_with") == NEW_LABEL, row and row.get("pending_with"))

    csv_text = client.get("/api/reports/export?fmt=csv&days=90", headers=admin).text
    rows = list(csv.reader(io.StringIO(csv_text)))
    col = rows[0].index("Pending With")
    expect("the CSV export uses the new name",
           any(len(rw) > col and rw[col] == NEW_LABEL for rw in rows[1:]), rows[:3])

    xlsx = client.get("/api/reports/export?fmt=xlsx&days=90", headers=admin)
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(xlsx.content)).active
    cells = [str(c.value) for rw in ws.iter_rows() for c in rw]
    expect("the Excel export uses the new name", NEW_LABEL in cells, cells[:20])


def test_label_source_is_the_database(client, admin):
    """Negative control: with role_labels() neutered the name must degrade,
    which proves the assertions above are driven by the DB, not a coincidence."""
    print("\nB. The names really come from the roles table")
    original = reports_router.role_labels

    async def _empty(_db):
        return {}

    reports_router.role_labels = _empty
    try:
        approvers = {a["value"]: a["label"]
                     for a in client.get("/api/reports/filters", headers=admin).json().get("approvers", [])}
    finally:
        reports_router.role_labels = original
    expect("without the roles table the name degrades to the humanised key",
           approvers.get("ap_operator") == "Ap Operator", approvers)

    approvers = {a["value"]: a["label"]
                 for a in client.get("/api/reports/filters", headers=admin).json().get("approvers", [])}
    expect("and comes back once the lookup is restored",
           approvers.get("ap_operator") == NEW_LABEL, approvers)


def test_unknown_role_degrades(client, admin):
    print("\nB. An unknown role key still renders")
    seed_invoice_awaiting("regional_buyer")          # a key with no row in `roles`
    approvers = {a["value"]: a["label"]
                 for a in client.get("/api/reports/filters", headers=admin).json().get("approvers", [])}
    expect("a role key with no row falls back to a humanised name",
           approvers.get("regional_buyer") == "Regional Buyer", approvers)


def test_sap_refusal_names_the_role(client, invoice_id):
    print("\nB. The SAP parking refusal names the role")
    wrong = make_user("tax_manager")
    r = client.post(f"/api/sap/invoices/{invoice_id}/post", json={}, headers=wrong)
    detail = str(r.json().get("detail"))
    expect("a role that cannot park is refused", r.status_code == 403, r.status_code)
    expect("the refusal names the renamed role", NEW_LABEL in detail, detail)
    expect("the refusal names Admin too", "Admin" in detail, detail)


# ═══════════════════════════════════════════════════════════════════════════
# Group C — blast radius
# ═══════════════════════════════════════════════════════════════════════════

def test_blast_radius(client, admin):
    print("\nC. What a rename actually changes")
    before = snapshot()
    r = client.patch("/api/roles/ap_operator", json={"label": SECOND_LABEL}, headers=admin)
    expect("the rename succeeded", r.status_code == 200, r.text[:160])
    after = snapshot()

    for table in [t for t in before if t != "roles"]:
        expect(f"{table} is byte-identical after a rename", before[table] == after[table],
               f"{before[table]} -> {after[table]}")
    expect("no table gained or lost rows",
           all(before[t][0] == after[t][0] for t in before),
           {t: (before[t][0], after[t][0]) for t in before if before[t][0] != after[t][0]})
    expect("the roles table did change", before["roles"][1] != after["roles"][1])

    async def _rows(s):
        return (await s.execute(text("SELECT id, key, label, is_system, description FROM roles ORDER BY id"))).all()
    rows = db_run(_rows)
    renamed = [r for r in rows if r[1] == "ap_operator"]
    expect("exactly one row carries the key", len(renamed) == 1, len(renamed))
    expect("only the label changed on that row",
           renamed[0][2] == SECOND_LABEL and renamed[0][3] == 1 and renamed[0][4] is None, renamed[0])


# ═══════════════════════════════════════════════════════════════════════════
# Group D — authorization still works off the key
# ═══════════════════════════════════════════════════════════════════════════

def test_authorization_survives_rename(client, admin):
    print("\nD. Authorization after a rename")
    operator = make_user("ap_operator")
    tax = make_user("tax_manager")

    expect("the renamed role can still open Reports",
           client.get("/api/reports/filters", headers=operator).status_code == 200)
    expect("a role without access is still refused",
           client.get("/api/reports/filters", headers=tax).status_code == 403)

    matrix = client.get("/api/role-permissions", headers=admin).json()["matrix"]
    expect("the permission matrix is still keyed by the role key",
           "ap_operator" in matrix and "/upload" in matrix["ap_operator"], list(matrix)[:5])

    step = WorkflowStep(template_id=1, step_order=1, step_name="s", approver_role="ap_operator")
    expect("workflow steps still match on the key",
           can_user_act_on_step(7, "ap_operator", None, step) is True)
    expect("workflow steps do not match on the display name",
           can_user_act_on_step(7, SECOND_LABEL, None, step) is False)


def test_park_gate_unchanged(client, invoice_id):
    print("\nD. The SAP parking gate")
    operator = make_user("ap_operator")
    r = client.post(f"/api/sap/invoices/{invoice_id}/post", json={}, headers=operator)
    expect("a role that may park is not refused by the role gate", r.status_code != 403, r.status_code)


# ═══════════════════════════════════════════════════════════════════════════
# Group E — what a rename will accept
# ═══════════════════════════════════════════════════════════════════════════

def test_label_validation(client, admin):
    print("\nE. Label validation")
    current = roles_now()["ap_operator"]["label"]

    r = client.patch("/api/roles/ap_operator", json={"label": "   "}, headers=admin)
    expect("a blank name is rejected", r.status_code in (400, 422), f"{r.status_code} {r.text[:120]}")
    expect("a blank name leaves the stored name alone", roles_now()["ap_operator"]["label"] == current)

    for size in (101, 4000):
        r = client.patch("/api/roles/ap_operator", json={"label": "A" * size}, headers=admin)
        expect(f"a {size}-character name is rejected, not stored or 500",
               r.status_code in (400, 422), f"{r.status_code} {r.text[:120]}")
    expect("an over-long name leaves the stored name alone",
           roles_now()["ap_operator"]["label"] == current, roles_now()["ap_operator"]["label"])

    r = client.patch("/api/roles/ap_operator", json={"label": "A" * 100}, headers=admin)
    expect("a name of exactly 100 characters is accepted", r.status_code == 200, r.text[:120])
    client.patch("/api/roles/ap_operator", json={"label": current}, headers=admin)

    r = client.patch("/api/roles/ap_operator", json={"description": "desc only"}, headers=admin)
    expect("omitting the label leaves it unchanged",
           r.status_code == 200 and roles_now()["ap_operator"]["label"] == current, r.text[:120])
    client.patch("/api/roles/ap_operator", json={"description": ""}, headers=admin)


def test_label_is_data_not_code(client, admin):
    print("\nE. Odd names are data, never code")
    hostile = "Zed'); DROP TABLE roles;--"
    r = client.patch("/api/roles/auditor", json={"label": hostile}, headers=admin)
    expect("a name containing SQL is accepted as text", r.status_code == 200, r.text[:120])
    expect("it round-trips verbatim", roles_now()["auditor"]["label"] == hostile)
    expect("the roles table is still there with all its rows", len(roles_now()) >= 8, len(roles_now()))

    emoji = "Purchaser 🛒 مشتري"
    client.patch("/api/roles/auditor", json={"label": emoji}, headers=admin)
    expect("unicode and emoji round-trip", roles_now()["auditor"]["label"] == emoji)
    labels = {a["value"]: a["label"] for a in client.get("/api/reports/filters", headers=admin).json()["approvers"]}
    expect("unicode survives the reports filter", "auditor" not in labels or labels["auditor"] == emoji, labels)

    client.patch("/api/roles/auditor", json={"label": "=1+1"}, headers=admin)
    seed_invoice_awaiting("auditor")
    csv_text = client.get("/api/reports/export?fmt=csv&days=90", headers=admin).text
    cells = [c for row in csv.reader(io.StringIO(csv_text)) for c in row]
    expect("a spreadsheet formula in a name is neutralised in the CSV export",
           not any(c.startswith(("=", "+", "-", "@")) and "1+1" in c for c in cells),
           [c for c in cells if "1+1" in c])
    client.patch("/api/roles/auditor", json={"label": "Auditor"}, headers=admin)


def test_who_may_rename(client):
    print("\nE. Who may rename")
    operator = make_user("ap_operator")
    supplier = make_supplier()
    before = roles_now()["tax_manager"]["label"]

    r = client.patch("/api/roles/tax_manager", json={"label": "Nope"}, headers=operator)
    expect("a non-admin cannot rename", r.status_code == 403, r.status_code)
    r = client.patch("/api/roles/tax_manager", json={"label": "Nope"}, headers=supplier)
    expect("a supplier cannot rename", r.status_code in (401, 403), r.status_code)
    expect("neither attempt changed the stored name", roles_now()["tax_manager"]["label"] == before)

    r = client.get("/api/roles", headers=supplier)
    if r.status_code == 200:
        first = (r.json().get("roles") or [{}])[0]
        expect("a supplier reading roles sees names only, not internal flags",
               set(first) <= {"key", "label"}, list(first))


def test_unknown_key(client, admin):
    print("\nE. Unknown role keys")
    expect("renaming a role that does not exist is a 404",
           client.patch("/api/roles/does_not_exist", json={"label": "x"}, headers=admin).status_code == 404)
    expect("deleting a role that does not exist is a 404",
           client.delete("/api/roles/does_not_exist", headers=admin).status_code == 404)


# ═══════════════════════════════════════════════════════════════════════════
# Group G — custom roles
# ═══════════════════════════════════════════════════════════════════════════

def test_custom_role_lifecycle(client, admin):
    print("\nG. Custom roles")
    r = client.post("/api/roles", json={"label": "Warehouse Lead"}, headers=admin)
    expect("a custom role can be created", r.status_code == 200, r.text[:120])
    key = r.json().get("key")
    expect("its key is slugified from the name", key == "warehouse_lead", key)
    expect("it is not a system role", r.json().get("is_system") == 0)

    dupe = client.post("/api/roles", json={"label": "Warehouse Lead"}, headers=admin)
    expect("creating the same role twice is refused", dupe.status_code == 409, dupe.status_code)

    r = client.patch(f"/api/roles/{key}", json={"label": "Depot Lead"}, headers=admin)
    expect("a custom role can be renamed without changing its key",
           r.status_code == 200 and r.json()["key"] == key, r.text[:120])

    expect("a built-in role cannot be deleted",
           client.delete("/api/roles/ap_operator", headers=admin).status_code == 400)

    holder = make_user(key)
    expect("a role still held by a user cannot be deleted",
           client.delete(f"/api/roles/{key}", headers=admin).status_code == 409)
    db_run(lambda s: _deactivate(s, holder))

    tpl = WorkflowTemplate(name="Uses the custom role", is_active=1)
    seed([tpl])
    seed([WorkflowStep(template_id=tpl.id, step_order=1, step_name="Review", approver_role=key)])
    expect("a role still used by a workflow step cannot be deleted",
           client.delete(f"/api/roles/{key}", headers=admin).status_code == 409)


async def _deactivate(s, headers):
    token = headers["Authorization"].split()[1]
    user = (await s.execute(select(InternalUser).where(InternalUser.auth_token == token))).scalar_one()
    await s.delete(user)
    await s.commit()


def test_grants_are_not_over_deleted(client, admin):
    print("\nG. Deleting a role leaves other roles' access alone")
    a = client.post("/api/roles", json={"label": "Temp Alpha"}, headers=admin).json()["key"]
    b = client.post("/api/roles", json={"label": "Temp Beta"}, headers=admin).json()["key"]
    seed([RolePermission(role=a, page_key="/invoices", level="edit"),
          RolePermission(role=b, page_key="/invoices", level="edit"),
          RolePermission(role=b, page_key="/reports", level="edit")])

    r = client.delete(f"/api/roles/{a}", headers=admin)
    expect("an unused custom role can be deleted", r.status_code == 200, r.text[:120])

    async def _count(s):
        rows = (await s.execute(text("SELECT role, count(*) FROM role_permissions GROUP BY role"))).all()
        return dict(rows)
    counts = _count and db_run(_count)
    expect("its own grants are gone", counts.get(a, 0) == 0, counts)
    expect("the other role keeps all of its grants", counts.get(b) == 2, counts)


def test_two_roles_one_name(client, admin):
    print("\nG. Two roles may share a display name")
    client.patch("/api/roles/ap_operator", json={"label": "Shared Name"}, headers=admin)
    r = client.post("/api/roles", json={"label": "Shared Name"}, headers=admin)
    expect("a second role may use the same display name", r.status_code == 200, r.text[:120])
    expect("but gets its own key", r.json()["key"] != "ap_operator", r.json()["key"])
    roles = roles_now()
    expect("both rows still exist", roles["ap_operator"]["label"] == roles[r.json()["key"]]["label"])
    client.patch("/api/roles/ap_operator", json={"label": SECOND_LABEL}, headers=admin)


# ═══════════════════════════════════════════════════════════════════════════
# Group H — known pre-existing hazards (warn only)
# ═══════════════════════════════════════════════════════════════════════════

def test_cold_start_race(client, admin):
    print("\nH. Pre-existing hazards (warnings, not failures)")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = [f.result().status_code for f in [pool.submit(client.get, "/api/roles", headers=admin)
                                                  for _ in range(5)]]
    warn("five simultaneous reads of /api/roles all succeed", all(c == 200 for c in codes), codes)
    warn("no duplicate role rows after concurrent reads", len(roles_now()) >= 8, len(roles_now()))


def test_frontend_defaults_match_backend():
    print("\nH. Frontend and backend defaults agree")
    import re
    from app.routers.role_permissions import SYSTEM_ROLES
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "config", "roleLabels.js")
    try:
        src = open(path, encoding="utf-8").read()
    except OSError:
        return warn("frontend roleLabels.js found", False, path)
    block = src.split("DEFAULT_ROLE_LABELS", 1)[1].split("};", 1)[0]
    fe = dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', block))
    expect("the frontend fallback names match the backend defaults", fe == dict(SYSTEM_ROLES),
           {k: (fe.get(k), dict(SYSTEM_ROLES).get(k)) for k in set(fe) | set(dict(SYSTEM_ROLES))
            if fe.get(k) != dict(SYSTEM_ROLES).get(k)})


# ═══════════════════════════════════════════════════════════════════════════

def run_suite():
    print("=" * 62)
    print(f"Role display names — {'Postgres' if URL.startswith('postgresql') else 'SQLite'}")
    print(f"  {URL}")
    print("=" * 62)

    assert_scratch_is_empty()                     # before the app seeds its admin user
    with TestClient(app_main.app) as client:      # lifespan → create_all
        admin = make_user("admin")

        test_bootstrap(client, admin)
        invoice_id, _ = seed_invoice_awaiting("ap_operator")
        test_rename_propagates(client, admin, invoice_id)
        test_existing_db_labels_survive(client, admin)
        test_label_source_is_the_database(client, admin)
        test_unknown_role_degrades(client, admin)
        test_sap_refusal_names_the_role(client, invoice_id)
        test_blast_radius(client, admin)
        test_authorization_survives_rename(client, admin)
        test_park_gate_unchanged(client, invoice_id)
        test_label_validation(client, admin)
        test_label_is_data_not_code(client, admin)
        test_who_may_rename(client)
        test_unknown_key(client, admin)
        test_custom_role_lifecycle(client, admin)
        test_grants_are_not_over_deleted(client, admin)
        test_two_roles_one_name(client, admin)
        test_cold_start_race(client, admin)

    test_frontend_defaults_match_backend()

    print("\n" + "=" * 62)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED")
        for f in _failures:
            print(f"  - {f}")
        print("=" * 62)
        sys.exit(1)
    print("RESULT: ALL ROLE LABEL TESTS PASSED")
    print("=" * 62)


if __name__ == "__main__":
    run_suite()
