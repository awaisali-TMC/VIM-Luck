import { useState, useEffect } from "react";
import { internalLogin } from "../services/authService";
import tmcLogo from "../assets/tmc-logo-dark.png";
import { pageDocumentTitle } from "../config/brand";

const TMC_BLUE = "#2EA3F2";
const TMC_BLUE_DARK = "#1577BE";

export default function LoginPage({ onLogin, notice }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [errors, setErrors] = useState({});
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 60);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    document.title = pageDocumentTitle("Sign In");
  }, []);

  const handleLogin = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!email.trim()) errs.email = "Email is required";
    if (!password.trim()) errs.password = "Password is required";
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }
    setErrors({});
    setLoading(true);
    try {
      const data = await internalLogin(email.trim(), password);
      localStorage.setItem("auth_token", data.token);
      setLoading(false);
      onLogin({
        id: data.user.id,
        email: data.user.email,
        name: data.user.display_name,
        role: data.user.role,
        department: data.user.department,
        token: data.token,
      });
    } catch (err) {
      setLoading(false);
      const detail = err.response?.data?.detail || "Login failed";
      setErrors({ general: detail });
    }
  };

  const inputContainerStyle = (field) => ({
    display: "flex",
    alignItems: "center",
    backgroundColor: focusedField === field ? "#fff" : "#F5F6F8",
    border: `1.5px solid ${focusedField === field ? TMC_BLUE : errors[field] ? "#EF4444" : "#D5D9E2"}`,
    borderRadius: 14,
    paddingLeft: 14,
    paddingRight: 14,
    height: 52,
    boxShadow: focusedField === field ? `0 0 0 3px ${TMC_BLUE}28` : "none",
    transition: "all 0.15s ease",
  });

  const iconColor = (field) => focusedField === field ? TMC_BLUE : "#8B95AB";

  return (
    <div
      style={{ backgroundColor: "#0A1628" }}
      className="min-h-screen flex items-center justify-center relative overflow-hidden px-6 py-10"
    >
      {/* Background orbs */}
      <div style={{ position: "absolute", top: -120, right: -90, width: 320, height: 320, borderRadius: "50%", backgroundColor: TMC_BLUE, opacity: 0.08, pointerEvents: "none" }} />
      <div style={{ position: "absolute", bottom: -80, left: -60, width: 220, height: 220, borderRadius: "50%", backgroundColor: TMC_BLUE_DARK, opacity: 0.1, pointerEvents: "none" }} />
      <div style={{ position: "absolute", top: "35%", left: -30, width: 100, height: 100, borderRadius: "50%", backgroundColor: TMC_BLUE, opacity: 0.06, pointerEvents: "none" }} />

      <div className="relative z-10 w-full max-w-sm flex flex-col items-center">
        {/* Brand */}
        <div
          style={{ transform: mounted ? "scale(1)" : "scale(0.7)", opacity: mounted ? 1 : 0, transition: "transform 0.55s cubic-bezier(0.175,0.885,0.32,1.275), opacity 0.4s ease" }}
          className="flex flex-col items-center mb-8"
        >
          <div className="flex items-center mb-2" style={{ gap: 10 }}>
            <div style={{ width: 4, height: 22, borderRadius: 2, backgroundColor: TMC_BLUE, flexShrink: 0 }} />
            <span style={{ fontSize: 26, fontWeight: 300, color: "rgba(255,255,255,0.9)", letterSpacing: "0.15em", lineHeight: 1 }}>
              cogni<span style={{ fontWeight: 700, color: "#fff" }}>vend</span>
            </span>
          </div>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontWeight: 400, letterSpacing: "0.12em", textTransform: "uppercase", textAlign: "center", margin: 0 }}>
            Vendor Compliance &amp; Invoice Automation
          </p>
        </div>

        {/* Form Card */}
        <div
          style={{ width: "100%", backgroundColor: "#fff", borderRadius: 24, padding: 28, boxShadow: "0 20px 60px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.15)", transform: mounted ? "translateY(0)" : "translateY(30px)", opacity: mounted ? 1 : 0, transition: "transform 0.5s ease 0.25s, opacity 0.5s ease 0.25s" }}
        >
          <h2 style={{ fontSize: 22, fontWeight: 700, color: "#1A1D27", margin: "0 0 4px 0" }}>Welcome back</h2>
          <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 24px 0" }}>Sign in to your account</p>

          {notice && (
            <div style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 10, padding: "10px 12px", margin: "0 0 18px", fontSize: 13, color: "#92400E" }}>
              {notice}
            </div>
          )}

          <form onSubmit={handleLogin} noValidate>
            {/* Email */}
            <div style={inputContainerStyle("email")}>
              <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: iconColor("email"), transition: "color 0.15s ease" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2" /><path d="M2 7l10 7 10-7" />
              </svg>
              <input
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setErrors((p) => ({ ...p, email: null })); }}
                onFocus={() => setFocusedField("email")}
                onBlur={() => setFocusedField(null)}
                autoComplete="email"
                autoCapitalize="none"
                style={{ flex: 1, border: "none", outline: "none", backgroundColor: "transparent", fontSize: 15, color: "#2E3340", minWidth: 0 }}
              />
            </div>
            {errors.email && <p style={{ fontSize: 12, color: "#EF4444", margin: "5px 0 10px 2px" }}>{errors.email}</p>}

            {/* Password */}
            <div style={{ ...inputContainerStyle("password"), marginTop: errors.email ? 0 : 14 }}>
              <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: iconColor("password"), transition: "color 0.15s ease" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" />
              </svg>
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setErrors((p) => ({ ...p, password: null })); }}
                onFocus={() => setFocusedField("password")}
                onBlur={() => setFocusedField(null)}
                autoComplete="current-password"
                style={{ flex: 1, border: "none", outline: "none", backgroundColor: "transparent", fontSize: 15, color: "#2E3340", minWidth: 0 }}
              />
              <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ background: "none", border: "none", cursor: "pointer", padding: 4, color: "#8B95AB", display: "flex", alignItems: "center", flexShrink: 0 }}>
                {showPassword ? (
                  <svg style={{ width: 18, height: 18 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg style={{ width: 18, height: 18 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
            {errors.password && <p style={{ fontSize: 12, color: "#EF4444", margin: "5px 0 0 2px" }}>{errors.password}</p>}
            {errors.general && <p style={{ fontSize: 12, color: "#EF4444", margin: "8px 0 0 2px", textAlign: "center" }}>{errors.general}</p>}

            {/* Password resets are an admin action (Admin → User Management) */}
            <div style={{ height: 20 }} />

            {/* Sign In */}
            <button
              type="submit"
              disabled={loading}
              style={{ width: "100%", height: 52, backgroundColor: TMC_BLUE, borderRadius: 14, border: "none", cursor: loading ? "not-allowed" : "pointer", fontSize: 16, fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, boxShadow: `0 4px 20px ${TMC_BLUE}55`, opacity: loading ? 0.85 : 1, transition: "opacity 0.15s ease, transform 0.1s ease" }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.backgroundColor = "#1B8FDE"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = TMC_BLUE; }}
              onMouseDown={(e) => { if (!loading) e.currentTarget.style.transform = "scale(0.98)"; }}
              onMouseUp={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
            >
              {loading ? (
                <>
                  <svg style={{ width: 18, height: 18, animation: "spin 0.8s linear infinite" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                  </svg>
                  Signing in...
                </>
              ) : (
                <>
                  Sign In
                  <svg style={{ width: 18, height: 18 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Powered By */}
        <div
          style={{ display: "flex", flexDirection: "column", alignItems: "center", marginTop: 24, opacity: mounted ? 1 : 0, transition: "opacity 0.5s ease 0.65s" }}
        >
          <span style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600, marginBottom: 8 }}>
            Powered By
          </span>
          <img src={tmcLogo} alt="TMC" style={{ height: 42, width: 42, objectFit: "contain" }} />
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
