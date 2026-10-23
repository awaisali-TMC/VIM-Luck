import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: 60000, // 60s default; long AI extraction calls (upload) override this per-request
});

// The internal portal (index.html) and supplier portal (supplier.html) share
// an origin — and therefore localStorage. Each app must use ONLY its own
// session token: falling back to the other portal's token silently switches
// the caller's identity (e.g. the supplier portal acting as an internal user,
// which is how "all suppliers' invoices" leaked into a supplier's view).
// Exact-path match: the supplier app lives ONLY at /supplier(.html). A plain
// includes("supplier") also matched the INTERNAL /suppliers admin route and
// made it send the supplier token to admin endpoints.
const IS_SUPPLIER_APP = /^\/supplier(\.html)?($|\/)/.test(window.location.pathname);

export function getAuthToken() {
  return IS_SUPPLIER_APP
    ? localStorage.getItem("supplier_token")
    : localStorage.getItem("auth_token");
}

// Attach the session token to every request as a Bearer header so the backend
// can authenticate the caller. (Previously most calls sent no credentials.)
api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, clear THIS app's stale token and tell the app to drop to the login
// screen. This happens when the session was invalidated — most commonly because
// the same account signed in elsewhere (login rotates the single session token,
// so the older session's token stops matching). Skip the login call itself
// (a bad password also returns 401).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url = error?.config?.url || "";
    if (status === 401 && !url.includes("/login")) {
      localStorage.removeItem(IS_SUPPLIER_APP ? "supplier_token" : "auth_token");
      window.dispatchEvent(new CustomEvent("auth:session-expired"));
    }
    return Promise.reject(error);
  }
);

export default api;
