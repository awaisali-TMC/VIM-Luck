import { useState, useEffect, useCallback } from "react";
import {
  listTemplates, createTemplate, updateTemplate, deleteTemplate,
  addStep, deleteStep,
} from "../services/workflowService";
import Card from "../components/common/Card";
import Button from "../components/common/Button";
import Badge from "../components/common/Badge";
import Modal from "../components/common/Modal";

const INVOICE_TYPES = [
  { value: "all", label: "All Types" },
  { value: "po_material", label: "PO — Material" },
  { value: "po_service", label: "PO — Service" },
  { value: "non_po", label: "Non-PO" },
  { value: "import", label: "Import" },
];

// Fallback until the dynamic role list loads (roles are DB-managed in RBAC v2)
const FALLBACK_APPROVER_ROLES = [
  { value: "ap_manager", label: "AP Manager" },
  { value: "ap_operator", label: "Purchaser" },
  { value: "tax_manager", label: "Tax Manager" },
  { value: "procurement_manager", label: "Procurement Manager" },
  { value: "finance_director", label: "Finance Director" },
  { value: "department_head", label: "Department Head" },
  { value: "auditor", label: "Auditor" },
  { value: "admin", label: "Admin" },
];

export default function WorkflowTemplatesPage() {
  const [approverRoles, setApproverRoles] = useState(FALLBACK_APPROVER_ROLES);
  useEffect(() => {
    import("../services/permissionService").then(({ listRoles }) =>
      listRoles().then((data) => {
        const roles = (data.roles || []).map((r) => ({ value: r.key, label: r.label }));
        if (roles.length) setApproverRoles(roles);
      })
    ).catch(() => { /* keep fallback */ });
  }, []);
  const APPROVER_ROLES = approverRoles;
  const ROLE_LABEL = Object.fromEntries(APPROVER_ROLES.map((r) => [r.value, r.label]));
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [saving, setSaving] = useState(false);

  // Template form
  const [form, setForm] = useState({
    name: "", description: "", invoice_type: "all",
    min_amount: "", max_amount: "", currency: "PKR",
    is_active: 1, priority: 100, steps: [],
  });

  // Step form (for adding steps inline)
  const [stepForm, setStepForm] = useState({
    step_name: "", approver_role: "ap_manager", sla_hours: 48, is_required: 1, auto_approve_below: "",
  });

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTemplates();
      setTemplates(data || []);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to load templates");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const handleCreate = () => {
    setEditingTemplate(null);
    setForm({
      name: "", description: "", invoice_type: "all",
      min_amount: "", max_amount: "", currency: "PKR",
      is_active: 1, priority: 100, steps: [],
    });
    setShowModal(true);
  };

  const handleEdit = (t) => {
    setEditingTemplate(t);
    setForm({
      name: t.name, description: t.description || "", invoice_type: t.invoice_type || "all",
      min_amount: t.min_amount ?? "", max_amount: t.max_amount ?? "", currency: t.currency || "PKR",
      is_active: t.is_active, priority: t.priority || 100,
      steps: (t.steps || []).map((s) => ({ ...s })),
    });
    setShowModal(true);
  };

  const handleSaveTemplate = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        name: form.name,
        description: form.description || null,
        invoice_type: form.invoice_type,
        min_amount: form.min_amount !== "" ? parseFloat(form.min_amount) : null,
        max_amount: form.max_amount !== "" ? parseFloat(form.max_amount) : null,
        currency: form.currency,
        is_active: form.is_active,
        priority: parseInt(form.priority) || 100,
      };

      if (editingTemplate) {
        await updateTemplate(editingTemplate.id, payload);
      } else {
        payload.steps = form.steps.map((s, i) => ({
          step_order: i + 1,
          step_name: s.step_name,
          approver_role: s.approver_role || null,
          approver_user_id: s.approver_user_id || null,
          is_required: s.is_required ?? 1,
          auto_approve_below: s.auto_approve_below || null,
          sla_hours: s.sla_hours || 48,
        }));
        await createTemplate(payload);
      }
      setShowModal(false);
      fetchTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteTemplate = async (id) => {
    if (!confirm("Delete this workflow template?")) return;
    try {
      await deleteTemplate(id);
      fetchTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || "Delete failed");
    }
  };

  const handleAddStepToExisting = async (templateId) => {
    if (!stepForm.step_name.trim()) return;
    setSaving(true);
    try {
      const template = templates.find((t) => t.id === templateId);
      const maxOrder = template?.steps?.length || 0;
      await addStep(templateId, {
        step_order: maxOrder + 1,
        step_name: stepForm.step_name,
        approver_role: stepForm.approver_role,
        sla_hours: parseInt(stepForm.sla_hours) || 48,
        is_required: stepForm.is_required,
        auto_approve_below: stepForm.auto_approve_below ? parseFloat(stepForm.auto_approve_below) : null,
      });
      setStepForm({ step_name: "", approver_role: "ap_manager", sla_hours: 48, is_required: 1, auto_approve_below: "" });
      fetchTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || "Add step failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteStep = async (templateId, stepId) => {
    try {
      await deleteStep(templateId, stepId);
      fetchTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || "Delete step failed");
    }
  };

  // Add step to form (for new templates)
  const addStepToForm = () => {
    if (!stepForm.step_name.trim()) return;
    setForm({
      ...form,
      steps: [
        ...form.steps,
        {
          step_order: form.steps.length + 1,
          step_name: stepForm.step_name,
          approver_role: stepForm.approver_role,
          sla_hours: parseInt(stepForm.sla_hours) || 48,
          is_required: stepForm.is_required,
          auto_approve_below: stepForm.auto_approve_below ? parseFloat(stepForm.auto_approve_below) : null,
        },
      ],
    });
    setStepForm({ step_name: "", approver_role: "ap_manager", sla_hours: 48, is_required: 1, auto_approve_below: "" });
  };

  const removeStepFromForm = (idx) => {
    setForm({
      ...form,
      steps: form.steps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_order: i + 1 })),
    });
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-neutral-900 m-0">Workflow Templates</h2>
          <p className="text-2xs text-neutral-500 mt-0.5">Configure multi-level approval workflows</p>
        </div>
        <Button size="sm" onClick={handleCreate}>+ New Template</Button>
      </div>

      {error && (
        <div className="bg-danger-bg border border-danger-base rounded-base px-3 py-2 text-2xs text-danger-dark">
          {error}
          <button onClick={() => setError(null)} className="ml-2 font-bold cursor-pointer bg-transparent border-none text-danger-dark">&times;</button>
        </div>
      )}

      {loading ? (
        <Card><div className="text-center py-8 text-xs text-neutral-500">Loading...</div></Card>
      ) : templates.length === 0 ? (
        <Card><div className="text-center py-8 text-xs text-neutral-400">No workflow templates configured</div></Card>
      ) : (
        <div className="flex flex-col gap-3">
          {templates.map((t) => {
            const isExpanded = expandedId === t.id;
            return (
              <Card key={t.id}>
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : t.id)}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg">⚡</span>
                    <div>
                      <div className="text-sm font-semibold text-neutral-900">{t.name}</div>
                      <div className="text-2xs text-neutral-500">
                        {t.invoice_type === "all" ? "All types" : t.invoice_type}
                        {t.min_amount != null && ` · Min: ${t.currency} ${Number(t.min_amount).toLocaleString()}`}
                        {t.max_amount != null && ` · Max: ${t.currency} ${Number(t.max_amount).toLocaleString()}`}
                        {` · ${(t.steps || []).length} step${(t.steps || []).length !== 1 ? "s" : ""}`}
                        {` · Priority: ${t.priority}`}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge status={t.is_active ? "active" : "blocked"} label={t.is_active ? "Active" : "Inactive"} size="xs" />
                    <span className="text-neutral-400 text-xs">{isExpanded ? "▲" : "▼"}</span>
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-4 border-t border-neutral-100 pt-4">
                    {t.description && (
                      <p className="text-2xs text-neutral-600 mb-3">{t.description}</p>
                    )}

                    {/* Steps list */}
                    <h4 className="text-2xs font-semibold text-neutral-600 uppercase mb-2">Approval Steps</h4>
                    {(t.steps || []).length === 0 ? (
                      <p className="text-2xs text-neutral-400 mb-3">No steps configured</p>
                    ) : (
                      <div className="flex flex-col gap-1.5 mb-3">
                        {(t.steps || []).sort((a, b) => a.step_order - b.step_order).map((s) => (
                          <div key={s.id} className="flex items-center gap-3 bg-neutral-25 rounded-base px-3 py-2">
                            <span className="w-5 h-5 bg-brand-100 text-brand-600 rounded-full flex items-center justify-center text-2xs font-bold flex-shrink-0">
                              {s.step_order}
                            </span>
                            <div className="flex-1">
                              <span className="text-xs font-medium text-neutral-800">{s.step_name}</span>
                              <span className="text-2xs text-neutral-500 ml-2">
                                {ROLE_LABEL[s.approver_role] || s.approver_role || "Any"}
                                {s.sla_hours ? ` · ${s.sla_hours}h SLA` : ""}
                                {s.auto_approve_below ? ` · Auto-approve below ${s.auto_approve_below}` : ""}
                                {!s.is_required ? " · Optional" : ""}
                              </span>
                            </div>
                            <Button variant="ghost" size="xs" onClick={() => handleDeleteStep(t.id, s.id)}>
                              &#10005;
                            </Button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Add step inline */}
                    <div className="flex items-end gap-2 mb-3">
                      <div className="flex-1">
                        <label className="block text-2xs font-semibold text-neutral-500 mb-0.5">Step Name</label>
                        <input
                          type="text"
                          value={stepForm.step_name}
                          onChange={(e) => setStepForm({ ...stepForm, step_name: e.target.value })}
                          className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                          placeholder="e.g. Manager Review"
                        />
                      </div>
                      <div>
                        <label className="block text-2xs font-semibold text-neutral-500 mb-0.5">Role</label>
                        <select
                          value={stepForm.approver_role}
                          onChange={(e) => setStepForm({ ...stepForm, approver_role: e.target.value })}
                          className="text-xs border border-neutral-200 rounded-base px-2 py-1.5 bg-white"
                        >
                          {APPROVER_ROLES.map((r) => (
                            <option key={r.value} value={r.value}>{r.label}</option>
                          ))}
                        </select>
                      </div>
                      <div style={{ width: 70 }}>
                        <label className="block text-2xs font-semibold text-neutral-500 mb-0.5">SLA (h)</label>
                        <input
                          type="number"
                          value={stepForm.sla_hours}
                          onChange={(e) => setStepForm({ ...stepForm, sla_hours: e.target.value })}
                          className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none"
                        />
                      </div>
                      <Button size="sm" onClick={() => handleAddStepToExisting(t.id)} disabled={saving || !stepForm.step_name.trim()}>
                        + Add
                      </Button>
                    </div>

                    {/* Template actions */}
                    <div className="flex items-center gap-2 border-t border-neutral-100 pt-3">
                      <Button variant="secondary" size="sm" onClick={() => handleEdit(t)}>Edit Template</Button>
                      <Button variant="ghost" size="sm" onClick={() => handleDeleteTemplate(t.id)}>Delete</Button>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Create/Edit Template Modal */}
      {showModal && (
        <Modal
          open={showModal}
          title={editingTemplate ? "Edit Workflow Template" : "Create Workflow Template"}
          onClose={() => setShowModal(false)}
          width={700}
        >
          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none focus:border-brand-400"
                placeholder="e.g. High-Value Invoice Approval"
              />
            </div>
            <div>
              <label className="block text-2xs font-semibold text-neutral-600 mb-1">Description</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none resize-none focus:border-brand-400"
                rows={2}
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Invoice Type</label>
                <select
                  value={form.invoice_type}
                  onChange={(e) => setForm({ ...form, invoice_type: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 bg-white"
                >
                  {INVOICE_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Min Amount</label>
                <input
                  type="number"
                  value={form.min_amount}
                  onChange={(e) => setForm({ ...form, min_amount: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none"
                  placeholder="No minimum"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Max Amount</label>
                <input
                  type="number"
                  value={form.max_amount}
                  onChange={(e) => setForm({ ...form, max_amount: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none"
                  placeholder="No maximum"
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Currency</label>
                <input
                  type="text"
                  value={form.currency}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none"
                />
              </div>
              <div>
                <label className="block text-2xs font-semibold text-neutral-600 mb-1">Priority</label>
                <input
                  type="number"
                  value={form.priority}
                  onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  className="w-full text-xs border border-neutral-200 rounded-base px-3 py-2 outline-none"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-xs text-neutral-700">
                  <input
                    type="checkbox"
                    checked={form.is_active === 1}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked ? 1 : 0 })}
                  />
                  Active
                </label>
              </div>
            </div>

            {/* Steps editor (only for new templates) */}
            {!editingTemplate && (
              <>
                <h4 className="text-xs font-semibold text-neutral-800 mt-2 mb-1">Approval Steps</h4>
                {form.steps.length > 0 && (
                  <div className="flex flex-col gap-1.5 mb-2">
                    {form.steps.map((s, idx) => (
                      <div key={idx} className="flex items-center gap-2 bg-neutral-25 rounded-base px-3 py-1.5">
                        <span className="text-2xs font-bold text-brand-600">{idx + 1}.</span>
                        <span className="text-xs text-neutral-800 flex-1">{s.step_name}</span>
                        <span className="text-2xs text-neutral-500">{ROLE_LABEL[s.approver_role] || s.approver_role}</span>
                        <span className="text-2xs text-neutral-400">{s.sla_hours}h</span>
                        <button
                          onClick={() => removeStepFromForm(idx)}
                          className="text-neutral-400 hover:text-danger-base cursor-pointer bg-transparent border-none text-xs"
                        >
                          &#10005;
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <input
                      type="text"
                      value={stepForm.step_name}
                      onChange={(e) => setStepForm({ ...stepForm, step_name: e.target.value })}
                      className="w-full text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none focus:border-brand-400"
                      placeholder="Step name"
                    />
                  </div>
                  <select
                    value={stepForm.approver_role}
                    onChange={(e) => setStepForm({ ...stepForm, approver_role: e.target.value })}
                    className="text-xs border border-neutral-200 rounded-base px-2 py-1.5 bg-white"
                  >
                    {APPROVER_ROLES.map((r) => (
                      <option key={r.value} value={r.value}>{r.label}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    value={stepForm.sla_hours}
                    onChange={(e) => setStepForm({ ...stepForm, sla_hours: e.target.value })}
                    className="w-16 text-xs border border-neutral-200 rounded-base px-2 py-1.5 outline-none"
                    placeholder="SLA"
                  />
                  <Button size="sm" variant="secondary" onClick={addStepToForm} disabled={!stepForm.step_name.trim()}>
                    + Add Step
                  </Button>
                </div>
              </>
            )}

            <div className="flex justify-end gap-2 mt-3">
              <Button variant="secondary" size="sm" onClick={() => setShowModal(false)}>Cancel</Button>
              <Button size="sm" onClick={handleSaveTemplate} disabled={saving || !form.name.trim()}>
                {saving ? "Saving..." : editingTemplate ? "Save Changes" : "Create Template"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
