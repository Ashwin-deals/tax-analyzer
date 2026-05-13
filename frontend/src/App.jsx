import { useCallback, useEffect, useState } from "react";

import {
  analyzeStatement,
  downloadExport,
  fetchSummary,
  fetchTransactions,
  uploadStatement,
} from "./api/client";
import ChartSummary from "./components/ChartSummary";
import Filters from "./components/Filters";
import SummaryCards from "./components/SummaryCards";
import TransactionTable from "./components/TransactionTable";
import UploadPanel from "./components/UploadPanel";

const initialFilters = {
  confidence: "ALL",
  review: "ALL",
  search: "",
};

export default function App() {
  const [statementId, setStatementId] = useState(null);
  const [summary, setSummary] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [filters, setFilters] = useState(initialFilters);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tableLoading, setTableLoading] = useState(false);

  const loadTransactions = useCallback(async () => {
    if (!statementId) return;
    setTableLoading(true);
    try {
      const payload = await fetchTransactions(statementId, {
        category: selectedCategory,
        confidence: filters.confidence,
        review: filters.review,
        search: filters.search,
      });
      setTransactions(payload.transactions || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setTableLoading(false);
    }
  }, [statementId, selectedCategory, filters]);

  useEffect(() => {
    loadTransactions();
  }, [loadTransactions]);

  async function handleUpload(file) {
    setLoading(true);
    setError("");
    setStatus(`Uploading ${file.name}...`);
    setSummary(null);
    setTransactions([]);

    try {
      const uploaded = await uploadStatement(file);
      setStatus("Analyzing transactions...");
      await analyzeStatement(uploaded.statementId);
      const summaryPayload = await fetchSummary(uploaded.statementId);
      setSummary(summaryPayload.summary);
      setSelectedCategory("ALL");
      setFilters(initialFilters);
      setStatementId(uploaded.statementId);
      setStatus(`Completed analysis for ${uploaded.filename}`);
    } catch (err) {
      setError(err.message);
      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  async function handleExport() {
    if (!statementId) return;
    try {
      await downloadExport(statementId, selectedCategory);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 md:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="dashboard-header rounded-2xl px-8 py-8 text-white shadow-card">
          <h1 className="text-3xl font-extrabold">Bank Statement Analyzer</h1>
          <p className="mt-2 max-w-3xl text-sm text-white/75 md:text-base">
            Explainable GST, POSSIBLE GST, TDS, and NORMAL transaction interpretation for XLSX, CSV, and PDF statements.
          </p>
        </header>

        <UploadPanel onUpload={handleUpload} loading={loading} status={status} />

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-semibold text-red-700">
            {error}
          </div>
        )}

        {summary ? (
          <>
            <SummaryCards summary={summary} />
            <ChartSummary summary={summary} />
            <Filters
              selectedCategory={selectedCategory}
              filters={filters}
              onCategoryChange={setSelectedCategory}
              onFiltersChange={setFilters}
              onExport={handleExport}
            />
            <TransactionTable rows={transactions} loading={tableLoading} />
          </>
        ) : (
          <section className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-card">
            <h2 className="text-lg font-bold text-slate-900">Upload a statement to begin</h2>
            <p className="mt-2 text-sm text-slate-500">
              The dashboard will populate classification KPIs, amount summaries, review flags, and transaction tables after analysis.
            </p>
          </section>
        )}
      </div>
    </main>
  );
}
