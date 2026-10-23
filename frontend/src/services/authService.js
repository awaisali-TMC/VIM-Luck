import api from "./api";

// ── Internal Auth ────────────────────────────────────────────────────────────

export async function internalLogin(email, password) {
  const response = await api.post("/api/auth/internal/login", { email, password });
  return response.data;
}

export async function internalMe(token) {
  // Token travels in the Authorization header (set explicitly here because the
  // axios interceptor may not see localStorage yet during session restore).
  const response = await api.get("/api/auth/internal/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

export async function internalLogout(token) {
  const response = await api.post("/api/auth/internal/logout", null, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return response.data;
}

// ── Admin User Management ────────────────────────────────────────────────────

export async function listUsers({ skip = 0, limit = 50, role, is_active } = {}) {
  const params = { skip, limit };
  if (role) params.role = role;
  if (is_active !== undefined) params.is_active = is_active;
  const response = await api.get("/api/admin/users", { params });
  return response.data;
}

export async function createUser(data) {
  const response = await api.post("/api/admin/users", data);
  return response.data;
}

export async function getUser(id) {
  const response = await api.get(`/api/admin/users/${id}`);
  return response.data;
}

export async function updateUser(id, data) {
  const response = await api.patch(`/api/admin/users/${id}`, data);
  return response.data;
}

export async function resetUserPassword(id, newPassword) {
  const response = await api.post(`/api/admin/users/${id}/reset-password`, {
    new_password: newPassword,
  });
  return response.data;
}
