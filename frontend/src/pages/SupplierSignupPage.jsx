import { useState } from "react";
import { requestOtp, verifyOtp, supplierSignup } from "../services/supplierService";

const GREEN = "#10B981";
const DARK = "#0A1628";

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

function StepDot({ step, current, label }) {
  const done = step < current;
  const active = step === current;
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        backgroundColor: done ? GREEN : active ? DARK : "#E5E7EB",
        color: done || active ? "#fff" : "#9CA3AF",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, fontWeight: 700, transition: "all 0.2s ease",
      }}>
        {done ? "✓" : step}
      </div>
      <span style={{ fontSize: 11, fontWeight: active ? 600 : 400, color: active ? DARK : "#9CA3AF", whiteSpace: "nowrap" }}>
        {label}
      </span>
    </div>
  );
}

function StepLine({ done }) {
  return (
    <div style={{ flex: 1, height: 2, backgroundColor: done ? GREEN : "#E5E7EB", marginBottom: 18, transition: "background-color 0.3s ease" }} />
  );
}

export default function SupplierSignupPage({ onBack, onSignupComplete }) {
  const [step, setStep] = useState(1); // 1: mobile, 2: otp, 3: profile, 4: success

  // Step 1 & 2
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");

  // Step 3
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [focused, setFocused] = useState(null);

  const focus = (f) => setFocused(f);
  const blur = () => setFocused(null);

  /* Step 1 → 2: Request OTP */
  const handleRequestOtp = async (e) => {
    e.preventDefault();
    if (!mobile.trim()) { setError("Please enter your mobile number."); return; }
    setError("");
    setLoading(true);
    try {
      await requestOtp(mobile.trim(), "signup");
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to send OTP.");
    } finally {
      setLoading(false);
    }
  };

  /* Step 2 → 3: Verify the OTP with the server before letting the user
     continue (final signup consumes it again — this check does not). */
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    if (otp.length !== 6) { setError("Enter the 6-digit OTP."); return; }
    setError("");
    setLoading(true);
    try {
      await verifyOtp(mobile.trim(), otp.trim());
      setStep(3);
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid OTP. Please check and try again.");
    } finally {
      setLoading(false);
    }
  };

  /* Step 3 → 4: Complete signup */
  const handleSignup = async (e) => {
    e.preventDefault();
    if (!name.trim()) { setError("Name is required."); return; }
    if (!companyName.trim()) { setError("Company name is required."); return; }
    setError("");
    setLoading(true);
    try {
      await supplierSignup({
        mobile: mobile.trim(),
        otp_code: otp.trim(),
        name: name.trim(),
        company_name: companyName.trim(),
        email: email.trim() || null,
        password: password || null,
      });
      setStep(4);
    } catch (err) {
      setError(err.response?.data?.detail || "Signup failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const stepLabels = ["Mobile", "Verify OTP", "Profile", "Done"];

  return (
    <div style={{ backgroundColor: DARK }} className="min-h-screen flex items-center justify-center relative overflow-hidden px-6 py-10">
      {/* Background orbs */}
      <div style={{ position: "absolute", top: -100, right: -80, width: 280, height: 280, borderRadius: "50%", backgroundColor: GREEN, opacity: 0.07, pointerEvents: "none" }} />
      <div style={{ position: "absolute", bottom: -60, left: -50, width: 200, height: 200, borderRadius: "50%", backgroundColor: GREEN, opacity: 0.06, pointerEvents: "none" }} />

      <div style={{ width: "100%", maxWidth: 420, position: "relative", zIndex: 10 }}>
        {/* Brand */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <div style={{ width: 4, height: 22, borderRadius: 2, backgroundColor: GREEN, flexShrink: 0 }} />
            <span style={{ fontSize: 24, fontWeight: 300, color: "rgba(255,255,255,0.9)", letterSpacing: "0.15em" }}>
              Supplier<span style={{ fontWeight: 700, color: "#fff" }}>Hub</span>
            </span>
          </div>
          <p style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", fontWeight: 400, letterSpacing: "0.12em", textTransform: "uppercase", margin: 0 }}>
            Create your supplier account
          </p>
        </div>

        {/* Card */}
        <div style={{ backgroundColor: "#fff", borderRadius: 24, padding: 28, boxShadow: "0 20px 60px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.15)" }}>

          {/* Step indicator */}
          {step < 4 && (
            <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 28 }}>
              {stepLabels.map((label, i) => (
                <div key={i} style={{ display: "flex", alignItems: "flex-start", flex: i < stepLabels.length - 1 ? 1 : "none" }}>
                  <StepDot step={i + 1} current={step} label={label} />
                  {i < stepLabels.length - 1 && <StepLine done={step > i + 1} />}
                </div>
              ))}
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13, color: "#B91C1C" }}>
              {error}
            </div>
          )}

          {/* ── Step 1: Mobile ── */}
          {step === 1 && (
            <form onSubmit={handleRequestOtp} noValidate>
              <h2 style={{ fontSize: 20, fontWeight: 700, color: "#1A1D27", margin: "0 0 4px 0" }}>Enter your mobile</h2>
              <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 20px 0" }}>We'll send a one-time code to verify your number.</p>

              <div style={inputBox(focused === "mobile")}>
                <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: focused === "mobile" ? GREEN : "#8B95AB", transition: "color 0.15s ease" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="2" /><line x1="12" y1="18" x2="12.01" y2="18" />
                </svg>
                <input type="tel" placeholder="Mobile number (e.g. 03001234567)" value={mobile} onChange={(e) => { setMobile(e.target.value); setError(""); }} onFocus={() => focus("mobile")} onBlur={blur} autoComplete="tel" style={inputStyle} />
              </div>

              <div style={{ height: 16 }} />
              <button type="submit" disabled={loading} style={{ width: "100%", height: 52, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: loading ? "not-allowed" : "pointer", fontSize: 15, fontWeight: 700, color: "#fff", opacity: loading ? 0.8 : 1, transition: "opacity 0.15s ease" }}>
                {loading ? "Sending..." : "Send OTP →"}
              </button>
              <div style={{ textAlign: "center", marginTop: 16 }}>
                <button type="button" onClick={onBack} style={{ background: "none", border: "none", color: "#8B95AB", fontSize: 13, cursor: "pointer" }}>← Back to Login</button>
              </div>
            </form>
          )}

          {/* ── Step 2: OTP ── */}
          {step === 2 && (
            <form onSubmit={handleVerifyOtp} noValidate>
              <h2 style={{ fontSize: 20, fontWeight: 700, color: "#1A1D27", margin: "0 0 4px 0" }}>Verify your mobile</h2>
              <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 16px 0" }}>
                OTP sent to <strong style={{ color: "#1A1D27" }}>{mobile}</strong>.{" "}
                <button type="button" onClick={() => { setStep(1); setOtp(""); setError(""); }} style={{ background: "none", border: "none", color: GREEN, fontWeight: 600, cursor: "pointer", fontSize: 14, padding: 0 }}>Change</button>
              </p>

              <div style={inputBox(focused === "otp")}>
                <svg style={{ width: 18, height: 18, marginRight: 10, flexShrink: 0, color: focused === "otp" ? GREEN : "#8B95AB" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" />
                </svg>
                <input type="text" placeholder="6-digit OTP" value={otp} onChange={(e) => { setOtp(e.target.value.replace(/\D/g, "").slice(0, 6)); setError(""); }} onFocus={() => focus("otp")} onBlur={blur} maxLength={6} inputMode="numeric" style={{ ...inputStyle, fontSize: 22, fontWeight: 700, letterSpacing: 6 }} />
              </div>

              <div style={{ height: 16 }} />
              <button type="submit" disabled={otp.length < 6 || loading} style={{ width: "100%", height: 52, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: otp.length < 6 || loading ? "not-allowed" : "pointer", fontSize: 15, fontWeight: 700, color: "#fff", opacity: otp.length < 6 || loading ? 0.6 : 1, transition: "opacity 0.15s ease" }}>
                {loading ? "Verifying..." : "Verify OTP →"}
              </button>
              <div style={{ textAlign: "center", marginTop: 12 }}>
                <button type="button" onClick={handleRequestOtp} style={{ background: "none", border: "none", color: "#8B95AB", fontSize: 13, cursor: "pointer" }}>Resend OTP</button>
              </div>
            </form>
          )}

          {/* ── Step 3: Profile ── */}
          {step === 3 && (
            <form onSubmit={handleSignup} noValidate>
              <h2 style={{ fontSize: 20, fontWeight: 700, color: "#1A1D27", margin: "0 0 4px 0" }}>Complete your profile</h2>
              <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 20px 0" }}>Tell us about your business to finish registration.</p>

              {/* Name */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Full Name *</label>
                <div style={inputBox(focused === "name")}>
                  <input type="text" placeholder="Your full name" value={name} onChange={(e) => { setName(e.target.value); setError(""); }} onFocus={() => focus("name")} onBlur={blur} style={inputStyle} />
                </div>
              </div>

              {/* Company */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Company Name *</label>
                <div style={inputBox(focused === "company")}>
                  <input type="text" placeholder="Your company / business name" value={companyName} onChange={(e) => { setCompanyName(e.target.value); setError(""); }} onFocus={() => focus("company")} onBlur={blur} style={inputStyle} />
                </div>
              </div>

              {/* Email */}
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Email <span style={{ fontWeight: 400, textTransform: "none" }}>(optional)</span></label>
                <div style={inputBox(focused === "email")}>
                  <input type="email" placeholder="business@example.com" value={email} onChange={(e) => setEmail(e.target.value)} onFocus={() => focus("email")} onBlur={blur} style={inputStyle} />
                </div>
              </div>

              {/* Password */}
              <div style={{ marginBottom: 20 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#6B7590", textTransform: "uppercase", letterSpacing: "0.05em", display: "block", marginBottom: 6 }}>Password <span style={{ fontWeight: 400, textTransform: "none" }}>(optional — for future password login)</span></label>
                <div style={inputBox(focused === "pwd")}>
                  <input type={showPassword ? "text" : "password"} placeholder="Create a password" value={password} onChange={(e) => setPassword(e.target.value)} onFocus={() => focus("pwd")} onBlur={blur} style={inputStyle} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ background: "none", border: "none", cursor: "pointer", color: "#8B95AB", padding: 4, display: "flex", alignItems: "center" }}>
                    <svg style={{ width: 17, height: 17 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                      {showPassword ? <><path d="M17.94 17.94A10 10 0 0112 20c-7 0-11-8-11-8a18 18 0 015.06-5.94M9.9 4.24A9 9 0 0112 4c7 0 11 8 11 8a18 18 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></> : <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>}
                    </svg>
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading} style={{ width: "100%", height: 52, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: loading ? "not-allowed" : "pointer", fontSize: 15, fontWeight: 700, color: "#fff", opacity: loading ? 0.8 : 1, transition: "opacity 0.15s ease" }}>
                {loading ? "Creating account..." : "Create Account →"}
              </button>
            </form>
          )}

          {/* ── Step 4: Success ── */}
          {step === 4 && (
            <div style={{ textAlign: "center", padding: "8px 0" }}>
              <div style={{ width: 72, height: 72, borderRadius: "50%", backgroundColor: "#ECFDF5", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px", fontSize: 32 }}>
                ✅
              </div>
              <h2 style={{ fontSize: 22, fontWeight: 700, color: "#1A1D27", margin: "0 0 8px 0" }}>You're registered!</h2>
              <p style={{ fontSize: 14, color: "#6B7590", margin: "0 0 8px 0", lineHeight: 1.6 }}>
                Your supplier account for <strong>{companyName}</strong> has been created successfully.
              </p>
              <div style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 12, padding: "12px 16px", marginBottom: 24, fontSize: 13, color: "#78350F", lineHeight: 1.6 }}>
                ⏳ <strong>Pending Admin Approval</strong><br />
                Your account is being reviewed. You'll be able to log in once an admin approves it. This usually takes 1–2 business days.
              </div>
              <button onClick={onSignupComplete} style={{ width: "100%", height: 48, backgroundColor: GREEN, borderRadius: 14, border: "none", cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#fff" }}>
                Back to Login
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
