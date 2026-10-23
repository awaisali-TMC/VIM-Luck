/**
 * RBAC v2: role → page access LEVELS.
 *
 * The live matrix comes from the backend (`GET /api/role-permissions`,
 * editable on the admin Roles & Permissions page):
 *    matrix = { role_key: { page_key: "view" | "edit" } }
 * A page missing from a role's map = no access. "view" opens the page
 * read-only (actions hidden); "edit" is full access.
 *
 * - "admin" always has edit access to everything (implicit, not stored).
 * - ADMIN_PAGES are hard-locked to admin and not part of the editable matrix.
 * - "/results" follows "/upload" (same feature).
 * - DEFAULT_MATRIX below is only the fallback while the live matrix loads.
 */

export const MANAGED_PAGES = [
  { key: "/",              label: "Analytics" },
  { key: "/ap-visibility", label: "AP Visibility" },
  { key: "/ap",            label: "Purchaser Dashboard" },
  { key: "/tax",           label: "Tax Manager Dashboard" },
  { key: "/auditor",       label: "Auditor Dashboard" },
  { key: "/approvals",     label: "My Approvals" },
  { key: "/upload",        label: "Upload Invoice" },
  { key: "/invoices",      label: "Invoice Inbox" },
  { key: "/reports",       label: "Reports" },
  { key: "/po/new",        label: "Upload PO" },
  { key: "/po",            label: "Purchase Orders" },
];

const ADMIN_PAGES = ["/suppliers", "/email-inbox", "/users", "/workflows", "/tax-rules", "/permissions"];

// Fallback while the live matrix loads — mirrors the backend seed.
export const DEFAULT_MATRIX = {
  ap_manager:          { "/": "edit", "/ap-visibility": "edit", "/ap": "edit", "/approvals": "edit",
                         "/upload": "edit", "/invoices": "edit", "/po/new": "edit", "/po": "edit" },
  ap_operator:         { "/ap": "edit", "/upload": "edit", "/invoices": "edit", "/reports": "edit", "/po/new": "edit", "/po": "edit" },
  finance_director:    { "/": "edit", "/ap-visibility": "edit", "/approvals": "edit", "/invoices": "edit", "/po": "edit" },
  tax_manager:         { "/tax": "edit", "/approvals": "edit", "/invoices": "view" },
  auditor:             { "/auditor": "edit", "/invoices": "view", "/po": "edit" },
  procurement_manager: { "/approvals": "edit", "/invoices": "view", "/po/new": "edit", "/po": "edit" },
  department_head:     { "/approvals": "edit", "/invoices": "view" },
};

function pageKey(path) {
  return path === "/results" ? "/upload" : path;
}

function rolePages(role, matrix) {
  const stored = (matrix && matrix[role]) ?? DEFAULT_MATRIX[role] ?? {};
  // Floor: every role can at least open the Invoice Inbox read-only — mentions,
  // notifications and comments must work for everyone. An explicit row (set by
  // the page toggle) upgrades it to full access.
  return stored["/invoices"] ? stored : { ...stored, "/invoices": "view" };
}

/** Access level for a role on a page: "edit" | "view" | null (no access). */
export function pageLevel(role, path, matrix = null) {
  if (!role) return null;
  if (role === "admin") return "edit";
  if (ADMIN_PAGES.includes(path)) return null;
  return rolePages(role, matrix)[pageKey(path)] ?? null;
}

export function canAccessPath(role, path, matrix = null) {
  return pageLevel(role, path, matrix) !== null;
}

/** True when the role may take actions on the page (not just view it). */
export function canEditPage(role, path, matrix = null) {
  return pageLevel(role, path, matrix) === "edit";
}

/** Landing page per role — first choice if allowed, else the first allowed page. */
export function homeRoute(role, matrix = null) {
  if (role === "admin") return "/";
  const preferred = {
    ap_operator: "/ap",
    tax_manager: "/tax",
    auditor: "/auditor",
    procurement_manager: "/po",
    department_head: "/approvals",
    ap_manager: "/",
    finance_director: "/",
  }[role] || "/invoices";
  if (canAccessPath(role, preferred, matrix)) return preferred;
  return Object.keys(rolePages(role, matrix))[0] || "/invoices";
}
