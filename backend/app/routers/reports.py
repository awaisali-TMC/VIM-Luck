"""Reports endpoints — filterable invoice reporting for admin & purchasers (ap_operator).

A single set of filters (vendor, supplier account, status, pending-with approver,
source, date range, amount range) drives four endpoints:

  GET /api/reports/filters   — available filter options (populate the dropdowns)
  GET /api/reports/summary   — KPI cards, status breakdown, top vendors, pending-by-approver
  GET /api/reports/invoices  — the filtered invoice rows (paginated table)
  GET /api/reports/export    — the filtered rows as a CSV or XLSX download

Gating is declared at include-time in main.py (admin + ap_operator). Every query
excludes soft-deleted invoices and is written portably (no SQLite-only date
functions) so it runs on both SQLite dev and the Postgres cloud instances.
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.invoice import Invoice
from app.models.supplier import SupplierUser
from app.models.workflow import ApprovalRequest, WorkflowStep
from app.routers.role_permissions import role_labels, humanize_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


# ── Display labels (shared by the dropdowns, the table and the exports) ───────

STATUS_LABELS = {
    "draft": "Draft",
    "pending_processing": "Processing",
    "validated": "Validated",
    "pending_approval": "Pending Approval",
    "approved": "Approved",
    "rejected": "Rejected",
    "exception": "Exception",
    "parked": "Parked",
    "posted": "Posted",
}
# Canonical left-to-right order for the status breakdown / donut.
STATUS_ORDER = list(STATUS_LABELS.keys())

SOURCE_LABELS = {
    "upload": "Upload",
    "web_upload": "Web Upload",
    "mobile_upload": "Mobile",
    "email": "Email",
    "supplier": "Supplier Portal",
    "po_flip": "From PO",
}

# Approver-role names come from the roles table (role_labels), so a rename in
# Roles & Permissions also shows in "Pending with".


# ── Filter helpers ────────────────────────────────────────────────────────────

def _sheet_safe(value):
    """Stop a spreadsheet treating a cell as a formula.

    Cell values include user-editable text (vendor names, and since role names
    became editable, the "Pending With" column), and Excel executes a cell that
    starts with = + - @. Prefixing an apostrophe keeps it as text.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse a YYYY-MM-DD (or full ISO) string into a UTC-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _date_bounds(date_from: Optional[str], date_to: Optional[str], days: int):
    """Resolve the [start, end) window. Falls back to the last `days` days."""
    now = datetime.now(timezone.utc)
    start = _parse_date(date_from) or (now - timedelta(days=days))
    end_dt = _parse_date(date_to)
    # Make the end date inclusive of the whole day the user picked.
    end = (end_dt + timedelta(days=1)) if end_dt else (now + timedelta(days=1))
    return start, end


def _base_conditions(
    start: datetime,
    end: datetime,
    vendor: Optional[str],
    supplier_id: Optional[int],
    source: Optional[List[str]],
    amount_min: Optional[float],
    amount_max: Optional[float],
    sap_status: Optional[str] = None,
):
    """Conditions shared by every report query EXCEPT the status / pending-with
    filters (those are layered on per-endpoint). Always drops soft-deleted rows."""
    conds = [
        func.coalesce(Invoice.is_deleted, 0) == 0,
        Invoice.created_at >= start,
        Invoice.created_at < end,
    ]
    if vendor:
        conds.append(Invoice.supplier_name == vendor)
    if supplier_id:
        conds.append(Invoice.supplier_id == supplier_id)
    if source:
        conds.append(Invoice.source_type.in_(source))
    if amount_min is not None:
        conds.append(func.coalesce(Invoice.total_amount, 0) >= amount_min)
    if amount_max is not None:
        conds.append(func.coalesce(Invoice.total_amount, 0) <= amount_max)
    if sap_status == "none":
        conds.append(or_(Invoice.sap_document_number.is_(None), Invoice.sap_document_number == ""))
    elif sap_status in ("parked", "posted"):
        conds.append(Invoice.sap_doc_status == sap_status)
    return conds


async def _pending_map(db: AsyncSession) -> dict[int, str]:
    """invoice_id → approver_role currently awaiting action.

    Built from every in-progress ApprovalRequest by matching its
    current_step_order against the steps of its workflow template.
    """
    reqs = (
        await db.execute(
            select(
                ApprovalRequest.invoice_id,
                ApprovalRequest.workflow_template_id,
                ApprovalRequest.current_step_order,
            ).where(ApprovalRequest.overall_status == "in_progress")
        )
    ).all()
    if not reqs:
        return {}

    template_ids = {r[1] for r in reqs if r[1] is not None}
    steps: dict[tuple, str] = {}
    if template_ids:
        step_rows = (
            await db.execute(
                select(
                    WorkflowStep.template_id,
                    WorkflowStep.step_order,
                    WorkflowStep.approver_role,
                ).where(WorkflowStep.template_id.in_(template_ids))
            )
        ).all()
        for tid, order, role in step_rows:
            steps[(tid, order)] = role

    mapping: dict[int, str] = {}
    for inv_id, tid, order in reqs:
        role = steps.get((tid, order))
        if role:
            mapping[inv_id] = role
    return mapping


# Shared query-param signature so all endpoints accept the same filters.
def _filter_params(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    days: int = Query(90, ge=1, le=1825),
    vendor: Optional[str] = Query(None),
    supplier_id: Optional[int] = Query(None),
    status: Optional[List[str]] = Query(None),
    pending_with: Optional[str] = Query(None),
    source: Optional[List[str]] = Query(None),
    amount_min: Optional[float] = Query(None),
    amount_max: Optional[float] = Query(None),
    sap_status: Optional[str] = Query(None, pattern="^(none|parked|posted)$"),
):
    return {
        "date_from": date_from,
        "date_to": date_to,
        "days": days,
        "vendor": vendor,
        "supplier_id": supplier_id,
        "status": status,
        "pending_with": pending_with,
        "source": source,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "sap_status": sap_status,
    }


async def _pending_with_ids(db: AsyncSession, pending_with: str) -> list[int]:
    """Invoice ids currently pending with a specific approver role."""
    pmap = await _pending_map(db)
    return [inv_id for inv_id, role in pmap.items() if role == pending_with]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Distinct values to populate the filter dropdowns."""
    not_deleted = func.coalesce(Invoice.is_deleted, 0) == 0

    # Vendors = distinct supplier_name on the invoices themselves.
    vendor_rows = (
        await db.execute(
            select(Invoice.supplier_name, func.count(Invoice.id))
            .where(and_(not_deleted, Invoice.supplier_name.isnot(None), Invoice.supplier_name != ""))
            .group_by(Invoice.supplier_name)
            .order_by(func.count(Invoice.id).desc())
        )
    ).all()
    vendors = [{"value": r[0], "count": r[1]} for r in vendor_rows]

    # Supplier accounts = portal users that have submitted at least one invoice.
    acct_rows = (
        await db.execute(
            select(SupplierUser.id, SupplierUser.company_name, func.count(Invoice.id))
            .join(Invoice, Invoice.supplier_id == SupplierUser.id)
            .where(not_deleted)
            .group_by(SupplierUser.id, SupplierUser.company_name)
            .order_by(SupplierUser.company_name)
        )
    ).all()
    supplier_accounts = [
        {"value": r[0], "label": r[1] or f"Supplier #{r[0]}", "count": r[2]} for r in acct_rows
    ]

    # Fixed source catalog (like statuses) so every channel is always
    # selectable — e.g. "Mobile" appears even before any mobile invoice exists.
    sources = [
        {"value": key, "label": SOURCE_LABELS[key]}
        for key in ("web_upload", "mobile_upload", "email", "supplier", "po_flip", "upload")
    ]

    # Approver roles used by any workflow step (for the "pending with" filter).
    role_rows = (
        await db.execute(
            select(WorkflowStep.approver_role)
            .where(WorkflowStep.approver_role.isnot(None))
            .group_by(WorkflowStep.approver_role)
        )
    ).all()
    labels = await role_labels(db)
    approvers = [
        {"value": r[0], "label": labels.get(r[0]) or humanize_role(r[0])}
        for r in role_rows
        if r[0]
    ]

    statuses = [{"value": s, "label": STATUS_LABELS[s]} for s in STATUS_ORDER]

    # SAP document tracking states (fixed catalog). The app only PARKS
    # invoices — posting happens inside SAP — so "posted" isn't offered as a
    # filter option (the API still accepts it for backwards compatibility).
    sap_statuses = [
        {"value": "none", "label": "Not in SAP"},
        {"value": "parked", "label": "Parked"},
    ]

    return {
        "vendors": vendors,
        "supplier_accounts": supplier_accounts,
        "statuses": statuses,
        "approvers": approvers,
        "sources": sources,
        "sap_statuses": sap_statuses,
    }


@router.get("/summary")
async def get_summary(
    filters: dict = Depends(_filter_params),
    db: AsyncSession = Depends(get_db),
):
    """KPI cards + status breakdown + top vendors + pending-by-approver."""
    start, end = _date_bounds(filters["date_from"], filters["date_to"], filters["days"])
    base = _base_conditions(
        start, end, filters["vendor"], filters["supplier_id"],
        filters["source"], filters["amount_min"], filters["amount_max"],
        filters["sap_status"],
    )

    # Full conditions add the status + pending-with filters on top of base.
    full = list(base)
    if filters["status"]:
        full.append(Invoice.status.in_(filters["status"]))
    if filters["pending_with"]:
        ids = await _pending_with_ids(db, filters["pending_with"])
        full.append(Invoice.id.in_(ids or [-1]))

    # KPI totals over the filtered set.
    totals = (
        await db.execute(
            select(func.count(Invoice.id), func.sum(Invoice.total_amount)).where(and_(*full))
        )
    ).one()
    total_invoices = totals[0] or 0
    total_value = float(totals[1] or 0)

    # Status breakdown (respects the full filters, so the donut matches the table).
    status_rows = (
        await db.execute(
            select(
                Invoice.status,
                func.count(Invoice.id),
                func.sum(Invoice.total_amount),
            )
            .where(and_(*full))
            .group_by(Invoice.status)
        )
    ).all()
    status_counts = {r[0]: (r[1], float(r[2] or 0)) for r in status_rows}
    by_status = [
        {
            "status": s,
            "label": STATUS_LABELS.get(s, s),
            "count": status_counts[s][0],
            "amount": round(status_counts[s][1], 2),
        }
        for s in STATUS_ORDER
        if s in status_counts
    ]

    # Top vendors by value.
    vendor_rows = (
        await db.execute(
            select(
                Invoice.supplier_name,
                func.count(Invoice.id),
                func.sum(Invoice.total_amount),
            )
            .where(and_(*full, Invoice.supplier_name.isnot(None)))
            .group_by(Invoice.supplier_name)
            .order_by(func.sum(Invoice.total_amount).desc())
            .limit(10)
        )
    ).all()
    top_vendors = [
        {
            "supplier_name": r[0] or "Unknown",
            "count": r[1],
            "amount": round(float(r[2] or 0), 2),
        }
        for r in vendor_rows
    ]

    # Pending-by-approver. Intentionally uses BASE filters only (date/vendor/
    # supplier/source/amount) — it is the dedicated "what's waiting on whom"
    # view and must not vanish when the user narrows the status filter.
    pmap = await _pending_map(db)
    pending_by_approver: list[dict] = []
    labels = await role_labels(db)
    if pmap:
        pend_rows = (
            await db.execute(
                select(Invoice.id, Invoice.total_amount)
                .where(and_(*base, Invoice.id.in_(list(pmap.keys()))))
            )
        ).all()
        agg: dict[str, list] = {}
        for inv_id, amt in pend_rows:
            role = pmap.get(inv_id)
            if not role:
                continue
            slot = agg.setdefault(role, [0, 0.0])
            slot[0] += 1
            slot[1] += float(amt or 0)
        pending_by_approver = sorted(
            (
                {
                    "role": role,
                    "label": labels.get(role) or humanize_role(role),
                    "count": c,
                    "amount": round(a, 2),
                }
                for role, (c, a) in agg.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "kpis": {
            "total_invoices": total_invoices,
            "total_value": round(total_value, 2),
            "pending_approval": status_counts.get("pending_approval", (0, 0))[0],
            "exceptions": status_counts.get("exception", (0, 0))[0],
            "posted": status_counts.get("posted", (0, 0))[0],
        },
        "by_status": by_status,
        "top_vendors": top_vendors,
        "pending_by_approver": pending_by_approver,
    }


async def _query_invoices(db: AsyncSession, filters: dict, limit: Optional[int] = None, offset: int = 0, sort: str = "date"):
    """Shared invoice fetch for the table endpoint and the export endpoint."""
    start, end = _date_bounds(filters["date_from"], filters["date_to"], filters["days"])
    conds = _base_conditions(
        start, end, filters["vendor"], filters["supplier_id"],
        filters["source"], filters["amount_min"], filters["amount_max"],
        filters["sap_status"],
    )
    if filters["status"]:
        conds.append(Invoice.status.in_(filters["status"]))
    if filters["pending_with"]:
        ids = await _pending_with_ids(db, filters["pending_with"])
        conds.append(Invoice.id.in_(ids or [-1]))

    total = (await db.execute(select(func.count(Invoice.id)).where(and_(*conds)))).scalar() or 0

    q = select(Invoice).where(and_(*conds))
    if sort == "supplier":
        # Supplier-grouped view: alphabetical by vendor, newest first within each.
        q = q.order_by(func.lower(func.coalesce(Invoice.supplier_name, "")), Invoice.created_at.desc())
    else:
        q = q.order_by(Invoice.created_at.desc())
    if limit is not None:
        q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()

    # Resolve pending-with role + supplier-account name for the rows we return.
    pmap = await _pending_map(db)
    labels = await role_labels(db)
    acct_ids = {inv.supplier_id for inv in rows if inv.supplier_id}
    acct_names: dict[int, str] = {}
    if acct_ids:
        acct_rows = (
            await db.execute(
                select(SupplierUser.id, SupplierUser.company_name).where(SupplierUser.id.in_(acct_ids))
            )
        ).all()
        acct_names = {r[0]: r[1] for r in acct_rows}

    items = []
    for inv in rows:
        role = pmap.get(inv.id)
        items.append(
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "supplier_name": inv.supplier_name,
                "supplier_account": acct_names.get(inv.supplier_id) if inv.supplier_id else None,
                "status": inv.status,
                "status_label": STATUS_LABELS.get(inv.status, inv.status),
                "total_amount": round(float(inv.total_amount or 0), 2),
                "currency": inv.currency or "PKR",
                "source_type": inv.source_type or "upload",
                "source_label": SOURCE_LABELS.get(inv.source_type or "upload", (inv.source_type or "upload").replace("_", " ").title()),
                "pending_with": (labels.get(role) or humanize_role(role)) if role else None,
                "sap_document_number": inv.sap_document_number or None,
                "sap_fiscal_year": inv.sap_fiscal_year or None,
                "sap_doc_status": inv.sap_doc_status or None,
                "sap_status_label": (inv.sap_doc_status or "").capitalize() or None,
                "original_filename": inv.original_filename,
                "invoice_date": inv.invoice_date,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
        )
    return items, total


@router.get("/invoices")
async def get_report_invoices(
    filters: dict = Depends(_filter_params),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort: str = Query("date", pattern="^(date|supplier)$"),
    db: AsyncSession = Depends(get_db),
):
    """The filtered invoice list backing the report table (paginated)."""
    offset = (page - 1) * page_size
    items, total = await _query_invoices(db, filters, limit=page_size, offset=offset, sort=sort)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 1,
    }


def _group_by_supplier(items: list) -> list:
    """[(supplier, rows)] preserving order — items must already be supplier-sorted."""
    groups: list = []
    for it in items:
        key = it["supplier_name"] or "Unknown supplier"
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(it)
    return groups


@router.get("/export")
async def export_report(
    filters: dict = Depends(_filter_params),
    fmt: str = Query("csv", pattern="^(csv|xlsx)$"),
    sort: str = Query("date", pattern="^(date|supplier)$"),
    db: AsyncSession = Depends(get_db),
):
    """Download the filtered invoices as CSV or Excel (capped at 10k rows).

    With sort=supplier the file is grouped: a supplier header line (count +
    subtotal) precedes each supplier's invoices — the client-facing tracking
    report format.
    """
    items, _ = await _query_invoices(db, filters, limit=10000, offset=0, sort=sort)

    columns = [
        ("id", "#"),
        ("invoice_number", "Invoice Reference"),
        ("supplier_name", "Vendor"),
        ("supplier_account", "Supplier Account"),
        ("status_label", "Status"),
        ("pending_with", "Pending With"),
        ("sap_document_number", "SAP Doc #"),
        ("sap_status_label", "SAP Status"),
        ("total_amount", "Amount"),
        ("currency", "Currency"),
        ("source_label", "Source"),
        ("invoice_date", "Invoice Date"),
        ("created_at", "Received"),
        ("original_filename", "Scanned File"),
    ]
    grouped = _group_by_supplier(items) if sort == "supplier" else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")

    def group_title(name: str, rows: list) -> str:
        subtotal = sum(float(r["total_amount"] or 0) for r in rows)
        return f"{name} — {len(rows)} invoice(s) · PKR {subtotal:,.0f}"

    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Invoices"
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F2937")
        group_font = Font(bold=True)
        group_fill = PatternFill("solid", fgColor="ECEEF2")
        for col_idx, (_, header) in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill

        def write_row(r_idx: int, item: dict) -> None:
            for c_idx, (key, _) in enumerate(columns, start=1):
                ws.cell(row=r_idx, column=c_idx, value=_sheet_safe(item.get(key)))

        r = 2
        if grouped is not None:
            for name, rows in grouped:
                cell = ws.cell(row=r, column=1, value=group_title(name, rows))
                for c_idx in range(1, len(columns) + 1):
                    ws.cell(row=r, column=c_idx).fill = group_fill
                cell.font = group_font
                r += 1
                for item in rows:
                    write_row(r, item)
                    r += 1
        else:
            for item in items:
                write_row(r, item)
                r += 1

        widths = [6, 22, 30, 24, 16, 18, 14, 11, 14, 9, 14, 14, 22, 30]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="invoice-report-{stamp}.xlsx"'},
        )

    # CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for _, header in columns])
    if grouped is not None:
        for name, rows in grouped:
            writer.writerow([_sheet_safe(group_title(name, rows))])
            for item in rows:
                writer.writerow([_sheet_safe(item.get(key, "")) for key, _ in columns])
    else:
        for item in items:
            writer.writerow([_sheet_safe(item.get(key, "")) for key, _ in columns])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="invoice-report-{stamp}.csv"'},
    )
