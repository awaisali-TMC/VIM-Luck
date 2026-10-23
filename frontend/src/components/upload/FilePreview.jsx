import Badge from "../common/Badge";
import Button from "../common/Button";
import WarningsBanner from "./WarningsBanner";

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FilePreview({ file, status, pageCount, onRemove, warnings }) {
  const badgeStatus = status === "extracting" ? "extracting" : "validated";
  const badgeLabel = status === "extracting" ? "Extracting..." : "Extraction Complete";

  return (
    <div>
      <div className="flex items-center gap-4 py-3">
        <div className="w-11 h-11 rounded-base bg-danger-bg flex items-center justify-center text-xl">
          &#128196;
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-xs text-neutral-900 truncate">{file.name}</div>
          <div className="text-2xs text-neutral-500">
            {formatFileSize(file.size)}
            {pageCount ? ` \u00B7 ${pageCount} pages detected` : ""}
          </div>
        </div>
        <Badge status={badgeStatus} label={badgeLabel} />
        <Button variant="secondary" size="xs" onClick={onRemove}>
          Remove
        </Button>
      </div>

      {/* Inline warnings — compact pill that expands on click */}
      {status !== "extracting" && (
        <WarningsBanner warnings={warnings} />
      )}
    </div>
  );
}
