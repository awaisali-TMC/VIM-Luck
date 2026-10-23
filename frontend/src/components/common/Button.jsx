const VARIANTS = {
  primary:   "bg-brand-600 text-white border-transparent hover:bg-brand-700",
  secondary: "bg-neutral-0 text-neutral-700 border-neutral-200 hover:bg-neutral-50",
  success:   "bg-success-base text-white border-transparent hover:opacity-90",
  danger:    "bg-danger-base text-white border-transparent hover:opacity-90",
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
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`
        inline-flex items-center gap-1.5 border rounded-base font-medium
        cursor-pointer transition-all duration-150 font-sans leading-snug
        disabled:opacity-50 disabled:cursor-not-allowed
        ${VARIANTS[variant]} ${SIZES[size]} ${className}
      `}
    >
      {children}
    </button>
  );
}
