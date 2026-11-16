// overflowVisible: opt out of overflow-hidden so absolutely-positioned popovers
// (e.g. filter dropdowns) can extend past the card edge.
export default function Card({ title, subtitle, action, children, noPad = false, className = "", bodyClassName = "", overflowVisible = false }) {
  return (
    <div className={`bg-neutral-0 border border-neutral-100 rounded-md shadow-sm ${overflowVisible ? "" : "overflow-hidden"} ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-100">
          <div>
            <h3 className="text-base font-semibold text-neutral-900 m-0">{title}</h3>
            {subtitle && <span className="text-2xs text-neutral-500">{subtitle}</span>}
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
