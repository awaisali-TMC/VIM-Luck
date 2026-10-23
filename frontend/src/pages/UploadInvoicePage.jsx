import { useState, useCallback } from "react";
import { uploadInvoice, uploadInvoiceBatch } from "../services/invoiceService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import UploadZone from "../components/upload/UploadZone";

function ProcessingView({ file, fileCount = 1 }) {
  const name = fileCount > 1 ? `${fileCount} files` : (file?.name || "document");
  const size = fileCount > 1 ? "" : file ? `${(file.size / 1024).toFixed(0)} KB` : "";

  return (
    <div className="flex flex-col items-center justify-center py-10 gap-5">
      {/* Animated rings */}
      <div className="relative w-16 h-16">
        <span
          className="absolute inset-0 rounded-full border-2 border-brand-200 opacity-60"
          style={{ animation: "ping 1.8s cubic-bezier(0,0,0.2,1) infinite" }}
        />
        <span
          className="absolute inset-1 rounded-full border-2 border-brand-300 opacity-40"
          style={{ animation: "ping 1.8s cubic-bezier(0,0,0.2,1) infinite 0.4s" }}
        />
        <span className="absolute inset-0 flex items-center justify-center">
          <svg className="w-7 h-7 text-brand-500" style={{ animation: "spin 2s linear infinite" }} viewBox="0 0 24 24" fill="none">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        </span>
      </div>

      {/* Status text */}
      <div className="text-center">
        <div className="text-sm font-semibold text-neutral-800 mb-1">
          Processing
        </div>
        <div className="text-2xs text-neutral-500">
          Extracting fields, line items, and validating data
        </div>
      </div>

      {/* File chip */}
      <div className="flex items-center gap-2 bg-neutral-50 border border-neutral-100 rounded-full px-3 py-1.5">
        <span className="text-xs">&#128196;</span>
        <span className="text-2xs font-medium text-neutral-700">{name}</span>
        {size && <span className="text-2xs text-neutral-400">{size}</span>}
      </div>

      {/* Progress steps */}
      <div className="flex items-center gap-6 mt-1">
        {["Uploading", "Parsing", "Extracting"].map((step, i) => (
          <div key={step} className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full bg-brand-400"
              style={{ animation: `pulse 1.5s ease-in-out infinite ${i * 0.3}s` }}
            />
            <span className="text-[10px] font-medium text-neutral-500 uppercase tracking-wider">
              {step}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Upload-only page. Once extraction completes, calls onExtractionComplete
 * to hand off to the results page.
 *
 * Props:
 *  - onExtractionComplete: (file, extractionResult) => void
 */
/**
 * Props:
 *  - onExtractionComplete(file, result)  single-invoice file -> review screen
 *  - onBatchComplete(result)             multi-file / multi-invoice -> drafts saved server-side
 *  - title                               card title (default "Upload Invoice")
 *                                        upload so drafts the server saves itself (multi-invoice
 *                                        files, batches) carry the lane marker too. Omitted =
 *                                        today's PO flow, unchanged.
 */
export default function UploadInvoicePage({
  onExtractionComplete,
  onBatchComplete,
  title = "Upload Invoice",
}) {
  const [state, setState] = useState("idle"); // idle | extracting | error
  const [file, setFile] = useState(null);
  const [fileCount, setFileCount] = useState(1);
  const [error, setError] = useState(null);

  // Batch results (multiple files, or one file containing several invoices)
  // skip the review screen: drafts are saved server-side. Each portal decides
  // where to go next via onBatchComplete — the internal portal routes to the
  // Invoice Inbox; the supplier portal switches to its history view. Keeping
  // this a callback avoids depending on react-router (the supplier app has no
  // Router, so calling useNavigate here would crash it).
  const goToInbox = useCallback((result) => {
    onBatchComplete?.(result);
  }, [onBatchComplete]);

  const handleFilesSelected = useCallback(
    async (selectedFiles) => {
      const files = Array.isArray(selectedFiles) ? selectedFiles : [selectedFiles];
      setFile(files[0]);
      setFileCount(files.length);
      setState("extracting");
      setError(null);

      try {
        if (files.length === 1) {
          const result = await uploadInvoice(files[0]);
          if (result?.batch) {
            // One file, several invoices — split & saved as drafts server-side.
            goToInbox(result);
          } else {
            onExtractionComplete?.(files[0], result);
          }
        } else {
          const result = await uploadInvoiceBatch(files);
          if ((result.invoices || []).length === 0) {
            const msgs = (result.errors || []).map((e) => `${e.file}: ${e.error}`).join("; ");
            throw new Error(msgs || "No invoices could be processed.");
          }
          goToInbox(result);
        }
      } catch (err) {
        const message =
          err.response?.data?.detail || err.message || "Upload failed";
        setError(typeof message === "string" ? message : JSON.stringify(message));
        setState("error");
      }
    },
    [onExtractionComplete, goToInbox]
  );

  const handleReset = useCallback(() => {
    setFile(null);
    setError(null);
    setState("idle");
  }, []);

  return (
    <div>
      <Card
        title={title}
        action={
          state === "idle" ? (
            <Badge status="info" label="Supported: PDF, JPEG, PNG, TIFF" size="xs" />
          ) : state === "extracting" ? (
            <Badge status="pending" label="Processing..." size="xs" />
          ) : null
        }
      >
        {state === "idle" && (
          <UploadZone onFilesSelected={handleFilesSelected} />
        )}

        {state === "extracting" && (
          <ProcessingView file={file} fileCount={fileCount} />
        )}

        {state === "error" && (
          <div className="py-6 flex flex-col items-center gap-4">
            <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-500" viewBox="0 0 24 24" fill="none">
                <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <div className="text-center">
              <div className="text-sm font-semibold text-neutral-800 mb-1">
                Processing Failed
              </div>
              <div className="text-2xs text-neutral-500 max-w-sm">
                {error}
              </div>
            </div>
            <Button variant="secondary" size="sm" onClick={handleReset}>
              Try Again
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
