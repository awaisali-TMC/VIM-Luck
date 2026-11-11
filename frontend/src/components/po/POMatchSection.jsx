import { useState, useEffect, useCallback, useRef } from "react";
import {
  triggerPOMatch,
  getInvoiceMatches,
  autoSuggestPO,
  deleteMatchResult,
} from "../../services/purchaseOrderService";
import { syncSAPGRN } from "../../services/sapService";
import POSearchBox from "./POSearchBox";
import SAPGRNFetch from "./SAPGRNFetch";
import Card from "../common/Card";
import Badge from "../common/Badge";
import Button from "../common/Button";

export default function POMatchSection({ invoiceId, poReference, onMatched, readOnly = false }) {
  const [selectedPO, setSelectedPO] = useState(null);
  const [matchType, setMatchType] = useState("2-way");
  const [matching, setMatching] = useState(false);
  const [matchResults, setMatchResults] = useState([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [, setLoadingSuggestions] = useState(false);
  const [error, setError] = useState(null);
  const [warning, setWarning] = useState(null);
  const [expandedResult, setExpandedResult] = useState(null);
  const [grnQuery, setGrnQuery] = useState("");   // text in the GRN field (for enabling Run)
  const grnRef = useRef(null);                      // imperative handle on SAPGRNFetch

  // Load existing match results
  const loadMatches = useCallback(async () => {
    if (!invoiceId) return;
    setLoadingResults(true);
    try {
      const results = await getInvoiceMatches(invoiceId);
      setMatchResults(results || []);
      if (results?.length > 0) {
        setExpandedResult(results[0].id);
      }
    } catch {
      // ignore
    } finally {
      setLoadingResults(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  // Auto-suggest on load if poReference exists
  useEffect(() => {
    if (!poReference || !invoiceId) return;
    setLoadingSuggestions(true);
    autoSuggestPO(invoiceId)
      .then((data) => setSuggestions(data || []))
      .catch(() => {})
      .finally(() => setLoadingSuggestions(false));
  }, [invoiceId, poReference]);

  const handleRunMatch = useCallback(async (poOverride) => {
    const po = poOverride || selectedPO;
    if (!po) {
      setError("Please select a Purchase Order first.");
      return;
    }
    setMatching(true);
    setError(null);
    setWarning(null);
    try {
      // For 3-way, make sure the PO's goods receipts are imported from SAP first.
      // Otherwise the engine sees received=0 and every line fails the 3-way check
      // (the GRN/SES column stays empty). Best-effort: if there are no GRNs in SAP
      // or the sync fails, proceed and let the match reflect received=0.
      if (matchType === "3-way" && po.po_number) {
        try {
          const grnRes = await syncSAPGRN(po.po_number);
          if ((grnRes?.total_in_sap ?? 0) === 0) {
            setWarning(
              `No goods receipts found in SAP for PO ${po.po_number}. ` +
              `A 3-way match needs a goods receipt, so it can't pass — switch to 2-Way, ` +
              `or run again once the GR is posted in SAP.`
            );
          }
        } catch {
          /* no GRNs in SAP / sync failed — continue with whatever is local */
        }
      }
      await triggerPOMatch(invoiceId, po.id, matchType);
      await loadMatches();
      onMatched?.();  // tell the page to refetch the invoice (matched_po_id is now set)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Matching failed");
    } finally {
      setMatching(false);
    }
  }, [invoiceId, selectedPO, matchType, loadMatches, onMatched]);

  // Single-button flow: for 3-way, resolve/select the PO typed in the GRN field
  // and load its GRNs, then run the match — fetch and match in one click.
  const handleFetchAndMatch = useCallback(async () => {
    let po = selectedPO;
    if (matchType === "3-way" && grnRef.current) {
      try {
        const resolved = await grnRef.current.resolveAndFetch();
        if (resolved) po = resolved;
      } catch { /* fall back to selectedPO */ }
    }
    if (!po) {
      setError("Enter or select a Purchase Order first.");
      return;
    }
    await handleRunMatch(po);
  }, [selectedPO, matchType, handleRunMatch]);

  const handleDeleteResult = useCallback(async (matchId) => {
    try {
      await deleteMatchResult(matchId);
      setMatchResults((prev) => prev.filter((r) => r.id !== matchId));
    } catch {
      // ignore
    }
  }, []);

  const handleSuggestionSelect = (suggestion) => {
    setSelectedPO({
      id: suggestion.po_id,
      po_number: suggestion.po_number,
      vendor_name: suggestion.vendor_name,
      total_amount: suggestion.total_amount,
      currency: "PKR",
    });
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Match Trigger Section — hidden for read-only (reviewer) users */}
      {!readOnly && (
      <Card title="PO Matching">
        <div className="flex flex-col gap-4">
          {/* Auto-suggestions */}
          {suggestions.length > 0 && (
            <div>
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">Suggested Purchase Orders</div>
              <div className="flex flex-col gap-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s.po_id}
                    onClick={() => handleSuggestionSelect(s)}
                    className={`flex items-center justify-between px-3 py-2 rounded-base border text-xs cursor-pointer transition-colors ${
                      selectedPO?.id === s.po_id
                        ? "border-brand-400 bg-brand-50 text-brand-700"
                        : "border-neutral-200 bg-neutral-0 hover:bg-neutral-25 text-neutral-700"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-semibold">{s.po_number}</span>
                      <span className="text-neutral-500">{s.vendor_name}</span>
                      <span className={`text-2xs font-semibold px-1.5 py-0.5 rounded-full ${
                        s.confidence >= 0.9 ? "bg-success-bg text-success-dark" :
                        s.confidence >= 0.6 ? "bg-warning-bg text-warning-dark" :
                        "bg-neutral-50 text-neutral-500"
                      }`}>
                        {Math.round(s.confidence * 100)}% match
                      </span>
                    </div>
                    <span className="font-mono text-neutral-600">
                      PKR {s.total_amount != null ? Number(s.total_amount).toLocaleString() : ""}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Manual PO Search */}
          <div>
            <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">
              {suggestions.length > 0 ? "Or search manually" : "Select Purchase Order"}
            </div>
            <POSearchBox onSelect={(po) => setSelectedPO(po)} />
            {selectedPO && (
              <div className="mt-2 flex items-center gap-2 text-xs text-brand-700 bg-brand-50 border border-brand-200 rounded-base px-3 py-2">
                <span className="font-semibold">Selected:</span>
                <span>{selectedPO.po_number}</span>
                <span className="text-neutral-500">{selectedPO.vendor_name}</span>
                <button
                  onClick={() => setSelectedPO(null)}
                  className="ml-auto text-neutral-400 hover:text-danger-dark bg-transparent border-none cursor-pointer"
                >
                  &#x2715;
                </button>
              </div>
            )}
          </div>

          {/* Match Type Toggle */}
          <div className="flex items-center gap-4">
            <div className="text-2xs font-semibold text-neutral-500 uppercase">Match Type:</div>
            <div className="flex gap-2">
              <button
                onClick={() => setMatchType("2-way")}
                className={`px-3 py-1.5 rounded-base text-2xs font-semibold border cursor-pointer transition-colors ${
                  matchType === "2-way"
                    ? "bg-brand-600 text-white border-brand-600"
                    : "bg-neutral-0 text-neutral-600 border-neutral-200 hover:bg-neutral-50"
                }`}
              >
                2-Way (PO vs Invoice)
              </button>
              <button
                onClick={() => setMatchType("3-way")}
                className={`px-3 py-1.5 rounded-base text-2xs font-semibold border cursor-pointer transition-colors ${
                  matchType === "3-way"
                    ? "bg-brand-600 text-white border-brand-600"
                    : "bg-neutral-0 text-neutral-600 border-neutral-200 hover:bg-neutral-50"
                }`}
              >
                3-Way (PO + GRN/SES vs Invoice)
              </button>
            </div>
          </div>

          {/* 3-way needs goods receipts — fetch them live from SAP. The field
              has the same PO type-ahead as the search above and keeps whatever
              PO the user types. "Run 3-Way Match" imports GRNs for the selected
              PO automatically. */}
          {matchType === "3-way" && (
            <div className="pt-1">
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-2">
                Goods Receipts (GRN) — fetch from SAP
              </div>
              <SAPGRNFetch
                ref={grnRef}
                defaultPoNumber={selectedPO?.po_number || poReference || ""}
                onPoSelected={(po) => setSelectedPO(po)}
                onQueryChange={setGrnQuery}
              />
            </div>
          )}

          {error && (
            <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2">
              <span className="text-2xs text-danger-dark font-medium">{error}</span>
            </div>
          )}

          {warning && (
            <div className="bg-warning-bg border border-warning-base rounded-base px-3 py-2">
              <span className="text-2xs text-warning-dark font-medium">&#9888; {warning}</span>
            </div>
          )}

          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              onClick={handleFetchAndMatch}
              disabled={matching || (matchType === "3-way" ? (!selectedPO && !grnQuery.trim()) : !selectedPO)}
            >
              {matching ? "Matching..." : matchType === "3-way" ? "Fetch GRNs & Run 3-Way Match" : "Run 2-Way Match"}
            </Button>
          </div>
        </div>
      </Card>
      )}

      {/* Match Results */}
      {loadingResults ? (
        <Card>
          <div className="text-center py-4 text-xs text-neutral-500">Loading match results...</div>
        </Card>
      ) : matchResults.length > 0 ? (
        matchResults.map((result) => (
          <Card
            key={result.id}
            noPad
          >
            {/* Result Header */}
            <div
              className="flex items-center justify-between px-5 py-3 cursor-pointer hover:bg-neutral-25 transition-colors"
              onClick={() => setExpandedResult(expandedResult === result.id ? null : result.id)}
            >
              <div className="flex items-center gap-3">
                <Badge status={result.match_status} />
                <span className="text-xs font-semibold text-neutral-800">
                  PO: {result.po_number || `#${result.po_id}`}
                </span>
                <span className="text-2xs text-neutral-500">
                  {result.match_type} match
                </span>
                {result.overall_score != null && (
                  <span className={`text-2xs font-bold px-2 py-0.5 rounded-full ${
                    result.overall_score >= 0.9 ? "bg-success-bg text-success-dark" :
                    result.overall_score >= 0.5 ? "bg-warning-bg text-warning-dark" :
                    "bg-danger-bg text-danger-dark"
                  }`}>
                    Score: {Math.round(result.overall_score * 100)}%
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {result.total_amount_diff != null && (
                  <span className={`text-2xs font-mono ${
                    Math.abs(result.total_amount_diff) < 1 ? "text-success-dark" : "text-danger-dark"
                  }`}>
                    Diff: {Number(result.total_amount_diff).toLocaleString()}
                    {result.total_amount_diff_pct != null && ` (${result.total_amount_diff_pct.toFixed(1)}%)`}
                  </span>
                )}
                {!readOnly && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteResult(result.id); }}
                    className="text-neutral-400 hover:text-danger-dark bg-transparent border-none cursor-pointer text-xs ml-2"
                    title="Delete match result"
                  >
                    &#x1F5D1;
                  </button>
                )}
                <span className="text-neutral-400 text-xs ml-1">{expandedResult === result.id ? "\u25B2" : "\u25BC"}</span>
              </div>
            </div>

            {/* Expanded Line Matches */}
            {expandedResult === result.id && (
              <div className="border-t border-neutral-100">
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-neutral-25">
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Status</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">Invoice Line</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-left">PO Line</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-center">Qty</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-center">Price</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Qty Diff</th>
                      <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">Price Diff</th>
                      {result.match_type === "3-way" && (
                        <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase text-right">GRN/SES</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {(result.line_matches || []).map((lm, idx) => (
                      <tr key={lm.id || idx} className={idx % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
                        <td className="px-3 py-2 border-b border-neutral-50">
                          <Badge status={lm.match_status} size="xs" />
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50">
                          <div className="text-neutral-800 truncate max-w-[180px]" title={lm.invoice_line_description}>
                            {lm.invoice_line_description || "\u2014"}
                          </div>
                          {lm.invoice_line_qty != null && (
                            <div className="text-2xs text-neutral-500">
                              Qty: {lm.invoice_line_qty} | Price: {lm.invoice_line_price?.toLocaleString()} | Amt: {lm.invoice_line_amount?.toLocaleString()}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50">
                          <div className="text-neutral-800 truncate max-w-[180px]" title={lm.po_line_description}>
                            {lm.po_line_description || "\u2014"}
                          </div>
                          {lm.po_line_qty != null && (
                            <div className="text-2xs text-neutral-500">
                              Qty: {lm.po_line_qty} | Price: {lm.po_line_price?.toLocaleString()} | Amt: {lm.po_line_amount?.toLocaleString()}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50 text-center">
                          {lm.quantity_match ? (
                            <span className="text-success-dark font-semibold">&#10003;</span>
                          ) : (
                            <span className="text-danger-dark font-semibold">&#10007;</span>
                          )}
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50 text-center">
                          {lm.price_match ? (
                            <span className="text-success-dark font-semibold">&#10003;</span>
                          ) : (
                            <span className="text-danger-dark font-semibold">&#10007;</span>
                          )}
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono text-2xs">
                          {lm.quantity_diff != null ? (
                            <span className={Math.abs(lm.quantity_diff) < 0.01 ? "text-success-dark" : "text-danger-dark"}>
                              {lm.quantity_diff > 0 ? "+" : ""}{lm.quantity_diff.toFixed(2)}
                              {lm.quantity_diff_pct != null && ` (${lm.quantity_diff_pct.toFixed(1)}%)`}
                            </span>
                          ) : "\u2014"}
                        </td>
                        <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono text-2xs">
                          {lm.price_diff != null ? (
                            <span className={Math.abs(lm.price_diff) < 0.01 ? "text-success-dark" : "text-danger-dark"}>
                              {lm.price_diff > 0 ? "+" : ""}{lm.price_diff.toFixed(2)}
                              {lm.price_diff_pct != null && ` (${lm.price_diff_pct.toFixed(1)}%)`}
                            </span>
                          ) : "\u2014"}
                        </td>
                        {result.match_type === "3-way" && (
                          <td className="px-3 py-2 border-b border-neutral-50 text-right font-mono text-2xs text-neutral-600">
                            {lm.grn_received_qty != null && `GRN: ${lm.grn_received_qty}`}
                            {lm.ses_completed_qty != null && `SES: ${lm.ses_completed_qty}`}
                            {lm.grn_received_qty == null && lm.ses_completed_qty == null && "\u2014"}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {/* Reasoning detail */}
                {(result.line_matches || []).some((lm) => lm.reasoning) && (
                  <div className="px-5 py-3 border-t border-neutral-100 bg-neutral-25">
                    <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Match Reasoning</div>
                    {(result.line_matches || []).filter((lm) => lm.reasoning).map((lm, idx) => (
                      <div key={idx} className="text-2xs text-neutral-600 mb-1">
                        <span className="font-medium">{lm.invoice_line_description || `Line ${idx + 1}`}:</span>{" "}
                        {lm.reasoning}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>
        ))
      ) : null}
    </div>
  );
}
