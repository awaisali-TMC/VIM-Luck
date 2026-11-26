// Which SAP transaction an invoice is for, chosen on the upload screen:
//   MIR7 - PO-based invoice (PO match, GRs, parked to SAP)
//   FV60 - invoice without a PO (recorded only: not matched or parked yet)
// Older invoices have no value and count as MIR7.
export function sapTransactionOf(invoiceOrValue) {
  const v = typeof invoiceOrValue === "string" ? invoiceOrValue : invoiceOrValue?.sap_transaction;
  return String(v || "MIR7").toUpperCase() === "FV60" ? "FV60" : "MIR7";
}
