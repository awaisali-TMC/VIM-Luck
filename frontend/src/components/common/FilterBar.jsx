import { Fragment } from "react";

export default function FilterBar({ filters }) {
  return (
    <div className="flex gap-2.5 items-center mb-4 flex-nowrap">
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
          ) : (
            <select
              value={f.value}
              onChange={f.onChange}
              className="py-1.5 px-2.5 pr-7 border border-neutral-200 rounded-base text-xs bg-neutral-0 text-neutral-700 cursor-pointer shrink-0 font-sans"
            >
              {f.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          )}
        </Fragment>
      ))}
    </div>
  );
}
