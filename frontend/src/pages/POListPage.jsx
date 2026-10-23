import { useState, useEffect, useMemo, useCallback } from "react";
import { getPurchaseOrders } from "../services/purchaseOrderService";
import { syncAllSAPPOs, testSAPConnection } from "../services/sapService";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import KpiCard from "../components/common/KpiCard";
import TabBar from "../components/common/TabBar";
import FilterBar from "../components/common/FilterBar";
import DataTable from "../components/common/DataTable";
import Modal from "../components/common/Modal";
import { tokens } from "../styles/tokens";

export default function POListPage({ onViewPO, onCreatePO }) {
  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const perPage = 10;

  // SAP sync state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [sapConnected, setSapConnected] = useState(null); // null = unknown, true/false

  const loadPOs = useCallback(async () => {
    try {
      const data = await getPurchaseOrders(0, 200);
      setPurchaseOrders(data.purchase_orders || []);
      setTotal(data.total || 0);
    } catch {
      // API not available yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPOs(); }, [loadPOs]);

  // Check SAP connection on mount
  useEffect(() => {
    testSAPConnection()
      .then((res) => setSapConnected(res.connected))
      .catch(() => setSapConnected(false));
  }, []);

  const handleSyncFromSAP = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await syncAllSAPPOs(100);
      setSyncResult(result);
      await loadPOs(); // refresh the list
    } catch (err) {
      setSyncResult({ error: err.response?.data?.detail || "SAP sync failed" });
    } finally {
      setSyncing(false);
    }
  };

  // Status counts
  const statusCounts = useMemo(() => {
    const counts = { all: purchaseOrders.length, open: 0, partial: 0, received: 0, closed: 0 };
    for (const po of purchaseOrders) {
      if (po.status === "open" || po.status === "draft") counts.open++;
      if (po.status === "partially_received") counts.partial++;
      if (po.status === "fully_received") counts.received++;
      if (po.status === "closed" || po.status === "cancelled") counts.closed++;
    }
    return counts;
  }, [purchaseOrders]);

  // Tab filter
  const tabFiltered = useMemo(() => {
    if (tab === "all") return purchaseOrders;
    if (tab === "open") return purchaseOrders.filter((po) => ["open", "draft"].includes(po.status));
    if (tab === "partial") return purchaseOrders.filter((po) => po.status === "partially_received");
    if (tab === "received") return purchaseOrders.filter((po) => po.status === "fully_received");
    if (tab === "closed") return purchaseOrders.filter((po) => ["closed", "cancelled"].includes(po.status));
    return purchaseOrders;
  }, [purchaseOrders, tab]);

  // Search filter
  const searchFiltered = useMemo(() => {
    if (!search.trim()) return tabFiltered;
    const q = search.toLowerCase();
    return tabFiltered.filter(
      (po) =>
        (po.po_number || "").toLowerCase().includes(q) ||
        (po.vendor_name || "").toLowerCase().includes(q) ||
        String(po.id).includes(q)
    );
  }, [tabFiltered, search]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(searchFiltered.length / perPage));
  const paginated = searchFiltered.slice((page - 1) * perPage, page * perPage);

  useEffect(() => { setPage(1); }, [tab, search]);

  // Compute total PO value
  const totalValue = useMemo(() => {
    return purchaseOrders.reduce((sum, po) => sum + (po.total_amount || 0), 0);
  }, [purchaseOrders]);

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8 text-xs text-neutral-500">Loading purchase orders...</div>
      </Card>
    );
  }

  if (purchaseOrders.length === 0) {
    return (
      <Card>
        <div className="text-center py-12">
          <div className="text-[40px] mb-3">&#128230;</div>
          <div className="text-sm font-semibold text-neutral-800 mb-1">No purchase orders yet</div>
          <div className="text-xs text-neutral-500 mb-4">Create or upload your first PO to get started</div>
          <Button variant="primary" size="sm" onClick={onCreatePO}>
            + Create Purchase Order
          </Button>
        </div>
      </Card>
    );
  }

  const columns = [
    {
      key: "po_number", label: "PO Number",
      render: (v, row) => (
        <span
          className="text-brand-600 font-semibold cursor-pointer hover:underline"
          onClick={(e) => { e.stopPropagation(); onViewPO?.(row.id); }}
        >
          {v}
        </span>
      ),
    },
    { key: "vendor_name", label: "Vendor", render: (v) => v || "\u2014" },
    {
      key: "po_type", label: "Type",
      render: (v) => (
        <span className="capitalize text-neutral-600 text-2xs font-medium bg-neutral-50 px-2 py-0.5 rounded-full">
          {v}
        </span>
      ),
    },
    {
      key: "total_amount", label: "Amount", align: "right",
      render: (v, row) => (
        <span className="font-semibold font-mono text-xs whitespace-nowrap text-neutral-900">
          {v != null ? `${row.currency || "PKR"} ${Number(v).toLocaleString()}` : "\u2014"}
        </span>
      ),
    },
    {
      key: "po_date", label: "Date",
      render: (v) => <span className="text-neutral-500 whitespace-nowrap">{v || "\u2014"}</span>,
    },
    {
      key: "line_items", label: "Items",
      render: (v) => <span className="text-neutral-600">{v?.length || 0}</span>,
    },
    {
      key: "source_type", label: "Source",
      render: (v) => {
        if (v === "sap") return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold bg-blue-50 border border-blue-200 text-blue-700">
            SAP
          </span>
        );
        if (v === "file_upload") return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold bg-purple-50 border border-purple-200 text-purple-700">
            Upload
          </span>
        );
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-semibold bg-neutral-50 border border-neutral-200 text-neutral-600">
            Manual
          </span>
        );
      },
    },
    { key: "status", label: "Status", render: (v) => <Badge status={v} /> },
    {
      key: "_actions", label: "",
      render: (_, row) => (
        <Button
          variant="primary"
          size="xs"
          onClick={(e) => { e.stopPropagation(); onViewPO?.(row.id); }}
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <div>
      {/* KPIs */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <KpiCard size="lg" label="Total POs" value={String(statusCounts.all)} sub={`PKR ${Math.round(totalValue).toLocaleString()}`} accentColor={tokens.color.brand[500]} icon="&#128230;" />
        <KpiCard size="lg" label="Open" value={String(statusCounts.open)} sub="Active orders" accentColor={tokens.color.status.info.base} icon="&#128196;" />
        <KpiCard size="lg" label="Partially Received" value={String(statusCounts.partial)} sub="In progress" accentColor={tokens.color.status.warning.base} icon="&#128666;" />
        <KpiCard size="lg" label="Fully Received" value={String(statusCounts.received)} sub="Ready to match" accentColor={tokens.color.status.success.base} icon="&#9989;" />
        <KpiCard size="lg" label="Closed" value={String(statusCounts.closed)} sub="Completed" accentColor={tokens.color.status.posted.base} icon="&#128274;" />
      </div>

      {/* SAP Sync Result */}
      {syncResult && (
        <div className={`mb-4 rounded-base px-4 py-3 text-xs font-medium ${
          syncResult.error
            ? "bg-danger-bg border border-danger-base text-danger-dark"
            : "bg-success-bg border border-success-base text-success-dark"
        }`}>
          {syncResult.error
            ? syncResult.error
            : `SAP Sync: ${syncResult.synced} new POs imported, ${syncResult.skipped} already existed (${syncResult.total_in_sap} in SAP)`}
          <button
            onClick={() => setSyncResult(null)}
            className="ml-3 text-2xs bg-transparent border-none cursor-pointer underline opacity-70 hover:opacity-100"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* SAP Connection Status */}
      {sapConnected === true && (
        <div className="mb-4 flex items-center gap-2 text-2xs text-blue-600">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          SAP connected (S/4HANA)
        </div>
      )}

      {/* Main Table Card */}
      <Card
        title="Purchase Orders"
        action={
          <div className="flex items-center gap-2">
            {sapConnected && (
              <Button
                variant="secondary"
                size="xs"
                onClick={handleSyncFromSAP}
                disabled={syncing}
              >
                {syncing ? "Syncing..." : "Sync from SAP"}
              </Button>
            )}
            <Button variant="secondary" size="xs">&#8595; Export</Button>
            <Button variant="primary" size="xs" onClick={onCreatePO}>
              + Upload PO
            </Button>
          </div>
        }
        noPad
      >
        <div className="px-5 pt-3">
          <TabBar
            active={tab}
            onChange={setTab}
            tabs={[
              { key: "all", label: "All POs", count: statusCounts.all },
              { key: "open", label: "Open", count: statusCounts.open },
              { key: "partial", label: "Partial Receipt", count: statusCounts.partial },
              { key: "received", label: "Fully Received", count: statusCounts.received },
              { key: "closed", label: "Closed", count: statusCounts.closed },
            ]}
          />
          <FilterBar
            filters={[
              { type: "search", placeholder: "Search PO number, vendor...", value: search, onChange: (e) => setSearch(e.target.value) },
            ]}
          />
        </div>
        <DataTable columns={columns} data={paginated} onRowClick={(row) => onViewPO?.(row.id)} />
        <div className="flex items-center justify-between px-5 py-3 text-2xs text-neutral-500">
          <span>Showing {paginated.length} of {searchFiltered.length} purchase orders</span>
          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1).slice(0, 8).map((p) => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={`w-7 h-7 rounded-base border text-[11px] font-semibold cursor-pointer transition-colors ${
                  p === page
                    ? "border-brand-600 bg-brand-600 text-white"
                    : "border-neutral-200 bg-neutral-0 text-neutral-600 hover:bg-neutral-50"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
