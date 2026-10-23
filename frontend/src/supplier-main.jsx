import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import SupplierApp from "./SupplierApp.jsx";

// The supplier app's routes live under /supplier/*. Direct hits on the raw
// entry points (/supplier.html or /supplier) don't match the router basename,
// so normalize them to the dashboard before the router mounts.
if (/^\/supplier(\.html)?\/?$/.test(window.location.pathname)) {
  window.history.replaceState(null, "", "/supplier/dashboard");
}

createRoot(document.getElementById("supplier-root")).render(
  <StrictMode>
    <BrowserRouter basename="/supplier">
      <SupplierApp />
    </BrowserRouter>
  </StrictMode>
);
