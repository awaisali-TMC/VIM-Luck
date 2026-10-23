export default function TabBar({ tabs, active, onChange }) {
  return (
    <div className="flex border-b-2 border-neutral-100 mb-5">
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs border-b-2 -mb-[2px] bg-transparent cursor-pointer transition-all duration-150 font-sans ${
              isActive
                ? "text-brand-600 font-semibold border-brand-600"
                : "text-neutral-500 font-normal border-transparent hover:text-neutral-700"
            }`}
          >
            {tab.label}
            {tab.count != null && (
              <span
                className={`text-[10px] font-semibold px-1.5 py-px rounded-full ${
                  isActive
                    ? "bg-brand-50 text-brand-600"
                    : "bg-neutral-100 text-neutral-500"
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
