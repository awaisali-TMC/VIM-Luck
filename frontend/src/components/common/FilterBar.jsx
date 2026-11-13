import { Fragment } from "react";

/**
 * Filter row. Each filter is one of:
 *  - { type: "search", placeholder, value, onChange }
 *  - { type: "date", value, onChange, title }           // native date picker
 *  - { type: "select", value, onChange, options }        // options: string[] OR
 *      {value,label}[] (use objects when the stored value differs from its label)
 */
export default function FilterBar({ filters }) {
  return (
    <div className="flex gap-2.5 items-center mb-4 flex-wrap">
      {filters.map((f, i) => (
        <Fragment key={i}>
          {f.type === "search" ? (
            <div className="relative flex-1 min-w-[180px]">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm opacity-40">
                &#x2315;
              </span>
              <input
                placeholder={f.placeholder}
                value={f.value || ""}
                onChange={f.onChange}
                className="w-full py-1.5 pl-8 pr-3 border border-neutral-200 rounded-base text-xs bg-neutral-0 text-neutral-700 outline-none focus:border-brand-400 transition-colors font-sans"
              />
            </div>
          ) : f.type === "date" ? (
            // Native date inputs ignore `placeholder`, so show a visible label.
            <label className="flex items-center gap-1.5 text-2xs font-medium text-neutral-500 shrink-0" title={f.title}>
              {f.label && <span className="whitespace-nowrap">{f.label}</span>}
              <input
                type="date"
                value={f.value || ""}
                onChange={f.onChange}
                className="py-1.5 px-2.5 border border-neutral-200 rounded-base text-xs bg-neutral-0 text-neutral-700 cursor-pointer font-sans outline-none focus:border-brand-400 transition-colors"
              />
            </label>
          ) : (
            <select
              value={f.value}
              onChange={f.onChange}
              title={f.title}
              className="py-1.5 px-2.5 pr-7 border border-neutral-200 rounded-base text-xs bg-neutral-0 text-neutral-700 cursor-pointer shrink-0 font-sans"
            >
              {f.options.map((o) => {
                const value = typeof o === "object" ? o.value : o;
                const label = typeof o === "object" ? o.label : o;
                return (
                  <option key={value} value={value}>
                    {label}
                  </option>
                );
              })}
            </select>
          )}
        </Fragment>
      ))}
    </div>
  );
}
