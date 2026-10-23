import { useState, useEffect, useCallback } from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import api from "../../services/api";

export default function GLCodingCard({ invoiceId, lineItems = [], currentUser }) {
  const [accounts, setAccounts] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false); // show add form
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Form state
  const [form, setForm] = useState({
    line_item_id: "",
    gl_code: "",
    amount: "",
    cost_center: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [accRes, assignRes] = await Promise.all([
        api.get("/api/gl-accounts", { params: { limit: 200 } }),
        api.get(`/api/gl-accounts/assignments/${invoiceId}`),
      ]);
      setAccounts(accRes.data.accounts || []);
      setAssignments(assignRes.data.assignments || []);
    } catch (err) {
      setError("Failed to load GL data");
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAdd = async () => {
    if (!form.gl_code) return;
    setSaving(true);
    setError(null);
    try {
      await api.post("/api/gl-accounts/assignments", null, {
        params: {
          invoice_id: invoiceId,
          gl_code: form.gl_code,
          line_item_id: form.line_item_id || undefined,
          amount: form.amount || undefined,
          cost_center: form.cost_center || undefined,
          assigned_by_id: currentUser?.id,
          assigned_by_name: currentUser?.display_name || currentUser?.name || "User",
        },
      });
      setForm({ line_item_id: "", gl_code: "", amount: "", cost_center: "" });
      setAdding(false);
      fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to assign GL code");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/gl-accounts/assignments/${id}`);
      fetchData();
    } catch (err) {
      setError("Failed to remove assignment");
    }
  };

  // Group assignments by line item
  const grouped = {};
  const headerAssignments = [];
  assignments.forEach((a) => {
    if (a.line_item_id) {
      if (!grouped[a.line_item_id]) grouped[a.line_item_id] = [];
      grouped[a.line_item_id].push(a);
    } else {
      headerAssignments.push(a);
    }
  });

  const selectedAccount = accounts.find((a) => a.code === form.gl_code);

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">&#128209;</span>
          <h3 className="text-xs font-bold text-neutral-800 m-0">GL Account Coding</h3>
          {assignments.length > 0 && (
            <span className="bg-brand-50 text-brand-600 text-2xs font-bold px-1.5 py-px rounded-full">
              {assignments.length}
            </span>
          )}
        </div>
        {!adding && (
          <Button variant="secondary" size="xs" onClick={() => setAdding(true)}>
            + Assign GL
          </Button>
        )}
      </div>

      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-3 text-2xs text-danger-dark">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-4 text-2xs text-neutral-400">Loading GL assignments...</div>
      ) : (
        <>
          {/* Add form */}
          {adding && (
            <div className="bg-neutral-25 border border-neutral-100 rounded-base p-3 mb-3">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-2xs font-semibold text-neutral-600 mb-1">GL Account</label>
                  <select
                    value={form.gl_code}
                    onChange={(e) => setForm({ ...form, gl_code: e.target.value })}
                    className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 focus:border-brand-400 outline-none bg-white"
                  >
                    <option value="">Select GL Account...</option>
                    {accounts.map((a) => (
                      <option key={a.code} value={a.code}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-2xs font-semibold text-neutral-600 mb-1">Line Item (optional)</label>
                  <select
                    value={form.line_item_id}
                    onChange={(e) => setForm({ ...form, line_item_id: e.target.value })}
                    className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 focus:border-brand-400 outline-none bg-white"
                  >
                    <option value="">Header-level (all)</option>
                    {lineItems.map((li) => (
                      <option key={li.id} value={li.id}>
                        #{li.id} — {li.description?.substring(0, 40) || "No description"}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-2xs font-semibold text-neutral-600 mb-1">Amount</label>
                  <input
                    type="number"
                    step="0.01"
                    value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })}
                    placeholder="Full amount if blank"
                    className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 focus:border-brand-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-2xs font-semibold text-neutral-600 mb-1">Cost Center</label>
                  <input
                    type="text"
                    value={form.cost_center}
                    onChange={(e) => setForm({ ...form, cost_center: e.target.value })}
                    placeholder={selectedAccount?.cost_center || "e.g. CC-001"}
                    className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 focus:border-brand-400 outline-none"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="xs" onClick={() => { setAdding(false); setError(null); }}>
                  Cancel
                </Button>
                <Button size="xs" onClick={handleAdd} disabled={!form.gl_code || saving}>
                  {saving ? "Saving..." : "Assign"}
                </Button>
              </div>
            </div>
          )}

          {/* Header-level assignments */}
          {headerAssignments.length > 0 && (
            <div className="mb-3">
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Header-Level Assignments</div>
              {headerAssignments.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between bg-white border border-neutral-100 rounded-base px-3 py-2 mb-1"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs font-bold text-brand-600">{a.gl_code}</span>
                    <span className="text-xs text-neutral-700">{a.gl_name}</span>
                    {a.cost_center && (
                      <span className="text-2xs bg-neutral-50 text-neutral-500 px-1.5 py-px rounded">
                        CC: {a.cost_center}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {a.amount != null && (
                      <span className="text-xs font-medium text-neutral-900">
                        PKR {Number(a.amount).toLocaleString()}
                      </span>
                    )}
                    <button
                      onClick={() => handleDelete(a.id)}
                      className="text-neutral-400 hover:text-danger-base text-xs cursor-pointer bg-transparent border-none"
                      title="Remove"
                    >
                      &#10005;
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Line-item assignments */}
          {Object.keys(grouped).length > 0 && (
            <div>
              <div className="text-2xs font-semibold text-neutral-500 uppercase mb-1">Line-Item Assignments</div>
              {Object.entries(grouped).map(([liId, assigns]) => {
                const li = lineItems.find((l) => l.id === parseInt(liId));
                return (
                  <div key={liId} className="mb-2">
                    <div className="text-2xs text-neutral-500 mb-0.5">
                      Line #{liId}: {li?.description?.substring(0, 50) || "—"}
                    </div>
                    {assigns.map((a) => (
                      <div
                        key={a.id}
                        className="flex items-center justify-between bg-white border border-neutral-100 rounded-base px-3 py-1.5 mb-0.5 ml-3"
                      >
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-2xs font-bold text-brand-600">{a.gl_code}</span>
                          <span className="text-2xs text-neutral-700">{a.gl_name}</span>
                          {a.cost_center && (
                            <span className="text-2xs bg-neutral-50 text-neutral-500 px-1 py-px rounded">
                              {a.cost_center}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {a.amount != null && (
                            <span className="text-2xs font-medium">PKR {Number(a.amount).toLocaleString()}</span>
                          )}
                          <button
                            onClick={() => handleDelete(a.id)}
                            className="text-neutral-400 hover:text-danger-base text-2xs cursor-pointer bg-transparent border-none"
                          >
                            &#10005;
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}

          {assignments.length === 0 && !adding && (
            <div className="text-center py-4 text-2xs text-neutral-400">
              No GL account assignments yet. Click "Assign GL" to add coding.
            </div>
          )}
        </>
      )}
    </Card>
  );
}
