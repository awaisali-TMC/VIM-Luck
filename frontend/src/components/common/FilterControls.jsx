/**
 * Reusable filter controls for report/list screens.
 *
 *  - <FilterDropdown>   single- or multi-select, optionally searchable
 *  - <DateRangeFilter>  preset ranges (incl. OGDCL fiscal year) + custom dates
 *  - <AmountRangeFilter> min/max numeric range
 *
 * All three share the same "labelled field + popover menu" look so a filter bar
 * reads as a row of consistent dropdowns. None of them own any business logic —
 * they emit plain values through onChange and the parent holds the filter state.
 */
import { useState, useRef, useEffect, useMemo } from "react";
import { DATE_PRESETS } from "../../utils/dateRange";

// ── Shared field shell (label on top, value + caret button, popover below) ────

function useOutsideClose(ref, onClose) {
  useEffect(() => {
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [ref, onClose]);
}

function Field({ label, valueNode, active, open, onToggle, children, width = "min-w-[168px]", align = "left" }) {
  const ref = useRef(null);
  useOutsideClose(ref, () => open && onToggle(false));
  return (
    <div className="relative flex flex-col gap-1" ref={ref}>
      <span className="text-2xs text-neutral-400 uppercase tracking-wider pl-0.5">{label}</span>
      <button
        type="button"
        onClick={() => onToggle(!open)}
        className={`inline-flex items-center gap-2 ${width} min-h-[34px] px-2.5 py-1.5 border rounded-md text-xs cursor-pointer transition-colors
          ${open
            ? "border-brand-500 bg-neutral-0 text-neutral-800"
            : active
            ? "border-brand-300 bg-brand-50 text-brand-700"
            : "border-neutral-200 bg-neutral-0 text-neutral-800 hover:border-neutral-300"}`}
      >
        <span className="truncate">{valueNode}</span>
        <span className="ml-auto pl-1.5 text-[9px] text-neutral-400 leading-none">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className={`absolute z-30 top-full ${align === "right" ? "right-0" : "left-0"} mt-1 bg-neutral-0 border border-neutral-100 rounded-md shadow-lg p-1.5 min-w-full`}>
          {children}
        </div>
      )}
    </div>
  );
}

function CheckBox({ checked }) {
  return (
    <span
      className={`w-[15px] h-[15px] rounded-[4px] border flex items-center justify-center flex-none text-white text-[10px] leading-none
        ${checked ? "bg-brand-600 border-brand-600" : "border-neutral-300 bg-neutral-0"}`}
    >
      {checked ? "✓" : ""}
    </span>
  );
}

// ── FilterDropdown ────────────────────────────────────────────────────────────

export function FilterDropdown({
  label,
  options = [],
  value,
  onChange,
  multiple = false,
  searchable = false,
  placeholder = "All",
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  const norm = options.map((o) =>
    typeof o === "string" ? { value: o, label: o } : o
  );
  const selected = multiple ? (Array.isArray(value) ? value : []) : value;

  const filtered = useMemo(() => {
    if (!searchable || !q.trim()) return norm;
    const needle = q.trim().toLowerCase();
    return norm.filter((o) => String(o.label).toLowerCase().includes(needle));
  }, [norm, q, searchable]);

  const active = multiple ? selected.length > 0 : selected != null && selected !== "";

  const valueNode = (() => {
    if (multiple) {
      if (selected.length === 0) return <span className="text-neutral-400">{placeholder}</span>;
      if (selected.length === 1) {
        const one = norm.find((o) => o.value === selected[0]);
        return <span className="font-medium">{one?.label ?? selected[0]}</span>;
      }
      return <span className="font-medium">{selected.length} selected</span>;
    }
    if (active) {
      const one = norm.find((o) => o.value === selected);
      return <span className="font-medium">{one?.label ?? selected}</span>;
    }
    return <span className="text-neutral-400">{placeholder}</span>;
  })();

  const toggleMulti = (v) => {
    const set = new Set(selected);
    set.has(v) ? set.delete(v) : set.add(v);
    onChange([...set]);
  };

  const pickSingle = (v) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <Field label={label} valueNode={valueNode} active={active} open={open} onToggle={setOpen}>
      <div className="w-[224px]">
        {searchable && (
          <div className="flex items-center gap-2 border border-neutral-200 rounded-base px-2.5 py-1.5 mb-1.5 mx-0.5 mt-0.5">
            <span className="text-neutral-400 text-xs">⌕</span>
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={`Search ${label.toLowerCase()}…`}
              className="w-full bg-transparent border-none outline-none text-xs text-neutral-800 placeholder:text-neutral-400"
            />
          </div>
        )}

        <div className="max-h-[248px] overflow-y-auto">
          {!multiple && (
            <button
              type="button"
              onClick={() => pickSingle(null)}
              className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-base text-xs text-left cursor-pointer hover:bg-neutral-50"
            >
              <span className={!active ? "text-brand-600 w-[15px] text-center" : "w-[15px] text-center text-transparent"}>✓</span>
              <span className={!active ? "font-medium text-neutral-900" : "text-neutral-700"}>{placeholder}</span>
            </button>
          )}

          {filtered.length === 0 && (
            <div className="px-2.5 py-3 text-center text-2xs text-neutral-400">No matches</div>
          )}

          {filtered.map((o) => {
            const isSel = multiple ? selected.includes(o.value) : selected === o.value;
            return (
              <button
                key={String(o.value)}
                type="button"
                onClick={() => (multiple ? toggleMulti(o.value) : pickSingle(o.value))}
                className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-base text-xs text-left cursor-pointer hover:bg-neutral-50 ${isSel ? "text-neutral-900 font-medium" : "text-neutral-700"}`}
              >
                {multiple ? (
                  <CheckBox checked={isSel} />
                ) : (
                  <span className={isSel ? "text-brand-600 w-[15px] text-center" : "w-[15px] text-center text-transparent"}>✓</span>
                )}
                {o.dot && <span className="w-2 h-2 rounded-[3px] flex-none" style={{ background: o.dot }} />}
                <span className="truncate flex-1">{o.label}</span>
                {o.count != null && <span className="text-2xs text-neutral-400 tabular-nums">{o.count}</span>}
              </button>
            );
          })}
        </div>

        {multiple && (
          <div className="flex items-center justify-between px-1.5 pt-1.5 mt-1 border-t border-neutral-100 text-2xs">
            <button
              type="button"
              onClick={() => onChange(filtered.map((o) => o.value))}
              className="text-brand-600 font-semibold bg-transparent border-none cursor-pointer"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-neutral-400 bg-transparent border-none cursor-pointer"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    </Field>
  );
}

// ── DateRangeFilter ───────────────────────────────────────────────────────────

export function DateRangeFilter({ value, onChange, label = "Date range" }) {
  const [open, setOpen] = useState(false);
  const preset = value?.preset || "90";
  const presetLabel = DATE_PRESETS.find((p) => p.key === preset)?.label || "Last 90 days";

  const valueNode = (
    <span className="font-medium">
      {preset === "custom" && value?.date_from
        ? `${value.date_from} → ${value.date_to || "…"}`
        : `🗓 ${presetLabel}`}
    </span>
  );

  const setPreset = (key) => {
    if (key === "custom") {
      onChange({ ...value, preset: "custom" });
    } else {
      onChange({ preset: key, date_from: null, date_to: null });
      setOpen(false);
    }
  };

  return (
    <Field label={label} valueNode={valueNode} active={preset !== "90"} open={open} onToggle={setOpen} width="min-w-[176px]">
      <div className="w-[220px]">
        {DATE_PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => setPreset(p.key)}
            className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-base text-xs text-left cursor-pointer hover:bg-neutral-50 ${preset === p.key ? "text-neutral-900 font-medium" : "text-neutral-700"}`}
          >
            <span className={preset === p.key ? "text-brand-600 w-[15px] text-center" : "w-[15px] text-center text-transparent"}>✓</span>
            {p.label}
          </button>
        ))}
        {preset === "custom" && (
          <div className="border-t border-neutral-100 mt-1 pt-2 px-1 flex flex-col gap-2">
            <label className="flex items-center justify-between gap-2 text-2xs text-neutral-500">
              From
              <input
                type="date"
                value={value?.date_from || ""}
                onChange={(e) => onChange({ ...value, preset: "custom", date_from: e.target.value })}
                className="border border-neutral-200 rounded-base px-2 py-1 text-xs text-neutral-800"
              />
            </label>
            <label className="flex items-center justify-between gap-2 text-2xs text-neutral-500">
              To
              <input
                type="date"
                value={value?.date_to || ""}
                onChange={(e) => onChange({ ...value, preset: "custom", date_to: e.target.value })}
                className="border border-neutral-200 rounded-base px-2 py-1 text-xs text-neutral-800"
              />
            </label>
          </div>
        )}
      </div>
    </Field>
  );
}

// ── AmountRangeFilter ─────────────────────────────────────────────────────────

export function AmountRangeFilter({ value, onChange, label = "Amount" }) {
  const [open, setOpen] = useState(false);
  const [min, setMin] = useState(value?.min ?? "");
  const [max, setMax] = useState(value?.max ?? "");

  // Re-sync the draft inputs from the committed value each time the menu opens
  // (also covers an external "Clear all"). No syncing effect needed.
  const toggle = (next) => {
    if (next) {
      setMin(value?.min ?? "");
      setMax(value?.max ?? "");
    }
    setOpen(next);
  };

  const active = (value?.min ?? "") !== "" || (value?.max ?? "") !== "";
  const fmt = (n) => Number(n).toLocaleString();
  const valueNode = active ? (
    <span className="font-medium">
      {value.min !== "" && value.min != null ? fmt(value.min) : "0"}
      {" – "}
      {value.max !== "" && value.max != null ? fmt(value.max) : "∞"}
    </span>
  ) : (
    <span className="text-neutral-400">Any</span>
  );

  const apply = () => {
    onChange({ min: min === "" ? "" : Number(min), max: max === "" ? "" : Number(max) });
    setOpen(false);
  };

  return (
    <Field label={label} valueNode={valueNode} active={active} open={open} onToggle={toggle} width="min-w-[140px]" align="right">
      <div className="w-[210px] p-1 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <input
            type="number"
            inputMode="numeric"
            value={min}
            onChange={(e) => setMin(e.target.value)}
            placeholder="Min"
            className="w-full border border-neutral-200 rounded-base px-2 py-1.5 text-xs text-neutral-800"
          />
          <span className="text-neutral-300">–</span>
          <input
            type="number"
            inputMode="numeric"
            value={max}
            onChange={(e) => setMax(e.target.value)}
            placeholder="Max"
            className="w-full border border-neutral-200 rounded-base px-2 py-1.5 text-xs text-neutral-800"
          />
        </div>
        <div className="flex items-center justify-between pt-1.5 border-t border-neutral-100 text-2xs">
          <button
            type="button"
            onClick={() => { setMin(""); setMax(""); onChange({ min: "", max: "" }); }}
            className="text-neutral-400 bg-transparent border-none cursor-pointer"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={apply}
            className="text-white bg-brand-600 hover:bg-brand-700 rounded-base px-3 py-1 font-semibold border-none cursor-pointer"
          >
            Apply
          </button>
        </div>
      </div>
    </Field>
  );
}
