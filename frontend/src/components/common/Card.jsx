// overflowVisible: opt out of overflow-hidden so absolutely-positioned popovers
// (e.g. filter dropdowns) can extend past the card edge.
export default function Card({ title, subtitle, action, children, noPad = false, className = "", bodyClassName = "", overflowVisible = false }) {
  return (
    <div className={`bg-neutral-0 border border-neutral-100 rounded-lg shadow-sm ${overflowVisible ? "" : "overflow-hidden"} ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-neutral-100 bg-gradient-to-b from-neutral-0 to-neutral-25">
          <div className="min-w-0">
            <h3 className="flex items-center gap-2 text-base font-semibold text-neutral-900 m-0">
              {/* Brand accent before every card title */}
              <span aria-hidden="true" className="w-1 h-4 rounded-full bg-brand-500 flex-shrink-0" />
              {title}
            </h3>
            {subtitle && <span className="block text-2xs text-neutral-500 mt-0.5 ml-3">{subtitle}</span>}
          </div>
          {action}
        </div>
      )}
      <div className={`${noPad ? "" : "p-5"} ${bodyClassName}`}>
        {children}
      </div>
    </div>
  );
}
