import { useState, useEffect } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import api from "../../services/api";

const TYPE_CONFIG = {
  po_material: { label: "PO — Material", color: "#3B82F6", icon: "📦" },
  po_service: { label: "PO — Service", color: "#8B5CF6", icon: "🔧" },
  non_po: { label: "Non-PO", color: "#F59E0B", icon: "📄" },
  import_invoice: { label: "Import", color: "#059669", icon: "🌍" },
  credit_note: { label: "Credit Note", color: "#10B981", icon: "\u2796" },
  debit_note: { label: "Debit Note", color: "#EF4444", icon: "\u2795" },
  utility: { label: "Utility", color: "#6366F1", icon: "⚡" },
  expense: { label: "Expense", color: "#EC4899", icon: "💳" },
};

export default function InvoiceClassificationCard({ invoiceId, currentDocType, onClassified }) {
  const [classification, setClassification] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState(null);

  const classify = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/invoices/${invoiceId}/classify`);
      setClassification(res.data);
    } catch (err) {
      setError("Classification failed");
    } finally {
      setLoading(false);
    }
  };

  const applyType = async (type) => {
    setApplying(true);
    try {
      await api.post(`/api/invoices/${invoiceId}/apply-classification`, null, {
        params: { invoice_type: type },
      });
      if (onClassified) onClassified(type);
    } catch (err) {
      setError("Failed to apply classification");
    } finally {
      setApplying(false);
    }
  };

  const cfg = TYPE_CONFIG[classification?.invoice_type] || TYPE_CONFIG.non_po;
  const currentCfg = TYPE_CONFIG[currentDocType] || null;

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">&#129302;</span>
          <h3 className="text-xs font-bold text-neutral-800 m-0">Auto-Classification</h3>
          {currentDocType && currentCfg && (
            <span
              className="text-2xs font-bold px-2 py-0.5 rounded-full"
              style={{ backgroundColor: `${currentCfg.color}15`, color: currentCfg.color }}
            >
              {currentCfg.icon} {currentCfg.label}
            </span>
          )}
        </div>
        {!classification && !loading && (
          <Button variant="secondary" size="xs" onClick={classify}>
            Classify
          </Button>
        )}
      </div>

      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-2 text-2xs text-danger-dark">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center py-3 text-2xs text-neutral-400">Analyzing invoice...</div>
      )}

      {classification && (
        <div className="flex flex-col gap-3">
          {/* Primary classification */}
          <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">{cfg.icon}</span>
                <div>
                  <div className="text-xs font-bold text-neutral-900">{cfg.label}</div>
                  <div className="text-2xs text-neutral-500">
                    Confidence: {classification.confidence}%
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className="h-1.5 w-16 bg-neutral-100 rounded-full overflow-hidden"
                >
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${classification.confidence}%`,
                      backgroundColor: classification.confidence >= 70 ? "#10B981" : classification.confidence >= 40 ? "#F59E0B" : "#EF4444",
                    }}
                  />
                </div>
              </div>
            </div>

            {classification.reasoning && (
              <div className="text-2xs text-neutral-500 mt-1">{classification.reasoning}</div>
            )}

            {classification.sub_type && (
              <div className="text-2xs text-neutral-400 mt-1">
                Sub-type: <strong>{classification.sub_type}</strong>
              </div>
            )}
          </div>

          {/* Score breakdown */}
          {classification.all_scores && (
            <div>
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Score Breakdown</div>
              <div className="grid grid-cols-4 gap-1">
                {Object.entries(classification.all_scores)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, score]) => {
                    const tc = TYPE_CONFIG[type];
                    if (!tc) return null;
                    return (
                      <div key={type} className="text-center py-1">
                        <div className="text-2xs font-bold" style={{ color: tc.color }}>
                          {score}
                        </div>
                        <div className="text-2xs text-neutral-400 truncate">{tc.label}</div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-2 border-t border-neutral-100">
            {classification.invoice_type !== currentDocType ? (
              <Button
                size="xs"
                onClick={() => applyType(classification.invoice_type)}
                disabled={applying}
              >
                {applying ? "Applying..." : `Apply: ${cfg.label}`}
              </Button>
            ) : (
              <span className="text-2xs text-success-dark font-medium">
                &#10003; Already classified as {cfg.label}
              </span>
            )}
            <Button variant="ghost" size="xs" onClick={classify} disabled={loading}>
              Re-classify
            </Button>
          </div>
        </div>
      )}

      {!classification && !loading && (
        <div className="text-center py-3 text-2xs text-neutral-400">
          Click "Classify" to auto-detect invoice type using AI rules
        </div>
      )}
    </Card>
  );
}
