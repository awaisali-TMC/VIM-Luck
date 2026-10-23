import { useState } from "react";
import Card from "../common/Card";
import Badge from "../common/Badge";
import Button from "../common/Button";
import api from "../../services/api";

function formatCurrency(amount, currency = "PKR") {
  if (amount == null) return "---";
  return `${currency} ${Number(amount).toLocaleString()}`;
}

export default function CreditDebitNoteCard({ invoice, onRefresh }) {
  const [showCreate, setShowCreate] = useState(false);
  const [linkedInvoice, setLinkedInvoice] = useState(null);
  const [loading, setLoading] = useState(false);

  const docType = invoice?.document_type?.toLowerCase() || "invoice";
  const isCreditDebit = docType === "credit_note" || docType === "debit_note";
  const hasLink = invoice?.linked_invoice_id || invoice?.original_invoice_number;

  // Load linked invoice details if this is a credit/debit note
  const loadLinked = async () => {
    if (!invoice?.linked_invoice_id) return;
    setLoading(true);
    try {
      const res = await api.get(`/api/invoices/${invoice.linked_invoice_id}`);
      setLinkedInvoice(res.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  if (!isCreditDebit && !hasLink) return null;

  const typeLabel = docType === "credit_note" ? "Credit Note" : docType === "debit_note" ? "Debit Note" : "Linked Document";
  const typeColor = docType === "credit_note" ? "#10B981" : docType === "debit_note" ? "#EF4444" : "#6366F1";

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">{docType === "credit_note" ? "\u2796" : "\u2795"}</span>
        <h3 className="text-xs font-bold text-neutral-800 m-0">{typeLabel}</h3>
        <span
          className="text-2xs font-bold px-2 py-0.5 rounded-full"
          style={{ backgroundColor: `${typeColor}15`, color: typeColor }}
        >
          {typeLabel}
        </span>
      </div>

      {/* Reason */}
      {invoice.credit_debit_reason && (
        <div className="bg-neutral-25 border border-neutral-100 rounded-base px-3 py-2 mb-3">
          <div className="text-2xs font-semibold text-neutral-500 mb-0.5">Reason</div>
          <div className="text-xs text-neutral-700">{invoice.credit_debit_reason}</div>
        </div>
      )}

      {/* Link to original invoice */}
      <div className="flex flex-col gap-2">
        {invoice.original_invoice_number && (
          <div className="flex items-center gap-2">
            <span className="text-2xs font-semibold text-neutral-500 w-32">Original Invoice #:</span>
            <span className="text-xs font-medium text-brand-600">{invoice.original_invoice_number}</span>
          </div>
        )}
        {invoice.linked_invoice_id && (
          <div className="flex items-center gap-2">
            <span className="text-2xs font-semibold text-neutral-500 w-32">Linked Invoice ID:</span>
            <span className="text-xs font-medium text-brand-600">#{invoice.linked_invoice_id}</span>
            {!linkedInvoice && !loading && (
              <button
                onClick={loadLinked}
                className="text-2xs text-brand-500 hover:text-brand-700 underline bg-transparent border-none cursor-pointer"
              >
                View details
              </button>
            )}
          </div>
        )}
      </div>

      {/* Linked invoice preview */}
      {loading && (
        <div className="text-2xs text-neutral-400 mt-2">Loading linked invoice...</div>
      )}
      {linkedInvoice && (
        <div className="bg-white border border-neutral-100 rounded-base p-3 mt-3">
          <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">Original Invoice</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-2xs text-neutral-400">Invoice #</div>
              <div className="text-xs font-medium text-neutral-800">
                {linkedInvoice.invoice_number || `#${linkedInvoice.id}`}
              </div>
            </div>
            <div>
              <div className="text-2xs text-neutral-400">Supplier</div>
              <div className="text-xs text-neutral-800">{linkedInvoice.supplier_name || "---"}</div>
            </div>
            <div>
              <div className="text-2xs text-neutral-400">Total Amount</div>
              <div className="text-xs font-medium text-neutral-900">
                {formatCurrency(linkedInvoice.total_amount, linkedInvoice.currency)}
              </div>
            </div>
            <div>
              <div className="text-2xs text-neutral-400">Date</div>
              <div className="text-xs text-neutral-800">{linkedInvoice.invoice_date || "---"}</div>
            </div>
            <div>
              <div className="text-2xs text-neutral-400">Status</div>
              <Badge status={linkedInvoice.status} size="xs" />
            </div>
          </div>
        </div>
      )}

      {/* Net effect summary for credit notes */}
      {isCreditDebit && linkedInvoice && (
        <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3 mt-3">
          <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">Net Effect</div>
          <div className="flex items-center gap-6">
            <div>
              <div className="text-2xs text-neutral-400">Original</div>
              <div className="text-xs font-medium">{formatCurrency(linkedInvoice.total_amount, linkedInvoice.currency)}</div>
            </div>
            <span className="text-neutral-300">{docType === "credit_note" ? "\u2212" : "+"}</span>
            <div>
              <div className="text-2xs text-neutral-400">{typeLabel}</div>
              <div className="text-xs font-medium" style={{ color: typeColor }}>
                {formatCurrency(invoice.total_amount, invoice.currency)}
              </div>
            </div>
            <span className="text-neutral-300">=</span>
            <div>
              <div className="text-2xs text-neutral-400">Net</div>
              <div className="text-xs font-bold text-neutral-900">
                {formatCurrency(
                  docType === "credit_note"
                    ? (linkedInvoice.total_amount || 0) - (invoice.total_amount || 0)
                    : (linkedInvoice.total_amount || 0) + (invoice.total_amount || 0),
                  invoice.currency
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
