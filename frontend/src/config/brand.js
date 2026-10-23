// Brand shown in browser-tab titles: this instance serves only Lucky Cement Limited.
// It is fixed — no hostname sniffing (the shared-build hostname test was
// dropped when the repo was split per customer; it silently broke whenever
// the deploy hostname changed). The static <title> in index.html and
// supplier.html must match it.
export function getBrandName() {
  return "Lucky Cement Limited";
}

// Browser-tab title: "<page> · <brand>", e.g. "Invoice Detail · Lucky Cement Limited".
export function pageDocumentTitle(pageTitle) {
  const brand = getBrandName();
  return pageTitle ? `${pageTitle} · ${brand}` : brand;
}
