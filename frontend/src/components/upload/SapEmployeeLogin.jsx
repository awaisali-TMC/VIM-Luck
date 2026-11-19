import { useEffect, useState } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import { getSAPEmployeeLogin, signInSAPEmployee } from "../../services/sapService";

const errText = (err, fallback) => {
  const d = err?.response?.data?.detail;
  return typeof d === "string" ? d : d?.message || fallback;
};

/**
 * Lucky Cement: the user signs in with their SAP employee ID before uploading.
 * The backend checks the ID + password with SAP's login service and stores
 * them, so the parking workflow starts under this employee (USERI / PWDI).
 *
 * Renders `children` (the upload card) once signed in. When the feature is off
 * on this instance, it renders `children` straight away and nothing else.
 */
export default function SapEmployeeLogin({ children }) {
  const [status, setStatus] = useState(null);   // null = loading
  const [loadError, setLoadError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    getSAPEmployeeLogin()
      .then((s) => {
        if (!alive) return;
        setStatus(s);
        setUserId(s.pernr || "");
        if (s.enabled && !s.signed_in && s.message) setError(s.message);
      })
      .catch((err) => alive && setLoadError(errText(err, "Could not check your SAP login.")));
    return () => { alive = false; };
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await signInSAPEmployee(userId.trim(), password);
      setStatus(s);
      setUserId(s.pernr || userId);
      setEditing(false);
    } catch (err) {
      setError(errText(err, "SAP login failed."));
    } finally {
      setPassword("");
      setBusy(false);
    }
  };

  if (loadError) {
    return (
      <Card title="SAP Employee Login">
        <div className="text-xs text-danger-dark">{loadError}</div>
      </Card>
    );
  }
  if (!status) {
    return <div className="text-2xs text-neutral-500 px-1 py-2">Checking your SAP login…</div>;
  }
  if (!status.enabled) return children;

  const signedIn = status.signed_in && !editing;

  return (
    <div className="flex flex-col gap-4">
      {signedIn ? (
        <div className="flex items-center justify-between bg-success-bg border border-success-base rounded-md px-4 py-2.5">
          <div className="text-xs text-success-dark">
            <strong>Signed in to SAP</strong> as {status.name || "employee"} ({status.pernr})
            {status.mode === "fake" && <span className="ml-2 opacity-70">· fixture SAP</span>}
          </div>
          <Button variant="ghost" size="xs" onClick={() => { setEditing(true); setError(null); }}>
            Change
          </Button>
        </div>
      ) : (
        <Card
          title="SAP Employee Login"
          subtitle="Sign in with your SAP employee ID. Invoices you park start the SAP approval workflow under this ID."
        >
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-2xs font-medium text-neutral-600">
              Employee ID
              <input
                className="border border-neutral-200 rounded px-2.5 py-1.5 text-xs w-40"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="e.g. 00004007"
                autoComplete="username"
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-2xs font-medium text-neutral-600">
              SAP password
              <input
                type="password"
                className="border border-neutral-200 rounded px-2.5 py-1.5 text-xs w-48"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <Button type="submit" size="sm" disabled={busy || !userId.trim() || !password}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
            {editing && status.signed_in && (
              <Button type="button" variant="ghost" size="sm" onClick={() => { setEditing(false); setError(null); }}>
                Cancel
              </Button>
            )}
          </form>
          {error && (
            <div className="mt-3 bg-danger-bg border border-danger-base rounded-md px-3 py-2 text-2xs text-danger-dark">
              {error}
            </div>
          )}
        </Card>
      )}
      {signedIn && children}
    </div>
  );
}
