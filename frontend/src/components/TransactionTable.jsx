import { titleCase } from "../lib/format";

const priorityColumns = ["TAX_CATEGORY", "CONFIDENCE", "REVIEW_RECOMMENDED", "ML_ASSIST", "REASON"];

function columnsFor(rows) {
  const all = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const ordered = priorityColumns.filter((col) => all.includes(col));
  const rest = all.filter((col) => !priorityColumns.includes(col));
  return [...rest.slice(0, 4), ...ordered, ...rest.slice(4)];
}

function cellValue(column, value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (column === "REVIEW_RECOMMENDED") return value ? "Yes" : "No";
  return String(value);
}

function badgeClass(column, value) {
  if (column === "CONFIDENCE") {
    if (value === "HIGH") return "bg-green-100 text-green-700";
    if (value === "MEDIUM") return "bg-amber-100 text-amber-700";
    if (value === "LOW") return "bg-red-100 text-red-700";
  }
  if (column === "TAX_CATEGORY") {
    if (value === "GST") return "bg-green-100 text-green-700";
    if (value === "POSSIBLE_GST") return "bg-lime-100 text-lime-700";
    if (value === "TDS") return "bg-amber-100 text-amber-700";
    return "bg-blue-100 text-blue-700";
  }
  if (column === "REVIEW_RECOMMENDED") {
    return value ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500";
  }
  return "";
}

export default function TransactionTable({ rows, loading }) {
  const columns = columnsFor(rows || []);

  return (
    <section className="rounded-xl bg-white shadow-card">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <h2 className="text-lg font-bold text-slate-900">Classified Transactions</h2>
        <span className="text-sm font-semibold text-slate-500">{rows.length} rows</span>
      </div>

      {loading ? (
        <div className="p-8 text-center text-sm text-slate-500">Loading transactions...</div>
      ) : rows.length === 0 ? (
        <div className="p-8 text-center text-sm text-slate-500">No transactions found for the selected filters.</div>
      ) : (
        <div className="table-scroll max-h-[620px] overflow-auto">
          <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="whitespace-nowrap border-b border-slate-200 px-4 py-3 text-xs font-bold uppercase tracking-wide text-slate-500">
                    {titleCase(column)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="hover:bg-slate-50">
                  {columns.map((column) => {
                    const value = row[column];
                    const badge = badgeClass(column, value);
                    return (
                      <td key={column} className="max-w-sm border-b border-slate-100 px-4 py-3 align-top text-slate-700">
                        {badge ? (
                          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${badge}`}>
                            {cellValue(column, value)}
                          </span>
                        ) : (
                          <span className={column === "REASON" ? "line-clamp-3" : "whitespace-nowrap"}>
                            {cellValue(column, value)}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
