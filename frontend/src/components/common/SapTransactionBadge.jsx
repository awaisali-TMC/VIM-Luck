import { sapTransactionOf } from "../../utils/sapTransaction";

// MIR7 (PO-based) / FV60 (no PO) pill — see utils/sapTransaction.js.
export default function SapTransactionBadge({ value, className = "" }) {
  const fv60 = sapTransactionOf(value) === "FV60";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-2xs font-semibold font-mono whitespace-nowrap ${
        fv60
          ? "bg-amber-50 border-amber-200 text-amber-700"
          : "bg-neutral-50 border-neutral-200 text-neutral-600"
      } ${className}`}
      title={fv60 ? "FV60 — invoice without a PO" : "MIR7 — PO-based invoice"}
    >
      {fv60 ? "FV60" : "MIR7"}
    </span>
  );
}
