import api from "./api";

/**
 * Verify a single NTN or CNIC against the FBR Active Taxpayer List.
 *
 * @param {string} ntn          - NTN (7-digit) or CNIC (13-digit)
 * @param {boolean} checkLive   - Fall back to live FBR IRIS 2.0 API
 * @param {string|null} protocolId - "1004" Income Tax (default), "1005" Sales Tax, "3001" AJK
 */
export async function verifyNTN(ntn, checkLive = false, protocolId = null) {
  const payload = { ntn, check_live: checkLive };
  if (protocolId) payload.protocol_id = protocolId;
  const res = await api.post("/api/fbr/verify-ntn", payload);
  return res.data;
}

/**
 * Verify multiple NTNs/CNICs in one call.
 *
 * @param {string[]} identifiers - Mix of NTNs and CNICs (max 100)
 * @param {boolean} checkLive
 * @param {string|null} protocolId
 */
export async function verifyBatch(identifiers, checkLive = false, protocolId = null) {
  const payload = { identifiers, check_live: checkLive };
  if (protocolId) payload.protocol_id = protocolId;
  const res = await api.post("/api/fbr/verify-batch", payload);
  return res.data;
}

/** Verify an invoice's supplier NTN and check WHT compliance. */
export async function verifyInvoiceFBR(invoiceId) {
  const res = await api.post(`/api/fbr/invoices/${invoiceId}/verify-fbr`);
  return res.data;
}

/** Get ATL database statistics (record count, file size, last modified). */
export async function getATLStats() {
  const res = await api.get("/api/fbr/atl-stats");
  return res.data;
}

/** Get the current IRIS JWT token cache status. */
export async function getTokenStatus() {
  const res = await api.get("/api/fbr/token-status");
  return res.data;
}

/** Force re-extraction of the Bearer JWT from the IRIS Angular bundle. */
export async function refreshToken() {
  const res = await api.post("/api/fbr/refresh-token");
  return res.data;
}
