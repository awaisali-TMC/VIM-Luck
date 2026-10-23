import KpiCard from "../common/KpiCard";
import { tokens } from "../../styles/tokens";

export default function ExtractionKPIs({ result }) {
  const highConfCount = result.fields.filter((f) => f.confidence >= 95).length;

  return (
    <div className="grid grid-cols-4 gap-4">
      <KpiCard
        label="Overall Confidence"
        value={`${result.overall_confidence}%`}
        sub="Above threshold"
        accentColor={tokens.color.status.success.base}
        icon="&#127919;"
      />
      <KpiCard
        label="Document Type"
        value={result.document_type || "Invoice"}
        sub={`${result.page_count} page${result.page_count !== 1 ? "s" : ""}`}
        accentColor={tokens.color.brand[500]}
        icon="&#128203;"
      />
      <KpiCard
        label="Fields Extracted"
        value={`${result.fields.length}`}
        sub={`${highConfCount} high confidence`}
        accentColor={tokens.color.status.info.base}
        icon="&#128269;"
      />
      <KpiCard
        label="Processing Time"
        value={`${(result.processing_time_ms / 1000).toFixed(1)}s`}
        sub={result.product_match_processing_time_ms
          ? `Match: ${(result.product_match_processing_time_ms / 1000).toFixed(1)}s`
          : undefined
        }
        accentColor={tokens.color.status.posted.base}
        icon="&#9889;"
      />
    </div>
  );
}
