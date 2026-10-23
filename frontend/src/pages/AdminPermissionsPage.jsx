import { useState, useEffect } from "react";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Spinner from "../components/common/Spinner";
import {
  getRolePermissions, saveRolePermissions,
  createRole, updateRole, deleteRole,
} from "../services/permissionService";
import { loadRoleLabels } from "../config/roleLabels";

/** Simple on/off switch. */
function Toggle({ on, onChange, disabled = false }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!on)}
      className={`relative w-9 h-5 rounded-full transition-colors border-none cursor-pointer ${
        on ? "bg-brand-600" : "bg-neutral-200"
      } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
      aria-pressed={on}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${
          on ? "left-[18px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

/**
 * RBAC admin console — master-detail:
 *  left  = role list (add / rename / delete; system roles protected)
 *  right = selected role's pages, one toggle each (+ a master toggle for all)
 * A page toggled ON = full access; OFF = hidden. Exception: the Invoice Inbox
 * is always at least read-only for every role (mentions/comments), the toggle
 * grants full actions. Admin itself always has full access.
 */
export default function AdminPermissionsPage() {
  const [roles, setRoles] = useState([]);
  const [pages, setPages] = useState([]);
  const [matrix, setMatrix] = useState({});      // { role: { page: level } }
  const [selected, setSelected] = useState(null); // role key
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState(null);

  // Add/rename role UI state
  const [newRoleName, setNewRoleName] = useState("");
  const [addingRole, setAddingRole] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [savingName, setSavingName] = useState(false);

  const load = () =>
    getRolePermissions().then((data) => {
      const editable = (data.roles || []).filter((r) => r.key !== "admin");
      setRoles(editable);
      setPages(data.pages || []);
      setMatrix(data.matrix || {});
      setSelected((prev) => (prev && editable.some((r) => r.key === prev) ? prev : editable[0]?.key || null));
    });

  useEffect(() => {
    load()
      .catch(() => setMessage({ type: "error", text: "Failed to load roles & permissions." }))
      .finally(() => setLoading(false));
  }, []);

  const role = roles.find((r) => r.key === selected);
  const rolePerms = matrix[selected] || {};
  // Toggle ON means "full access". A legacy "view" row (read-only) shows as
  // OFF — the Invoice Inbox row explains the always-visible read-only floor.
  const isOn = (pageKey) => rolePerms[pageKey] === "edit";
  const allOn = pages.length > 0 && pages.every((p) => isOn(p.key));

  const setPage = (pageKey, on) => {
    setMatrix((prev) => {
      const cur = { ...(prev[selected] || {}) };
      if (on) cur[pageKey] = "edit";
      else delete cur[pageKey];
      return { ...prev, [selected]: cur };
    });
    setDirty(true);
    setMessage(null);
  };

  const setAll = (on) => {
    setMatrix((prev) => ({
      ...prev,
      [selected]: on ? Object.fromEntries(pages.map((p) => [p.key, "edit"])) : {},
    }));
    setDirty(true);
    setMessage(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await saveRolePermissions(matrix);
      setMatrix(res.matrix || matrix);
      setDirty(false);
      setMessage({ type: "success", text: "Permissions saved. Users pick up changes on their next page load." });
    } catch (err) {
      setMessage({ type: "error", text: err.response?.data?.detail || "Failed to save permissions." });
    } finally {
      setSaving(false);
    }
  };

  const handleAddRole = async () => {
    if (!newRoleName.trim()) return;
    setAddingRole(true);
    setMessage(null);
    try {
      const created = await createRole(newRoleName.trim());
      setNewRoleName("");
      await load();
      setSelected(created.key);
      setMessage({ type: "success", text: `Role "${created.label}" created — now toggle its pages below.` });
    } catch (err) {
      setMessage({ type: "error", text: err.response?.data?.detail || "Failed to create role." });
    } finally {
      setAddingRole(false);
    }
  };

  const handleRename = async () => {
    if (!renameValue.trim() || !role || savingName) return;
    // A rename reloads the matrix from the server, which would silently throw
    // away page toggles the admin has not saved yet — and leave Save Changes
    // enabled, ready to write the reverted matrix back.
    if (dirty) {
      setMessage({ type: "error", text: "Save or discard your page changes first — renaming reloads them." });
      return;
    }
    setMessage(null);
    setSavingName(true);
    const previous = role.label;
    try {
      const updated = await updateRole(role.key, { label: renameValue.trim() });
      setRenaming(false);
      await load();
      loadRoleLabels({ force: true }); // sidebar, comments, approvals pick up the new name
      setMessage({ type: "success", text: `Renamed "${previous}" to "${updated.label}".` });
    } catch (err) {
      setMessage({ type: "error", text: err.response?.data?.detail || "Failed to rename role." });
    } finally {
      setSavingName(false);
    }
  };

  const handleDelete = async () => {
    if (!role || role.is_system) return;
    if (!window.confirm(`Delete role "${role.label}"? Users must not hold it.`)) return;
    try {
      await deleteRole(role.key);
      await load();
      setMessage({ type: "success", text: `Role "${role.label}" deleted.` });
    } catch (err) {
      setMessage({ type: "error", text: err.response?.data?.detail || "Failed to delete role." });
    }
  };

  if (loading) {
    return (
      <Card>
        <Spinner text="Loading roles & permissions..." />
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {message && (
        <div className={`rounded-base px-4 py-2.5 border text-2xs font-medium ${
          message.type === "success"
            ? "bg-success-bg border-success-base text-success-dark"
            : "bg-danger-bg border-danger-base text-danger-dark"
        }`}>
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-[280px_1fr] gap-4 items-start">
        {/* ── Left: role list ── */}
        <Card title="Roles" subtitle="Admin always has full access" noPad>
          <div className="flex flex-col">
            {roles.map((r) => (
              <button
                key={r.key}
                onClick={() => { setSelected(r.key); setRenaming(false); }}
                className={`text-left px-4 py-2.5 border-b border-neutral-50 cursor-pointer transition-colors ${
                  r.key === selected ? "bg-brand-50 border-l-[3px] border-l-brand-500" : "hover:bg-neutral-25 border-l-[3px] border-l-transparent"
                }`}
              >
                <div className="text-xs font-semibold text-neutral-800">{r.label}</div>
                <div className="text-2xs text-neutral-400">
                  {r.is_system ? "System role" : "Custom role"} · {Object.keys(matrix[r.key] || {}).length} page(s)
                </div>
              </button>
            ))}

            {/* Add role */}
            <div className="p-3 border-t border-neutral-100">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newRoleName}
                  onChange={(e) => setNewRoleName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddRole()}
                  placeholder="New role name…"
                  className="flex-1 min-w-0 border border-neutral-200 rounded-base px-2.5 py-1.5 text-xs outline-none focus:border-brand-400"
                />
                <Button size="xs" onClick={handleAddRole} disabled={addingRole || !newRoleName.trim()}>
                  {addingRole ? "…" : "Add"}
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* ── Right: selected role's page toggles ── */}
        {role ? (
          <Card
            // Card only renders its header (and so the rename input in `action`)
            // when it has a title, so keep one while renaming.
            title={renaming ? "Rename role" : `${role.label}`}
            subtitle={renaming ? `Currently "${role.label}"` : "Toggle which pages this role can open"}
            action={
              <div className="flex items-center gap-2">
                {renaming ? (
                  <>
                    <input
                      type="text"
                      value={renameValue}
                      autoFocus
                      maxLength={100}     /* roles.label is VARCHAR(100) */
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleRename()}
                      className="border border-neutral-200 rounded-base px-2.5 py-1.5 text-xs outline-none focus:border-brand-400"
                    />
                    <Button size="xs" onClick={handleRename} disabled={savingName || !renameValue.trim()}>
                      {savingName ? "Saving…" : "Save name"}
                    </Button>
                    <Button size="xs" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
                  </>
                ) : (
                  <>
                    <Button size="xs" variant="ghost" onClick={() => { setRenaming(true); setRenameValue(role.label); }}>
                      Rename
                    </Button>
                    {!role.is_system && (
                      <Button size="xs" variant="ghost" onClick={handleDelete}>Delete</Button>
                    )}
                    <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
                      {saving ? "Saving..." : "Save Changes"}
                    </Button>
                  </>
                )}
              </div>
            }
            noPad
          >
            <div>
              {/* Master toggle — all pages on/off */}
              <div className="flex items-center justify-between px-4 py-3 bg-neutral-25 border-b border-neutral-100">
                <div>
                  <span className="text-xs font-semibold text-neutral-800">All Pages</span>
                  <span className="text-2xs text-neutral-400 ml-2">turn everything on or off</span>
                </div>
                <Toggle on={allOn} onChange={setAll} />
              </div>

              {pages.map((page, i) => {
                const on = isOn(page.key);
                const isInvoices = page.key === "/invoices";
                return (
                  <div
                    key={page.key}
                    className={`flex items-center justify-between px-4 py-2.5 border-b border-neutral-50 ${
                      i % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"
                    }`}
                  >
                    <div>
                      <span className="text-xs font-medium text-neutral-800">{page.label}</span>
                      {isInvoices && !on && (
                        <span className="text-2xs text-info-dark ml-2">always visible read-only — toggle on to allow actions</span>
                      )}
                    </div>
                    <Toggle on={on} onChange={(v) => setPage(page.key, v)} />
                  </div>
                );
              })}
            </div>
          </Card>
        ) : (
          <Card>
            <div className="text-center py-8 text-2xs text-neutral-400">Select or create a role.</div>
          </Card>
        )}
      </div>

      <div className="text-2xs text-neutral-400 px-1">
        Notes: the Invoice Inbox is always at least read-only for every role (so mentions, notifications and
        comments work); toggling it on grants full invoice actions. Admin pages (User Management, Workflows,
        etc.) are always admin-only. New pages appear here as they ship.
      </div>
    </div>
  );
}
