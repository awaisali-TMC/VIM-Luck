import { useState, useEffect, useCallback } from "react";
import { listUsers, createUser, updateUser, resetUserPassword } from "../services/authService";
import { listRoles } from "../services/permissionService";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Badge from "../components/common/Badge";
import KpiCard from "../components/common/KpiCard";
import Modal from "../components/common/Modal";

// Fallback until the dynamic role list loads (RBAC v2 — roles live in the DB
// and are managed on the Roles & Permissions page).
const FALLBACK_ROLES = [
  { value: "admin", label: "Admin" },
  { value: "ap_manager", label: "AP Manager" },
  { value: "ap_operator", label: "Purchaser" },
  { value: "tax_manager", label: "Tax Manager" },
  { value: "procurement_manager", label: "Procurement Manager" },
  { value: "auditor", label: "Auditor" },
  { value: "finance_director", label: "Finance Director" },
  { value: "department_head", label: "Department Head" },
];

const DEPARTMENTS = [
  "Finance", "Procurement", "IT", "Operations", "HR", "Legal", "Audit", "Treasury",
];

export default function AdminUsersPage() {
  // Dynamic role catalog (falls back to the built-ins while loading)
  const [roleOptions, setRoleOptions] = useState(FALLBACK_ROLES);
  useEffect(() => {
    listRoles()
      .then((data) => {
        const roles = (data.roles || []).map((r) => ({ value: r.key, label: r.label }));
        if (roles.length) setRoleOptions(roles);
      })
      .catch(() => { /* keep fallback */ });
  }, []);
  const ROLES = roleOptions;
  const ROLE_LABEL = Object.fromEntries(ROLES.map((r) => [r.value, r.label]));
  const [users, setUsers] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterRole, setFilterRole] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [formData, setFormData] = useState({
    email: "", display_name: "", password: "", role: "ap_operator", department: "", is_active: 1,
  });
  const [resetPw, setResetPw] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterRole) params.role = filterRole;
      const data = await listUsers(params);
      setUsers(data.users || []);
      setCounts(data.counts || {});
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [filterRole]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleCreate = () => {
    setEditingUser(null);
    setFormData({ email: "", display_name: "", password: "", role: "ap_operator", department: "", is_active: 1 });
    setShowModal(true);
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setFormData({
      email: user.email, display_name: user.display_name, password: "",
      role: user.role, department: user.department || "", is_active: user.is_active,
    });
    setShowModal(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editingUser) {
        const payload = {
          display_name: formData.display_name,
          role: formData.role,
          department: formData.department || null,
          is_active: formData.is_active,
        };
        await updateUser(editingUser.id, payload);
      } else {
        await createUser({
          email: formData.email,
          display_name: formData.display_name,
          password: formData.password,
          role: formData.role,
          department: formData.department || null,
        });
      }
      setShowModal(false);
      fetchUsers();
    } catch (err) {
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleResetPassword = async () => {
    if (!resetPw.trim()) return;
    setSaving(true);
    try {
      await resetUserPassword(resetTarget.id, resetPw);
      setShowResetModal(false);
      setResetPw("");
    } catch (err) {
      setError(err.response?.data?.detail || "Reset failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="Total Users" value={counts.total || users.length} icon="👥" />
        <KpiCard label="Active" value={counts.active || 0} icon="✅" />
        <KpiCard label="Inactive" value={counts.inactive || 0} icon="🚫" />
        <KpiCard label="Roles" value={ROLES.length} icon="🔑" />
      </div>

      {/* Actions */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-semibold text-neutral-900 m-0">Internal Users</h3>
            <select
              value={filterRole}
              onChange={(e) => setFilterRole(e.target.value)}
              className="text-xs border border-neutral-200 rounded-base px-2 py-1 bg-white"
            >
              <option value="">All Roles</option>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={handleCreate}>+ New User</Button>
        </div>

        {error && (
          <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-3 text-2xs text-danger-dark">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-8 text-xs text-neutral-500">Loading...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-neutral-100">
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Name</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Email</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Role</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Department</th>
                  <th className="text-left py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Status</th>
                  <th className="text-right py-2 px-3 font-semibold text-neutral-500 uppercase text-2xs">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-neutral-50 hover:bg-neutral-25 transition-colors">
                    <td className="py-2.5 px-3 font-medium text-neutral-900">{u.display_name}</td>
                    <td className="py-2.5 px-3 text-neutral-600">{u.email}</td>
                    <td className="py-2.5 px-3">
                      <Badge status={u.role === "admin" ? "active" : "info"} label={ROLE_LABEL[u.role] || u.role} size="xs" />
                    </td>
                    <td className="py-2.5 px-3 text-neutral-600">{u.department || "—"}</td>
                    <td className="py-2.5 px-3">
                      <Badge status={u.is_active ? "active" : "blocked"} label={u.is_active ? "Active" : "Inactive"} size="xs" />
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button variant="ghost" size="xs" onClick={() => handleEdit(u)}>Edit</Button>
                        <Button variant="ghost" size="xs" onClick={() => { setResetTarget(u); setResetPw(""); setShowResetModal(true); }}>
                          Reset PW
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr><td colSpan={6} className="py-8 text-center text-neutral-400">No users found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Create/Edit Modal */}
      {showModal && (
        <Modal
          open={showModal}
          title={editingUser ? "Edit User" : "Create User"}
          onClose={() => setShowModal(false)}
        >
          <div className="flex flex-col gap-3">
            {!editingUser && (
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Email</label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none"
                  placeholder="user@ogdcl.com"
                />
              </div>
            )}
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">Display Name</label>
              <input
                type="text"
                value={formData.display_name}
                onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none"
                placeholder="Full Name"
              />
            </div>
            {!editingUser && (
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Password</label>
                <input
                  type="password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none"
                  placeholder="Min 6 characters"
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Role</label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 bg-white"
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Department</label>
                <select
                  value={formData.department}
                  onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 bg-white"
                >
                  <option value="">— None —</option>
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
            </div>
            {editingUser && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_active === 1}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked ? 1 : 0 })}
                  id="user-active"
                />
                <label htmlFor="user-active" className="text-xs text-neutral-700">Active</label>
              </div>
            )}
            <div className="flex justify-end gap-2 mt-2">
              <Button variant="secondary" size="sm" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : editingUser ? "Save Changes" : "Create User"}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reset Password Modal */}
      {showResetModal && (
        <Modal open={showResetModal} title={`Reset Password — ${resetTarget?.display_name}`} onClose={() => setShowResetModal(false)}>
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">New Password</label>
              <input
                type="password"
                value={resetPw}
                onChange={(e) => setResetPw(e.target.value)}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 focus:border-brand-400 outline-none"
                placeholder="Min 6 characters"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setShowResetModal(false)}>Cancel</Button>
              <Button size="sm" onClick={handleResetPassword} disabled={saving || !resetPw.trim()}>
                {saving ? "Resetting..." : "Reset Password"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
