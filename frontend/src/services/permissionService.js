import api from "./api";

export async function getRolePermissions() {
  const res = await api.get("/api/role-permissions");
  return res.data; // { roles: [{key,label,description,is_system}], pages: [{key,label}], matrix: {role:{page:level}} }
}

export async function saveRolePermissions(matrix) {
  const res = await api.put("/api/role-permissions", { matrix });
  return res.data;
}

export async function listRoles() {
  const res = await api.get("/api/roles");
  return res.data; // { roles: [...] }
}

export async function createRole(label, description = null) {
  const res = await api.post("/api/roles", { label, description });
  return res.data;
}

export async function updateRole(key, patch) {
  const res = await api.patch(`/api/roles/${encodeURIComponent(key)}`, patch);
  return res.data;
}

export async function deleteRole(key) {
  const res = await api.delete(`/api/roles/${encodeURIComponent(key)}`);
  return res.data;
}
