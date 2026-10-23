import { useRef } from "react";
import { useDropzone } from "react-dropzone";
import Button from "../common/Button";

const ACCEPTED_TYPES = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/tiff": [".tiff", ".tif"],
};

export default function UploadZone({ onFilesSelected }) {
  const cameraInputRef = useRef(null);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTED_TYPES,
    maxSize: 20 * 1024 * 1024, // 20MB per file
    multiple: true,
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        onFilesSelected(acceptedFiles);
      }
    },
  });

  const handleCameraCapture = (e) => {
    const captured = e.target.files?.[0];
    if (captured) onFilesSelected([captured]);
    e.target.value = ""; // allow re-capturing the same shot
  };

  return (
    <div>
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
        <div className="text-[40px] mb-3">&#128196;</div>
        <div className="text-sm font-semibold text-neutral-800 mb-1">
          Drag & drop invoice files here
        </div>
        <div className="text-xs text-neutral-500 mb-4">
          or click to browse — you can select multiple files at once
        </div>
        <Button size="sm">Browse Files</Button>
        <div className="text-2xs text-neutral-400 mt-3">
          Supported: PDF, JPEG, PNG, TIFF &middot; Max 20MB each &middot; multiple invoices in one PDF are split automatically
        </div>
      </div>

      {/* Mobile scan — capture="environment" opens the rear camera on phones */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleCameraCapture}
      />
      <div className="flex items-center justify-center mt-3">
        <button
          type="button"
          onClick={() => cameraInputRef.current?.click()}
          className="flex items-center gap-2 text-xs font-semibold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100 border border-brand-100 rounded-full px-4 py-2 cursor-pointer transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
          Scan with camera
        </button>
      </div>
    </div>
  );
}
