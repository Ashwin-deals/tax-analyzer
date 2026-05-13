import { Search } from "lucide-react";

import { categories } from "../lib/format";

export default function Filters({ selectedCategory, filters, onCategoryChange, onFiltersChange, onExport }) {
  return (
    <section className="rounded-xl bg-white p-4 shadow-card">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          <button
            className={`rounded-lg px-4 py-2 text-sm font-bold ${selectedCategory === "ALL" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            onClick={() => onCategoryChange("ALL")}
          >
            ALL
          </button>
          {categories.map((category) => (
            <button
              key={category.key}
              className={`rounded-lg px-4 py-2 text-sm font-bold ${selectedCategory === category.key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
              onClick={() => onCategoryChange(category.key)}
            >
              {category.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
            <input
              className="w-full rounded-lg border border-slate-200 py-2 pl-10 pr-3 text-sm outline-none focus:border-slate-400 md:w-64"
              placeholder="Search transactions"
              value={filters.search}
              onChange={(event) => onFiltersChange({ ...filters, search: event.target.value })}
            />
          </div>
          <select
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            value={filters.confidence}
            onChange={(event) => onFiltersChange({ ...filters, confidence: event.target.value })}
          >
            <option value="ALL">All confidence</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <select
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400"
            value={filters.review}
            onChange={(event) => onFiltersChange({ ...filters, review: event.target.value })}
          >
            <option value="ALL">All review states</option>
            <option value="true">Review recommended</option>
            <option value="false">No review</option>
          </select>
          <button
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-700"
            onClick={onExport}
          >
            Export
          </button>
        </div>
      </div>
    </section>
  );
}
