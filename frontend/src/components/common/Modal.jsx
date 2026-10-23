import { useEffect } from "react";

export default function Modal({ open, onClose, title, children, width = 600, footer }) {
  useEffect(() => {
    if (!open) return;
    const handleEsc = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" />

      {/* Panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative bg-neutral-0 rounded-lg shadow-xl max-w-[90vw] max-h-[85vh] overflow-hidden flex flex-col"
        style={{ width }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100">
          <h3 className="m-0 text-lg font-semibold text-neutral-900">
            {title}
          </h3>
          <button
            onClick={onClose}
            className="bg-transparent border-none text-lg cursor-pointer text-neutral-400 hover:text-neutral-700 p-1"
          >
            &#x2715;
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 overflow-y-auto flex-1">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-2 px-6 py-3 border-t border-neutral-100 bg-neutral-25">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
