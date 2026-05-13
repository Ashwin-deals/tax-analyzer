import { formatNumber } from "../lib/format";

const toneClass = {
  indigo: "border-indigo-500 text-indigo-500",
  green: "border-green-500 text-green-600",
  lime: "border-lime-500 text-lime-600",
  amber: "border-amber-500 text-amber-600",
  blue: "border-blue-500 text-blue-600",
  slate: "border-slate-400 text-slate-600",
};

export default function KpiCard({ label, value, tone = "slate", money = false }) {
  return (
    <div className={`rounded-xl border-l-4 bg-white p-5 text-center shadow-card ${toneClass[tone] || toneClass.slate}`}>
      <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-2xl font-extrabold leading-none">
        {money ? value : formatNumber(value)}
      </div>
    </div>
  );
}
