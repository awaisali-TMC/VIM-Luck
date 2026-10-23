import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useParams } from "react-router-dom";
import { internalMe, internalLogout } from "./services/authService";
import { getPendingApprovals } from "./services/workflowService";
import { ExtractionProvider, useExtraction } from "./context/ExtractionContext";
import { PermissionsProvider } from "./context/PermissionsContext";
import { canAccessPath, homeRoute } from "./config/rolePermissions";
import { getRolePermissions } from "./services/permissionService";
import Layout from "./components/layout/Layout";
import AdminPermissionsPage from "./pages/AdminPermissionsPage";
import LoginPage from "./pages/LoginPage";
import UploadInvoicePage from "./pages/UploadInvoicePage";
import ExtractionResultsPage from "./pages/ExtractionResultsPage";
import InvoiceListPage from "./pages/InvoiceListPage";
import InvoiceDetailPage from "./pages/InvoiceDetailPage";
import APOperatorDashboard from "./pages/APOperatorDashboard";
import TaxManagerDashboard from "./pages/TaxManagerDashboard";
import AuditorDashboard from "./pages/AuditorDashboard";
import AdminSuppliersPage from "./pages/AdminSuppliersPage";
import AdminEmailInboxPage from "./pages/AdminEmailInboxPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import POListPage from "./pages/POListPage";
import POCreatePage from "./pages/POCreatePage";
import PODetailPage from "./pages/PODetailPage";
import MyApprovalsPage from "./pages/MyApprovalsPage";
import WorkflowTemplatesPage from "./pages/WorkflowTemplatesPage";
import AnalyticsDashboard from "./pages/AnalyticsDashboard";
import TaxRulesPage from "./pages/TaxRulesPage";
import APVisibilityPage from "./pages/APVisibilityPage";
import ReportsPage from "./pages/ReportsPage";

// --- Route element wrappers ---
// These adapt page components that still take navigation callbacks / id props
// to React Router's hooks (useNavigate / useParams) and the ExtractionContext.

function APOperatorRoute() {
  const navigate = useNavigate();
  return (
    <APOperatorDashboard
      onViewInvoice={(id) => navigate(`/invoices/${id}`)}
      onOpenInbox={() => navigate("/invoices")}
    />
  );
}

function TaxManagerRoute() {
  const navigate = useNavigate();
  return <TaxManagerDashboard onViewInvoice={(id) => navigate(`/invoices/${id}`)} />;
}

function AuditorRoute() {
  const navigate = useNavigate();
  return <AuditorDashboard onViewInvoice={(id) => navigate(`/invoices/${id}`)} />;
}

function APVisibilityRoute() {
  const navigate = useNavigate();
  return <APVisibilityPage onViewInvoice={(id) => navigate(`/invoices/${id}`)} />;
}

function MyApprovalsRoute({ currentUser }) {
  const navigate = useNavigate();
  return (
    <MyApprovalsPage
      currentUser={currentUser}
      onViewInvoice={(id) => navigate(`/invoices/${id}`)}
    />
  );
}

function UploadRoute() {
  const navigate = useNavigate();
  const { handleExtractionComplete } = useExtraction();
  // Batch / multi-invoice uploads skip the review screen — land on the Invoice
  // Inbox with the new drafts highlighted.
  const handleBatchComplete = (result) => {
    const ids = (result.invoices || []).map((i) => i.id);
    navigate("/invoices", {
      state: { newInvoiceIds: ids, uploadErrors: result.errors || [] },
    });
  };
  return (
    <UploadInvoicePage
      onExtractionComplete={handleExtractionComplete}
      onBatchComplete={handleBatchComplete}
    />
  );
}


function ResultsRoute() {
  const {
    extractionResult,
    extractionFile,
    savedInvoice,
    resultsState,
    resultsError,
    handleSave,
    handleDiscardResults,
    setLineItemOverrides,
  } = useExtraction();

  // Landed here without an in-flight extraction (e.g. refresh) — go back to upload.
  if (!extractionResult) {
    return <Navigate to="/upload" replace />;
  }

  return (
    <ExtractionResultsPage
      extractionResult={extractionResult}
      file={extractionFile}
      savedInvoice={savedInvoice}
      state={resultsState}
      error={resultsError}
      onSave={handleSave}
      onDiscard={handleDiscardResults}
      onLineItemOverridesChange={setLineItemOverrides}
    />
  );
}

function InvoiceListRoute() {
  const navigate = useNavigate();
  return (
    <InvoiceListPage
      onViewInvoice={(id) => navigate(`/invoices/${id}`)}
      onUpload={() => navigate("/upload")}
    />
  );
}

function InvoiceDetailRoute({ currentUser }) {
  const navigate = useNavigate();
  const { id } = useParams();
  return (
    <InvoiceDetailPage
      invoiceId={id}
      onBack={() => navigate("/invoices")}
      currentUser={currentUser}
    />
  );
}

function POListRoute() {
  const navigate = useNavigate();
  return (
    <POListPage
      onViewPO={(id) => navigate(`/po/${id}`)}
      onCreatePO={() => navigate("/po/new")}
    />
  );
}

function POCreateRoute() {
  const navigate = useNavigate();
  return (
    <POCreatePage
      onCreated={(id) => navigate(`/po/${id}`)}
      onCancel={() => navigate("/po")}
    />
  );
}

function PODetailRoute() {
  const navigate = useNavigate();
  const { id } = useParams();
  return <PODetailPage poId={id} onBack={() => navigate("/po")} />;
}

function EmailInboxRoute() {
  const { handleEmailExtractionComplete } = useExtraction();
  return <AdminEmailInboxPage onEmailExtractionComplete={handleEmailExtractionComplete} />;
}

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [sessionRestoring, setSessionRestoring] = useState(true);
  const [pendingCount, setPendingCount] = useState(0);
  // Live role→page-level matrix + dynamic role list (admin-editable).
  // Static defaults apply until loaded.
  const [permMatrix, setPermMatrix] = useState(null);
  const [permRoles, setPermRoles] = useState([]);
  const [sessionNotice, setSessionNotice] = useState("");

  // Session invalidated (401) — e.g. this account signed in elsewhere. Drop to
  // the login screen with an explanation instead of leaving a broken session.
  useEffect(() => {
    const onExpired = () => {
      localStorage.removeItem("auth_token");
      setCurrentUser(null);
      setPermMatrix(null);
      setSessionNotice("You were signed out because your account was signed in on another device.");
    };
    window.addEventListener("auth:session-expired", onExpired);
    return () => window.removeEventListener("auth:session-expired", onExpired);
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    getRolePermissions()
      .then((data) => {
        setPermMatrix(data.matrix || null);
        setPermRoles(data.roles || []);
      })
      .catch(() => { /* keep static defaults */ });
  }, [currentUser]);

  // Restore session from localStorage token on mount
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time session-restore init
    if (!token) { setSessionRestoring(false); return; }
    internalMe(token)
      .then((data) => {
        setCurrentUser({
          id: data.id,
          email: data.email,
          name: data.display_name,
          role: data.role,
          department: data.department,
          token,
        });
      })
      .catch(() => {
        localStorage.removeItem("auth_token");
      })
      .finally(() => setSessionRestoring(false));
  }, []);

  // Fetch pending approval count periodically — ONLY for roles that actually
  // have an approval inbox. For non-approvers (e.g. AP operator) the count is
  // always 0, so we skip the poll entirely. Also pauses while the tab is
  // hidden so a backgrounded tab doesn't keep hitting the backend.
  useEffect(() => {
    if (!currentUser?.token) return;
    // Non-approvers (e.g. AP operator) have no approval inbox — the count stays
    // at its default 0 and we never poll.
    if (!canAccessPath(currentUser.role, "/approvals", permMatrix)) return;
    const fetchPending = () => {
      if (document.hidden) return;
      getPendingApprovals(currentUser.token)
        .then((data) => setPendingCount(data.total || 0))
        .catch(() => {});
    };
    fetchPending();
    const interval = setInterval(fetchPending, 60000); // every 60s
    const onVisible = () => { if (!document.hidden) fetchPending(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [currentUser?.token, currentUser?.role, permMatrix]);

  const handleLogout = async () => {
    const token = currentUser?.token || localStorage.getItem("auth_token");
    if (token) {
      try { await internalLogout(token); } catch { /* ignore */ }
    }
    localStorage.removeItem("auth_token");
    setCurrentUser(null);
    setPermMatrix(null); // next login refetches (role may differ)
  };

  // Show loading while restoring session
  if (sessionRestoring) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-50">
        <div className="text-neutral-400 text-sm">Restoring session...</div>
      </div>
    );
  }

  if (!currentUser) {
    return <LoginPage onLogin={(u) => { setSessionNotice(""); setCurrentUser(u); }} notice={sessionNotice} />;
  }

  const role = currentUser.role;
  const home = homeRoute(role, permMatrix);
  // Role guard: render the page only if this role may open the path,
  // otherwise send the user to their own home dashboard.
  const guard = (path, element) =>
    canAccessPath(role, path, permMatrix) ? element : <Navigate to={home} replace />;

  return (
    <PermissionsProvider matrix={permMatrix} role={role} roles={permRoles}>
    <ExtractionProvider>
      <Routes>
        <Route
          element={
            <Layout
              currentUser={currentUser}
              pendingCount={pendingCount}
              onLogout={handleLogout}
              permissions={permMatrix}
            />
          }
        >
          <Route index element={guard("/", <AnalyticsDashboard />)} />
          <Route path="ap-visibility" element={guard("/ap-visibility", <APVisibilityRoute />)} />
          <Route path="ap" element={guard("/ap", <APOperatorRoute />)} />
          <Route path="tax" element={guard("/tax", <TaxManagerRoute />)} />
          <Route path="auditor" element={guard("/auditor", <AuditorRoute />)} />

          <Route path="approvals" element={guard("/approvals", <MyApprovalsRoute currentUser={currentUser} />)} />

          <Route path="upload" element={guard("/upload", <UploadRoute />)} />
          <Route path="results" element={guard("/results", <ResultsRoute />)} />

          <Route path="invoices" element={guard("/invoices", <InvoiceListRoute />)} />
          <Route path="invoices/:id" element={guard("/invoices", <InvoiceDetailRoute currentUser={currentUser} />)} />

          <Route path="reports" element={guard("/reports", <ReportsPage />)} />

          <Route path="po" element={guard("/po", <POListRoute />)} />
          <Route path="po/new" element={guard("/po/new", <POCreateRoute />)} />
          <Route path="po/:id" element={guard("/po", <PODetailRoute />)} />

          <Route path="suppliers" element={guard("/suppliers", <AdminSuppliersPage />)} />
          <Route path="email-inbox" element={guard("/email-inbox", <EmailInboxRoute />)} />
          <Route path="users" element={guard("/users", <AdminUsersPage />)} />
          <Route path="permissions" element={guard("/permissions", <AdminPermissionsPage />)} />
          <Route path="workflows" element={guard("/workflows", <WorkflowTemplatesPage />)} />
          <Route path="tax-rules" element={guard("/tax-rules", <TaxRulesPage />)} />

          {/* Unknown paths fall back to the role's home dashboard */}
          <Route path="*" element={<Navigate to={home} replace />} />
        </Route>
      </Routes>
    </ExtractionProvider>
    </PermissionsProvider>
  );
}
