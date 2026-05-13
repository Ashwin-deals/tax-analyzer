import KpiCard from "./KpiCard";
import { categories, formatMoney } from "../lib/format";

export default function SummaryCards({ summary }) {
  const categoryCounts = summary?.categoryCounts || {};
  const totals = summary?.amountTotals || {};

  return (
    <div className="space-y-5">
      <section>
        <h2 className="mb-3 text-lg font-bold text-slate-900">Classification Summary</h2>
        <div className="grid gap-4 md:grid-cols-5">
          <KpiCard label="Total" value={summary?.totalTransactions || 0} tone="indigo" />
          {categories.map((category) => (
            <KpiCard
              key={category.key}
              label={category.label}
              value={categoryCounts[category.key] || 0}
              tone={category.tone}
            />
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-bold text-slate-900">Amount Summary</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <KpiCard label="Total Debit" value={formatMoney(totals.debit)} tone="indigo" money />
          <KpiCard label="Total Credit" value={formatMoney(totals.credit)} tone="blue" money />
          <KpiCard label="Total Deposit" value={formatMoney(totals.deposit)} tone="green" money />
        </div>
      </section>
    </div>
  );
}
