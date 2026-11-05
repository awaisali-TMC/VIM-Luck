import { useState, useCallback, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation, useParams } from "react-router-dom";
import { saveInvoice, matchProducts, getInvoices } from "../services/invoiceService";
import SupplierDashboard from "./SupplierDashboard";
import UploadInvoicePage from "./UploadInvoicePage";
import ExtractionResultsPage from "./ExtractionResultsPage";
import InvoiceDetailPage from "./InvoiceDetailPage";
import Badge from "../components/common/Badge";
import SupplierNotificationsPage from "./SupplierNotificationsPage";
import SupplierProfilePage from "./SupplierProfilePage";
import SupplierPOsPage from "./SupplierPOsPage";
import tmcLogo from "../assets/tmc-logo-dark.png";

// Router paths (under basename /supplier — the browser shows /supplier/pos etc.)
const NAV = [
  { path: "/dashboard", label: "My Dashboard", icon: "📊" },
  { path: "/pos",       label: "My POs", icon: "📦" },
  { path: "/upload",    label: "Upload Invoice", icon: "📤" },
  { path: "/invoices",  label: "My Invoices", icon: "📋" },
  { path: "/tracker",   label: "Status Tracker", icon: "🔔" },
  { path: "/profile",   label: "My Profile", icon: "👤" },
];

const TITLE_RULES = [
  { test: (p) => p.startsWith("/dashboard"), title: "Supplier Dashboard" },
  { test: (p) => p.startsWith("/pos"), title: "My Purchase Orders" },
  { test: (p) => p === "/upload/review", title: "Extraction Results" },
  { test: (p) => p.startsWith("/upload"), title: "Upload Invoice" },
  { test: (p) => /^\/invoices\/\d+/.test(p), title: "Invoice Detail" },
  { test: (p) => p.startsWith("/invoices"), title: "My Invoices" },
  { test: (p) => p.startsWith("/tracker"), title: "Invoice Status Tracker" },
  { test: (p) => p.startsWith("/profile"), title: "Supplier Profile" },
];

/* ── History / invoice list for suppliers ───────────────────────────────── */
function HistoryView({ onViewInvoice, onUpload, highlightIds = [], uploadErrors = [] }) {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const newIds = new Set(highlightIds);

  useEffect(() => {
    (async () => {
      try {
        const data = await getInvoices(0, 100);
        setInvoices(data.invoices || []);
      } catch {
        setInvoices([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const fmtDate = (s) => {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleDateString("en-PK", { day: "2-digit", month: "short", year: "numeric" });
    } catch {
      return s;
    }
  };

  return (
    <div className="bg-neutral-0 border border-neutral-100 rounded-lg shadow-xs">
      <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900">All Submissions</h3>
          <p className="text-xs text-neutral-400 mt-0.5">{invoices.length} total invoices</p>
        </div>
        <button
          onClick={onUpload}
          className="text-xs font-semibold text-white bg-emerald-500 hover:bg-emerald-600 px-4 py-2 rounded-lg cursor-pointer border-none transition-colors"
        >
          + Upload New
        </button>
      </div>

      {/* Just-uploaded banner (batch / multi-invoice upload) */}
      {newIds.size > 0 && (
        <div className="mx-5 mt-4 px-4 py-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800">
          <strong>{newIds.size} invoice{newIds.size > 1 ? "s" : ""} just uploaded</strong> as drafts — highlighted below. Open each to review and submit.
          {uploadErrors.length > 0 && (
            <span className="block mt-1 text-amber-700">
              {uploadErrors.length} file(s) couldn&apos;t be processed: {uploadErrors.map((e) => e.file).join(", ")}
            </span>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <svg className="w-6 h-6 text-emerald-400 animate-spin" viewBox="0 0 24 24" fill="none">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </div>
      ) : invoices.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-sm font-semibold text-neutral-700 mb-1">No invoices yet</p>
          <p className="text-xs text-neutral-400 mb-4">Upload your first invoice to get started</p>
          <button
            onClick={onUpload}
            className="text-xs font-semibold text-white bg-emerald-500 hover:bg-emerald-600 px-4 py-2 rounded-lg cursor-pointer border-none"
          >
            Upload Invoice
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-neutral-25 border-b border-neutral-100">
                {["#", "Invoice No.", "Supplier", "Date", "Amount", "Status", "Submitted"].map((h, i) => (
                  <th
                    key={h || `col-${i}`}
                    className="px-4 py-2.5 text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {invoices.map((inv) => (
                <tr
                  key={inv.id}
                  // The whole row opens the invoice, unless text is being selected.
                  onClick={() => {
                    if (window.getSelection()?.toString()) return;
                    onViewInvoice(inv.id);
                  }}
                  className={`cursor-pointer transition-colors ${newIds.has(inv.id) ? "bg-emerald-50/60" : "hover:bg-neutral-25"}`}
                >
                  <td className="px-4 py-3 text-neutral-400">
                    <span className="inline-flex items-center gap-1.5">
                      {newIds.has(inv.id) && <span className="w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" title="Just uploaded" />}
                      {/* A real button, so the invoice opens from the keyboard too. */}
                      <button
                        type="button"
                        className="text-emerald-600 font-semibold cursor-pointer hover:underline bg-transparent border-none p-0"
                        onClick={(e) => { e.stopPropagation(); onViewInvoice(inv.id); }}
                        title="Open invoice"
                      >
                        #{inv.id}
                      </button>
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono font-semibold text-neutral-800">{inv.invoice_number || "—"}</td>
                  <td className="px-4 py-3 text-neutral-600 max-w-[160px] truncate">{inv.supplier_name || "—"}</td>
                  <td className="px-4 py-3 text-neutral-500 whitespace-nowrap">{fmtDate(inv.invoice_date)}</td>
                  <td className="px-4 py-3 font-semibold text-neutral-800 whitespace-nowrap">
                    {inv.total_amount != null ? `PKR ${Number(inv.total_amount).toLocaleString()}` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge status={inv.status} />
                  </td>
                  <td className="px-4 py-3 text-neutral-400 whitespace-nowrap">{fmtDate(inv.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ── Invoice detail route (id lives in the URL) ─────────────────────────── */
function InvoiceDetailRoute({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  return (
    <InvoiceDetailPage
      invoiceId={Number(id)}
      onBack={() => navigate("/invoices")}
      // Pass the supplier identity so attachments record the uploader and
      // the supplier can manage (delete) their own attached documents.
      currentUser={{ name: user?.company_name || user?.name, role: "supplier", token: user?.token }}
    />
  );
}

/* ── Main Supplier Portal ───────────────────────────────────────────────── */
export default function SupplierPortal({ user, onLogout }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Extraction / results state (transient — the review screen needs the
  // in-memory extraction, so a hard reload of /upload/review returns to /upload)
  const [extractionFile, setExtractionFile] = useState(null);
  const [extractionResult, setExtractionResult] = useState(null);
  const [resultsState, setResultsState] = useState("extracted");
  const [resultsError, setResultsError] = useState(null);
  const [lineItemOverrides, setLineItemOverrides] = useState({});

  // PO flip-to-invoice state
  const [flipPO, setFlipPO] = useState(null);

  // Batch / multi-invoice upload → drafts, then land on My Invoices highlighted.
  const [batchNewIds, setBatchNewIds] = useState([]);
  const [batchErrors, setBatchErrors] = useState([]);

  const navigateToDetail = useCallback((id) => navigate(`/invoices/${id}`), [navigate]);

  const navigateToHistory = useCallback(() => {
    setBatchNewIds([]);
    setBatchErrors([]);
    navigate("/invoices");
  }, [navigate]);

  // A file with several invoices, or several files, were saved as drafts
  // server-side (no review screen) — show them highlighted in My Invoices.
  const handleBatchComplete = useCallback((result) => {
    setBatchNewIds((result.invoices || []).map((i) => i.id));
    setBatchErrors(result.errors || []);
    navigate("/invoices");
  }, [navigate]);

  const handleExtractionComplete = useCallback((file, result) => {
    setExtractionFile(file);

    // Ensure at least one line item
    if (result && (!result.line_items || result.line_items.length === 0)) {
      const fieldMap = {};
      for (const f of (result.fields || [])) fieldMap[f.field_name] = f.value;
      const totalAmount = parseFloat(String(fieldMap.total_amount || "0").replace(/,/g, "")) || 0;
      result = {
        ...result,
        line_items: [{ description: "N/A", quantity: 1, unit: "", unit_price: totalAmount, amount: totalAmount }],
      };
    }

    // Recalculate unit_price = amount / qty
    if (result?.line_items) {
      result = {
        ...result,
        line_items: result.line_items.map((li) => {
          const qty = parseFloat(li.quantity);
          const amount = parseFloat(li.amount);
          return {
            ...li,
            unit_price: qty && amount ? Math.round((amount / qty) * 100) / 100 : li.unit_price,
          };
        }),
      };
    }

    setExtractionResult(result);
    setResultsState("extracted");
    setResultsError(null);
    setLineItemOverrides({});
    navigate("/upload/review");
  }, [navigate]);

  const handleSave = useCallback(
    async (status = "draft") => {
      if (!extractionResult) return;
      setResultsState("saving");
      setResultsError(null);

      try {
        const fieldMap = {};
        for (const f of extractionResult.fields) fieldMap[f.field_name] = f.value;
        const confMap = {};
        for (const f of extractionResult.fields) confMap[f.field_name] = f.confidence;

        const payload = {
          invoice_number: fieldMap.invoice_id || fieldMap.invoice_number || null,
          invoice_date: fieldMap.invoice_date || null,
          due_date: fieldMap.due_date || null,
          currency: fieldMap.currency || "PKR",
          supplier_name: fieldMap.supplier_name || null,
          supplier_address: fieldMap.supplier_address || null,
          supplier_ntn: fieldMap.supplier_tax_id || null,
          receiver_name: fieldMap.receiver_name || null,
          receiver_address: fieldMap.receiver_address || null,
          subtotal_amount: parseFloat(String(fieldMap.net_amount || "").replace(/,/g, "")) || null,
          tax_amount: parseFloat(String(fieldMap.total_tax_amount || "").replace(/,/g, "")) || null,
          total_amount: parseFloat(String(fieldMap.total_amount || "").replace(/,/g, "")) || null,
          gst_amount: null,
          wht_amount: null,
          po_reference: fieldMap.purchase_order || null,
          bank_iban: fieldMap.remit_to_address || null,
          document_type: extractionResult.document_type,
          overall_confidence: extractionResult.overall_confidence,
          field_confidences: confMap,
          warnings: extractionResult.warnings,
          processing_time_ms: extractionResult.processing_time_ms,
          original_filename: extractionResult.original_filename || (flipPO ? `PO-${flipPO.po_number}-invoice` : "unknown"),
          stored_filepath: extractionResult.stored_filepath || "po-flip",
          mime_type: extractionFile?.type || "application/pdf",
          file_size_bytes: extractionFile?.size || 0,
          page_count: extractionResult.page_count,
          status,
          source_type: "supplier",
          line_items: extractionResult.line_items.map((li, idx) => {
            const get = (col) => {
              const k = `${idx}-${col}`;
              return k in lineItemOverrides ? lineItemOverrides[k] : undefined;
            };
            const descOv = get("description");
            const qtyOv  = get("quantity");
            const unitOv = get("unit");
            const rateOv = get("unit_price");
            const amtOv  = get("amount");
            const modified = [descOv, qtyOv, unitOv, rateOv, amtOv].some((v) => v !== undefined);
            return {
              description: descOv !== undefined ? descOv : li.description,
              quantity:    qtyOv  !== undefined ? qtyOv  : li.quantity,
              unit:        unitOv !== undefined ? unitOv : li.unit,
              unit_price:  rateOv !== undefined ? rateOv : li.unit_price,
              amount:      amtOv  !== undefined ? amtOv  : li.amount,
              ai_description: li.description,
              ai_quantity:    li.quantity,
              ai_unit:        li.unit,
              ai_unit_price:  li.unit_price,
              ai_amount:      li.amount,
              description_confidence: li.description_confidence,
              quantity_confidence:    li.quantity_confidence,
              unit_price_confidence:  li.unit_price_confidence,
              amount_confidence:      li.amount_confidence,
              user_modified: modified,
            };
          }),
        };

        const saved = await saveInvoice(payload);
        if (status === "pending_processing" && saved?.id) {
          matchProducts(saved.id).catch(() => {});
        }

        setFlipPO(null);
        setExtractionFile(null);
        setExtractionResult(null);
        setResultsState("extracted");
        setResultsError(null);
        setLineItemOverrides({});
        navigateToHistory();
      } catch (err) {
        setResultsError(err.response?.data?.detail || err.message || "Save failed");
        setResultsState("error");
      }
    },
    [extractionResult, extractionFile, lineItemOverrides, flipPO, navigateToHistory]
  );

  const handleDiscardResults = useCallback(() => {
    setExtractionFile(null);
    setExtractionResult(null);
    setResultsState("extracted");
    setResultsError(null);
    setLineItemOverrides({});
    navigate("/upload");
  }, [navigate]);

  const isNavActive = (path) => {
    const p = location.pathname;
    if (path === "/upload") return p.startsWith("/upload"); // includes /upload/review
    return p === path || p.startsWith(`${path}/`);
  };

  const isReviewScreen = location.pathname === "/upload/review";
  const pageTitle = TITLE_RULES.find((r) => r.test(location.pathname))?.title || "Supplier Portal";

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 h-screen flex flex-col transition-all duration-200 z-50 ${
          sidebarCollapsed ? "w-14" : "w-60"
        }`}
        style={{ backgroundColor: "#0A1628" }}
      >
        {/* Logo */}
        <div className="flex items-center justify-between px-3 h-14 border-b border-white/10">
          <div className="flex items-center gap-2 min-w-0">
            <img src={tmcLogo} alt="TMC" className="w-8 h-8 object-contain flex-shrink-0" />
            {!sidebarCollapsed && (
              <div className="flex flex-col leading-tight min-w-0">
                <span className="text-sm font-bold text-white tracking-wide">TMC</span>
                <span className="text-[10px] text-emerald-400 font-medium">eInvoice Supplier</span>
              </div>
            )}
          </div>
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="text-white/40 hover:text-white cursor-pointer bg-transparent border-none text-sm ml-auto flex-shrink-0"
          >
            {sidebarCollapsed ? "▶" : "◀"}
          </button>
        </div>

        {/* Supplier badge */}
        {!sidebarCollapsed && (
          <div className="mx-3 mt-3 mb-1 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2">
            <span className="text-emerald-400 text-xs">📦</span>
            <span className="text-emerald-300 text-[11px] font-semibold">Supplier Portal</span>
          </div>
        )}

        {/* Nav */}
        <div className="flex-1 py-3 overflow-y-auto">
          {!sidebarCollapsed && (
            <div className="px-4 mb-2 text-[10px] font-semibold text-white/30 uppercase tracking-widest">
              Navigation
            </div>
          )}
          {NAV.map((item) => {
            const active = isNavActive(item.path);
            return (
              <button
                key={item.path}
                onClick={() => {
                  if (item.path === "/invoices") navigateToHistory();
                  else navigate(item.path);
                }}
                className={`w-full flex items-center gap-3 py-2.5 text-xs font-medium cursor-pointer border-none transition-all duration-150 ${
                  sidebarCollapsed ? "justify-center px-0" : "px-4"
                } ${
                  active
                    ? "bg-emerald-500/10 text-emerald-400 border-l-[3px] border-l-emerald-500 font-semibold"
                    : "bg-transparent text-white/50 hover:bg-white/5 hover:text-white border-l-[3px] border-l-transparent"
                }`}
              >
                <span className="text-[15px]">{item.icon}</span>
                {!sidebarCollapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </div>

        {/* Footer */}
        {!sidebarCollapsed && (
          <div className="px-4 py-3 border-t border-white/10 flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-white text-2xs font-bold flex-shrink-0"
              style={{ backgroundColor: "#10B981" }}
            >
              {user?.name?.slice(0, 2).toUpperCase() || "SP"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-2xs font-semibold text-white/80 truncate">{user?.name || "Supplier"}</div>
              <div className="text-2xs text-white/30">Supplier Account</div>
            </div>
            <button
              onClick={onLogout}
              title="Sign out"
              className="text-white/30 hover:text-white/70 bg-transparent border-none cursor-pointer flex-shrink-0 transition-colors"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          </div>
        )}
      </aside>

      {/* Main content */}
      <div className={`flex-1 flex flex-col transition-all duration-200 ${sidebarCollapsed ? "ml-14" : "ml-60"}`}>
        {/* Top bar — hidden on the extraction review screen */}
        {!isReviewScreen && (
          <header className="sticky top-0 z-40 bg-white border-b border-neutral-100 h-14 flex items-center justify-between px-6 shadow-xs">
            <div className="flex items-center gap-3">
              <h1 className="text-lg font-semibold text-neutral-900">{pageTitle}</h1>
              <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-600 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Supplier Portal
              </span>
            </div>
          </header>
        )}

        <main className="flex-1 p-6 bg-neutral-50">
          <Routes>
            <Route
              path="/dashboard"
              element={
                <SupplierDashboard
                  user={user}
                  onUpload={() => navigate("/upload")}
                  onViewInvoice={navigateToDetail}
                />
              }
            />
            <Route
              path="/pos"
              element={<SupplierPOsPage onInvoiceCreated={(invoiceId) => navigateToDetail(invoiceId)} />}
            />
            <Route
              path="/upload"
              element={
                <UploadInvoicePage
                  onExtractionComplete={handleExtractionComplete}
                  onBatchComplete={handleBatchComplete}
                />
              }
            />
            <Route
              path="/upload/review"
              element={
                extractionResult ? (
                  <ExtractionResultsPage
                    extractionResult={extractionResult}
                    file={extractionFile}
                    savedInvoice={null}
                    state={resultsState}
                    error={resultsError}
                    onSave={handleSave}
                    onDiscard={handleDiscardResults}
                    onLineItemOverridesChange={setLineItemOverrides}
                  />
                ) : (
                  // Hard reload loses the in-memory extraction — start over.
                  <Navigate to="/upload" replace />
                )
              }
            />
            <Route
              path="/invoices"
              element={
                <HistoryView
                  onViewInvoice={navigateToDetail}
                  onUpload={() => navigate("/upload")}
                  highlightIds={batchNewIds}
                  uploadErrors={batchErrors}
                />
              }
            />
            <Route path="/invoices/:id" element={<InvoiceDetailRoute user={user} />} />
            <Route
              path="/tracker"
              element={<SupplierNotificationsPage user={user} onViewInvoice={navigateToDetail} />}
            />
            <Route path="/profile" element={<SupplierProfilePage user={user} />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
