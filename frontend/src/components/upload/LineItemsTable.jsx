import { useState, useRef, useEffect } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import api from "../../services/api";

function fmtNum(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString();
}

function matchConfidenceColor(conf) {
  if (conf >= 0.85) return "text-emerald-600 bg-emerald-50 border-emerald-200";
  if (conf >= 0.6) return "text-amber-600 bg-amber-50 border-amber-200";
  return "text-red-600 bg-red-50 border-red-200";
}

// --- Product Picker Modal (fetches from API) ---
function ProductPickerModal({ open, onClose, onSelect, currentCode }) {
  const [search, setSearch] = useState("");
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .get("/api/products/", { params: { limit: 500 } })
      .then((res) => setProducts(res.data.products || []))
      .catch(() => setProducts([]))
      .finally(() => setLoading(false));
  }, [open]);

  if (!open) return null;

  const filtered = search
    ? products.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.code.toLowerCase().includes(search.toLowerCase()) ||
          p.category.toLowerCase().includes(search.toLowerCase())
      )
    : products;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl w-[580px] max-h-[75vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-neutral-100 flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-neutral-900">
              Select Account / Product
            </div>
            <div className="text-2xs text-neutral-500">
              {products.length} products in catalog
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 bg-transparent border-none cursor-pointer text-base"
          >
            &#10005;
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-neutral-50">
          <input
            type="text"
            placeholder="Search by name, code, or category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            className="w-full bg-neutral-50 border border-neutral-200 rounded-base px-3 py-2 text-xs outline-none focus:border-brand-400 transition-colors"
          />
        </div>

        {/* Product List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="px-5 py-8 text-center text-2xs text-neutral-400">
              Loading products...
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-5 py-8 text-center text-2xs text-neutral-400">
              No products match your search
            </div>
          ) : (
            filtered.map((p) => {
              const isSelected = p.code === currentCode;
              return (
                <button
                  key={p.code}
                  onClick={() => {
                    onSelect(p);
                    onClose();
                  }}
                  className={`w-full flex items-center gap-3 px-5 py-2.5 border-none cursor-pointer text-left transition-colors ${
                    isSelected
                      ? "bg-brand-50"
                      : "bg-transparent hover:bg-neutral-25"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-neutral-800">
                        {p.name}
                      </span>
                      {isSelected && (
                        <span className="text-[10px] font-semibold text-brand-600 bg-brand-100 px-1.5 py-0.5 rounded">
                          Current
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] font-mono text-neutral-500">
                        {p.code}
                      </span>
                      <span className="text-[10px] text-neutral-400">
                        &middot;
                      </span>
                      <span className="text-[10px] text-neutral-400">
                        {p.category}
                      </span>
                    </div>
                  </div>
                  <svg
                    className="w-4 h-4 text-neutral-300"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

// --- ERP Match Cell ---
function ErpMatchCell({ geminiMatch, overrideProduct, onOverride }) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const product = overrideProduct || (geminiMatch ? {
    code: geminiMatch.product_code,
    name: geminiMatch.product_name,
    category: geminiMatch.product_category,
  } : null);
  const confidence = overrideProduct ? 1.0 : geminiMatch?.confidence || 0;
  const reasoning = geminiMatch?.reasoning;
  const colors = matchConfidenceColor(confidence);

  return (
    <>
      <div className="flex items-center gap-1.5">
        {product ? (
          <>
            <div className="flex flex-col gap-0.5" title={reasoning || ""}>
              <span
                className={`text-2xs font-medium px-1.5 py-0.5 rounded border ${colors}`}
              >
                {product.name}
              </span>
              <span className="text-[10px] text-neutral-400 font-mono">
                {product.code}
                {confidence > 0 && (
                  <span className="ml-1">
                    {Math.round(confidence * 100)}%
                  </span>
                )}
              </span>
            </div>
            <button
              onClick={() => setPickerOpen(true)}
              className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded bg-transparent hover:bg-neutral-100 border-none cursor-pointer transition-colors"
              title="Change product mapping"
            >
              <svg
                className="w-3 h-3 text-neutral-400 hover:text-brand-500"
                viewBox="0 0 16 16"
                fill="none"
              >
                <path
                  d="M11.5 1.5l3 3-9 9H2.5v-3l9-9z"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </>
        ) : (
          <div className="flex items-center gap-1.5">
            <span className="text-2xs text-neutral-400 italic">No match</span>
            <button
              onClick={() => setPickerOpen(true)}
              className="text-2xs text-brand-500 hover:text-brand-700 bg-transparent border-none cursor-pointer"
            >
              Select
            </button>
          </div>
        )}
      </div>
      <ProductPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={onOverride}
        currentCode={product?.code}
      />
    </>
  );
}

// --- Inline editable cell ---
// `requireValue` — reject clearing a numeric cell to empty as well as
// unparseable text. Set on the invoice-detail table, where a line with no
// quantity/price leaves `amount` derived from nothing; NOT set on the
// extraction-review table, where a blank number is legitimate (the AI found
// none). Unparseable text is rejected either way: parseFloat("z") is NaN, and
// NaN serialises to null in JSON, which the API stores as a real null.
function EditableCell({ value, type, align, onCommit, isModified, readOnly, requireValue }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [invalid, setInvalid] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const startEdit = () => {
    if (readOnly) return;
    setDraft(value ?? "");
    setInvalid(false);
    setEditing(true);
  };

  const commit = () => {
    let newValue = draft;
    if (type === "number") {
      // Keep the cell open with the user's text so they can fix it, rather than
      // sending a null that silently clears the field server-side.
      if (draft === "" ? requireValue : Number.isNaN(parseFloat(draft))) {
        setInvalid(true);
        return;
      }
      newValue = draft === "" ? null : parseFloat(draft);
    }
    setInvalid(false);
    setEditing(false);
    if (newValue !== value && !(newValue == null && value == null)) {
      onCommit(newValue);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      commit();
    } else if (e.key === "Escape") {
      setInvalid(false);
      setEditing(false);
    }
  };

  const displayValue = type === "number" ? fmtNum(value) : value || "—";

  if (editing) {
    return (
      <>
        <input
          ref={inputRef}
          type="text"
          inputMode={type === "number" ? "decimal" : "text"}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            if (invalid) setInvalid(false);
          }}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          aria-invalid={invalid || undefined}
          className={`w-full box-border bg-white border border-brand-400 rounded px-2 py-1 text-xs
                      outline-none ring-1 ring-brand-400/20 transition-colors
                      ${align === "right" ? "text-right" : ""}
                      ${type === "number" ? "font-mono" : ""}
                      ${invalid ? "!border-danger-base ring-1 ring-danger-base/40" : ""}`}
        />
        {invalid && (
          <span className="text-2xs text-danger-dark font-medium mt-0.5 block">
            {draft === "" ? "Required" : "Enter a number"}
          </span>
        )}
      </>
    );
  }

  return (
    <div
      onClick={startEdit}
      className={`rounded px-2 py-1 -mx-2 -my-1 transition-colors
                  ${readOnly ? "cursor-default text-neutral-400" : "cursor-pointer hover:bg-brand-50/50"}
                  group relative
                  ${isModified ? "bg-amber-50/60" : ""}`}
      title={readOnly ? "Auto-calculated (Amount ÷ Qty)" : "Click to edit"}
    >
      <span>{displayValue}</span>
      {isModified && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 ml-1.5 align-middle" />
      )}
    </div>
  );
}

const BASE_COLUMNS = [
  { key: "description", label: "Description", align: "left", type: "text", width: "" },
  { key: "quantity", label: "Qty", align: "right", type: "number", width: "w-[8%]" },
  { key: "unit", label: "Unit", align: "right", type: "text", width: "w-[8%]" },
  { key: "unit_price", label: "Rate", align: "right", type: "number", width: "w-[10%]", readOnly: true },
  { key: "amount", label: "Amount", align: "right", type: "number", width: "w-[12%]" },
];

const ACCOUNT_MATCH_COLUMN = { key: "erp_match", label: "Matched Account", align: "left", type: "custom", width: "w-[24%]" };

// --- Match-status badge (invoice line vs PO) ---
function MatchBadge({ status, blocked }) {
  if (status === "unmatched") {
    return (
      <span
        className={`ml-2 inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
          blocked
            ? "text-danger-dark bg-danger-bg border-danger-base"
            : "text-amber-700 bg-amber-50 border-amber-200"
        }`}
        title="This line has no matching PO line, so it cannot be parked. Uncheck or delete it."
      >
        {blocked ? "not on PO · blocks parking" : "not on PO"}
      </span>
    );
  }
  if (status === "matched") {
    return (
      <span className="ml-2 inline-block text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
        on PO
      </span>
    );
  }
  return null;
}

/**
 * Controlled line-items table for the Invoice Detail / parking flow.
 * Distinct from the uncontrolled extraction table below. ONE always-on view:
 *  - inline-editable cells (description, qty, rate) that AUTOSAVE per line
 *    (amount = qty × rate, recomputed server-side) when `editable`,
 *  - per-line selection checkboxes (which lines get parked),
 *  - a permanent delete button per line,
 *  - a match-status indicator (on PO / not on PO).
 * No separate "edit mode" — fields are directly editable while pre-approval.
 */
function ControlledLineItems({
  lineItems,
  editable,
  onLineSave,       // (lineId, {field: value}) => persist
  onAddLineItem,    // () => add a blank line
  selectable,
  selectionLocked,  // checkboxes read-only (after submit-for-approval)
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onDeleteLineItem,
  matchStatusById,
  taxSummary,
  blockedIds,       // Set of selected line ids that have no PO item
  blockedMessage,   // sentence naming them and what to do
}) {
  const rows = lineItems || [];
  const showSelect = selectable;
  const showDelete = typeof onDeleteLineItem === "function";
  const showMatch = !!matchStatusById;
  const showActions = showDelete;

  const allSelected = showSelect && rows.length > 0 && rows.every((li) => selectedIds?.has(li.id));
  const selectedCount = showSelect ? rows.filter((li) => selectedIds?.has(li.id)).length : 0;
  const notOnPoCount = showMatch ? rows.filter((li) => matchStatusById[li.id] === "unmatched").length : 0;

  const cellNum = (v) => (v == null || v === "" ? "—" : Number(v).toLocaleString());

  return (
    <Card
      title="Line Items"
      subtitle={
        `${rows.length} item${rows.length !== 1 ? "s" : ""}` +
        (showSelect ? ` · ${selectedCount} selected for parking${selectionLocked ? " (locked)" : ""}` : "") +
        (notOnPoCount ? ` · ${notOnPoCount} not on PO` : "") +
        (editable ? " · click a cell to edit (auto-saves)" : "")
      }
      action={
        editable && onAddLineItem ? (
          <Button size="xs" variant="ghost" onClick={onAddLineItem}>+ Add line</Button>
        ) : null
      }
      noPad
    >
      {blockedMessage && (
        <div role="alert" className="mx-3.5 mt-3 mb-1 bg-danger-bg border border-danger-base rounded-base px-3 py-2 text-2xs text-danger-dark">
          {blockedMessage}
        </div>
      )}
      {/* Cap the list and scroll inside it so many rows don't stretch the page;
          the header row stays pinned (sticky) while scrolling. */}
      <div className="overflow-auto max-h-[70vh]">
        <table className="w-full table-fixed border-collapse text-xs">
          <thead>
            <tr>
              {showSelect && (
                <th className="sticky top-0 z-10 bg-neutral-25 w-[5%] px-3 py-2 border-b-2 border-neutral-100 text-center">
                  <input type="checkbox" checked={allSelected} disabled={selectionLocked} onChange={() => onToggleSelectAll?.(!allSelected)} title={selectionLocked ? "Selection locked after submit" : "Select all"} />
                </th>
              )}
              <th className="sticky top-0 z-10 bg-neutral-25 text-left px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100">Description</th>
              <th className="sticky top-0 z-10 bg-neutral-25 text-right w-[9%] px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100">Qty</th>
              <th className="sticky top-0 z-10 bg-neutral-25 text-right w-[7%] px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100">Unit</th>
              <th className="sticky top-0 z-10 bg-neutral-25 text-right w-[12%] px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100">Rate</th>
              <th className="sticky top-0 z-10 bg-neutral-25 text-right w-[14%] px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100">Amount</th>
              {showActions && (
                <th className="sticky top-0 z-10 bg-neutral-25 w-[6%] px-3 py-2 border-b-2 border-neutral-100"></th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((li, i) => {
              const id = li.id;
              const selected = !showSelect || selectedIds?.has(id);
              const rowDim = showSelect && !selected ? "opacity-40" : "";
              const isBlocked = !!blockedIds?.has(id);
              const stripe = isBlocked ? "bg-danger-bg" : i % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25";
              return (
                <tr key={id ?? i} className={`${stripe} ${rowDim}`}>
                  {showSelect && (
                    <td className="px-3 py-2 border-b border-neutral-50 text-center">
                      <input type="checkbox" checked={!!selectedIds?.has(id)} disabled={selectionLocked}
                        onChange={() => onToggleSelect?.(id)}
                        title={selectionLocked ? "Selection locked after submit for approval" : undefined} />
                    </td>
                  )}
                  <td className="px-3.5 py-2 border-b border-neutral-50 font-medium text-neutral-800">
                    {editable ? (
                      <EditableCell value={li.description} type="text" align="left"
                        onCommit={(v) => onLineSave(id, { description: v })} />
                    ) : (
                      <div>{li.description || "—"}</div>
                    )}
                    {showMatch && <div className="mt-0.5"><MatchBadge status={matchStatusById[id]} blocked={isBlocked} /></div>}
                    {li.matched_product_name && (
                      <div className="text-[10px] text-neutral-400 mt-0.5 font-normal">
                        &rarr; {li.matched_product_name}
                        {li.matched_product_code && <span className="font-mono ml-1">{li.matched_product_code}</span>}
                      </div>
                    )}
                  </td>
                  <td className="px-3.5 py-2 border-b border-neutral-50 text-right font-mono">
                    {editable ? (
                      <EditableCell value={li.quantity} type="number" align="right" requireValue
                        onCommit={(v) => onLineSave(id, { quantity: v })} />
                    ) : cellNum(li.quantity)}
                  </td>
                  <td className="px-3.5 py-2 border-b border-neutral-50 text-right text-neutral-500">
                    {editable ? (
                      <EditableCell value={li.unit} type="text" align="right"
                        onCommit={(v) => onLineSave(id, { unit: v })} />
                    ) : (li.unit || "—")}
                  </td>
                  <td className="px-3.5 py-2 border-b border-neutral-50 text-right font-mono">
                    {editable ? (
                      <EditableCell value={li.unit_price} type="number" align="right" requireValue
                        onCommit={(v) => onLineSave(id, { unit_price: v })} />
                    ) : cellNum(li.unit_price)}
                  </td>
                  <td className="px-3.5 py-2 border-b border-neutral-50 text-right font-mono font-semibold"
                      title={editable ? "Auto-calculated (Qty × Rate)" : undefined}>
                    {cellNum(li.amount)}
                  </td>
                  {showActions && (
                    <td className="px-3 py-2 border-b border-neutral-50 text-center">
                      {showDelete && (
                        <button onClick={() => onDeleteLineItem(id, i)} title="Delete this line from the invoice"
                          className="text-neutral-400 hover:text-danger-base bg-transparent border-none cursor-pointer">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"/>
                          </svg>
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="px-3.5 py-6 text-center text-neutral-400 text-2xs">No line items</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {taxSummary && taxSummary.length > 0 && (
        <div className="px-3.5 py-3 border-t-2 border-neutral-100 flex flex-col gap-1.5 text-xs">
          {taxSummary.map(({ label, value, isTotal, isTax }) => (
            <div key={label} className={`flex justify-between ${isTotal ? "font-bold text-neutral-900 border-t border-neutral-200 pt-1.5" : isTax ? "font-medium text-brand-700" : "font-normal text-neutral-600"}`}>
              <span>{isTax ? `  ${label}` : label}</span>
              <span className="font-mono">{value}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function LineItemsTable({
  lineItems,
  taxSummary,
  productMatches = [],
  lineItemsSource = "document_ai",
  onOverridesChange,
  showAccountMatch = false,
  matchingPending = false,
  // Controlled mode (Invoice Detail / parking) — when onLineSave is supplied
  // the table is the single inline-editable view (no separate edit mode).
  editable = false,
  onLineSave,
  onAddLineItem,
  selectable = false,
  selectionLocked = false,
  selectedIds = null,
  onToggleSelect,
  onToggleSelectAll,
  onDeleteLineItem,
  matchStatusById = null,
  blockedIds = null,
  blockedMessage = null,
}) {
  const [overrides, setOverrides] = useState({});
  const [erpOverrides, setErpOverrides] = useState({});

  // Controlled path: Invoice Detail page (inline edit, selection, delete, match).
  if (typeof onLineSave === "function" || selectable || typeof onDeleteLineItem === "function") {
    return (
      <ControlledLineItems
        lineItems={lineItems}
        editable={editable}
        onLineSave={onLineSave}
        onAddLineItem={onAddLineItem}
        selectable={selectable}
        selectionLocked={selectionLocked}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
        onToggleSelectAll={onToggleSelectAll}
        onDeleteLineItem={onDeleteLineItem}
        matchStatusById={matchStatusById}
        taxSummary={taxSummary}
        blockedIds={blockedIds}
        blockedMessage={blockedMessage}
      />
    );
  }

  const COLUMNS = showAccountMatch
    ? [BASE_COLUMNS[0], ACCOUNT_MATCH_COLUMN, ...BASE_COLUMNS.slice(1)]
    : BASE_COLUMNS;

  // Build a map of line_item_index -> match for quick lookup (from productMatches prop or line item fields)
  const matchMap = {};
  for (const m of productMatches) {
    matchMap[m.line_item_index] = m;
  }
  // Also pick up matches stored on the line items themselves (from DB after background job)
  lineItems.forEach((li, i) => {
    if (!matchMap[i] && li.matched_product_code) {
      matchMap[i] = {
        product_code: li.matched_product_code,
        product_name: li.matched_product_name,
        product_category: li.matched_product_category,
        confidence: li.match_confidence ?? 0,
        reasoning: li.match_reasoning,
      };
    }
  });

  const handleErpOverride = (index, product) => {
    setErpOverrides((prev) => ({ ...prev, [index]: product }));
  };

  const handleCommit = (rowIdx, colKey, newValue) => {
    setOverrides((prev) => {
      const next = { ...prev, [`${rowIdx}-${colKey}`]: newValue };

      // Auto-recalculate rate (unit_price) = amount / qty
      if (colKey === "quantity" || colKey === "amount") {
        const qty = colKey === "quantity"
          ? newValue
          : ((`${rowIdx}-quantity` in next) ? next[`${rowIdx}-quantity`] : lineItems[rowIdx]?.quantity);
        const amount = colKey === "amount"
          ? newValue
          : ((`${rowIdx}-amount` in next) ? next[`${rowIdx}-amount`] : lineItems[rowIdx]?.amount);

        if (qty != null && amount != null && parseFloat(qty) !== 0) {
          next[`${rowIdx}-unit_price`] = Math.round(parseFloat(amount) / parseFloat(qty) * 100) / 100;
        }
      }

      onOverridesChange?.(next);
      return next;
    });
  };

  const getCellValue = (rowIdx, colKey) => {
    const key = `${rowIdx}-${colKey}`;
    if (key in overrides) return overrides[key];
    return lineItems[rowIdx]?.[colKey];
  };

  const isModified = (rowIdx, colKey) => `${rowIdx}-${colKey}` in overrides;

  const modifiedCount = Object.keys(overrides).length;
  const geminiExtracted = lineItemsSource === "gemini";

  return (
    <Card
      title={
        <div className="flex items-center gap-2">
          <span>Line Items</span>
          {geminiExtracted && (
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-brand-700 bg-brand-50 border border-brand-200 px-2 py-0.5 rounded-full">
              &#128270; Gemini Extracted
            </span>
          )}
        </div>
      }
      subtitle={`${lineItems.length} item${lineItems.length !== 1 ? "s" : ""}${
        showAccountMatch && !matchingPending && Object.keys(matchMap).length > 0
          ? ` · ${Object.keys(matchMap).length} account${Object.keys(matchMap).length !== 1 ? "s" : ""} matched`
          : ""
      }`}
      action={
        matchingPending ? (
          <span className="inline-flex items-center gap-1.5 text-2xs font-medium text-brand-600 bg-brand-50 border border-brand-100 px-2.5 py-1 rounded-full">
            <svg
              style={{ animation: "spin 1s linear infinite", flexShrink: 0 }}
              width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            Matching accounts…
          </span>
        ) : modifiedCount > 0 ? (
          <span className="text-2xs text-amber-600 font-medium">
            {modifiedCount} field{modifiedCount !== 1 ? "s" : ""} modified
          </span>
        ) : null
      }
      noPad
    >
      <table className="w-full table-fixed border-collapse text-xs">
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`${col.align === "left" ? "text-left" : "text-right"} ${col.width || ""} px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100 bg-neutral-25`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lineItems.map((li, i) => (
            <tr key={li.id || i} className={i % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
              {COLUMNS.map((col) => {
                if (col.key === "erp_match") {
                  return (
                    <td
                      key={col.key}
                      className="px-3.5 py-2 border-b border-neutral-50"
                    >
                      {matchingPending ? (
                        <div className="flex items-center gap-2">
                          <div
                            style={{ animation: "spin 1.2s linear infinite" }}
                            className="w-3.5 h-3.5 rounded-full border-2 border-brand-200 border-t-brand-500 flex-shrink-0"
                          />
                          <span className="text-2xs text-neutral-400 italic">Processing…</span>
                        </div>
                      ) : (
                        <ErpMatchCell
                          geminiMatch={matchMap[i]}
                          overrideProduct={erpOverrides[i]}
                          onOverride={(product) => handleErpOverride(i, product)}
                        />
                      )}
                    </td>
                  );
                }

                return (
                  <td
                    key={col.key}
                    className={`px-3.5 py-2 border-b border-neutral-50 ${
                      col.align === "right" ? "text-right" : ""
                    } ${col.key === "amount" ? "font-semibold" : ""} ${
                      col.type === "number" ? "font-mono" : ""
                    } ${col.key === "description" ? "font-medium text-neutral-800" : ""} ${
                      col.key === "unit" ? "text-neutral-500" : ""
                    }`}
                  >
                    <EditableCell
                      value={getCellValue(i, col.key)}
                      type={col.type}
                      align={col.align}
                      colKey={col.key}
                      onCommit={(newVal) => handleCommit(i, col.key, newVal)}
                      isModified={isModified(i, col.key)}
                      readOnly={col.readOnly}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
          {lineItems.length === 0 && (
            <tr>
              <td
                colSpan={6}
                className="px-3.5 py-6 text-center text-neutral-400 text-2xs"
              >
                No line items
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Tax Summary */}
      {taxSummary && taxSummary.length > 0 && (
        <div className="px-3.5 py-3 border-t-2 border-neutral-100 flex flex-col gap-1.5 text-xs">
          {taxSummary.map(({ label, value, isTotal, isTax }) => (
            <div
              key={label}
              className={`flex justify-between ${
                isTotal
                  ? "font-bold text-neutral-900 border-t border-neutral-200 pt-1.5"
                  : isTax
                  ? "font-medium text-brand-700"
                  : "font-normal text-neutral-600"
              }`}
            >
              <span>{isTax ? `  ${label}` : label}</span>
              <span className="font-mono">{value}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
