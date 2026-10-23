import { Fragment } from "react";

// groupKey/renderGroupHeader (both optional): when provided, a full-width
// header row is inserted before each run of rows whose groupKey changes —
// rows must already be sorted by that key.
export default function DataTable({ columns, data, onRowClick, rowClassName, groupKey, renderGroupHeader }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className="px-3.5 py-2.5 text-2xs font-semibold text-neutral-500 uppercase tracking-wider border-b-2 border-neutral-100 bg-neutral-25 whitespace-nowrap"
                style={{ textAlign: col.align || "left" }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, ri) => {
            const newGroup =
              groupKey && renderGroupHeader &&
              (ri === 0 || groupKey(row) !== groupKey(data[ri - 1]));
            return (
              <Fragment key={ri}>
                {newGroup && (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-3.5 py-2 bg-neutral-50 border-b border-neutral-100"
                    >
                      {renderGroupHeader(groupKey(row), row)}
                    </td>
                  </tr>
                )}
                <tr
                  onClick={() => onRowClick?.(row)}
                  className={`transition-all duration-150 ${
                    onRowClick ? "cursor-pointer hover:bg-brand-50" : ""
                  } ${rowClassName?.(row) || (ri % 2 === 0 ? "bg-neutral-0" : "bg-neutral-25")}`}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className="px-3.5 py-2.5 border-b border-neutral-50 text-neutral-800 align-middle"
                      style={{ textAlign: col.align || "left" }}
                    >
                      {col.render
                        ? col.render(row[col.key], row)
                        : row[col.key]}
                    </td>
                  ))}
                </tr>
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
