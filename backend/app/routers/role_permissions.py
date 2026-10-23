"""RBAC v2: dynamic roles + per-page access levels, editable by admin.

- `roles` table: the 8 originals are seeded as system roles (not deletable);
  admins can add/rename/delete custom roles.
- `role_permissions`: one row per (role, page) with level "view" | "edit";
  no row = no access. Admin is implicit full access and never stored.
- Pages are a code catalog (PAGES below) — new pages ship with releases and
  appear in the admin grid automatically.
"""

import logging
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.role_permission import RolePermission, SeededPage
from app.models.role import Role
from app.models.internal_user import InternalUser
from app.models.workflow import WorkflowStep
from app.security import Principal, get_current_principal, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/role-permissions", tags=["role-permissions"])
roles_router = APIRouter(prefix="/api/roles", tags=["roles"])

LEVELS = ("view", "edit")

# The 8 built-in roles, seeded as system roles.
SYSTEM_ROLES = [
    ("admin",               "Admin"),
    ("ap_manager",          "AP Manager"),
    ("ap_operator",         "Purchaser"),
    ("finance_director",    "Finance Director"),
    ("tax_manager",         "Tax Manager"),
    ("procurement_manager", "Procurement Manager"),
    ("auditor",             "Auditor"),
    ("department_head",     "Department Head"),
]

# Manageable sidebar pages (code catalog; "/results" follows "/upload" on the
# frontend; ADMIN-section pages are hard-locked to admin and not managed here).
PAGES = [
    {"key": "/",              "label": "Analytics"},
    {"key": "/ap-visibility", "label": "AP Visibility"},
    {"key": "/ap",            "label": "Purchaser Dashboard"},
    {"key": "/tax",           "label": "Tax Manager Dashboard"},
    {"key": "/auditor",       "label": "Auditor Dashboard"},
    {"key": "/approvals",     "label": "My Approvals"},
    {"key": "/upload",        "label": "Upload Invoice"},
    {"key": "/invoices",      "label": "Invoice Inbox"},
    {"key": "/reports",       "label": "Reports"},
    {"key": "/po/new",        "label": "Upload PO"},
    {"key": "/po",            "label": "Purchase Orders"},
]
PAGE_KEYS = {p["key"] for p in PAGES}

# Default level matrix for fresh installs (mirrors pre-v2 behavior: only the
# Invoice Inbox distinguished view vs edit — reviewer roles were read-only).
DEFAULT_MATRIX: dict[str, dict[str, str]] = {
    "ap_manager":          {"/": "edit", "/ap-visibility": "edit", "/ap": "edit", "/approvals": "edit",
                            "/upload": "edit", "/invoices": "edit", "/po/new": "edit", "/po": "edit"},
    "ap_operator":         {"/ap": "edit", "/upload": "edit", "/invoices": "edit", "/reports": "edit", "/po/new": "edit", "/po": "edit"},
    "finance_director":    {"/": "edit", "/ap-visibility": "edit", "/approvals": "edit", "/invoices": "edit", "/po": "edit"},
    "tax_manager":         {"/tax": "edit", "/approvals": "edit", "/invoices": "view"},
    "auditor":             {"/auditor": "edit", "/invoices": "view", "/po": "edit"},
    "procurement_manager": {"/approvals": "edit", "/invoices": "view", "/po/new": "edit", "/po": "edit"},
    "department_head":     {"/approvals": "edit", "/invoices": "view"},
}

# Roles that could edit invoices before levels existed (used only by the
# one-time migration of pre-v2 rows).
_PRE_V2_INVOICE_EDITORS = {"admin", "ap_manager", "ap_operator", "finance_director"}


class _RoleFields(BaseModel):
    """Shared validation. The limits are the column widths in models/role.py —
    Postgres enforces them (a longer value is an unhandled 500), SQLite does
    not, so they are checked here and both engines behave the same."""

    @field_validator("label", "description", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class RoleCreate(_RoleFields):
    label: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)


class RoleUpdate(_RoleFields):
    # Omitted = unchanged; present must be a usable name (blank is rejected
    # rather than silently ignored).
    label: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)


class MatrixUpdate(BaseModel):
    # {role_key: {page_key: "view"|"edit"}} — pages omitted = no access
    matrix: dict[str, dict[str, str]]


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug[:50]


async def _ensure_seeded(db: AsyncSession) -> None:
    """Seed the roles table and permission matrix on first use, and apply the
    one-time level migration for installs that predate levels."""
    have_roles = (await db.execute(select(Role.id).limit(1))).first()
    if have_roles is None:
        for key, label in SYSTEM_ROLES:
            db.add(Role(key=key, label=label, is_system=1))
        # One-time level fix for pre-v2 rows: everything was implicitly "edit"
        # except reviewer roles on the Invoice Inbox, which were read-only.
        rows = (await db.execute(select(RolePermission))).scalars().all()
        if rows:
            for r in rows:
                r.level = ("view" if r.page_key == "/invoices" and r.role not in _PRE_V2_INVOICE_EDITORS
                           else (r.level or "edit"))
        else:
            for role, pages in DEFAULT_MATRIX.items():
                for pk, level in pages.items():
                    db.add(RolePermission(role=role, page_key=pk, level=level))
        await db.commit()
        logger.info("Seeded roles table (+ permission levels)")
    await _sync_new_pages(db)


async def _sync_new_pages(db: AsyncSession) -> None:
    """Auto-grant defaults for pages ADDED to the catalog after install.

    New pages always appear in the admin grid (PAGES is code, not data) and
    admin has implicit access to everything. This closes the remaining gap:
    when a release ships a new page, the DEFAULT_MATRIX grants for it are
    applied to already-seeded databases too — exactly once per page (tracked in
    rbac_seeded_pages), so any admin edits afterwards are never overridden.
    """
    marked = {r[0] for r in (await db.execute(select(SeededPage.page_key))).all()}
    unmarked = [p["key"] for p in PAGES if p["key"] not in marked]
    if not unmarked:
        return
    # Pages that already have at least one grant predate this marker table (or
    # were just seeded above) — mark them as-is. Only pages no role has ever
    # been granted are treated as new and receive their defaults.
    granted_rows = (await db.execute(select(RolePermission.page_key).distinct())).all()
    ever_granted = {r[0] for r in granted_rows}
    added = []
    for pk in unmarked:
        if pk not in ever_granted:
            for role, pages in DEFAULT_MATRIX.items():
                if pk in pages:
                    db.add(RolePermission(role=role, page_key=pk, level=pages[pk]))
                    added.append(f"{role}:{pk}")
        db.add(SeededPage(page_key=pk))
    await db.commit()
    if added:
        logger.info(f"Applied default grants for new page(s): {', '.join(added)}")


async def _load_matrix(db: AsyncSession) -> dict[str, dict[str, str]]:
    rows = (await db.execute(select(RolePermission))).scalars().all()
    matrix: dict[str, dict[str, str]] = {}
    for row in rows:
        matrix.setdefault(row.role, {})[row.page_key] = row.level or "edit"
    return matrix


def humanize_role(key: str) -> str:
    """Last-resort display name for a role key with no label anywhere."""
    return (key or "").replace("_", " ").title()


async def role_labels(db: AsyncSession) -> dict[str, str]:
    """{role key: display name}. Names come from the roles table, so a rename
    in Roles & Permissions shows everywhere; the built-in defaults cover a
    table that has not been seeded yet."""
    labels = dict(SYSTEM_ROLES)
    rows = (await db.execute(select(Role.key, Role.label))).all()
    labels.update({key: label for key, label in rows if label})
    return labels


async def _load_roles(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(Role).order_by(Role.is_system.desc(), Role.label))).scalars().all()
    return [{"key": r.key, "label": r.label, "description": r.description, "is_system": r.is_system} for r in rows]


# ── Permission matrix ─────────────────────────────────────────────────────────

@router.get("")
async def get_role_permissions(db: AsyncSession = Depends(get_db)):
    """Roles + page catalog + level matrix. Seeds defaults on first use."""
    await _ensure_seeded(db)
    return {"roles": await _load_roles(db), "pages": PAGES, "matrix": await _load_matrix(db)}


@router.put("", dependencies=[Depends(require_admin)])
async def update_role_permissions(data: MatrixUpdate, db: AsyncSession = Depends(get_db)):
    """Replace the matrix (admin only). Unknown roles/pages/levels rejected."""
    await _ensure_seeded(db)
    known_roles = {r["key"] for r in await _load_roles(db)}
    for role, pages in data.matrix.items():
        if role not in known_roles:
            raise HTTPException(status_code=400, detail=f"Unknown role '{role}'")
        for pk, level in pages.items():
            if pk not in PAGE_KEYS:
                raise HTTPException(status_code=400, detail=f"Unknown page '{pk}'")
            if level not in LEVELS:
                raise HTTPException(status_code=400, detail=f"Invalid level '{level}' (use view|edit)")

    await db.execute(delete(RolePermission))
    for role, pages in data.matrix.items():
        if role == "admin":
            continue  # admin is implicit full access
        for pk, level in pages.items():
            db.add(RolePermission(role=role, page_key=pk, level=level))
    await db.commit()
    logger.info("Role-permission matrix updated by admin")
    return {"success": True, "matrix": await _load_matrix(db)}


# ── Roles CRUD ────────────────────────────────────────────────────────────────

@roles_router.get("")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """All roles — used by the user form, workflow steps, and the admin grid.

    Suppliers reach this too (their invoice pages show approver role names), so
    they get names only — not the descriptions or the system/custom flag.
    """
    await _ensure_seeded(db)
    roles = await _load_roles(db)
    if principal.kind != "internal":
        roles = [{"key": r["key"], "label": r["label"]} for r in roles]
    return {"roles": roles}


@roles_router.post("", dependencies=[Depends(require_admin)])
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db)):
    await _ensure_seeded(db)
    label = data.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Role name is required")
    key = _slugify(label)
    if not key:
        raise HTTPException(status_code=400, detail="Role name must contain letters/numbers")
    exists = (await db.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail=f"A role with key '{key}' already exists")
    db.add(Role(key=key, label=label, description=data.description, is_system=0))
    await db.commit()
    logger.info(f"Role created: {key}")
    return {"key": key, "label": label, "description": data.description, "is_system": 0}


@roles_router.patch("/{key}", dependencies=[Depends(require_admin)])
async def update_role(key: str, data: RoleUpdate, db: AsyncSession = Depends(get_db)):
    role = (await db.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if data.label is not None:
        role.label = data.label
    if data.description is not None:
        role.description = data.description
    await db.commit()
    return {"key": role.key, "label": role.label, "description": role.description, "is_system": role.is_system}


@roles_router.delete("/{key}", dependencies=[Depends(require_admin)])
async def delete_role(key: str, db: AsyncSession = Depends(get_db)):
    role = (await db.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted")
    in_use = (await db.execute(
        select(func.count(InternalUser.id)).where(InternalUser.role == key)
    )).scalar()
    if in_use:
        raise HTTPException(status_code=409, detail=f"{in_use} user(s) still have this role — reassign them first")
    # A workflow step naming a deleted role can never be actioned by anyone but
    # an admin (workflow_engine.can_user_act_on_step matches on the key).
    on_steps = (await db.execute(
        select(func.count(WorkflowStep.id)).where(WorkflowStep.approver_role == key)
    )).scalar()
    if on_steps:
        raise HTTPException(
            status_code=409,
            detail=f"{on_steps} workflow step(s) still route to this role — change them first",
        )
    await db.execute(delete(RolePermission).where(RolePermission.role == key))
    await db.delete(role)
    await db.commit()
    logger.info(f"Role deleted: {key}")
    return {"deleted": True, "key": key}
