/* eslint-disable react-refresh/only-export-components -- context file intentionally exports the provider + its hook together */
import { createContext, useContext, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { saveInvoice, matchProducts } from "../services/invoiceService";
import { markAttachmentProcessed } from "../services/emailService";

const ExtractionContext = createContext(null);

export function useExtraction() {
  const ctx = useContext(ExtractionContext);
  if (!ctx) {
    throw new Error("useExtraction must be used within an ExtractionProvider");
  }
  return ctx;
}

/**
 * Holds the in-flight extraction-results state that cannot live in the URL.
 *
 * Shape exposed via context:
 *  - extractionFile, extractionResult, savedInvoice
 *  - resultsState ("extracted" | "saving" | "saved" | "error"), resultsError
 *  - lineItemOverrides, setLineItemOverrides
 *  - discardTarget (route path the Discard button returns to)
 *  - pendingEmailAttachmentId, pendingEmailFrom
 *  - handleExtractionComplete(file, result)       — from UploadInvoicePage
 *  - handleEmailExtractionComplete(filename, size, result, attachmentId, from) — from AdminEmailInboxPage
 *  - handleSave(status)                           — from ExtractionResultsPage
 *  - handleDiscardResults()                       — from ExtractionResultsPage
 */
export function ExtractionProvider({ children }) {
  const navigate = useNavigate();

  const [extractionFile, setExtractionFile] = useState(null);
  const [extractionResult, setExtractionResult] = useState(null);
  const [savedInvoice, setSavedInvoice] = useState(null);
  const [resultsState, setResultsState] = useState("extracted");
  const [resultsError, setResultsError] = useState(null);
  const [lineItemOverrides, setLineItemOverrides] = useState({});
  const [discardTarget, setDiscardTarget] = useState("/upload");
  const [pendingEmailAttachmentId, setPendingEmailAttachmentId] = useState(null);
  const [pendingEmailFrom, setPendingEmailFrom] = useState(null);

  // Called by UploadInvoicePage when extraction finishes
  const handleExtractionComplete = useCallback((file, result) => {
    setExtractionFile(file);
    if (result && (!result.line_items || result.line_items.length === 0)) {
      const fieldMap = {};
      for (const f of (result.fields || [])) {
        fieldMap[f.field_name] = f.value;
      }
      const totalRaw = fieldMap.total_amount;
      const totalAmount = totalRaw ? parseFloat(String(totalRaw).replace(/,/g, "")) : 0;
      result = {
        ...result,
        line_items: [{
          description: "N/A",
          quantity: 1,
          unit: "",
          unit_price: totalAmount || 0,
          amount: totalAmount || 0,
        }],
      };
    }

    if (result?.line_items) {
      result = {
        ...result,
        line_items: result.line_items.map((li) => {
          const qty = parseFloat(li.quantity);
          const amount = parseFloat(li.amount);
          return {
            ...li,
            unit_price: qty && amount ? Math.round((amount / qty) * 100) / 100 : li.unit_price,
          };
        }),
      };
    }
    setExtractionResult(result);
    setSavedInvoice(null);
    setResultsState("extracted");
    setResultsError(null);
    setLineItemOverrides({});
    setDiscardTarget("/upload");
    setPendingEmailAttachmentId(null);
    setPendingEmailFrom(null);
    navigate("/results");
  }, [navigate]);

  // Called by AdminEmailInboxPage when an attachment is ready for review
  const handleEmailExtractionComplete = useCallback((filename, fileSize, result, attachmentId, fromAddress) => {
    let enriched = result;
    if (enriched && (!enriched.line_items || enriched.line_items.length === 0)) {
      const fieldMap = {};
      for (const f of (enriched.fields || [])) {
        fieldMap[f.field_name] = f.value;
      }
      const totalRaw = fieldMap.total_amount;
      const totalAmount = totalRaw ? parseFloat(String(totalRaw).replace(/,/g, "")) : 0;
      enriched = {
        ...enriched,
        line_items: [{
          description: "N/A",
          quantity: 1,
          unit: "",
          unit_price: totalAmount || 0,
          amount: totalAmount || 0,
        }],
      };
    }
    if (enriched?.line_items) {
      enriched = {
        ...enriched,
        line_items: enriched.line_items.map((li) => {
          const qty = parseFloat(li.quantity);
          const amount = parseFloat(li.amount);
          return {
            ...li,
            unit_price: qty && amount ? Math.round((amount / qty) * 100) / 100 : li.unit_price,
          };
        }),
      };
    }
    setExtractionFile({ name: filename, size: fileSize || 0 });
    setExtractionResult(enriched);
    setSavedInvoice(null);
    setResultsState("extracted");
    setResultsError(null);
    setLineItemOverrides({});
    setDiscardTarget("/email-inbox");
    setPendingEmailAttachmentId(attachmentId || null);
    setPendingEmailFrom(fromAddress || null);
    navigate("/results");
  }, [navigate]);

  const resetExtraction = useCallback(() => {
    setExtractionFile(null);
    setExtractionResult(null);
    setSavedInvoice(null);
    setResultsState("extracted");
    setResultsError(null);
    setLineItemOverrides({});
    setDiscardTarget("/upload");
    setPendingEmailAttachmentId(null);
    setPendingEmailFrom(null);
  }, []);

  // Called by ExtractionResultsPage to save invoice
  const handleSave = useCallback(
    async (status = "draft") => {
      if (!extractionResult) return;
      setResultsState("saving");
      setResultsError(null);

      try {
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
          mime_type: extractionFile?.type || "application/pdf",
          file_size_bytes: extractionFile?.size || null,
          page_count: extractionResult.page_count,
          status,
          source_type: pendingEmailAttachmentId ? "email" : "web_upload",
          source_email_id: pendingEmailAttachmentId || null,
          source_email_from: pendingEmailFrom || null,
          line_items: extractionResult.line_items.map((li, idx) => {
            const getOverride = (colKey) => {
              const key = `${idx}-${colKey}`;
              return key in lineItemOverrides ? lineItemOverrides[key] : undefined;
            };
            const descOverride = getOverride("description");
            const qtyOverride = getOverride("quantity");
            const unitOverride = getOverride("unit");
            const rateOverride = getOverride("unit_price");
            const amtOverride = getOverride("amount");
            const hasOverride =
              descOverride !== undefined ||
              qtyOverride !== undefined ||
              unitOverride !== undefined ||
              rateOverride !== undefined ||
              amtOverride !== undefined;

            return {
              description: descOverride !== undefined ? descOverride : li.description,
              quantity: qtyOverride !== undefined ? qtyOverride : li.quantity,
              unit: unitOverride !== undefined ? unitOverride : li.unit,
              unit_price: rateOverride !== undefined ? rateOverride : li.unit_price,
              amount: amtOverride !== undefined ? amtOverride : li.amount,
              ai_description: li.description,
              ai_quantity: li.quantity,
              ai_unit: li.unit,
              ai_unit_price: li.unit_price,
              ai_amount: li.amount,
              description_confidence: li.description_confidence,
              quantity_confidence: li.quantity_confidence,
              unit_price_confidence: li.unit_price_confidence,
              amount_confidence: li.amount_confidence,
              user_modified: hasOverride,
            };
          }),
        };

        const saved = await saveInvoice(payload);
        if (status === "pending_processing" && saved?.id) {
          matchProducts(saved.id).catch(() => {});
        }
        if (pendingEmailAttachmentId && saved?.id) {
          markAttachmentProcessed(pendingEmailAttachmentId, saved.id).catch(() => {});
        }
        resetExtraction();
        navigate("/invoices");
      } catch (err) {
        const message =
          err.response?.data?.detail || err.message || "Save failed";
        setResultsError(message);
        setResultsState("error");
      }
    },
    [extractionResult, extractionFile, lineItemOverrides, pendingEmailAttachmentId, pendingEmailFrom, navigate, resetExtraction]
  );

  const handleDiscardResults = useCallback(() => {
    const target = discardTarget;
    resetExtraction();
    navigate(target);
  }, [discardTarget, navigate, resetExtraction]);

  const value = {
    extractionFile,
    extractionResult,
    savedInvoice,
    resultsState,
    resultsError,
    lineItemOverrides,
    setLineItemOverrides,
    discardTarget,
    pendingEmailAttachmentId,
    pendingEmailFrom,
    handleExtractionComplete,
    handleEmailExtractionComplete,
    handleSave,
    handleDiscardResults,
  };

  return (
    <ExtractionContext.Provider value={value}>
      {children}
    </ExtractionContext.Provider>
  );
}
