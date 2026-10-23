import { useState, useMemo } from "react";

/* ================================================================== */
/*  Full-screen Document AI Raw Output Overlay                         */
/*  4 tabs matching Google's sample: Fields, Key-Value Pairs, Tables, OCR */
/* ================================================================== */

/* ---------- tiny helpers ---------- */

function confColor(c) {
  if (c >= 0.85) return "#059669";   // emerald-600
  if (c >= 0.6)  return "#d97706";   // amber-600
  return "#ef4444";                   // red-500
}

function ConfPill({ value }) {
  if (value == null) return null;
  const pct = value <= 1 ? value * 100 : value;
  return (
    <span
      className="inline-block text-[10px] font-mono px-1.5 py-0.5 rounded-full"
      style={{ color: confColor(value <= 1 ? value : value / 100), background: `${confColor(value <= 1 ? value : value / 100)}12` }}
    >
      {pct.toFixed(1)}%
    </span>
  );
}

/* ---------- Tab definitions ---------- */

const TABS = [
  { key: "fields",  label: "Fields",           icon: "⬡" },
  { key: "kv",      label: "Key‑Value Pairs",  icon: "⇄" },
  { key: "tables",  label: "Tables",           icon: "⊞" },
  { key: "ocr",     label: "OCR Text",         icon: "¶" },
];

/* ================================================================== */
/*  Main component                                                     */
/* ================================================================== */

export default function RawOutputDrawer({ open, onClose, data }) {
  const [tab, setTab] = useState("fields");

  // Derive raw data
  const raw = data?.raw_document_ai;
  const fullText = raw?.text || "";

  // Aggregate form fields & tables from all pages
  const { formFields, tables, stats } = useMemo(() => {
    if (!raw?.pages) return { formFields: [], tables: [], stats: { blocks: 0, paragraphs: 0, lines: 0 } };

    const ff = [];
    const tb = [];
    let blocks = 0, paragraphs = 0, lines = 0;

    for (const page of raw.pages) {
      const pageNum = page.page_number ?? 1;

      // Form fields
      if (page.form_fields) {
        for (const f of page.form_fields) {
          ff.push({ ...f, page: pageNum });
        }
      }

      // Tables
      if (page.tables) {
        for (let i = 0; i < page.tables.length; i++) {
          tb.push({ table: page.tables[i], page: pageNum, index: i });
        }
      }

      blocks += page.block_count || 0;
      paragraphs += page.paragraph_count || 0;
      lines += page.line_count || 0;
    }

    return { formFields: ff, tables: tb, stats: { blocks, paragraphs, lines } };
  }, [raw]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex flex-col bg-white">
      {/* ---- Top bar ---- */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-neutral-200 flex-shrink-0 bg-white">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-base font-semibold text-neutral-900 leading-tight">
              Document AI Raw Output
            </h1>
            <p className="text-2xs text-neutral-500 mt-0.5">
              {data.original_filename}
              <span className="mx-1.5">·</span>
              {data.processing_time_ms}ms
              <span className="mx-1.5">·</span>
              {data.page_count} page{data.page_count !== 1 ? "s" : ""}
              {raw && (
                <>
                  <span className="mx-1.5">·</span>
                  {fullText.length.toLocaleString()} chars OCR
                </>
              )}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-neutral-600 bg-neutral-100
                     hover:bg-neutral-200 rounded-md border-none cursor-pointer transition-colors"
        >
          <span className="text-sm">✕</span> Close
        </button>
      </header>

      {/* ---- Tab strip ---- */}
      <nav className="flex border-b border-neutral-200 px-6 flex-shrink-0 bg-neutral-50">
        {TABS.map((t) => {
          const active = tab === t.key;
          let count = null;
          if (t.key === "kv")     count = formFields.length;
          if (t.key === "tables") count = tables.length;
          if (t.key === "fields") count = (data.fields?.length || 0) + (data.line_items?.length || 0);

          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`relative px-5 py-3 text-xs font-medium border-none cursor-pointer transition-colors
                flex items-center gap-2 bg-transparent
                ${active ? "text-brand-600" : "text-neutral-500 hover:text-neutral-700"}`}
            >
              <span className="text-[13px] opacity-60">{t.icon}</span>
              {t.label}
              {count != null && count > 0 && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  active ? "bg-brand-100 text-brand-700" : "bg-neutral-200 text-neutral-500"
                }`}>
                  {count}
                </span>
              )}
              {active && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-500 rounded-t" />
              )}
            </button>
          );
        })}
      </nav>

      {/* ---- Content area ---- */}
      <div className="flex-1 overflow-y-auto">
        {!raw && (
          <EmptyFull
            icon="⚠"
            title="Raw output not available"
            subtitle="The backend did not return raw Document AI data. Restart the backend and re-upload the document."
          />
        )}

        {raw && tab === "fields"  && <FieldsTab data={data} raw={raw} />}
        {raw && tab === "kv"      && <KeyValueTab formFields={formFields} />}
        {raw && tab === "tables"  && <TablesTab tables={tables} />}
        {raw && tab === "ocr"     && <OcrTab fullText={fullText} stats={stats} />}
      </div>
    </div>
  );
}


/* ================================================================== */
/*  Tab 1: Fields (entities from Invoice Parser)                       */
/* ================================================================== */

function FieldsTab({ data, raw }) {
  const entities = raw.entities || [];

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Document Type" value={data.document_type || "—"} />
        <StatCard label="Overall Confidence" value={`${data.overall_confidence}%`} />
        <StatCard label="Fields" value={data.fields?.length || 0} />
        <StatCard label="Line Items" value={data.line_items?.length || 0} />
      </div>

      {/* Entities table */}
      <SectionHeading title="All Entities" count={entities.length} />
      <div className="border border-neutral-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-neutral-50 text-left">
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider">Type</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider">Mention Text</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider">Normalized</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider text-right">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {entities.map((e, i) => (
              <>
                <tr key={i} className={`${i % 2 === 0 ? "bg-white" : "bg-neutral-25"} ${e.properties ? "font-medium" : ""}`}>
                  <td className="px-4 py-2 font-mono text-[11px] text-neutral-600">{e.type}</td>
                  <td className="px-4 py-2 text-neutral-800 max-w-xs break-words">{e.mention_text || "—"}</td>
                  <td className="px-4 py-2 text-neutral-600">{e.normalized_value || "—"}</td>
                  <td className="px-4 py-2 text-right"><ConfPill value={e.confidence} /></td>
                </tr>
                {/* Nested properties (e.g. line_item sub-fields) */}
                {e.properties?.map((p, j) => (
                  <tr key={`${i}-${j}`} className="bg-neutral-50/50">
                    <td className="px-4 py-1.5 pl-8 font-mono text-[10px] text-neutral-400">↳ {p.type}</td>
                    <td className="px-4 py-1.5 text-[11px] text-neutral-700">{p.mention_text || "—"}</td>
                    <td className="px-4 py-1.5 text-[11px] text-neutral-500">{p.normalized_value || "—"}</td>
                    <td className="px-4 py-1.5 text-right"><ConfPill value={p.confidence} /></td>
                  </tr>
                ))}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Warnings */}
      {data.warnings?.length > 0 && (
        <div className="mt-6">
          <SectionHeading title="Warnings" count={data.warnings.length} />
          <div className="space-y-1.5">
            {data.warnings.map((w, i) => (
              <div key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-3 py-2 rounded">
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
/*  Tab 2: Key-Value Pairs (page-level form fields)                    */
/* ================================================================== */

function KeyValueTab({ formFields }) {
  if (formFields.length === 0) {
    return (
      <EmptyFull
        icon="⇄"
        title="No key-value pairs detected"
        subtitle="The Invoice Parser did not detect any page-level form fields on this document."
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <SectionHeading title="Key-Value Pairs" count={formFields.length} />
      <div className="border border-neutral-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-neutral-50 text-left">
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider w-[40px]">#</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider">Key</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider">Value</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider text-right">Key Conf.</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider text-right">Value Conf.</th>
              <th className="px-4 py-2.5 font-semibold text-neutral-500 uppercase text-[10px] tracking-wider text-center w-[60px]">Page</th>
            </tr>
          </thead>
          <tbody>
            {formFields.map((ff, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-neutral-25"}>
                <td className="px-4 py-2 text-neutral-400 font-mono">{i + 1}</td>
                <td className="px-4 py-2 font-medium text-neutral-800 max-w-[200px] break-words">{ff.key || "—"}</td>
                <td className="px-4 py-2 text-neutral-700 max-w-[300px] break-words">{ff.value || "—"}</td>
                <td className="px-4 py-2 text-right"><ConfPill value={ff.key_confidence} /></td>
                <td className="px-4 py-2 text-right"><ConfPill value={ff.value_confidence} /></td>
                <td className="px-4 py-2 text-center text-neutral-400">{ff.page}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


/* ================================================================== */
/*  Tab 3: Tables                                                      */
/* ================================================================== */

function TablesTab({ tables }) {
  if (tables.length === 0) {
    return (
      <EmptyFull
        icon="⊞"
        title="No tables detected"
        subtitle="The Invoice Parser did not detect any tables on this document."
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <SectionHeading title="Detected Tables" count={tables.length} />

      {tables.map(({ table, page, index }, i) => (
        <div key={i} className={i > 0 ? "mt-8" : ""}>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-semibold text-neutral-700">Table {index + 1}</span>
            <span className="text-[10px] text-neutral-400 bg-neutral-100 px-2 py-0.5 rounded">
              Page {page}
            </span>
            <span className="text-[10px] text-neutral-400">
              {table.header_rows?.length || 0} header row{(table.header_rows?.length || 0) !== 1 ? "s" : ""},
              {" "}{table.body_rows?.length || 0} body row{(table.body_rows?.length || 0) !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="border border-neutral-200 rounded-lg overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              {table.header_rows?.length > 0 && (
                <thead>
                  {table.header_rows.map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <th
                          key={ci}
                          className="text-left text-[11px] font-semibold text-neutral-700 bg-neutral-100
                                     px-3 py-2.5 border border-neutral-200"
                          colSpan={cell.col_span || 1}
                          rowSpan={cell.row_span || 1}
                        >
                          {cell.text || ""}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
              )}
              <tbody>
                {table.body_rows?.map((row, ri) => (
                  <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-neutral-25"}>
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className="px-3 py-2 text-neutral-800 border border-neutral-200"
                        colSpan={cell.col_span || 1}
                        rowSpan={cell.row_span || 1}
                      >
                        {cell.text || ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}


/* ================================================================== */
/*  Tab 4: OCR Text                                                    */
/* ================================================================== */

function OcrTab({ fullText, stats }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(fullText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!fullText) {
    return (
      <EmptyFull
        icon="¶"
        title="No OCR text"
        subtitle="Document AI did not return any text for this document."
      />
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Characters" value={fullText.length.toLocaleString()} />
        <StatCard label="Blocks" value={stats.blocks} />
        <StatCard label="Paragraphs" value={stats.paragraphs} />
        <StatCard label="Lines" value={stats.lines} />
      </div>

      {/* OCR output */}
      <div className="flex items-center justify-between mb-3">
        <SectionHeading title="Full OCR Text" />
        <button
          onClick={handleCopy}
          className="text-xs font-medium px-3 py-1.5 rounded-md border cursor-pointer transition-colors
                     bg-white border-neutral-200 text-neutral-600 hover:bg-neutral-50 hover:border-neutral-300"
        >
          {copied ? "✓ Copied" : "Copy text"}
        </button>
      </div>
      <pre className="text-[12px] font-mono text-neutral-700 whitespace-pre-wrap break-words leading-relaxed
                       bg-neutral-50 border border-neutral-200 rounded-lg p-5 max-h-[calc(100vh-280px)] overflow-y-auto">
        {fullText}
      </pre>
    </div>
  );
}


/* ================================================================== */
/*  Shared sub-components                                              */
/* ================================================================== */

function StatCard({ label, value }) {
  return (
    <div className="bg-neutral-50 border border-neutral-200 rounded-lg px-4 py-3 text-center">
      <div className="text-lg font-semibold text-neutral-800">{value}</div>
      <div className="text-[10px] font-medium text-neutral-400 uppercase tracking-wider mt-0.5">{label}</div>
    </div>
  );
}

function SectionHeading({ title, count }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <h3 className="text-xs font-semibold text-neutral-700 uppercase tracking-wider">{title}</h3>
      {count != null && (
        <span className="text-[10px] font-medium text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">
          {count}
        </span>
      )}
    </div>
  );
}

function EmptyFull({ icon, title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center px-8">
      <div className="text-3xl opacity-20 mb-3">{icon}</div>
      <div className="text-sm font-semibold text-neutral-600 mb-1">{title}</div>
      <div className="text-xs text-neutral-400 max-w-sm">{subtitle}</div>
    </div>
  );
}
