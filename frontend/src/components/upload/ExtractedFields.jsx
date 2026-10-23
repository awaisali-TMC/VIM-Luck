import Card from "../common/Card";

function confidenceColor(c) {
  if (c >= 95) return { dot: "bg-success-base", text: "text-success-base" };
  if (c >= 85) return { dot: "bg-warning-base", text: "text-warning-base" };
  return { dot: "bg-danger-base", text: "text-danger-base" };
}

export default function ExtractedFields({ fields }) {
  return (
    <Card title="Extracted Fields" subtitle="Review and correct AI-parsed values" noPad>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="text-left px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100 bg-neutral-25">
              Field
            </th>
            <th className="text-left px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100 bg-neutral-25">
              Extracted Value
            </th>
            <th className="text-center px-3.5 py-2 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100 bg-neutral-25 whitespace-nowrap">
              AI Conf.
            </th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f, i) => {
            const colors = confidenceColor(f.confidence);
            return (
              <tr key={i} className={i % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25"}>
                <td className="px-3.5 py-2 border-b border-neutral-50 text-neutral-500 text-2xs font-medium">
                  {f.label}
                </td>
                <td className="px-3.5 py-2 border-b border-neutral-50 text-neutral-900 font-medium">
                  {f.value}
                </td>
                <td className="px-3.5 py-2 border-b border-neutral-50 text-center">
                  <span className="inline-flex items-center gap-1">
                    <span className={`w-[7px] h-[7px] rounded-full ${colors.dot}`} />
                    <span className={`text-2xs font-semibold ${colors.text}`}>
                      {f.confidence}%
                    </span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
