import api from "./api";

// ── Supplier Auth ────────────────────────────────────────────────────────────

/**
 * Request an OTP for signup or login.
 * Returns { message, expires_in_minutes } — the code itself is delivered
 * out-of-band (SMS); it is never surfaced in the UI.
 */
export async function requestOtp(mobile, purpose = "signup") {
  const res = await api.post("/api/auth/supplier/request-otp", { mobile, purpose });
  return res.data;
}

/**
 * Server-side OTP check used to gate multi-step flows (does not consume the OTP).
 */
export async function verifyOtp(mobile, otp_code) {
  const res = await api.post("/api/auth/supplier/verify-otp", { mobile, otp_code });
  return res.data;
}

/**
 * Complete supplier self-signup after OTP verification.
 * Returns { message, supplier_id, status }
 */
export async function supplierSignup({ mobile, otp_code, name, company_name, email, password }) {
  const res = await api.post("/api/auth/supplier/signup", {
    mobile, otp_code, name, company_name, email, password,
  });
  return res.data;
}

/**
 * Login a supplier with mobile OTP.
 * Returns { token, supplier: { id, name, company_name, mobile, email, status } }
 */
export async function supplierLogin(mobile, otp_code) {
  const res = await api.post("/api/auth/supplier/login", { mobile, otp_code });
  return res.data;
}

/**
 * Validate a stored token and return current supplier user.
 */
export async function getSupplierMe(token) {
  const res = await api.get("/api/auth/supplier/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data;
}

/**
 * Logout — invalidates the session token on the server.
 */
export async function supplierLogout(token) {
  await api.post("/api/auth/supplier/logout", null, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

// ── Admin ────────────────────────────────────────────────────────────────────

/**
 * List all supplier accounts (admin).
 * Optional status filter: "pending" | "verified" | "rejected"
 */
export async function listSuppliers(status = null, skip = 0, limit = 50) {
  const params = { skip, limit };
  if (status) params.status = status;
  const res = await api.get("/api/admin/suppliers", { params });
  return res.data;
}

/**
 * Admin creates a supplier account (auto-verified). sap_vendor_number links
 * the account to the SAP vendor picked in the "Add from SAP" flow.
 */
export async function adminCreateSupplier({ name, company_name, mobile, email, password, sap_vendor_number, ntn }) {
  const res = await api.post("/api/admin/suppliers", {
    name, company_name, mobile, email, password, sap_vendor_number, ntn,
  });
  return res.data;
}

/**
 * Live SAP vendor-master search (admin) — powers the onboarding picker.
 * Digit query = vendor number; text query = company name.
 */
export async function searchSAPVendors(search, maxRows = 20) {
  const res = await api.get("/api/sap/vendors", { params: { search, max_rows: maxRows } });
  return res.data;
}

/**
 * Update supplier account details (admin) — e.g. attach a SAP vendor number
 * to an account created before SAP onboarding existed.
 */
export async function updateSupplierDetails(supplierId, patch) {
  const res = await api.patch(`/api/admin/suppliers/${supplierId}`, patch);
  return res.data;
}

/**
 * Fixed supplier demo OTP (admin). Stored in the app database, not .env.
 * Returns { otp, enabled, updated_by, updated_at }.
 */
export async function getSupplierDemoOtp() {
  const res = await api.get("/api/admin/settings/supplier-demo-otp");
  return res.data;
}

/** Set the demo OTP (4–10 digits), or pass null / "" to disable it. */
export async function setSupplierDemoOtp(otp) {
  const res = await api.put("/api/admin/settings/supplier-demo-otp", { otp: otp || null });
  return res.data;
}

/**
 * Approve or reject a supplier.
 * status: "verified" | "rejected"
 */
export async function updateSupplierStatus(supplierId, status, rejectionReason = null) {
  const res = await api.patch(`/api/admin/suppliers/${supplierId}/status`, {
    status,
    rejection_reason: rejectionReason,
  });
  return res.data;
}

/**
 * Delete a supplier account (admin).
 */
export async function deleteSupplier(supplierId) {
  await api.delete(`/api/admin/suppliers/${supplierId}`);
}
