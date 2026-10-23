import { useState, useEffect, useCallback } from "react";
import {
  fetchEmailsFromServer,
  listEmails,
  getEmail,
  processAttachment,
  getInboxConfig,
} from "../services/emailService";
import KpiCard from "../components/common/KpiCard";
import Modal from "../components/common/Modal";
import Button from "../components/common/Button";

/* ── Status badge ──────────────────────────────────────────────────────────── */
const EMAIL_STATUS_MAP = {
  unread:    { label: "Unread",    color: "#4F62F2", bg: "#EEF0FE", border: "#C7CDFC" },
  read:      { label: "Read",      color: "#6B7590", bg: "#F5F6F8", border: "#D5D9E2" },
  processed: { label: "Processed", color: "#10B981", bg: "#ECFDF5", border: "#A7F3D0" },
};

function EmailStatusChip({ status }) {
  const cfg = EMAIL_STATUS_MAP[status] || EMAIL_STATUS_MAP.read;
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

/* ── File type badge ───────────────────────────────────────────────────────── */
const MIME_LABELS = {
  "application/pdf": { label: "PDF", color: "#EF4444", bg: "#FEF2F2" },
  "image/jpeg":      { label: "JPG", color: "#F59E0B", bg: "#FFFBEB" },
  "image/png":       { label: "PNG", color: "#3B82F6", bg: "#EFF6FF" },
  "image/tiff":      { label: "TIF", color: "#8B5CF6", bg: "#F5F3FF" },
};

function MimeChip({ contentType }) {
  const cfg = MIME_LABELS[contentType] || { label: "FILE", color: "#6B7590", bg: "#F5F6F8" };
  return (
    <span style={{
      backgroundColor: cfg.bg, color: cfg.color,
      fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 4,
    }}>
      {cfg.label}
    </span>
  );
}

/* ── Format file size ──────────────────────────────────────────────────────── */
function fmtSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/* ── Format date ───────────────────────────────────────────────────────────── */
function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/* ── View Email Modal ──────────────────────────────────────────────────────── */
function ViewEmailModal({ emailId, onClose, onProcessAttachment }) {
  const [emailData, setEmailData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!emailId) return;
    setLoading(true);
    setError("");
    getEmail(emailId)
      .then(setEmailData)
      .catch(() => setError("Failed to load email."))
      .finally(() => setLoading(false));
  }, [emailId]);

  const handleProcess = async (att) => {
    if (att.processed) return;
    setProcessingId(att.id);
    setError("");
    try {
      const result = await processAttachment(att.id);
      // Pass from_address so the save payload can tag the invoice as email-sourced
      onProcessAttachment(att.filename, att.file_size, result, att.id, emailData?.from_address || "");
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || "Processing failed. Please try again.");
      setProcessingId(null);
    }
  };

  return (
    <Modal
      open={!!emailId}
      onClose={onClose}
      title="Email Details"
      width={640}
    >
      {loading && (
        <div className="flex items-center justify-center py-12 text-neutral-400 text-sm">
          Loading email…
        </div>
      )}

      {!loading && error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-3 text-xs text-danger-dark">
          {error}
        </div>
      )}

      {!loading && emailData && (
        <div className="flex flex-col gap-4">
          {/* Header metadata */}
          <div className="bg-neutral-25 rounded-base px-4 py-3 flex flex-col gap-1.5">
            <div className="flex items-start gap-2">
              <span className="text-2xs text-neutral-500 w-14 flex-shrink-0 pt-0.5">From</span>
              <span className="text-xs text-neutral-800 font-medium break-all">{emailData.from_address || "—"}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-2xs text-neutral-500 w-14 flex-shrink-0 pt-0.5">Subject</span>
              <span className="text-xs text-neutral-800 font-semibold">{emailData.subject || "(no subject)"}</span>
            </div>
            <div className="flex items-start gap-2">
              <span className="text-2xs text-neutral-500 w-14 flex-shrink-0 pt-0.5">Received</span>
              <span className="text-xs text-neutral-600">{fmtDate(emailData.received_at)}</span>
            </div>
          </div>

          {/* Body */}
          {emailData.body_text && (
            <div>
              <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-1.5">
                Message
              </div>
              <div
                className="text-xs text-neutral-700 leading-relaxed bg-neutral-25 rounded-base px-4 py-3 max-h-40 overflow-y-auto whitespace-pre-wrap break-words"
                style={{ fontFamily: "inherit" }}
              >
                {emailData.body_text}
              </div>
            </div>
          )}

          {/* Attachments */}
          {emailData.attachments && emailData.attachments.length > 0 && (
            <div>
              <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-2">
                Attachments ({emailData.attachments.length})
              </div>
              <div className="flex flex-col gap-2">
                {emailData.attachments.map((att) => (
                  <div
                    key={att.id}
                    className="flex items-center justify-between bg-neutral-0 border border-neutral-100 rounded-base px-3 py-2.5"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <MimeChip contentType={att.content_type} />
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-neutral-800 truncate max-w-72">
                          {att.filename}
                        </div>
                        <div className="text-2xs text-neutral-500">{fmtSize(att.file_size)}</div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      {att.processed ? (
                        <span className="text-2xs text-success-dark font-medium">
                          ✓ Processed {att.invoice_id ? `(#${att.invoice_id})` : ""}
                        </span>
                      ) : (
                        <Button
                          variant="primary"
                          size="xs"
                          onClick={() => handleProcess(att)}
                          disabled={processingId === att.id}
                        >
                          {processingId === att.id ? "Processing…" : "Process as Invoice"}
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {emailData.attachments && emailData.attachments.length === 0 && (
            <div className="text-xs text-neutral-400 text-center py-4">
              No invoice attachments found in this email.
            </div>
          )}

          {/* Processing error */}
          {error && (
            <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 text-xs text-danger-dark">
              {error}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────────────── */
export default function AdminEmailInboxPage({ onEmailExtractionComplete }) {
  const [emails, setEmails] = useState([]);
  const [stats, setStats] = useState({ total: 0, unread: 0, with_attachments: 0, processed: 0 });
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [search, setSearch] = useState("");
  const [viewEmailId, setViewEmailId] = useState(null);
  const [gmailConfig, setGmailConfig] = useState(null);

  const loadEmails = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listEmails(0, 100);
      setEmails(data.emails || []);
      setStats(data.stats || { total: 0, unread: 0, with_attachments: 0, processed: 0 });
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load emails.");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleFetch = useCallback(async () => {
    setFetching(true);
    setFetchResult(null);
    setError("");
    try {
      const result = await fetchEmailsFromServer();
      setFetchResult(result);
      await loadEmails();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to fetch emails from Gmail.");
    } finally {
      setFetching(false);
    }
  }, [loadEmails]);

  // Auto-fetch emails + load Gmail config on mount
  useEffect(() => {
    handleFetch();
    getInboxConfig().then(setGmailConfig).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Filter logic
  const filteredEmails = emails.filter((e) => {
    const matchesTab =
      activeTab === "all" ||
      (activeTab === "unread" && e.status === "unread") ||
      (activeTab === "attachments" && e.has_attachments) ||
      (activeTab === "processed" && e.status === "processed");

    if (!matchesTab) return false;

    if (search.trim()) {
      const q = search.toLowerCase();
      return (
        (e.from_address || "").toLowerCase().includes(q) ||
        (e.subject || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const tabs = [
    { key: "all",         label: `All (${stats.total})` },
    { key: "unread",      label: `Unread (${stats.unread})` },
    { key: "attachments", label: `Has Attachments (${stats.with_attachments})` },
    { key: "processed",   label: `Processed (${stats.processed})` },
  ];

  const handleProcessAttachment = useCallback(
    (filename, fileSize, result, attachmentId, fromAddress) => {
      onEmailExtractionComplete(filename, fileSize, result, attachmentId, fromAddress);
    },
    [onEmailExtractionComplete]
  );

  return (
    <div className="flex flex-col gap-6">
      {/* Gmail Account Banner */}
      <div className="flex items-center gap-3 bg-neutral-0 border border-neutral-100 rounded-lg px-5 py-3 shadow-xs">
        <span className="text-lg">📬</span>
        <div className="flex-1 min-w-0">
          <div className="text-2xs font-semibold text-neutral-500 uppercase tracking-wider mb-0.5">
            Monitoring Gmail Account
          </div>
          {gmailConfig?.gmail_address ? (
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-neutral-800">{gmailConfig.gmail_address}</span>
              {gmailConfig.configured ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, backgroundColor: "#ECFDF5", border: "1px solid #A7F3D0", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 600, color: "#10B981" }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "#10B981" }} />
                  Connected
                </span>
              ) : (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 600, color: "#EF4444" }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "#EF4444" }} />
                  Not Configured
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs text-neutral-400">
              Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env to connect
            </span>
          )}
        </div>
        <div className="text-2xs text-neutral-400">
          Fetches UNSEEN emails via IMAP · PDF &amp; image attachments only
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="Total Emails" value={stats.total} icon="📬" accentColor="#4F62F2" />
        <KpiCard label="Unread" value={stats.unread} icon="🔵" accentColor="#4F62F2" />
        <KpiCard label="With Attachments" value={stats.with_attachments} icon="📎" accentColor="#F59E0B" />
        <KpiCard label="Processed" value={stats.processed} icon="✅" accentColor="#10B981" />
      </div>

      {/* Main Card */}
      <div className="bg-neutral-0 border border-neutral-100 rounded-lg shadow-xs">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-neutral-800">Email Invoice Inbox</h2>
            {fetchResult && (
              <span className="text-2xs text-success-dark bg-success-bg border border-success-light rounded px-2 py-0.5">
                +{fetchResult.saved} new · {fetchResult.skipped} skipped
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Search by sender or subject…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="text-xs bg-neutral-50 border border-neutral-200 rounded-base px-3 py-1.5 w-56 outline-none focus:border-brand-400 transition-colors"
            />
            <Button
              variant="primary"
              size="sm"
              onClick={handleFetch}
              disabled={fetching}
            >
              {fetching ? (
                <span className="flex items-center gap-1.5">
                  <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" strokeOpacity="0.25" />
                    <path d="M21 12a9 9 0 00-9-9" />
                  </svg>
                  Fetching…
                </span>
              ) : "↻ Refresh"}
            </Button>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1 px-5 py-3 border-b border-neutral-100">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1.5 text-2xs font-semibold rounded-base border transition-all cursor-pointer ${
                activeTab === tab.key
                  ? "bg-brand-50 text-brand-700 border-brand-200"
                  : "bg-transparent text-neutral-500 border-transparent hover:bg-neutral-50 hover:text-neutral-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mx-5 mt-4 bg-danger-bg border border-danger-base rounded-base px-4 py-2.5 text-xs text-danger-dark">
            {error}
          </div>
        )}

        {/* Email Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-neutral-25 border-b border-neutral-100">
                <th className="text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-5 py-3">From</th>
                <th className="text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-3 py-3">Subject</th>
                <th className="text-left text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-3 py-3">Received</th>
                <th className="text-center text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-3 py-3">Attachments</th>
                <th className="text-center text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-3 py-3">Status</th>
                <th className="text-right text-2xs font-semibold text-neutral-500 uppercase tracking-wider px-5 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-neutral-400 text-xs">
                    Loading emails…
                  </td>
                </tr>
              )}

              {!loading && filteredEmails.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center">
                    <div className="text-3xl mb-2">📬</div>
                    <div className="text-sm font-medium text-neutral-600 mb-1">No emails found</div>
                    <div className="text-xs text-neutral-400">
                      {emails.length === 0
                        ? "Click Refresh to fetch emails from Gmail."
                        : "No emails match the current filter."}
                    </div>
                  </td>
                </tr>
              )}

              {!loading && filteredEmails.map((msg, idx) => (
                <tr
                  key={msg.id}
                  className={`border-b border-neutral-50 hover:bg-neutral-25 transition-colors cursor-pointer ${
                    idx % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"
                  } ${msg.status === "unread" ? "font-semibold" : ""}`}
                  onClick={() => setViewEmailId(msg.id)}
                >
                  <td className="px-5 py-3 text-neutral-800 max-w-[180px]">
                    <div className="truncate">{msg.from_address || "—"}</div>
                  </td>
                  <td className="px-3 py-3 text-neutral-700 max-w-[260px]">
                    <div className="truncate">{msg.subject || "(no subject)"}</div>
                  </td>
                  <td className="px-3 py-3 text-neutral-500 whitespace-nowrap">
                    {fmtDate(msg.received_at)}
                  </td>
                  <td className="px-3 py-3 text-center">
                    {msg.has_attachments ? (
                      <div className="flex items-center justify-center gap-1">
                        <span className="text-neutral-400">📎</span>
                        <span className="text-neutral-600 font-medium">
                          {msg.attachments?.length || 0}
                        </span>
                      </div>
                    ) : (
                      <span className="text-neutral-300">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-center">
                    <EmailStatusChip status={msg.status} />
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); setViewEmailId(msg.id); }}
                      className="text-brand-600 hover:text-brand-700 text-2xs font-semibold bg-transparent border-none cursor-pointer transition-colors"
                    >
                      Open →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* View Email Modal */}
      <ViewEmailModal
        emailId={viewEmailId}
        onClose={() => { setViewEmailId(null); loadEmails(); }}
        onProcessAttachment={handleProcessAttachment}
      />
    </div>
  );
}
