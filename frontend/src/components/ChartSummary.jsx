import { categories, formatNumber } from "../lib/format";

const barTone = {
  green: "bg-green-500",
  lime: "bg-lime-500",
  amber: "bg-amber-500",
  blue: "bg-blue-500",
};

export default function ChartSummary({ summary }) {
  const counts = summary?.categoryCounts || {};
  const confidence = summary?.confidenceCounts || {};
  const max = Math.max(...categories.map((item) => counts[item.key] || 0), 1);

  return (
    <section className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
      <div className="rounded-xl bg-white p-5 shadow-card">
        <h2 className="mb-4 text-lg font-bold text-slate-900">Category Distribution</h2>
        <div className="space-y-4">
          {categories.map((category) => {
            const value = counts[category.key] || 0;
            const width = `${Math.max((value / max) * 100, value ? 8 : 0)}%`;
            return (
              <div key={category.key}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="font-semibold text-slate-700">{category.label}</span>
                  <span className="text-slate-500">{formatNumber(value)}</span>
                </div>
                <div className="h-3 rounded-full bg-slate-100">
                  <div className={`h-3 rounded-full ${barTone[category.tone]}`} style={{ width }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="rounded-xl bg-white p-5 shadow-card">
        <h2 className="mb-4 text-lg font-bold text-slate-900">Confidence</h2>
        <div className="space-y-3">
          {["HIGH", "MEDIUM", "LOW"].map((level) => (
            <div key={level} className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
              <span className="text-sm font-bold text-slate-700">{level}</span>
              <span className="text-lg font-extrabold text-slate-900">{formatNumber(confidence[level] || 0)}</span>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
            <span className="text-sm font-bold text-amber-700">Review Recommended</span>
            <span className="text-lg font-extrabold text-amber-700">{formatNumber(summary?.reviewTotal || 0)}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
