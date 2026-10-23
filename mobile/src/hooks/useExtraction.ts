import { useState, useCallback } from 'react';
import { uploadInvoice, uploadInvoiceBatch, type PickedUpload } from '../services/invoiceService';
import { processExtractionResult } from '../services/calculations';
import { isBatchResult } from '../types';
import type { ExtractionResult, BatchUploadResult } from '../types';

export type PickedFile = PickedUpload & { size: number };

export interface ExtractionState {
  file: PickedFile | null;
  result: ExtractionResult | null;
  batch: BatchUploadResult | null;
  loading: boolean;
  error: string | null;
}

export default function useExtraction() {
  const [state, setState] = useState<ExtractionState>({
    file: null,
    result: null,
    batch: null,
    loading: false,
    error: null,
  });

  const selectFile = useCallback((file: PickedFile) => {
    setState({ file, result: null, batch: null, loading: false, error: null });
  }, []);

  // Extract the single selected file. A file that turns out to hold several
  // invoices comes back as a batch (drafts saved server-side) — surfaced via
  // `batch` instead of `result` so the caller skips the review screen.
  const extract = useCallback(async () => {
    if (!state.file) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const raw = await uploadInvoice(state.file);
      if (isBatchResult(raw)) {
        setState((s) => ({ ...s, batch: raw, loading: false }));
      } else {
        const result = processExtractionResult(raw);
        setState((s) => ({ ...s, result, loading: false }));
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Extraction failed';
      setState((s) => ({ ...s, error: msg, loading: false }));
    }
  }, [state.file]);

  // Upload several files (or scanned pages) at once — always a batch of drafts.
  const extractFiles = useCallback(async (files: PickedUpload[]) => {
    if (!files.length) return;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const batch = await uploadInvoiceBatch(files);
      if (!batch.invoices?.length) {
        const msgs = (batch.errors || []).map((e) => `${e.file}: ${e.error}`).join('; ');
        throw new Error(msgs || 'No invoices could be processed.');
      }
      setState((s) => ({ ...s, batch, loading: false }));
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Upload failed';
      setState((s) => ({ ...s, error: msg, loading: false }));
    }
  }, []);

  const reset = useCallback(() => {
    setState({ file: null, result: null, batch: null, loading: false, error: null });
  }, []);

  return {
    ...state,
    selectFile,
    extract,
    extractFiles,
    reset,
  };
}
