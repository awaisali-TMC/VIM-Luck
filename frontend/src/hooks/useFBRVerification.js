import { useState, useCallback } from "react";
import { verifyInvoiceFBR } from "../services/fbrService";

export default function useFBRVerification() {
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);

  const verify = useCallback(async (invoiceId) => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const data = await verifyInvoiceFBR(invoiceId);
      setVerifyResult(data);
      return data;
    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      setVerifyError(msg);
      return null;
    } finally {
      setVerifying(false);
    }
  }, []);

  return { verifying, verifyResult, verifyError, verify };
}
