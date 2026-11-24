import Card from "../common/Card";

// SAP's own messages for this invoice, as SAP sent them (like the Messages log of
// MIR7): what it answered to park / resubmit / unpark, and the workflow's log.
const TYPES = {
  E: { label: "Error", tone: "text-danger-dark", dot: "bg-danger-base" },
  A: { label: "Abort", tone: "text-danger-dark", dot: "bg-danger-base" },
  W: { label: "Warning", tone: "text-warning-dark", dot: "bg-warning-base" },
  S: { label: "Success", tone: "text-success-dark", dot: "bg-success-base" },
  I: { label: "Information", tone: "text-neutral-600", dot: "bg-neutral-400" },
};
const ACTIONS = {
  park: "Park", change: "Resubmit", post: "Post", validate: "Check before submit",
  unpark: "Unpark", hierarchy: "Approval hierarchy", workflow: "SAP approval workflow",
};

function Messages({ run }) {
  return (
    <table className="w-full border-collapse text-xs">
      <tbody>
        {run.messages.map((m, i) => {
          const t = TYPES[m.type] || TYPES.I;
          return (
            <tr key={i} className="border-t border-neutral-100 align-top">
              <td className="py-1.5 px-2 w-28 whitespace-nowrap">
                <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${t.dot}`} />
                <span className={t.tone}>{t.label}</span>
              </td>
              <td className="py-1.5 px-2 w-24 font-mono text-neutral-500 whitespace-nowrap">{[m.id, m.number].filter(Boolean).join(" ") || "—"}</td>
              <td className="py-1.5 px-2 text-neutral-800">
                {m.text}
                {m.at && <span className="ml-2 text-2xs text-neutral-400">{m.at}</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const heading = (run) => `${ACTIONS[run.action] || run.action}${run.document ? ` · document ${run.document}` : ""} · ${new Date(run.at).toLocaleString()}`;

export default function SAPMessagesCard({ runs }) {
  if (!runs?.length) return null;
  // The latest answer and the workflow's log both stay open: the log is re-read on
  // every page open and must not push the last park's errors out of sight.
  const latest = runs.find((r) => r.action !== "workflow");
  const log = runs.find((r) => r.action === "workflow");
  const open = [latest, log].filter(Boolean);
  const older = runs.filter((r) => !open.includes(r));
  const bad = open.reduce((n, r) => n + r.messages.filter((m) => m.type === "E" || m.type === "A").length, 0);
  return (
    <Card title="SAP Messages" subtitle={bad ? `${bad} error${bad === 1 ? "" : "s"} from SAP` : "As SAP sent them"}>
      {open.map((run) => (
        <div key={`${run.action}-${run.at}`} className="mb-2">
          <div className="text-2xs text-neutral-500 mb-0.5">{heading(run)}</div>
          <Messages run={run} />
        </div>
      ))}
      {older.length > 0 && (
        <details className="mt-2 text-2xs text-neutral-500">
          <summary className="cursor-pointer">Earlier messages ({older.length})</summary>
          {older.map((run, i) => (
            <div key={i} className="mt-2">
              <div className="mb-0.5">{heading(run)}</div>
              <Messages run={run} />
            </div>
          ))}
        </details>
      )}
    </Card>
  );
}
