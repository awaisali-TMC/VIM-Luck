import { useState, useMemo, useEffect, Fragment } from "react";

/**
 * Full-screen Document AI raw output viewer.
 *
 * Two tabs: FIELDS · OCR
 *
 * Data contract — `data.raw_document_ai` should contain:
 *   { text, entities[], pages[] }
 */

/* ------------------------------------------------------------------ */
/*  Confidence helpers                                                 */
/* ------------------------------------------------------------------ */

const CONF_COLORS = {
  high:   { fg: "#059669", bg: "#d1fae5" },   // emerald
  medium: { fg: "#d97706", bg: "#fef3c7" },   // amber
  low:    { fg: "#dc2626", bg: "#fee2e2" },    // red
};

function confTier(c) {
  if (c == null) return null;
  const pct = c <= 1 ? c : c / 100;
  if (pct >= 0.85) return "high";
  if (pct >= 0.60) return "medium";
  return "low";
}

function ConfPill({ value }) {
  if (value == null) return null;
  const pct = (value <= 1 ? value * 100 : value);
  const tier = confTier(value);
  const c = CONF_COLORS[tier];
  return (
    <span
      className="inline-block text-[10px] font-mono font-medium px-1.5 py-0.5 rounded"
      style={{ color: c.fg, backgroundColor: c.bg }}
    >
      {pct.toFixed(1)}%
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Tab definitions                                                    */
/* ------------------------------------------------------------------ */

const TABS = [
  { key: "fields",  label: "FIELDS" },
  { key: "ocr",     label: "OCR" },
];

/* ================================================================== */
/*  Main component                                                     */
/* ================================================================== */

export default function RawOutputViewer({ open, onClose, data }) {
  const [activeTab, setActiveTab] = useState("fields");

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const raw = data?.raw_document_ai;
  const fullText = raw?.text || "";

  /* Aggregate page-level OCR stats */
  const ocrStats = useMemo(() => {
    if (!raw?.pages) return { chars: 0, blocks: 0, paragraphs: 0, lines: 0, tokens: 0, pages: 0 };

    let blocks = 0, paragraphs = 0, lines = 0, tokens = 0;
    for (const pg of raw.pages) {
      blocks     += pg.block_count || 0;
      paragraphs += pg.paragraph_count || 0;
      lines      += pg.line_count || 0;
      tokens     += pg.token_count || 0;
    }

    return { chars: fullText.length, blocks, paragraphs, lines, tokens, pages: raw.pages.length };
  }, [raw, fullText]);

  if (!open) return null;

  const noRaw = !raw;

  return (
    <div className="fixed inset-0 z-[999] flex flex-col bg-white" style={{ fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* ================ TOP BAR ================ */}
      <div className="flex items-center justify-between px-6 h-14 border-b border-neutral-200 flex-shrink-0">
        <div className="flex items-center gap-3">
          {/* icon */}
          <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-200 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4F62F2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-semibold text-neutral-900 leading-none">
              Document AI — Raw Output
            </h1>
            <p className="text-[11px] text-neutral-400 mt-0.5 flex items-center gap-1.5 flex-wrap">
              <span>{data.original_filename}</span>
              <span className="text-neutral-300">|</span>
              <span>{data.processing_time_ms} ms</span>
              <span className="text-neutral-300">|</span>
              <span>{data.page_count} page{data.page_count !== 1 ? "s" : ""}</span>
              {!noRaw && (
                <>
                  <span className="text-neutral-300">|</span>
                  <span>{fullText.length.toLocaleString()} chars</span>
                </>
              )}
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="h-8 px-3 text-xs font-medium text-neutral-500 bg-neutral-100 hover:bg-neutral-200
                     rounded-md border-none cursor-pointer transition-colors flex items-center gap-1.5"
          title="Close (Esc)"
        >
          ✕ Close
        </button>
      </div>

      {/* ================ TAB BAR ================ */}
      <div className="flex items-end gap-0 px-6 bg-neutral-50 border-b border-neutral-200 flex-shrink-0">
        {TABS.map((t) => {
          const active = activeTab === t.key;
          let badge = null;
          if (t.key === "fields")  badge = raw?.entities?.length ?? null;

          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className="relative px-4 pb-2.5 pt-3 text-[11px] font-semibold tracking-wider border-none
                         cursor-pointer transition-colors bg-transparent flex items-center gap-1.5"
              style={{ color: active ? "#4F62F2" : "#9ca3af" }}
            >
              {t.label}
              {badge != null && (
                <span
                  className="text-[9px] font-semibold px-1.5 py-px rounded-full"
                  style={{
                    backgroundColor: active ? "#EEF0FF" : "#f3f4f6",
                    color: active ? "#4F62F2" : "#9ca3af",
                  }}
                >
                  {badge}
                </span>
              )}
              {active && (
                <span className="absolute bottom-0 inset-x-0 h-[2px] rounded-t" style={{ backgroundColor: "#4F62F2" }} />
              )}
            </button>
          );
        })}
      </div>

      {/* ================ CONTENT ================ */}
      <main className="flex-1 overflow-y-auto bg-neutral-50/50">
        {noRaw ? (
          <EmptyState
            title="Raw output unavailable"
            description="The backend didn't return raw Document AI data. Make sure you've restarted the backend with the latest code, then re-upload."
          />
        ) : (
          <>
            {activeTab === "fields"  && <FieldsPanel entities={raw.entities || []} data={data} />}
            {activeTab === "ocr"     && <OcrPanel fullText={fullText} stats={ocrStats} pages={raw.pages || []} />}
          </>
        )}
      </main>
    </div>
  );
}

/* ================================================================== */
/*  FIELDS tab                                                         */
/* ================================================================== */

function FieldsPanel({ entities, data }) {
  // Separate top-level fields from line_items (which have properties)
  const topLevel = entities.filter((e) => e.type !== "line_item");
  const lineItems = entities.filter((e) => e.type === "line_item");

  return (
    <div className="max-w-6xl mx-auto px-6 py-5 space-y-6">
      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-3">
        <Metric label="Document Type" value={data.document_type || "—"} />
        <Metric label="Overall Confidence" value={`${data.overall_confidence}%`} />
        <Metric label="Entity Fields" value={topLevel.length} />
        <Metric label="Line Items" value={lineItems.length} />
      </div>

      {/* Top-level entity fields */}
      {topLevel.length > 0 && (
        <TableCard title="Entity Fields" count={topLevel.length}>
          <thead>
            <Thead cells={["Type", "Mention Text", "Normalized Value", "Confidence"]} />
          </thead>
          <tbody>
            {topLevel.map((e, i) => (
              <tr key={i} className={rowBg(i)}>
                <Td mono>{e.type}</Td>
                <Td>{e.mention_text || "—"}</Td>
                <Td muted>{e.normalized_value || "—"}</Td>
                <TdRight><ConfPill value={e.confidence} /></TdRight>
              </tr>
            ))}
          </tbody>
        </TableCard>
      )}

      {/* Line items with nested properties */}
      {lineItems.length > 0 && (
        <TableCard title="Line Items (with sub-fields)" count={lineItems.length}>
          <thead>
            <Thead cells={["Type / Sub-field", "Mention Text", "Normalized Value", "Confidence"]} />
          </thead>
          <tbody>
            {lineItems.map((e, i) => (
              <Fragment key={i}>
                <tr className="bg-neutral-100/60 border-t border-neutral-200">
                  <Td mono bold>line_item #{i + 1}</Td>
                  <Td className="text-neutral-500 text-[11px] italic">{(e.mention_text || "").slice(0, 80)}{(e.mention_text || "").length > 80 ? "…" : ""}</Td>
                  <Td muted>{e.normalized_value || "—"}</Td>
                  <TdRight><ConfPill value={e.confidence} /></TdRight>
                </tr>
                {(e.properties || []).map((p, j) => (
                  <tr key={j} className={rowBg(j)}>
                    <Td mono className="pl-8 text-neutral-400">↳ {p.type}</Td>
                    <Td>{p.mention_text || "—"}</Td>
                    <Td muted>{p.normalized_value || "—"}</Td>
                    <TdRight><ConfPill value={p.confidence} /></TdRight>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </TableCard>
      )}

      {/* Warnings */}
      {data.warnings?.length > 0 && (
        <div>
          <SectionLabel text="Warnings" count={data.warnings.length} />
          <div className="space-y-1">
            {data.warnings.map((w, i) => (
              <div key={i} className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                {w}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================== */
/*  OCR tab                                                            */
/* ================================================================== */

function OcrPanel({ fullText, stats, pages }) {
  const [copied, setCopied] = useState(false);
  const [showLines, setShowLines] = useState(false);

  const copy = () => { navigator.clipboard.writeText(fullText); setCopied(true); setTimeout(() => setCopied(false), 2000); };

  if (!fullText) {
    return <EmptyState title="No OCR text" description="Document AI didn't return any extracted text for this document." />;
  }

  // Collect all lines across all pages
  const allLines = pages.flatMap((pg) => (pg.lines || []).map((l, i) => ({ page: pg.page_number || 1, idx: i + 1, text: l })));

  return (
    <div className="max-w-6xl mx-auto px-6 py-5 space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3">
        <Metric label="Pages" value={stats.pages} />
        <Metric label="Characters" value={stats.chars.toLocaleString()} />
        <Metric label="Blocks" value={stats.blocks} />
        <Metric label="Paragraphs" value={stats.paragraphs} />
        <Metric label="Lines" value={stats.lines} />
      </div>

      {/* Full text */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <SectionLabel text="Full Document Text" />
          <div className="flex items-center gap-2">
            {allLines.length > 0 && (
              <button
                onClick={() => setShowLines(!showLines)}
                className="h-7 px-2.5 text-[11px] font-medium rounded border cursor-pointer transition-colors
                           bg-white border-neutral-200 text-neutral-500 hover:bg-neutral-50"
              >
                {showLines ? "Show raw text" : "Show by lines"}
              </button>
            )}
            <button
              onClick={copy}
              className="h-7 px-2.5 text-[11px] font-medium rounded border cursor-pointer transition-colors
                         bg-white border-neutral-200 text-neutral-600 hover:bg-neutral-50"
            >
              {copied ? "✓ Copied" : "Copy"}
            </button>
          </div>
        </div>

        {showLines ? (
          <div className="border border-neutral-200 rounded-lg overflow-hidden bg-white">
            <table className="w-full text-xs">
              <thead>
                <Thead cells={["#", "Page", "Line Text"]} />
              </thead>
              <tbody>
                {allLines.map((l, i) => (
                  <tr key={i} className={rowBg(i)}>
                    <Td mono muted className="w-10">{l.idx}</Td>
                    <Td muted className="w-14 text-center">{l.page}</Td>
                    <Td className="whitespace-pre-wrap">{l.text}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <pre
            className="text-[12px] font-mono text-neutral-700 whitespace-pre-wrap break-words leading-relaxed
                        bg-white border border-neutral-200 rounded-lg p-5"
            style={{ maxHeight: "calc(100vh - 300px)", overflowY: "auto" }}
          >
            {fullText}
          </pre>
        )}
      </div>

      {/* Page-level extras: barcodes, visual elements, image quality */}
      {pages.some((pg) => pg.barcodes?.length || pg.visual_elements?.length || pg.image_quality) && (
        <div className="space-y-4">
          {pages.map((pg, pi) => (
            <Fragment key={pi}>
              {pg.barcodes?.length > 0 && (
                <div>
                  <SectionLabel text={`Barcodes (Page ${pg.page_number || pi + 1})`} count={pg.barcodes.length} />
                  <div className="grid grid-cols-3 gap-2">
                    {pg.barcodes.map((bc, bi) => (
                      <div key={bi} className="bg-white border border-neutral-200 rounded px-3 py-2 text-xs">
                        <div className="font-mono text-neutral-800">{bc.raw_value}</div>
                        <div className="text-[10px] text-neutral-400 mt-0.5">{bc.format} · {bc.value_format}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {pg.visual_elements?.length > 0 && (
                <div>
                  <SectionLabel text={`Visual Elements (Page ${pg.page_number || pi + 1})`} count={pg.visual_elements.length} />
                  <div className="flex flex-wrap gap-2">
                    {pg.visual_elements.map((ve, vi) => (
                      <span key={vi} className="text-xs bg-white border border-neutral-200 rounded px-2 py-1">
                        <span className="font-medium text-neutral-700">{ve.type}</span>
                        {ve.text && <span className="text-neutral-400 ml-1.5">{ve.text}</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {pg.image_quality && (
                <div>
                  <SectionLabel text={`Image Quality (Page ${pg.page_number || pi + 1})`} />
                  <div className="bg-white border border-neutral-200 rounded px-3 py-2 text-xs inline-flex items-center gap-3">
                    <span>Score: <strong>{((pg.image_quality.quality_score || 0) * 100).toFixed(1)}%</strong></span>
                    {pg.image_quality.defects?.map((d, di) => (
                      <span key={di} className="text-neutral-500">{d.type}: {(d.confidence * 100).toFixed(0)}%</span>
                    ))}
                  </div>
                </div>
              )}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}


/* ================================================================== */
/*  Shared primitives                                                  */
/* ================================================================== */

function Metric({ label, value }) {
  return (
    <div className="bg-white border border-neutral-200 rounded-lg px-4 py-3 text-center">
      <div className="text-base font-semibold text-neutral-800 leading-tight">{value}</div>
      <div className="text-[10px] font-medium text-neutral-400 uppercase tracking-wider mt-1">{label}</div>
    </div>
  );
}

function SectionLabel({ text, count }) {
  return (
    <div className="flex items-center gap-2 mb-0">
      <span className="text-[11px] font-bold text-neutral-500 uppercase tracking-wider">{text}</span>
      {count != null && (
        <span className="text-[9px] font-semibold text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">{count}</span>
      )}
    </div>
  );
}

function TableCard({ title, count, children }) {
  return (
    <div>
      <SectionLabel text={title} count={count} />
      <div className="border border-neutral-200 rounded-lg overflow-hidden bg-white mt-2">
        <table className="w-full text-xs">{children}</table>
      </div>
    </div>
  );
}

function Thead({ cells }) {
  return (
    <tr className="bg-neutral-50 text-left">
      {cells.map((c, i) => (
        <th
          key={i}
          className={`px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider ${
            i === cells.length - 1 && cells.length > 2 ? "text-right" : ""
          }`}
        >
          {c}
        </th>
      ))}
    </tr>
  );
}

function Td({ children, mono, bold, muted, className = "" }) {
  return (
    <td className={`px-4 py-2 ${mono ? "font-mono text-[11px]" : ""} ${bold ? "font-medium" : ""} ${muted ? "text-neutral-400" : "text-neutral-800"} max-w-xs break-words ${className}`}>
      {children}
    </td>
  );
}

function TdRight({ children }) {
  return <td className="px-4 py-2 text-right">{children}</td>;
}

function rowBg(i) {
  return i % 2 === 0 ? "bg-white" : "bg-neutral-50/50";
}

function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] text-center px-8">
      <div className="w-12 h-12 rounded-full bg-neutral-100 flex items-center justify-center mb-4">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <h3 className="text-sm font-semibold text-neutral-600 mb-1">{title}</h3>
      <p className="text-xs text-neutral-400 max-w-sm">{description}</p>
    </div>
  );
}
