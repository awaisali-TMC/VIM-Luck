import { useState, useCallback } from "react";
import { uploadPurchaseOrder } from "../services/purchaseOrderService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import { useDropzone } from "react-dropzone";

const ACCEPTED_TYPES = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/tiff": [".tiff", ".tif"],
};

function POUploadZone({ onFileSelected }) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED_TYPES,
    maxFiles: 1,
    maxSize: 20 * 1024 * 1024,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        onFileSelected(acceptedFiles[0]);
      }
    },
  });

  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-lg py-12 px-6 text-center cursor-pointer
        transition-all duration-200
        ${isDragActive
          ? "border-brand-500 bg-brand-50"
          : "border-neutral-200 bg-neutral-25 hover:border-brand-300 hover:bg-brand-50/30"
        }
      `}
    >
      <input {...getInputProps()} />
      <div className="text-[40px] mb-3">&#128230;</div>
      <div className="text-sm font-semibold text-neutral-800 mb-1">
        Drag & drop purchase order files here
      </div>
      <div className="text-xs text-neutral-500 mb-4">
        or click to browse from your computer
      </div>
      <Button size="sm">Browse Files</Button>
      <div className="text-2xs text-neutral-400 mt-3">
        Supported: PDF, JPEG, PNG, TIFF &middot; Max 20MB
      </div>
    </div>
  );
}

function ProcessingView({ file }) {
  const name = file?.name || "document";
  const size = file ? `${(file.size / 1024).toFixed(0)} KB` : "";

  return (
    <div className="flex flex-col items-center justify-center py-10 gap-5">
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

      <div className="text-center">
        <div className="text-sm font-semibold text-neutral-800 mb-1">
          Processing
        </div>
        <div className="text-2xs text-neutral-500">
          Extracting PO number, vendor, line items, and amounts
        </div>
      </div>

      <div className="flex items-center gap-2 bg-neutral-50 border border-neutral-100 rounded-full px-3 py-1.5">
        <span className="text-xs">&#128230;</span>
        <span className="text-2xs font-medium text-neutral-700">{name}</span>
        {size && <span className="text-2xs text-neutral-400">{size}</span>}
      </div>

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

export default function POCreatePage({ onCreated, onCancel }) {
  const [state, setState] = useState("idle"); // idle | extracting | error
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelected = useCallback(
    async (selectedFile) => {
      setFile(selectedFile);
      setState("extracting");
      setError(null);

      try {
        const created = await uploadPurchaseOrder(selectedFile);
        onCreated?.(created.id);
      } catch (err) {
        const message =
          err.response?.data?.detail || err.message || "Upload failed";
        setError(message);
        setState("error");
      }
    },
    [onCreated]
  );

  const handleReset = useCallback(() => {
    setFile(null);
    setError(null);
    setState("idle");
  }, []);

  return (
    <div>
      <Card
        title="Upload Purchase Order"
        action={
          state === "idle" ? (
            <Badge status="info" label="Supported: PDF, JPEG, PNG, TIFF" size="xs" />
          ) : state === "extracting" ? (
            <Badge status="pending" label="Processing..." size="xs" />
          ) : null
        }
      >
        {state === "idle" && (
          <POUploadZone onFileSelected={handleFileSelected} />
        )}

        {state === "extracting" && (
          <ProcessingView file={file} />
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

      {/* Manual PO entry — commented out for now */}
      {/* <ManualPOEntry onCreated={onCreated} onCancel={onCancel} /> */}
    </div>
  );
}
