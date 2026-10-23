import { useState } from "react";
import usePODetail from "../hooks/usePODetail";
import Card from "../components/common/Card";
import Badge from "../components/common/Badge";
import Button from "../components/common/Button";
import KpiCard from "../components/common/KpiCard";
import Spinner from "../components/common/Spinner";
import DataTable from "../components/common/DataTable";
import CreateGRNModal from "../components/po/CreateGRNModal";
import CreateSESModal from "../components/po/CreateSESModal";
import { tokens } from "../styles/tokens";

const STATUS_ACTIONS = {
  draft: [
    { label: "Open PO", variant: "primary", targetStatus: "open" },
  ],
  open: [
    { label: "Close PO", variant: "secondary", targetStatus: "closed" },
    { label: "Cancel PO", variant: "danger", targetStatus: "cancelled" },
  ],
  partially_received: [
    { label: "Close PO", variant: "secondary", targetStatus: "closed" },
  ],
  fully_received: [
    { label: "Close PO", variant: "primary", targetStatus: "closed" },
  ],
  closed: [],
  cancelled: [],
};

export default function PODetailPage({ poId, onBack }) {
  const {
    po,
    loading,
    error,
    editing,
    editFields,
    editLineItems,
    saving,
    startEditing,
    cancelEditing,
    handleFieldChange,
    handleLineItemChange,
    addLineItem,
    removeLineItem,
    saveEdits,
    changeStatus,
    refreshPO,
  } = usePODetail(poId);

  const [grnModalOpen, setGrnModalOpen] = useState(false);
  const [sesModalOpen, setSesModalOpen] = useState(false);

  if (loading) {
    return (
      <Card>
        <Spinner text="Loading purchase order..." subtext="Fetching PO details" />
      </Card>
    );
  }

  if (error && !po) {
    return (
      <Card>
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-3">
          <div className="font-semibold text-xs text-danger-dark mb-1">Failed to Load PO</div>
          <div className="text-2xs text-danger-dark mb-3">{error}</div>
          <Button variant="secondary" size="sm" onClick={onBack}>&larr; Back to List</Button>
        </div>
      </Card>
    );
  }

  if (!po) return null;

  const actions = STATUS_ACTIONS[po.status] || [];
  const canEdit = !["closed", "cancelled"].includes(po.status);
  const canAddGRN = ["open", "partially_received"].includes(po.status) && ["local", "foreign"].includes(po.po_type);
  const canAddSES = ["open", "partially_received"].includes(po.status) && po.po_type === "contract";
  const lineItemCount = po.line_items?.length || 0;
  const grnCount = po.grns?.length || 0;
  const sesCount = po.ses_records?.length || 0;

  // Calculate received quantities per PO line
  const receivedQtyMap = {};
  for (const grn of (po.grns || [])) {
    for (const li of (grn.line_items || [])) {
      receivedQtyMap[li.po_line_item_id] = (receivedQtyMap[li.po_line_item_id] || 0) + li.received_quantity;
    }
  }
  for (const ses of (po.ses_records || [])) {
    for (const li of (ses.line_items || [])) {
      receivedQtyMap[li.po_line_item_id] = (receivedQtyMap[li.po_line_item_id] || 0) + li.completed_quantity;
    }
  }

  const lineItemColumns = [
    { key: "item_number", label: "#" },
    { key: "description", label: "Description" },
    { key: "quantity", label: "Ordered Qty", align: "right" },
    { key: "unit", label: "Unit" },
    {
      key: "unit_price", label: "Unit Price", align: "right",
      render: (v) => v != null ? Number(v).toLocaleString() : "\u2014",
    },
    {
      key: "amount", label: "Amount", align: "right",
      render: (v) => v != null ? <span className="font-semibold font-mono">{Number(v).toLocaleString()}</span> : "\u2014",
    },
    {
      key: "id", label: "Received",
      render: (v) => {
        const received = receivedQtyMap[v] || 0;
        const poLine = po.line_items.find((li) => li.id === v);
        const ordered = poLine?.quantity || 0;
        const pct = ordered > 0 ? Math.round((received / ordered) * 100) : 0;
        return (
          <div className="flex items-center gap-2">
            <span className="text-neutral-700 font-mono">{received}</span>
            {ordered > 0 && (
              <span className={`text-2xs font-semibold px-1.5 py-0.5 rounded-full ${
                pct >= 100 ? "bg-success-bg text-success-dark" :
                pct > 0 ? "bg-warning-bg text-warning-dark" :
                "bg-neutral-50 text-neutral-500"
              }`}>
                {pct}%
              </span>
            )}
          </div>
        );
      },
    },
  ];

  const grnColumns = [
    { key: "grn_number", label: "GRN Number" },
    { key: "grn_date", label: "Date" },
    { key: "received_by", label: "Received By" },
    { key: "plant_location", label: "Location" },
    {
      key: "line_items", label: "Items",
      render: (v) => (
        <span className="text-neutral-600">{v?.length || 0} items</span>
      ),
    },
    {
      key: "created_at", label: "Created",
      render: (v) => v ? new Date(v).toLocaleDateString() : "\u2014",
    },
  ];

  const sesColumns = [
    { key: "ses_number", label: "SES Number" },
    { key: "ses_date", label: "Date" },
    {
      key: "service_period_from", label: "Service Period",
      render: (v, row) => (v || row.service_period_to) ? `${v || "?"} \u2013 ${row.service_period_to || "?"}` : "\u2014",
    },
    {
      key: "line_items", label: "Items",
      render: (v) => (
        <span className="text-neutral-600">{v?.length || 0} items</span>
      ),
    },
    {
      key: "created_at", label: "Created",
      render: (v) => v ? new Date(v).toLocaleDateString() : "\u2014",
    },
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>&larr; Back</Button>
          <div>
            <h2 className="text-xl font-bold text-neutral-900 m-0">{po.po_number}</h2>
            <span className="text-2xs text-neutral-500">
              {po.vendor_name}
              {po.po_date && <> &middot; {po.po_date}</>}
            </span>
          </div>
          <Badge status={po.status} />
          <span className="capitalize text-2xs font-medium text-neutral-500 bg-neutral-50 px-2 py-0.5 rounded-full">
            {po.po_type}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && !editing && (
            <Button variant="secondary" size="sm" onClick={startEditing}>&#9998; Edit</Button>
          )}
          {editing && (
            <>
              <Button variant="secondary" size="sm" onClick={cancelEditing}>Cancel</Button>
              <Button size="sm" onClick={saveEdits} disabled={saving}>
                {saving ? "Saving..." : "Save Changes"}
              </Button>
            </>
          )}
          {!editing && actions.map((action) => (
            <Button
              key={action.targetStatus}
              variant={action.variant}
              size="sm"
              onClick={() => changeStatus(action.targetStatus)}
              disabled={saving}
            >
              {action.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-4 py-2.5">
          <span className="text-2xs text-danger-dark font-medium">{error}</span>
        </div>
      )}

      {/* KPI Summary */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Total Amount"
          value={po.total_amount != null ? `${po.currency} ${Number(po.total_amount).toLocaleString()}` : "---"}
          sub={`${lineItemCount} line item${lineItemCount !== 1 ? "s" : ""}`}
          accentColor={tokens.color.brand[500]}
          icon="&#128176;"
        />
        <KpiCard
          label="Goods Receipts"
          value={String(grnCount)}
          sub={grnCount > 0 ? "Deliveries recorded" : "No deliveries yet"}
          accentColor={tokens.color.status.info.base}
          icon="&#128666;"
        />
        <KpiCard
          label="Service Entries"
          value={String(sesCount)}
          sub={sesCount > 0 ? "Services recorded" : "No services yet"}
          accentColor={tokens.color.status.warning.base}
          icon="&#128221;"
        />
        <KpiCard
          label="Source"
          value={po.source_type === "file_upload" ? "AI Extracted" : "Manual"}
          sub={po.original_filename || "Manual entry"}
          accentColor={tokens.color.status.posted.base}
          icon="&#128196;"
        />
      </div>

      {/* PO Header Fields (view/edit) */}
      <Card title="PO Details">
        {editing ? (
          <div className="grid grid-cols-3 gap-4">
            {[
              { key: "po_number", label: "PO Number" },
              { key: "vendor_name", label: "Vendor Name" },
              { key: "vendor_ntn", label: "Vendor NTN" },
              { key: "po_date", label: "PO Date", type: "date" },
              { key: "po_type", label: "PO Type", type: "select", options: [
                { value: "local", label: "Local" },
                { value: "foreign", label: "Foreign" },
                { value: "contract", label: "Contract" },
              ]},
              { key: "currency", label: "Currency", type: "select", options: [
                { value: "PKR", label: "PKR" },
                { value: "USD", label: "USD" },
                { value: "EUR", label: "EUR" },
              ]},
            ].map((field) => (
              <div key={field.key}>
                <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">{field.label}</label>
                {field.type === "select" ? (
                  <select
                    value={editFields[field.key] || ""}
                    onChange={(e) => handleFieldChange(field.key, e.target.value)}
                    className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 bg-white"
                  >
                    {field.options.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={field.type || "text"}
                    value={editFields[field.key] || ""}
                    onChange={(e) => handleFieldChange(field.key, e.target.value)}
                    className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
                  />
                )}
              </div>
            ))}
            <div className="col-span-3">
              <label className="block text-2xs font-semibold text-neutral-500 uppercase mb-1">Notes</label>
              <textarea
                value={editFields.notes || ""}
                onChange={(e) => handleFieldChange("notes", e.target.value)}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400 resize-none"
                rows={2}
              />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "PO Number", value: po.po_number },
              { label: "Vendor Name", value: po.vendor_name },
              { label: "Vendor NTN", value: po.vendor_ntn },
              { label: "PO Date", value: po.po_date },
              { label: "PO Type", value: po.po_type },
              { label: "Currency", value: po.currency },
            ].map((field) => (
              <div key={field.label}>
                <div className="text-2xs font-semibold text-neutral-500 uppercase mb-0.5">{field.label}</div>
                <div className="text-xs text-neutral-800 capitalize">{field.value || "\u2014"}</div>
              </div>
            ))}
            {po.notes && (
              <div className="col-span-3">
                <div className="text-2xs font-semibold text-neutral-500 uppercase mb-0.5">Notes</div>
                <div className="text-xs text-neutral-700">{po.notes}</div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Line Items */}
      <Card title={`Line Items (${lineItemCount})`} noPad>
        {editing ? (
          <div className="p-4">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left w-8">#</th>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left">Description</th>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-20">Qty</th>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-left w-20">Unit</th>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-28">Price</th>
                  <th className="px-3 py-2 text-2xs font-semibold text-neutral-500 uppercase border-b-2 border-neutral-100 bg-neutral-25 text-right w-28">Amount</th>
                  <th className="w-10"></th>
                </tr>
              </thead>
              <tbody>
                {editLineItems.map((li, idx) => (
                  <tr key={idx}>
                    <td className="px-3 py-2 text-neutral-400">{idx + 1}</td>
                    <td className="px-3 py-2">
                      <input type="text" value={li.description} onChange={(e) => handleLineItemChange(idx, "description", e.target.value)} className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400" />
                    </td>
                    <td className="px-3 py-2">
                      <input type="number" value={li.quantity ?? ""} onChange={(e) => handleLineItemChange(idx, "quantity", e.target.value)} className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400 text-right" />
                    </td>
                    <td className="px-3 py-2">
                      <input type="text" value={li.unit} onChange={(e) => handleLineItemChange(idx, "unit", e.target.value)} className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400" />
                    </td>
                    <td className="px-3 py-2">
                      <input type="number" value={li.unit_price ?? ""} onChange={(e) => handleLineItemChange(idx, "unit_price", e.target.value)} className="w-full text-xs border border-neutral-200 rounded px-2 py-1 outline-none focus:border-brand-400 text-right" />
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{li.amount ? Number(li.amount).toLocaleString() : "\u2014"}</td>
                    <td className="px-3 py-2 text-center">
                      {editLineItems.length > 1 && (
                        <button onClick={() => removeLineItem(idx)} className="text-danger-dark hover:text-danger-base bg-transparent border-none cursor-pointer">&#x2715;</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2">
              <Button variant="secondary" size="xs" onClick={addLineItem}>+ Add Line</Button>
            </div>
          </div>
        ) : (
          <DataTable columns={lineItemColumns} data={po.line_items || []} />
        )}
      </Card>

      {/* GRN Section */}
      <Card
        title={`Goods Received Notes (${grnCount})`}
        action={canAddGRN && (
          <Button variant="primary" size="xs" onClick={() => setGrnModalOpen(true)}>
            + Add GRN
          </Button>
        )}
        noPad
      >
        {grnCount > 0 ? (
          <DataTable columns={grnColumns} data={po.grns || []} />
        ) : (
          <div className="text-center py-6 text-xs text-neutral-500">
            No goods receipts recorded yet.
            {canAddGRN && " Click \"+ Add GRN\" to record a delivery."}
          </div>
        )}
      </Card>

      {/* SES Section */}
      <Card
        title={`Service Entry Sheets (${sesCount})`}
        action={canAddSES && (
          <Button variant="primary" size="xs" onClick={() => setSesModalOpen(true)}>
            + Add SES
          </Button>
        )}
        noPad
      >
        {sesCount > 0 ? (
          <DataTable columns={sesColumns} data={po.ses_records || []} />
        ) : (
          <div className="text-center py-6 text-xs text-neutral-500">
            No service entries recorded yet.
            {canAddSES && " Click \"+ Add SES\" to record a service completion."}
          </div>
        )}
      </Card>

      {/* GRN Modal */}
      <CreateGRNModal
        open={grnModalOpen}
        onClose={() => setGrnModalOpen(false)}
        poId={po.id}
        poLineItems={po.line_items || []}
        onCreated={() => {
          setGrnModalOpen(false);
          refreshPO();
        }}
      />

      {/* SES Modal */}
      <CreateSESModal
        open={sesModalOpen}
        onClose={() => setSesModalOpen(false)}
        poId={po.id}
        poLineItems={po.line_items || []}
        onCreated={() => {
          setSesModalOpen(false);
          refreshPO();
        }}
      />
    </div>
  );
}
