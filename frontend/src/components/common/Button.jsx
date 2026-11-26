const VARIANTS = {
  primary:   "bg-brand-600 text-white border-transparent shadow-sm hover:bg-brand-700 hover:shadow-md",
  secondary: "bg-neutral-0 text-neutral-700 border-neutral-200 shadow-xs hover:bg-neutral-50 hover:border-neutral-300",
  success:   "bg-success-base text-white border-transparent shadow-sm hover:bg-success-dark hover:shadow-md",
  danger:    "bg-danger-base text-white border-transparent shadow-sm hover:bg-danger-dark hover:shadow-md",
  ghost:     "bg-transparent text-neutral-600 border-transparent hover:bg-neutral-50",
};

const SIZES = {
  xs: "px-2 py-1 text-2xs",
  sm: "px-3.5 py-1.5 text-xs",
  md: "px-5 py-2 text-sm",
};

export default function Button({
  children,
  variant = "primary",
  size = "sm",
  onClick,
  disabled = false,
  className = "",
  title,
  type,
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`
        inline-flex items-center gap-1.5 border rounded-md font-medium
        cursor-pointer transition-all duration-150 font-sans leading-snug
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-300 focus-visible:ring-offset-1
        enabled:active:translate-y-px
        disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none
        ${VARIANTS[variant]} ${SIZES[size]} ${className}
      `}
    >
      {children}
    </button>
  );
}
