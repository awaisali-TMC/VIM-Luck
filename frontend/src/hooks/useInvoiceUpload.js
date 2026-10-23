import { useState, useCallback } from "react";
import { uploadInvoice, saveInvoice } from "../services/invoiceService";

/**
 * State machine for invoice upload flow:
 * idle -> extracting -> extracted -> saving -> saved
 *                    -> error
 */
export default function useInvoiceUpload() {
  const [state, setState] = useState("idle");
  const [file, setFile] = useState(null);
  const [extractionResult, setExtractionResult] = useState(null);
  const [savedInvoice, setSavedInvoice] = useState(null);
  const [error, setError] = useState(null);

  const handleFileSelected = useCallback(async (selectedFile) => {
    setFile(selectedFile);
    setState("extracting");
    setError(null);
    setExtractionResult(null);
    setSavedInvoice(null);

    try {
      const result = await uploadInvoice(selectedFile);
      setExtractionResult(result);
      setState("extracted");
    } catch (err) {
      const message =
        err.response?.data?.detail || err.message || "Upload failed";
      setError(message);
      setState("error");
    }
  }, []);

  const handleSave = useCallback(
    async (status = "draft") => {
      if (!extractionResult) return;
      setState("saving");
      setError(null);

      try {
        // Build save payload from extraction result
        const fieldMap = {};
        for (const f of extractionResult.fields) {
          fieldMap[f.field_name] = f.value;
        }

        const confMap = {};
        for (const f of extractionResult.fields) {
          confMap[f.field_name] = f.confidence;
        }

        const payload = {
          invoice_number: fieldMap.invoice_id || fieldMap.invoice_number || null,
          invoice_date: fieldMap.invoice_date || null,
          due_date: fieldMap.due_date || null,
          currency: fieldMap.currency || "PKR",
          supplier_name: fieldMap.supplier_name || null,
          supplier_address: fieldMap.supplier_address || null,
          supplier_ntn: fieldMap.supplier_tax_id || null,
          receiver_name: fieldMap.receiver_name || null,
          receiver_address: fieldMap.receiver_address || null,
          subtotal_amount: parseFloat(String(fieldMap.net_amount || "").replace(/,/g, "")) || null,
          tax_amount: parseFloat(String(fieldMap.total_tax_amount || "").replace(/,/g, "")) || null,
          total_amount: parseFloat(String(fieldMap.total_amount || "").replace(/,/g, "")) || null,
          gst_amount: null,
          wht_amount: null,
          po_reference: fieldMap.purchase_order || null,
          bank_iban: fieldMap.remit_to_address || null,
          document_type: extractionResult.document_type,
          overall_confidence: extractionResult.overall_confidence,
          field_confidences: confMap,
          warnings: extractionResult.warnings,
          processing_time_ms: extractionResult.processing_time_ms,
          original_filename: extractionResult.original_filename,
          stored_filepath: extractionResult.stored_filepath,
          mime_type: file?.type || "application/pdf",
          file_size_bytes: file?.size || null,
          page_count: extractionResult.page_count,
          status,
          line_items: extractionResult.line_items.map((li) => ({
            description: li.description,
            quantity: li.quantity,
            unit: li.unit,
            unit_price: li.unit_price,
            amount: li.amount,
            description_confidence: li.description_confidence,
            quantity_confidence: li.quantity_confidence,
            unit_price_confidence: li.unit_price_confidence,
            amount_confidence: li.amount_confidence,
          })),
        };

        const saved = await saveInvoice(payload);
        setSavedInvoice(saved);
        setState("saved");
      } catch (err) {
        const message =
          err.response?.data?.detail || err.message || "Save failed";
        setError(message);
        setState("error");
      }
    },
    [extractionResult, file]
  );

  const handleDiscard = useCallback(() => {
    setFile(null);
    setExtractionResult(null);
    setSavedInvoice(null);
    setError(null);
    setState("idle");
  }, []);

  return {
    state,
    file,
    extractionResult,
    savedInvoice,
    error,
    handleFileSelected,
    handleSave,
    handleDiscard,
  };
}
