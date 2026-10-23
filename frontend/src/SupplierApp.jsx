import { useState, useEffect } from "react";
import { requestOtp, supplierLogin, getSupplierMe, supplierLogout } from "./services/supplierService";
import SupplierPortal from "./pages/SupplierPortal";
import SupplierSignupPage from "./pages/SupplierSignupPage";

const GREEN = "#10B981";
const DARK = "#0A1628";
const TMC_BLUE = "#2EA3F2";

/* ── Shared input style helpers ─────────────────────────────────────────── */
const inputBox = (focused, error) => ({
  display: "flex",
  alignItems: "center",
  backgroundColor: focused ? "#fff" : "#F5F6F8",
  border: `1.5px solid ${focused ? GREEN : error ? "#EF4444" : "#D5D9E2"}`,
  borderRadius: 14,
  paddingLeft: 14,
  paddingRight: 14,
  height: 52,
  boxShadow: focused ? `0 0 0 3px ${GREEN}28` : "none",
  transition: "all 0.15s ease",
});

const inputStyle = {
  flex: 1,
  border: "none",
  outline: "none",
  backgroundColor: "transparent",
  fontSize: 15,
  color: "#2E3340",
  minWidth: 0,
};

/* ── Supplier Login Page ─────────────────────────────────────────────────── */
function SupplierLoginPage({ onLogin, notice }) {
  const [step, setStep] = useState("mobile"); // "mobile" | "otp"
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [focused, setFocused] = useState(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 60);
    return () => clearTimeout(t);
  }, []);

  const handleRequestOtp = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    if (!mobile.trim()) { setError("Please enter your mobile number."); return; }
    setError("");
    setLoading(true);
    try {
      await requestOtp(mobile.trim(), "login");
      setStep("otp");
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to send OTP. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    if (otp.length !== 6) { setError("Please enter the 6-digit OTP."); return; }
    setError("");
    setLoading(true);
    try {
      const res = await supplierLogin(mobile.trim(), otp.trim());
      localStorage.setItem("supplier_token", res.token);
      onLogin({ ...res.supplier, role: "supplier", token: res.token });
    } catch (err) {
      setError(err.response?.data?.detail || "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{ backgroundColor: DARK }}
      className="min-h-screen flex items-center justify-center relative overflow-hidden px-6 py-10"
    >
      {/* Background orbs */}
      <div style={{ position: "absolute", top: -120, right: -90, width: 320, height: 320, borderRadius: "50%", backgroundColor: GREEN, opacity: 0.07, pointerEvents: "none" }} />
      <div style={{ position: "absolute", bottom: -80, left: -60, width: 220, height: 220, borderRadius: "50%", backgroundColor: GREEN, opacity: 0.06, pointerEvents: "none" }} />

      <div
        className="relative z-10 w-full max-w-sm flex flex-col items-center"
        style={{ opacity: mounted ? 1 : 0, transform: mounted ? "translateY(0)" : "translateY(20px)", transition: "opacity 0.4s ease, transform 0.4s ease" }}
      >
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center mb-2" style={{ gap: 10 }}>
            <div style={{ width: 4, height: 22, borderRadius: 2, backgroundColor: GREEN, flexShrink: 0 }} />
            <span style={{ fontSize: 26, fontWeight: 300, color: "rgba(255,255,255,0.9)", letterSpacing: "0.15em", lineHeight: 1 }}>
              Supplier<span style={{ fontWeight: 700, color: "#fff" }}>Hub</span>
            </span>
          </div>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontWeight: 400, letterSpacing: "0.12em", textTransform: "uppercase", textAlign: "center", margin: 0 }}>
            Vendor Invoice Submission Portal
          </p>
        </div>

        {/* Card */}
        <div style={{ width: "100%", backgroundColor: "#fff", borderRadius: 24, padding: 28, boxShadow: "0 20px 60px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.15)" }}>
          <h2 style={{ fontSize: 22, fontWeight: 700, color: "#1A1D27", margin: "0 0 4px 0" }}>
            {step === "mobile" ? "Sign in" : "Enter OTP"}
          </h2>
          <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 24px 0" }}>
            {step === "mobile"
              ? "Enter your registered mobile number to continue."
              : <>OTP sent to <strong style={{ color: "#1A1D27" }}>{mobile}</strong>.{" "}
                  <button type="button" onClick={() => { setStep("mobile"); setOtp(""); setError(""); }} style={{ background: "none", border: "none", color: GREEN, fontWeight: 600, cursor: "pointer", fontSize: 14, padding: 0 }}>Change</button></>
            }
          </p>

          {/* Session-ended notice */}
          {notice && !error && (
            <div style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#92400E" }}>
              {notice}
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#B91C1C" }}>
              {error}
            </div>
          )}

          {/* Step: Mobile */}
          {step === "mobile" && (
            <form onSubmit={handleRequestOtp} noValidate>
              <div style={inputBox(focused === "mobile")}>
                <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: focused === "mobile" ? GREEN : "#8B95AB", transition: "color 0.15s ease" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="2" /><line x1="12" y1="18" x2="12.01" y2="18" />
                </svg>
                <input
                  type="tel"
                  placeholder="Mobile number (e.g. 03001234567)"
                  value={mobile}
                  onChange={(e) => { setMobile(e.target.value); setError(""); }}
                  onFocus={() => setFocused("mobile")}
                  onBlur={() => setFocused(null)}
                  autoComplete="tel"
                  style={inputStyle}
                />
              </div>
              <div style={{ height: 16 }} />
              <button
                type="submit"
                disabled={loading}
                style={{ width: "100%", height: 52, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: loading ? "not-allowed" : "pointer", fontSize: 16, fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: loading ? 0.85 : 1, transition: "opacity 0.15s ease", boxShadow: `0 4px 20px ${GREEN}55` }}
              >
                {loading ? "Sending OTP..." : <>Get OTP <svg style={{ width: 18, height: 18 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M12 5l7 7-7 7" /></svg></>}
              </button>
            </form>
          )}

          {/* Step: OTP */}
          {step === "otp" && (
            <form onSubmit={handleLogin} noValidate>
              <div style={inputBox(focused === "otp")}>
                <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: focused === "otp" ? GREEN : "#8B95AB", transition: "color 0.15s ease" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" />
                </svg>
                <input
                  type="text"
                  placeholder="6-digit OTP"
                  value={otp}
                  onChange={(e) => { setOtp(e.target.value.replace(/\D/g, "").slice(0, 6)); setError(""); }}
                  onFocus={() => setFocused("otp")}
                  onBlur={() => setFocused(null)}
                  maxLength={6}
                  inputMode="numeric"
                  autoFocus
                  style={{ ...inputStyle, fontSize: 22, fontWeight: 700, letterSpacing: 6 }}
                />
              </div>
              <div style={{ height: 16 }} />
              <button
                type="submit"
                disabled={loading || otp.length < 6}
                style={{ width: "100%", height: 52, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: (loading || otp.length < 6) ? "not-allowed" : "pointer", fontSize: 16, fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, opacity: (loading || otp.length < 6) ? 0.7 : 1, transition: "opacity 0.15s ease", boxShadow: `0 4px 20px ${GREEN}55` }}
              >
                {loading ? "Verifying..." : "Sign In →"}
              </button>
              <div style={{ textAlign: "center", marginTop: 12 }}>
                <button type="button" onClick={() => handleRequestOtp({})} style={{ background: "none", border: "none", color: "#8B95AB", fontSize: 13, cursor: "pointer" }}>
                  Resend OTP
                </button>
              </div>
            </form>
          )}

          {/* Self-signup entry removed — supplier accounts are created by an
              admin on the Supplier Accounts page. (SupplierSignupPage remains
              in code; restore this block to re-enable self-signup.) */}
        </div>

        {/* Powered by footer */}
        <div style={{ marginTop: 24, fontSize: 11, color: "rgba(255,255,255,0.3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Powered by cogni<strong style={{ color: "rgba(255,255,255,0.45)" }}>vend</strong>
        </div>
      </div>

      <style>{`@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  );
}

/* ── Root supplier app ───────────────────────────────────────────────────── */
export default function SupplierApp() {
  const [currentUser, setCurrentUser] = useState(null);
  const [showSignup, setShowSignup] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [sessionNotice, setSessionNotice] = useState("");

  // Session invalidated (401) — e.g. this supplier signed in elsewhere. Drop to
  // the login screen with an explanation.
  useEffect(() => {
    const onExpired = () => {
      localStorage.removeItem("supplier_token");
      setCurrentUser(null);
      setSessionNotice("You were signed out because your account was signed in on another device.");
    };
    window.addEventListener("auth:session-expired", onExpired);
    return () => window.removeEventListener("auth:session-expired", onExpired);
  }, []);

  // Restore session from localStorage on load
  useEffect(() => {
    const token = localStorage.getItem("supplier_token");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time session-restore init
    if (!token) { setRestoring(false); return; }
    getSupplierMe(token)
      .then((user) => setCurrentUser({ ...user, role: "supplier", token }))
      .catch(() => localStorage.removeItem("supplier_token"))
      .finally(() => setRestoring(false));
  }, []);

  const handleLogout = async () => {
    const token = localStorage.getItem("supplier_token");
    if (token) { supplierLogout(token).catch(() => {}); }
    localStorage.removeItem("supplier_token");
    setCurrentUser(null);
  };

  if (restoring) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: DARK, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <svg style={{ width: 32, height: 32, color: GREEN, animation: "spin 1s linear infinite" }} viewBox="0 0 24 24" fill="none">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
        <style>{`@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  if (showSignup) {
    return (
      <SupplierSignupPage
        onBack={() => setShowSignup(false)}
        onSignupComplete={() => setShowSignup(false)}
      />
    );
  }

  if (!currentUser) {
    return (
      <SupplierLoginPage
        onLogin={(u) => { setSessionNotice(""); setCurrentUser(u); }}
        onShowSignup={() => setShowSignup(true)}
        notice={sessionNotice}
      />
    );
  }

  return <SupplierPortal user={currentUser} onLogout={handleLogout} />;
}
