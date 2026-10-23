import { useState, useEffect } from "react";
import { getEntityAuditLogs } from "../../services/workflowService";
import Card from "../common/Card";
import Badge from "../common/Badge";

const ACTION_ICONS = {
  created: "📄",
  status_changed: "🔄",
  updated: "✏️",
  approved: "✅",
  rejected: "❌",
  returned: "↩️",
  delegated: "👤",
  skipped: "⏭️",
  initiated: "🚀",
};

const ACTION_COLORS = {
  approved: "border-l-emerald-400",
  rejected: "border-l-red-400",
  returned: "border-l-amber-400",
  status_changed: "border-l-blue-400",
  created: "border-l-neutral-300",
  updated: "border-l-blue-300",
  initiated: "border-l-indigo-400",
  delegated: "border-l-purple-400",
};

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function AuditTrailCard({ entityType, entityId }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!entityType || !entityId) return;
    setLoading(true);
    getEntityAuditLogs(entityType, entityId)
      .then((data) => setLogs(data.logs || []))
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  if (loading) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-neutral-900 mb-3">Audit Trail</h3>
        <div className="text-center py-4 text-2xs text-neutral-400">Loading...</div>
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-neutral-900 mb-3">Audit Trail</h3>
        <div className="text-center py-4 text-2xs text-neutral-400">No audit history yet</div>
      </Card>
    );
  }

  const displayed = expanded ? logs : logs.slice(0, 5);

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-neutral-900 m-0">Audit Trail</h3>
        <span className="text-2xs text-neutral-500">{logs.length} event{logs.length !== 1 ? "s" : ""}</span>
      </div>

      <div className="flex flex-col gap-0">
        {displayed.map((log, idx) => {
          const icon = ACTION_ICONS[log.action] || "📝";
          const colorClass = ACTION_COLORS[log.action] || "border-l-neutral-200";
          const isLast = idx === displayed.length - 1;

          return (
            <div
              key={log.id}
              className={`flex items-start gap-3 pl-3 py-2 border-l-2 ${colorClass} ${
                !isLast ? "" : ""
              }`}
            >
              <span className="text-sm flex-shrink-0 mt-0.5">{icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-2xs font-semibold text-neutral-800 capitalize">
                    {log.action.replace(/_/g, " ")}
                  </span>
                  {log.actor_name && (
                    <span className="text-2xs text-neutral-500">
                      by <span className="font-medium text-neutral-700">{log.actor_name}</span>
                    </span>
                  )}
                  <span className="text-2xs text-neutral-400">{timeAgo(log.created_at)}</span>
                </div>
                {log.new_value && (() => {
                  try {
                    const val = typeof log.new_value === "string" ? JSON.parse(log.new_value) : log.new_value;
                    if (val.status) {
                      return (
                        <div className="mt-1">
                          <Badge status={val.status} size="xs" />
                        </div>
                      );
                    }
                    if (val.comments) {
                      return (
                        <div className="mt-1 text-2xs text-neutral-600 italic">
                          &ldquo;{val.comments}&rdquo;
                        </div>
                      );
                    }
                  } catch { /* ignore */ }
                  return null;
                })()}
              </div>
            </div>
          );
        })}
      </div>

      {logs.length > 5 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-2xs text-brand-500 hover:text-brand-600 font-semibold bg-transparent border-none cursor-pointer"
        >
          {expanded ? "Show less" : `Show all ${logs.length} events`}
        </button>
      )}
    </Card>
  );
}
