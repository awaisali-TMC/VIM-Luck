import { useCallback, useEffect, useState } from "react";
import Modal from "./Modal";
import Button from "./Button";
import { VIEW_DOCUMENT_EVENT, saveBlob } from "../../utils/invoiceDocument";

// Types the browser renders itself. Anything else (TIFF, unknown) gets a
// Download button instead of a blank frame.
const FRAME_TYPES = ["application/pdf"];
const IMAGE_TYPES = ["image/jpeg", "image/png"];

/**
 * In-page viewer for an invoice's file. Mounted once (App.jsx); opened by
 * viewBlob() when "View" could not open a new tab — a blocked popup, which is
 * always the case in embedded previews.
 */
export default function DocumentViewer() {
  const [doc, setDoc] = useState(null); // { blob, filename, url }

  useEffect(() => {
    const onView = (e) => {
      const { blob, filename } = e.detail;
      setDoc({ blob, filename, url: URL.createObjectURL(blob) });
    };
    window.addEventListener(VIEW_DOCUMENT_EVENT, onView);
    return () => window.removeEventListener(VIEW_DOCUMENT_EVENT, onView);
  }, []);

  // Free each object URL once its document is closed or replaced.
  useEffect(() => {
    if (!doc) return undefined;
    return () => URL.revokeObjectURL(doc.url);
  }, [doc]);

  const close = useCallback(() => setDoc(null), []);

  if (!doc) return null;
  const name = doc.filename || "Invoice document";
  const type = doc.blob.type;

  return (
    <Modal
      open
      onClose={close}
      title={name}
      width={960}
      footer={
        <>
          <Button variant="secondary" onClick={close}>Close</Button>
          <Button onClick={() => saveBlob(doc.blob, doc.filename)}>Download</Button>
        </>
      }
    >
      {FRAME_TYPES.includes(type) ? (
        <iframe title={name} src={doc.url} className="block w-full h-[68vh] border-0" />
      ) : IMAGE_TYPES.includes(type) ? (
        <img src={doc.url} alt={name} className="block max-w-full mx-auto" />
      ) : (
        <p className="m-0 text-sm text-neutral-600">
          This file type can't be shown in the browser. Download it to open it.
        </p>
      )}
    </Modal>
  );
}
