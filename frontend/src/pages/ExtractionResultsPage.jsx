import { useState, useEffect } from "react";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import ExtractionKPIs from "../components/upload/ExtractionKPIs";
import AttentionFlagsPanel from "../components/upload/AttentionFlagsPanel";
import LineItemsTable from "../components/upload/LineItemsTable";
import WorkflowActions from "../components/upload/WorkflowActions";
import SupplierInfoCard from "../components/upload/SupplierInfoCard";
import InvoiceInfoCard from "../components/upload/InvoiceInfoCard";
import RawOutputViewer from "../components/upload/RawOutputViewer";
import SalesTaxCard from "../components/upload/SalesTaxCard";
import { verifyNTN } from "../services/fbrService";
import { lookupSAPVendor } from "../services/sapService";

// Field names that belong to the Supplier Information section
const SUPPLIER_FIELD_NAMES = new Set([
  "supplier_name",
  "supplier_tax_id",
  "supplier_address",
  "supplier_phone",
]);

function extractSupplierInfo(result) {
  if (!result || !result.fields) return { fields: [] };
  const fieldMap = {};
  const confMap = {};
  for (const f of result.fields) {
    fieldMap[f.field_name] = f.value;
    confMap[f.field_name] = f.confidence;
  }
  return {
    fields: [
      { label: "Supplier Name", value: fieldMap.supplier_name, confidence: confMap.supplier_name },
      { label: "NTN / Tax ID", value: fieldMap.supplier_tax_id, confidence: confMap.supplier_tax_id },
      { label: "Address", value: fieldMap.supplier_address, confidence: confMap.supplier_address },
      { label: "Phone", value: fieldMap.supplier_phone, confidence: confMap.supplier_phone },
    ].filter((f) => f.value),
  };
}

function getNonSupplierFields(fields) {
  if (!fields) return [];
  return fields.filter((f) => !SUPPLIER_FIELD_NAMES.has(f.field_name));
}

function fmtAmount(v) {
  const num = parseFloat(String(v).replace(/,/g, ""));
  if (isNaN(num)) return v;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function buildTaxSummary(result) {
  if (!result || !result.fields) return [];

  const fieldMap = {};
  for (const f of result.fields) {
    fieldMap[f.field_name] = f.value;
  }

  const rows = [];
  if (fieldMap.net_amount) {
    rows.push({ label: "Subtotal", value: `PKR ${fmtAmount(fieldMap.net_amount)}` });
  }

  // Show detected tax types from Gemini if available
  if (result.detected_taxes && result.detected_taxes.length > 0) {
    for (const tax of result.detected_taxes) {
      if (tax.amount != null) {
        const rateStr = tax.rate != null ? ` (${tax.rate}%)` : "";
        rows.push({
          label: `${tax.tax_type}${rateStr}`,
          value: `PKR ${fmtAmount(tax.amount)}`,
          isTax: true,
        });
      }
    }
  } else if (fieldMap.total_tax_amount) {
    rows.push({ label: "Tax", value: `PKR ${fmtAmount(fieldMap.total_tax_amount)}` });
  }

  if (fieldMap.total_amount) {
    rows.push({ label: "Total", value: `PKR ${fmtAmount(fieldMap.total_amount)}`, isTotal: true });
  }

  return rows;
}

/**
 * Full-page view for extraction results after an invoice has been uploaded.
 *
 * Props:
 *  - extractionResult: the result object from Document AI
 *  - file: the uploaded File object
 *  - savedInvoice: the saved invoice object (after save)
 *  - state: "extracted" | "saving" | "saved" | "error"
 *  - error: error message string
 *  - onSave: (status) => void
 *  - onDiscard: () => void  (goes back to upload)
 */
export default function ExtractionResultsPage({
  extractionResult,
  file,
  savedInvoice,
  state,
  error,
  onSave,
  onDiscard,
  onLineItemOverridesChange,
}) {
  const [rawDrawerOpen, setRawDrawerOpen] = useState(false);

  // FBR verification for supplier NTN
  const [fbrStatus, setFbrStatus] = useState("verifying");
  const [fbrTaxpayerName, setFbrTaxpayerName] = useState(null);
  // ERP (SAP vendor master) registration for the supplier
  const [erpStatus, setErpStatus] = useState("verifying");

  useEffect(() => {
    const f = extractionResult?.fields || [];
    const ntn = f.find((x) => x.field_name === "supplier_tax_id")?.value || "";
    const name = f.find((x) => x.field_name === "supplier_name")?.value || "";
    if (!ntn.trim() && !name.trim()) { setErpStatus("not_registered"); return; }
    lookupSAPVendor({ ntn: ntn.trim(), name: name.trim() })
      .then((r) => setErpStatus(r.registered ? "registered" : "not_registered"))
      .catch(() => setErpStatus("error"));
  }, [extractionResult]);

  useEffect(() => {
    const supplierNtn = extractionResult?.fields?.find((f) => f.field_name === "supplier_tax_id")?.value;
    if (!supplierNtn || !supplierNtn.trim()) {
      setFbrStatus("not_found");
      return;
    }
    setFbrStatus("verifying");
    verifyNTN(supplierNtn.trim())
      .then((result) => {
        if (result.status === "verified_active") {
          setFbrStatus("active");
          setFbrTaxpayerName(result.taxpayer_name);
        } else if (result.status === "verified_inactive") {
          setFbrStatus("inactive");
          setFbrTaxpayerName(result.taxpayer_name);
        } else {
          setFbrStatus("not_found");
        }
      })
      .catch(() => {
        setFbrStatus("error");
      });
  }, [extractionResult]);

  // --- Saved Success ---
  if (state === "saved") {
    return (
      <div className="flex flex-col gap-5">
        <Card>
          <div className="bg-success-bg border border-success-base rounded-base px-4 py-3 flex items-center justify-between">
            <div>
              <div className="font-semibold text-xs text-success-dark mb-0.5">
                Invoice saved successfully
              </div>
              <div className="text-2xs text-success-dark">
                Invoice #{savedInvoice?.id} — {savedInvoice?.original_filename}
              </div>
            </div>
            <Button variant="success" size="sm" onClick={onDiscard}>
              Upload Another
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  // --- Error during save ---
  if (state === "error" && error) {
    return (
      <div className="flex flex-col gap-5">
        <Card>
          <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-3">
            <div className="font-semibold text-xs text-danger-dark mb-1">
              Save Error
            </div>
            <div className="text-2xs text-danger-dark">{error}</div>
            <Button variant="secondary" size="xs" onClick={onDiscard} className="mt-3">
              Back to Upload
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (!extractionResult) return null;

  return (
    <div className="flex flex-col gap-5">
      {/* File info bar */}
      <div className="flex items-center justify-between bg-neutral-0 border border-neutral-100 rounded-base px-4 py-2.5 shadow-xs">
        <div className="flex items-center gap-3">
          <span className="text-base">&#128196;</span>
          <div>
            <span className="text-xs font-semibold text-neutral-800">
              {file?.name || extractionResult.original_filename}
            </span>
            <span className="text-2xs text-neutral-500 ml-2">
              {file ? `${(file.size / 1024).toFixed(0)} KB` : ""}
              {extractionResult.page_count
                ? ` · ${extractionResult.page_count} page${extractionResult.page_count !== 1 ? "s" : ""}`
                : ""}
            </span>
          </div>
          <Badge status="info" label="Extraction Complete" size="xs" />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRawDrawerOpen(true)}
            className="flex items-center gap-1.5 text-2xs font-medium text-neutral-500 hover:text-brand-600
                       bg-transparent border border-neutral-200 hover:border-brand-300 rounded px-2.5 py-1.5
                       cursor-pointer transition-colors"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
              <path d="M4.5 2.5h-2a1 1 0 00-1 1v9a1 1 0 001 1h11a1 1 0 001-1v-9a1 1 0 00-1-1h-2" strokeLinecap="round" />
              <path d="M5 5.5l-2 2.5 2 2.5M11 5.5l2 2.5-2 2.5M9 4.5l-2 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Raw Output
          </button>
          <Button variant="ghost" size="xs" onClick={onDiscard}>
            &#10005; Discard &amp; Upload New
          </Button>
        </div>
      </div>

      {/* Raw Document AI Output — full-screen overlay */}
      <RawOutputViewer
        open={rawDrawerOpen}
        onClose={() => setRawDrawerOpen(false)}
        data={extractionResult}
      />

      {/* Items needing attention — anomalies detected during extraction */}
      <AttentionFlagsPanel flags={extractionResult.attention_flags} />

      {/* KPI Summary */}
      <ExtractionKPIs result={extractionResult} />

      {/* Supplier Information */}
      <SupplierInfoCard
        supplierFields={extractSupplierInfo(extractionResult).fields}
        taxPayerStatus={fbrStatus}
        taxpayerName={fbrTaxpayerName}
        erpStatus={erpStatus}
      />

      {/* Invoice Information — full width */}
      <InvoiceInfoCard fields={getNonSupplierFields(extractionResult.fields)} />

      {/* Line Items — full width */}
      <LineItemsTable
        lineItems={extractionResult.line_items}
        taxSummary={buildTaxSummary(extractionResult)}
        lineItemsSource={extractionResult.line_items_source || "document_ai"}
        onOverridesChange={onLineItemOverridesChange}
      />

      {/* Tax Details */}
      <SalesTaxCard
        fields={extractionResult.fields}
        lineItems={extractionResult.line_items}
        detectedTaxes={extractionResult.detected_taxes || []}
        taxSummary={extractionResult.tax_summary}
        geminiConfidence={extractionResult.gemini_confidence}
        geminiProcessingTimeMs={extractionResult.gemini_processing_time_ms}
      />

      {/* Workflow Actions */}
      <WorkflowActions
        onDiscard={onDiscard}
        onSaveDraft={() => onSave("draft")}
        onSubmit={() => onSave("pending_processing")}
        saving={state === "saving"}
      />
    </div>
  );
}
