// Display names for role keys. The names live in the roles table and are
// edited on Roles & Permissions, so every screen that shows a role goes
// through roleLabel() — a rename there then shows everywhere. The built-ins
// below cover the moment before the list loads (and a failed load).
import { useEffect, useState } from "react";
import { listRoles } from "../services/permissionService";

export const DEFAULT_ROLE_LABELS = {
  admin: "Admin",
  ap_manager: "AP Manager",
  ap_operator: "Purchaser",
  tax_manager: "Tax Manager",
  procurement_manager: "Procurement Manager",
  auditor: "Auditor",
  finance_director: "Finance Director",
  department_head: "Department Head",
};

let labels = null;
let pending = null;
let generation = 0;      // guards against an older response overwriting a newer one
let warned = false;
const listeners = new Set();

export function humanizeRole(key) {
  return (key || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function roleLabel(key) {
  if (!key) return "";
  return labels?.[key] || DEFAULT_ROLE_LABELS[key] || humanizeRole(key);
}

// Fetch once per page load; pass { force: true } after a role is renamed.
export function loadRoleLabels({ force = false } = {}) {
  if (pending && !force) return pending;
  const mine = ++generation;
  pending = listRoles()
    .then((data) => {
      const fresh = Object.fromEntries((data.roles || []).map((r) => [r.key, r.label]));
      // Ignore a response overtaken by a later load (e.g. a forced reload after
      // a rename), and never let an empty list erase the names we already have.
      if (mine !== generation || !Object.keys(fresh).length) return labels;
      labels = fresh;
      listeners.forEach((fn) => fn());
      return labels;
    })
    .catch((err) => {
      pending = null; // try again on the next mount
      if (!warned) {
        warned = true;
        console.warn("Role names could not be loaded; falling back to the built-in names.", err);
      }
      return labels;
    });
  return pending;
}

// Returns roleLabel and re-renders the caller once the names have loaded.
export function useRoleLabel() {
  const [, rerender] = useState(0);
  useEffect(() => {
    const fn = () => rerender((n) => n + 1);
    listeners.add(fn);
    loadRoleLabels();
    return () => listeners.delete(fn);
  }, []);
  return roleLabel;
}
