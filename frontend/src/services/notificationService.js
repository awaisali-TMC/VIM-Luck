import api from "./api";

export async function getNotifications(limit = 30) {
  const res = await api.get("/api/notifications", { params: { limit } });
  return res.data; // { notifications: [...], unread: n }
}

export async function markNotificationRead(id) {
  const res = await api.post(`/api/notifications/${id}/read`);
  return res.data;
}

export async function markAllNotificationsRead() {
  const res = await api.post("/api/notifications/read-all");
  return res.data;
}
