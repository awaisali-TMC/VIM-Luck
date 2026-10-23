import { useState, useEffect, useCallback } from "react";
import {
  listSuppliers,
  adminCreateSupplier,
  updateSupplierStatus,
  searchSAPVendors,
  updateSupplierDetails,
} from "../services/supplierService";
import KpiCard from "../components/common/KpiCard";
import Badge from "../components/common/Badge";
import Modal from "../components/common/Modal";
import Button from "../components/common/Button";
import { tokens } from "../styles/tokens";

/* ── Status badge mapping for suppliers ─────────────────────────────────── */
const STATUS_MAP = {
  pending:  { label: "Pending Review", color: "#F59E0B", bg: "#FFFBEB", border: "#FDE68A" },
  verified: { label: "Verified",       color: "#10B981", bg: "#ECFDF5", border: "#A7F3D0" },
  rejected: { label: "Rejected",       color: "#EF4444", bg: "#FEF2F2", border: "#FECACA" },
};

function SupplierStatusChip({ status }) {
  const cfg = STATUS_MAP[status] || { label: status, color: "#6B7590", bg: "#F5F6F8", border: "#D5D9E2" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      backgroundColor: cfg.bg, border: `1px solid ${cfg.border}`,
      borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, color: cfg.color,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: cfg.color, flexShrink: 0 }} />
      {cfg.label}
    </span>
  );
}

/* ── Shared field styles ─────────────────────────────────────────────────── */
const fieldStyle = {
  width: "100%", height: 40, border: "1.5px solid #D5D9E2", borderRadius: 8,
  padding: "0 12px", fontSize: 13, color: "#2E3340", outline: "none",
  boxSizing: "border-box", backgroundColor: "#F9FAFB",
};
const readOnlyStyle = { ...fieldStyle, backgroundColor: "#ECEEF2", color: "#545D73", cursor: "not-allowed" };
const labelStyle = { fontSize: 11, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 5 };

/* ── SAP vendor search panel (shared by Add-from-SAP and Link-SAP) ────────── */
function VendorSearchPanel({ onSelect, selected }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null); // null = not searched yet
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const runSearch = async () => {
    const q = query.trim();
    if (q.length < 2) { setError("Type at least 2 characters."); return; }
    setError("");
    setSearching(true);
    try {
      const data = await searchSAPVendors(q);
      setResults(data.vendors || []);
    } catch (err) {
      setError(err.response?.data?.detail || "SAP search failed — check SAP connectivity.");
      setResults(null);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          style={fieldStyle}
          type="text"
          placeholder="Search SAP vendors by company name or vendor number…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); runSearch(); } }}
          autoFocus
        />
        <Button variant="primary" size="sm" onClick={runSearch} disabled={searching} className="h-10 flex-none">
          {searching ? "Searching…" : "Search"}
        </Button>
      </div>

      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "8px 12px", marginTop: 10, fontSize: 12, color: "#B91C1C" }}>
          {error}
        </div>
      )}

      {results !== null && !error && (
        results.length === 0 ? (
          <div style={{ marginTop: 10, padding: "14px 12px", textAlign: "center", fontSize: 12, color: "#8B95AB", border: "1px dashed #D5D9E2", borderRadius: 8 }}>
            No SAP vendors matched “{query.trim()}”.
          </div>
        ) : (
          <div style={{ maxHeight: 250, overflowY: "auto", marginTop: 10, border: "1px solid #ECEEF2", borderRadius: 8 }}>
            {results.map((v) => {
              const isSel = selected?.vendor_number === v.vendor_number;
              return (
                <button
                  key={v.vendor_number}
                  type="button"
                  onClick={() => onSelect(v)}
                  style={{
                    display: "flex", alignItems: "baseline", gap: 10, width: "100%", textAlign: "left",
                    padding: "9px 12px", border: "none", borderBottom: "1px solid #F5F6F8", cursor: "pointer",
                    backgroundColor: isSel ? "#EEF2FF" : "#fff",
                  }}
                >
                  <span style={{ fontFamily: "monospace", fontSize: 12, color: isSel ? "#3B45E5" : "#6B7590", flexShrink: 0 }}>
                    {v.vendor_number}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#2E3340", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.name || "(unnamed vendor)"}
                  </span>
                  {v.city && <span style={{ fontSize: 11, color: "#8B95AB", flexShrink: 0 }}>{v.city}</span>}
                  {isSel && <span style={{ fontSize: 12, color: "#3B45E5", flexShrink: 0 }}>✓</span>}
                </button>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}

/* ── Add Supplier Modal — onboard from SAP (search → contact details) ─────── */
function CreateSupplierModal({ open, onClose, onCreated }) {
  const [step, setStep] = useState("search"); // "search" | "form"
  const [vendor, setVendor] = useState(null); // picked SAP vendor
  const [manual, setManual] = useState(false); // manual entry (SAP down / edge cases)
  const [form, setForm] = useState({ name: "", company_name: "", mobile: "", email: "", ntn: "", password: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Fresh state every time the modal opens.
  useEffect(() => {
    if (open) {
      setStep("search"); setVendor(null); setManual(false); setError("");
      setForm({ name: "", company_name: "", mobile: "", email: "", ntn: "", password: "" });
    }
  }, [open]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const continueToForm = () => {
    if (!vendor) return;
    setForm((f) => ({ ...f, company_name: vendor.name, ntn: vendor.ntn || f.ntn }));
    setManual(false);
    setStep("form");
  };

  const enterManually = () => {
    setVendor(null);
    setManual(true);
    setStep("form");
  };

  const handleSubmit = async (e) => {
    e?.preventDefault();
    if (!form.name.trim() || !form.mobile.trim() || (manual && !form.company_name.trim())) {
      setError("Contact name and mobile are required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const created = await adminCreateSupplier({
        ...form,
        sap_vendor_number: vendor?.vendor_number || null,
      });
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create supplier.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={step === "search" ? "Add Supplier — pick the SAP vendor" : "Add Supplier — contact details"}
      width={520}
      footer={
        step === "search" ? (
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="ghost" onClick={enterManually}>Enter manually</Button>
            <Button variant="success" onClick={continueToForm} disabled={!vendor}>Continue →</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={loading}>Cancel</Button>
            <Button variant="success" onClick={handleSubmit} disabled={loading}>
              {loading ? "Creating..." : "Create Account"}
            </Button>
          </>
        )
      }
    >
      {step === "search" ? (
        <>
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "#6B7590" }}>
            The company identity comes from SAP — search the vendor master and select the supplier you are onboarding.
          </p>
          <VendorSearchPanel onSelect={setVendor} selected={vendor} />
        </>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          {error && (
            <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#B91C1C" }}>
              {error}
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Company (from SAP)</label>
              {manual ? (
                <input style={fieldStyle} type="text" placeholder="Business / company name" value={form.company_name} onChange={(e) => set("company_name", e.target.value)} />
              ) : (
                <input style={readOnlyStyle} type="text" value={form.company_name} readOnly />
              )}
            </div>
            <div>
              <label style={labelStyle}>SAP Vendor #</label>
              <input style={readOnlyStyle} type="text" value={vendor?.vendor_number || (manual ? "— not linked —" : "")} readOnly />
            </div>
            <div>
              <label style={labelStyle}>Contact Person *</label>
              <input style={fieldStyle} type="text" placeholder="Who will log in" value={form.name} onChange={(e) => set("name", e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Mobile Number *</label>
              <input style={fieldStyle} type="tel" placeholder="e.g. 03001234567 — their login" value={form.mobile} onChange={(e) => set("mobile", e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>Email <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span></label>
              <input style={fieldStyle} type="email" placeholder="supplier@company.com" value={form.email} onChange={(e) => set("email", e.target.value)} />
            </div>
            <div>
              <label style={labelStyle}>NTN <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span></label>
              <input style={fieldStyle} type="text" placeholder="e.g. 1234567-8" value={form.ntn} onChange={(e) => set("ntn", e.target.value)} />
            </div>
          </div>

          {!manual && (
            <button
              type="button"
              onClick={() => setStep("search")}
              style={{ marginTop: 10, background: "none", border: "none", padding: 0, fontSize: 12, color: "#3B45E5", cursor: "pointer" }}
            >
              ← pick a different SAP vendor
            </button>
          )}

          <div style={{ marginTop: 14, padding: "10px 12px", backgroundColor: "#ECFDF5", border: "1px solid #A7F3D0", borderRadius: 8, fontSize: 12, color: "#065F46" }}>
            ✓ The account is active immediately — the supplier signs in with this mobile number + OTP.
            {manual && <div style={{ marginTop: 4, color: "#B45309" }}>⚠ Not linked to SAP — this account won’t see SAP purchase orders until linked.</div>}
          </div>
        </form>
      )}
    </Modal>
  );
}

/* ── Link an existing account to a SAP vendor ────────────────────────────── */
function LinkSAPModal({ open, supplier, onClose, onLinked }) {
  const [vendor, setVendor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (open) { setVendor(null); setError(""); } }, [open]);

  const handleLink = async () => {
    if (!vendor) return;
    setLoading(true);
    setError("");
    try {
      const updated = await updateSupplierDetails(supplier.id, {
        sap_vendor_number: vendor.vendor_number,
        company_name: vendor.name || undefined,
        ntn: vendor.ntn || undefined,
      });
      onLinked(updated);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to link vendor.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Link SAP Vendor — ${supplier?.company_name || ""}`}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant="success" onClick={handleLink} disabled={!vendor || loading}>
            {loading ? "Linking..." : "Link Vendor"}
          </Button>
        </>
      }
    >
      <p style={{ margin: "0 0 12px", fontSize: 13, color: "#6B7590" }}>
        Pick the SAP vendor this account represents — the company name and NTN are taken from SAP.
      </p>
      {error && (
        <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "8px 12px", marginBottom: 10, fontSize: 12, color: "#B91C1C" }}>
          {error}
        </div>
      )}
      <VendorSearchPanel onSelect={setVendor} selected={vendor} />
    </Modal>
  );
}

/* ── Reject Reason Modal ─────────────────────────────────────────────────── */
function RejectModal({ open, supplier, onClose, onRejected }) {
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleReject = async () => {
    setError("");
    setLoading(true);
    try {
      const updated = await updateSupplierStatus(supplier.id, "rejected", reason.trim() || null);
      onRejected(updated);
      setReason("");
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to reject supplier.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Reject Supplier Account"
      width={420}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant="danger" onClick={handleReject} disabled={loading}>
            {loading ? "Rejecting..." : "Reject Account"}
          </Button>
        </>
      }
    >
      {error && <div style={{ backgroundColor: "#FEF2F2", borderRadius: 8, padding: "8px 12px", marginBottom: 12, fontSize: 13, color: "#B91C1C" }}>{error}</div>}
      <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 14px 0" }}>
        You are rejecting the account for <strong style={{ color: "#1A1D27" }}>{supplier?.name}</strong> ({supplier?.company_name}).
      </p>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>
        Rejection Reason <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span>
      </label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="e.g. Incomplete documentation, Duplicate account, etc."
        style={{ width: "100%", height: 90, border: "1.5px solid #D5D9E2", borderRadius: 8, padding: "10px 12px", fontSize: 13, color: "#2E3340", outline: "none", resize: "vertical", boxSizing: "border-box", fontFamily: "inherit" }}
      />
    </Modal>
  );
}

/* ── Main Page ───────────────────────────────────────────────────────────── */
export default function AdminSuppliersPage() {
  const [suppliers, setSuppliers] = useState([]);
  const [counts, setCounts] = useState({ total: 0, pending: 0, verified: 0, rejected: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // "all" | "pending" | "verified" | "rejected"
  const [search, setSearch] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [linkTarget, setLinkTarget] = useState(null); // supplier being linked to SAP
  const [actionLoading, setActionLoading] = useState(null); // supplier id being actioned

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSuppliers(filter === "all" ? null : filter);
      setSuppliers(data.suppliers || []);
      setCounts(data.counts || { total: 0, pending: 0, verified: 0, rejected: 0 });
    } catch {
      setSuppliers([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { fetchSuppliers(); }, [fetchSuppliers]);

  const handleApprove = async (supplier) => {
    setActionLoading(supplier.id);
    try {
      const updated = await updateSupplierStatus(supplier.id, "verified");
      setSuppliers((prev) => prev.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)));
      setCounts((c) => ({ ...c, pending: Math.max(0, c.pending - 1), verified: c.verified + 1 }));
    } catch {
      // silently fail — user can retry
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejected = (updated) => {
    setSuppliers((prev) => prev.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)));
    setCounts((c) => ({ ...c, pending: Math.max(0, c.pending - 1), rejected: c.rejected + 1 }));
  };

  const handleCreated = (created) => {
    setSuppliers((prev) => [created, ...prev]);
    setCounts((c) => ({ ...c, total: c.total + 1, verified: c.verified + 1 }));
  };

  const handleLinked = (updated) => {
    setSuppliers((prev) => prev.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)));
  };

  const fmtDate = (s) => {
    if (!s) return "—";
    try { return new Date(s).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" }); }
    catch { return s; }
  };

  const filtered = suppliers.filter((s) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      s.name?.toLowerCase().includes(q) ||
      s.company_name?.toLowerCase().includes(q) ||
      s.mobile?.includes(q) ||
      s.email?.toLowerCase().includes(q)
    );
  });

  const FILTERS = [
    { key: "all", label: "All" },
    { key: "pending", label: "Pending" },
    { key: "verified", label: "Verified" },
    { key: "rejected", label: "Rejected" },
  ];

  return (
    <div>
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <KpiCard size="lg" label="Total Suppliers" value={String(counts.total)} sub="Registered accounts" accentColor={tokens.color.brand[500]} icon="🏢" />
        <KpiCard size="lg" label="Pending Review" value={String(counts.pending)} sub="Awaiting approval" accentColor={tokens.color.status.warning.base} icon="⏳" />
        <KpiCard size="lg" label="Verified" value={String(counts.verified)} sub="Active accounts" accentColor={tokens.color.status.success.base} icon="✓" />
        <KpiCard size="lg" label="Rejected" value={String(counts.rejected)} sub="Denied accounts" accentColor={tokens.color.status.danger.base} icon="✗" />
      </div>

      {/* Table card */}
      <div className="bg-neutral-0 border border-neutral-100 rounded-lg shadow-xs">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100 gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-neutral-900">Supplier Accounts</h3>
            <span className="text-2xs text-neutral-400 bg-neutral-100 px-2 py-0.5 rounded-full">{filtered.length}</span>
          </div>
          <div className="flex items-center gap-2 flex-1 justify-end flex-wrap">
            {/* Filter tabs */}
            <div className="flex bg-neutral-50 border border-neutral-100 rounded-lg p-0.5 gap-0.5">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`text-xs font-semibold px-3 py-1.5 rounded-md cursor-pointer border-none transition-all ${filter === f.key ? "bg-white text-neutral-900 shadow-xs" : "bg-transparent text-neutral-500 hover:text-neutral-700"}`}
                >
                  {f.label}
                  {f.key !== "all" && (
                    <span className={`ml-1.5 text-[10px] font-bold px-1.5 py-px rounded-full ${f.key === "pending" ? "bg-warning-bg text-warning-dark" : f.key === "verified" ? "bg-success-bg text-success-dark" : "bg-danger-bg text-danger-dark"}`}>
                      {counts[f.key] || 0}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {/* Search */}
            <input
              type="text"
              placeholder="Search by name, company, mobile..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="text-xs border border-neutral-200 rounded-lg px-3 py-2 outline-none focus:border-brand-400 bg-neutral-50 w-52"
            />
            {/* Create button */}
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-1.5 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 px-4 py-2 rounded-lg cursor-pointer border-none transition-colors shadow-sm"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Add Supplier
            </button>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <svg className="w-6 h-6 text-brand-400 animate-spin" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-14 h-14 rounded-full bg-neutral-100 flex items-center justify-center mb-3 text-2xl">🏢</div>
            <p className="text-sm font-semibold text-neutral-700 mb-1">No suppliers found</p>
            <p className="text-xs text-neutral-400">
              {filter !== "all" ? `No ${filter} suppliers.` : "No supplier accounts yet."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-neutral-25 border-b border-neutral-100">
                  {["ID", "Name", "Company", "SAP Vendor #", "Mobile", "Email", "Status", "Registered", "Actions"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {filtered.map((s) => (
                  <tr key={s.id} className="hover:bg-neutral-25 transition-colors group">
                    <td className="px-4 py-3 text-neutral-400 font-mono">{s.id}</td>
                    <td className="px-4 py-3 font-semibold text-neutral-800 whitespace-nowrap">{s.name}</td>
                    <td className="px-4 py-3 text-neutral-600 max-w-[160px] truncate">{s.company_name}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {s.sap_vendor_number ? (
                        <span className="font-mono text-neutral-700">{s.sap_vendor_number}</span>
                      ) : (
                        <button
                          onClick={() => setLinkTarget(s)}
                          className="text-[11px] font-semibold text-brand-600 bg-brand-50 hover:bg-brand-100 px-2.5 py-1 rounded cursor-pointer border-none transition-colors"
                          title="Attach the SAP vendor this account represents"
                        >
                          ⛓ Link SAP
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-neutral-700 whitespace-nowrap">{s.mobile}</td>
                    <td className="px-4 py-3 text-neutral-500 max-w-[160px] truncate">{s.email || "—"}</td>
                    <td className="px-4 py-3">
                      <SupplierStatusChip status={s.status} />
                      {s.status === "rejected" && s.rejection_reason && (
                        <div className="text-[10px] text-neutral-400 mt-0.5 max-w-[120px] truncate" title={s.rejection_reason}>
                          {s.rejection_reason}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-neutral-400 whitespace-nowrap">{fmtDate(s.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {s.status === "pending" && (
                          <>
                            <button
                              onClick={() => handleApprove(s)}
                              disabled={actionLoading === s.id}
                              className="text-[11px] font-semibold text-success-dark bg-success-bg hover:bg-success-light px-2.5 py-1 rounded cursor-pointer border-none transition-colors disabled:opacity-50"
                            >
                              {actionLoading === s.id ? "..." : "✓ Approve"}
                            </button>
                            <button
                              onClick={() => setRejectTarget(s)}
                              disabled={actionLoading === s.id}
                              className="text-[11px] font-semibold text-danger-dark bg-danger-bg hover:bg-danger-light px-2.5 py-1 rounded cursor-pointer border-none transition-colors disabled:opacity-50"
                            >
                              ✗ Reject
                            </button>
                          </>
                        )}
                        {s.status === "rejected" && (
                          <button
                            onClick={() => handleApprove(s)}
                            disabled={actionLoading === s.id}
                            className="text-[11px] font-semibold text-success-dark bg-success-bg hover:bg-success-light px-2.5 py-1 rounded cursor-pointer border-none transition-colors"
                          >
                            Approve
                          </button>
                        )}
                        {s.status === "verified" && (
                          <button
                            onClick={() => setRejectTarget(s)}
                            className="opacity-0 group-hover:opacity-100 text-[11px] font-semibold text-danger-dark bg-danger-bg hover:bg-danger-light px-2.5 py-1 rounded cursor-pointer border-none transition-all"
                          >
                            Revoke
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pending alert banner */}
      {counts.pending > 0 && (
        <div className="mt-4 bg-warning-bg border border-warning-light rounded-lg px-5 py-3 flex items-center gap-3">
          <span className="text-lg">⏳</span>
          <p className="text-sm text-warning-dark">
            <strong>{counts.pending} supplier{counts.pending > 1 ? "s" : ""}</strong> pending review — approve or reject to grant portal access.
          </p>
        </div>
      )}

      {/* Modals */}
      <CreateSupplierModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={handleCreated} />
      <RejectModal open={!!rejectTarget} supplier={rejectTarget} onClose={() => setRejectTarget(null)} onRejected={handleRejected} />
      <LinkSAPModal open={!!linkTarget} supplier={linkTarget} onClose={() => setLinkTarget(null)} onLinked={handleLinked} />
    </div>
  );
}
