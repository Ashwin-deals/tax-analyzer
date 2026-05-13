import { UploadCloud } from "lucide-react";

export default function UploadPanel({ onUpload, loading, status }) {
  return (
    <section className="rounded-xl border border-dashed border-slate-300 bg-white p-6 shadow-card">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <div className="rounded-lg bg-slate-100 p-3 text-slate-700">
            <UploadCloud size={24} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">Upload Bank Statement</h2>
            <p className="mt-1 text-sm text-slate-500">
              Supports XLSX, XLS, CSV, and table-based PDF files.
            </p>
          </div>
        </div>

        <label className="inline-flex cursor-pointer items-center justify-center rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700">
          {loading ? "Processing..." : "Choose File"}
          <input
            type="file"
            accept=".xlsx,.xls,.csv,.pdf"
            className="hidden"
            disabled={loading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
      </div>
      {status && <div className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-600">{status}</div>}
    </section>
  );
}
