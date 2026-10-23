import { useState, useEffect, useCallback } from "react";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Badge from "../components/common/Badge";
import KpiCard from "../components/common/KpiCard";
import Modal from "../components/common/Modal";
import api from "../services/api";

const TAX_TYPES = ["gst", "wht", "sed", "fed", "customs", "cess"];
const APPLIES_TO = ["all", "goods", "services", "import", "export"];
const SUPPLIER_TYPES = [null, "registered", "unregistered"];
const SECTORS = [null, "oil_gas", "construction", "telecom", "manufacturing", "agriculture"];

const TAX_TYPE_COLORS = {
  gst: "#3B82F6",
  wht: "#8B5CF6",
  sed: "#F59E0B",
  fed: "#EF4444",
  customs: "#059669",
  cess: "#6366F1",
};

function TaxTypeBadge({ type }) {
  const color = TAX_TYPE_COLORS[type] || "#94A3B8";
  return (
    <span
      className="text-2xs font-bold px-2 py-0.5 rounded-full uppercase"
      style={{ backgroundColor: `${color}15`, color }}
    >
      {type}
    </span>
  );
}

export default function TaxRulesPage() {
  const [rules, setRules] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterType, setFilterType] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [modal, setModal] = useState(null); // null | "create" | rule object
  const [saving, setSaving] = useState(false);

  const emptyForm = {
    rule_code: "", rule_name: "", description: "", tax_type: "gst",
    rate: "", applies_to: "all", min_amount: "", max_amount: "",
    supplier_type: "", sector: "", fbr_section: "", sro_reference: "",
    effective_from: "", effective_to: "", is_active: 1, priority: 100,
  };
  const [form, setForm] = useState(emptyForm);

  const fetchRules = useCallback(async () => {
    setLoading(true);
    try {
      const params = { active_only: !showInactive, limit: 200 };
      if (filterType) params.tax_type = filterType;
      const res = await api.get("/api/tax-rules", { params });
      setRules(res.data.rules || []);
      setTotal(res.data.total || 0);
    } catch {
      setError("Failed to load tax rules");
    } finally {
      setLoading(false);
    }
  }, [filterType, showInactive]);

  useEffect(() => { fetchRules(); }, [fetchRules]);

  const openCreate = () => {
    setForm(emptyForm);
    setModal("create");
    setError(null);
  };

  const openEdit = (rule) => {
    setForm({
      rule_code: rule.rule_code || "",
      rule_name: rule.rule_name || "",
      description: rule.description || "",
      tax_type: rule.tax_type || "gst",
      rate: rule.rate ?? "",
      applies_to: rule.applies_to || "all",
      min_amount: rule.min_amount ?? "",
      max_amount: rule.max_amount ?? "",
      supplier_type: rule.supplier_type || "",
      sector: rule.sector || "",
      fbr_section: rule.fbr_section || "",
      sro_reference: rule.sro_reference || "",
      effective_from: rule.effective_from || "",
      effective_to: rule.effective_to || "",
      is_active: rule.is_active ?? 1,
      priority: rule.priority ?? 100,
    });
    setModal(rule);
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...form,
        rate: parseFloat(form.rate) || 0,
        min_amount: form.min_amount ? parseFloat(form.min_amount) : null,
        max_amount: form.max_amount ? parseFloat(form.max_amount) : null,
        supplier_type: form.supplier_type || null,
        sector: form.sector || null,
        effective_from: form.effective_from || null,
        effective_to: form.effective_to || null,
        priority: parseInt(form.priority) || 100,
      };

      if (modal === "create") {
        await api.post("/api/tax-rules", payload);
      } else {
        await api.put(`/api/tax-rules/${modal.id}`, payload);
      }
      setModal(null);
      fetchRules();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to save rule");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this tax rule?")) return;
    try {
      await api.delete(`/api/tax-rules/${id}`);
      fetchRules();
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to delete");
    }
  };

  const handleToggle = async (rule) => {
    try {
      await api.put(`/api/tax-rules/${rule.id}`, { is_active: rule.is_active ? 0 : 1 });
      fetchRules();
    } catch {
      setError("Failed to toggle rule");
    }
  };

  // Group by type for KPIs
  const typeCounts = {};
  rules.forEach((r) => {
    typeCounts[r.tax_type] = (typeCounts[r.tax_type] || 0) + 1;
  });

  return (
    <div className="flex flex-col gap-5">
      {/* KPIs */}
      <div className="grid grid-cols-5 gap-4">
        <KpiCard label="Total Rules" value={total} icon="&#128220;" accentColor="#4F62F2" />
        <KpiCard label="GST Rules" value={typeCounts.gst || 0} icon="&#128200;" accentColor="#3B82F6" />
        <KpiCard label="WHT Rules" value={typeCounts.wht || 0} icon="&#128181;" accentColor="#8B5CF6" />
        <KpiCard label="SED/FED" value={(typeCounts.sed || 0) + (typeCounts.fed || 0)} icon="&#128176;" accentColor="#F59E0B" />
        <KpiCard label="Other" value={(typeCounts.customs || 0) + (typeCounts.cess || 0)} icon="&#128214;" accentColor="#059669" />
      </div>

      {/* Main Table */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-xs font-bold text-neutral-800 m-0">FBR Tax Rules</h3>
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="text-2xs border border-neutral-200 rounded-base px-2 py-1 bg-white outline-none"
            >
              <option value="">All Types</option>
              {TAX_TYPES.map((t) => (
                <option key={t} value={t}>{t.toUpperCase()}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-2xs text-neutral-500 cursor-pointer">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
                className="cursor-pointer"
              />
              Show inactive
            </label>
          </div>
          <Button size="xs" onClick={openCreate}>+ Add Rule</Button>
        </div>

        {error && (
          <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 mb-3 text-2xs text-danger-dark">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-8 text-xs text-neutral-400">Loading rules...</div>
        ) : rules.length === 0 ? (
          <div className="text-center py-8 text-xs text-neutral-400">No tax rules found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-neutral-100">
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Code</th>
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Name</th>
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Type</th>
                  <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Rate</th>
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Applies To</th>
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Supplier</th>
                  <th className="text-left py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">FBR Ref</th>
                  <th className="text-center py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Active</th>
                  <th className="text-right py-2 px-2 text-2xs font-semibold text-neutral-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr
                    key={r.id}
                    className={`border-b border-neutral-50 hover:bg-neutral-25 transition-colors ${
                      !r.is_active ? "opacity-50" : ""
                    }`}
                  >
                    <td className="py-2 px-2 font-mono text-2xs font-bold text-brand-600">{r.rule_code}</td>
                    <td className="py-2 px-2 font-medium text-neutral-800 max-w-[180px] truncate">{r.rule_name}</td>
                    <td className="py-2 px-2"><TaxTypeBadge type={r.tax_type} /></td>
                    <td className="py-2 px-2 text-right font-bold text-neutral-900">{r.rate}%</td>
                    <td className="py-2 px-2 text-neutral-600 capitalize">{r.applies_to}</td>
                    <td className="py-2 px-2 text-neutral-600 capitalize">{r.supplier_type || "Any"}</td>
                    <td className="py-2 px-2 text-2xs text-neutral-500">{r.fbr_section || "---"}</td>
                    <td className="py-2 px-2 text-center">
                      <button
                        onClick={() => handleToggle(r)}
                        className={`w-8 h-4 rounded-full cursor-pointer border-none transition-colors ${
                          r.is_active ? "bg-success-base" : "bg-neutral-300"
                        }`}
                      >
                        <div
                          className={`w-3 h-3 rounded-full bg-white transition-transform ${
                            r.is_active ? "translate-x-4" : "translate-x-0.5"
                          }`}
                        />
                      </button>
                    </td>
                    <td className="py-2 px-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openEdit(r)}
                          className="text-brand-500 hover:text-brand-700 text-2xs bg-transparent border-none cursor-pointer"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(r.id)}
                          className="text-neutral-400 hover:text-danger-base text-2xs bg-transparent border-none cursor-pointer"
                        >
                          Del
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Create/Edit Modal */}
      {modal && (
        <Modal
          open={!!modal}
          title={modal === "create" ? "Add Tax Rule" : `Edit: ${modal.rule_name}`}
          onClose={() => setModal(null)}
        >
          <div className="flex flex-col gap-3 max-h-[70vh] overflow-y-auto">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Rule Code</label>
                <input
                  value={form.rule_code}
                  onChange={(e) => setForm({ ...form, rule_code: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="e.g. GST-STD"
                  disabled={modal !== "create"}
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Rule Name</label>
                <input
                  value={form.rule_name}
                  onChange={(e) => setForm({ ...form, rule_name: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="Standard GST"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Tax Type</label>
                <select
                  value={form.tax_type}
                  onChange={(e) => setForm({ ...form, tax_type: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none bg-white"
                >
                  {TAX_TYPES.map((t) => (
                    <option key={t} value={t}>{t.toUpperCase()}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Rate (%)</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.rate}
                  onChange={(e) => setForm({ ...form, rate: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="18.0"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Applies To</label>
                <select
                  value={form.applies_to}
                  onChange={(e) => setForm({ ...form, applies_to: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none bg-white"
                >
                  {APPLIES_TO.map((a) => (
                    <option key={a} value={a}>{a.charAt(0).toUpperCase() + a.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Supplier Type</label>
                <select
                  value={form.supplier_type}
                  onChange={(e) => setForm({ ...form, supplier_type: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none bg-white"
                >
                  <option value="">Any</option>
                  <option value="registered">Registered</option>
                  <option value="unregistered">Unregistered</option>
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Sector</label>
                <select
                  value={form.sector}
                  onChange={(e) => setForm({ ...form, sector: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none bg-white"
                >
                  <option value="">Any</option>
                  {SECTORS.filter(Boolean).map((s) => (
                    <option key={s} value={s}>{s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Priority</label>
                <input
                  type="number"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Min Amount</label>
                <input
                  type="number"
                  value={form.min_amount}
                  onChange={(e) => setForm({ ...form, min_amount: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="No minimum"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Max Amount</label>
                <input
                  type="number"
                  value={form.max_amount}
                  onChange={(e) => setForm({ ...form, max_amount: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="No maximum"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">FBR Section</label>
                <input
                  value={form.fbr_section}
                  onChange={(e) => setForm({ ...form, fbr_section: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="e.g. Section 153(1)(a)"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">SRO Reference</label>
                <input
                  value={form.sro_reference}
                  onChange={(e) => setForm({ ...form, sro_reference: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                  placeholder="e.g. SRO 1125(I)/2011"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Effective From</label>
                <input
                  type="date"
                  value={form.effective_from}
                  onChange={(e) => setForm({ ...form, effective_from: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Effective To</label>
                <input
                  type="date"
                  value={form.effective_to}
                  onChange={(e) => setForm({ ...form, effective_to: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                />
              </div>
            </div>
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400 resize-none"
                rows={2}
                placeholder="Rule description..."
              />
            </div>
            {error && <p className="text-2xs text-danger-dark">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setModal(null)}>Cancel</Button>
              <Button size="sm" onClick={handleSave} disabled={saving || !form.rule_code || !form.rule_name}>
                {saving ? "Saving..." : modal === "create" ? "Create Rule" : "Save Changes"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
