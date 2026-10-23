import { useState, useEffect, useCallback, useRef } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import Badge from "../common/Badge";
import {
  getAttachments,
  uploadAttachment,
  deleteAttachment,
  getDownloadUrl,
} from "../../services/attachmentService";

/* ── Helpers ───────────────────────────────────────────────────────────────── */

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

const FILE_ICONS = {
  "application/pdf": { icon: "📄", color: "text-red-500" },
  "image/jpeg": { icon: "🖼", color: "text-blue-500" },
  "image/png": { icon: "🖼", color: "text-blue-500" },
  "image/tiff": { icon: "🖼", color: "text-blue-500" },
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": { icon: "📝", color: "text-blue-700" },
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": { icon: "📊", color: "text-green-600" },
};

function fileIcon(contentType) {
  return FILE_ICONS[contentType] || { icon: "📎", color: "text-neutral-500" };
}

const DOC_TYPES = [
  { value: "work_order", label: "Work Order" },
  { value: "scan", label: "Scanned Document" },
  { value: "payment_proof", label: "Payment Proof" },
  { value: "goods_receipt", label: "Goods Receipt" },
  { value: "contract", label: "Contract" },
  { value: "other", label: "Other" },
];

const DOC_TYPE_LABEL = Object.fromEntries(DOC_TYPES.map((d) => [d.value, d.label]));

const DOC_TYPE_VARIANT = {
  work_order: "info",
  scan: "neutral",
  payment_proof: "success",
  goods_receipt: "warning",
  contract: "purple",
  other: "neutral",
};

/* ── Component ─────────────────────────────────────────────────────────────── */

export default function AttachmentsCard({ invoiceId, currentUser }) {
  const [attachments, setAttachments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [docType, setDocType] = useState("other");
  const [showUpload, setShowUpload] = useState(false);
  const fileInputRef = useRef(null);

  const fetchAttachments = useCallback(async () => {
    if (!invoiceId) return;
    setLoading(true);
    try {
      const data = await getAttachments(invoiceId);
      setAttachments(data || []);
    } catch {
      setAttachments([]);
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    fetchAttachments();
  }, [fetchAttachments]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadAttachment(
        invoiceId,
        file,
        docType,
        "",
        currentUser?.name || "",
        currentUser?.role || "",
      );
      fetchAttachments();
      setShowUpload(false);
      setDocType("other");
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteAttachment(id);
      fetchAttachments();
    } catch {
      /* ignore */
    }
  };

  const handleDownload = (att) => {
    const url = getDownloadUrl(att.id);
    window.open(url, "_blank");
  };

  return (
    <Card>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-neutral-900 m-0">
            Supporting Documents
          </h3>
          {attachments.length > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-100 text-brand-700 text-2xs font-bold">
              {attachments.length}
            </span>
          )}
        </div>
        <Button
          size="xs"
          variant={showUpload ? "ghost" : "primary"}
          onClick={() => setShowUpload(!showUpload)}
        >
          {showUpload ? "Cancel" : "+ Attach File"}
        </Button>
      </div>

      {/* Upload area */}
      {showUpload && (
        <div className="border border-dashed border-brand-300 bg-brand-50/40 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="text-xs border border-neutral-200 rounded px-2 py-1.5 bg-white focus:border-brand-400 outline-none"
            >
              {DOC_TYPES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>

            <label className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-xs font-medium rounded cursor-pointer hover:bg-brand-700 transition-colors">
              {uploading ? (
                "Uploading..."
              ) : (
                <>
                  <span>Browse Files</span>
                </>
              )}
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.docx,.xlsx,.doc,.xls"
                onChange={handleUpload}
                disabled={uploading}
              />
            </label>

            <span className="text-2xs text-neutral-400">
              PDF, JPEG, PNG, TIFF, DOCX, XLSX &middot; Max 20MB
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="text-2xs text-danger-dark bg-danger-light/30 rounded px-2 py-1 mb-2">
          {error}
        </div>
      )}

      {/* Attachment list */}
      {loading ? (
        <div className="text-center py-4 text-2xs text-neutral-400">
          Loading...
        </div>
      ) : attachments.length === 0 ? (
        <div className="text-center py-6 text-2xs text-neutral-400">
          <span className="text-lg block mb-1">📎</span>
          No documents attached yet
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {attachments.map((att) => {
            const fi = fileIcon(att.content_type);
            return (
              <div
                key={att.id}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-neutral-100 bg-neutral-50/50 hover:border-neutral-200 transition-colors group"
              >
                {/* Icon */}
                <span className={`text-lg flex-shrink-0 ${fi.color}`}>
                  {fi.icon}
                </span>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className="text-xs font-medium text-neutral-800 truncate cursor-pointer hover:text-brand-600 hover:underline"
                      onClick={() => handleDownload(att)}
                      title={att.filename}
                    >
                      {att.filename}
                    </span>
                    <Badge variant={DOC_TYPE_VARIANT[att.document_type] || "neutral"} size="xs">
                      {DOC_TYPE_LABEL[att.document_type] || att.document_type}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-2xs text-neutral-400">
                    <span>{formatBytes(att.file_size)}</span>
                    <span>&middot;</span>
                    {att.uploaded_by && (
                      <>
                        <span>{att.uploaded_by}</span>
                        <span>&middot;</span>
                      </>
                    )}
                    <span>{timeAgo(att.created_at)}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                  <button
                    onClick={() => handleDownload(att)}
                    className="text-2xs text-brand-600 hover:text-brand-800 bg-transparent border-none cursor-pointer px-1.5 py-0.5 rounded hover:bg-brand-50"
                    title="Download"
                  >
                    Download
                  </button>
                  {(currentUser?.role === "admin" || currentUser?.name === att.uploaded_by) && (
                    <button
                      onClick={() => handleDelete(att.id)}
                      className="text-2xs text-neutral-400 hover:text-danger-base bg-transparent border-none cursor-pointer px-1.5 py-0.5 rounded hover:bg-red-50"
                      title="Delete"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
