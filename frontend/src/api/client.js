const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the generic message.
    }
    throw new Error(message);
  }
  return response.json();
}

export async function uploadStatement(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/statements/upload", {
    method: "POST",
    body: form,
  });
}

export async function analyzeStatement(statementId) {
  return request(`/statements/${statementId}/analyze`, { method: "POST" });
}

export async function fetchSummary(statementId) {
  return request(`/statements/${statementId}/summary`);
}

export async function fetchTransactions(statementId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== "ALL") {
      params.set(key, value);
    }
  });
  const suffix = params.toString() ? `?${params}` : "";
  return request(`/statements/${statementId}/transactions${suffix}`);
}

export async function downloadExport(statementId, category = "ALL") {
  const params = new URLSearchParams({ category });
  const response = await fetch(`${API_BASE_URL}/statements/${statementId}/export?${params}`);
  if (!response.ok) {
    throw new Error("Could not export results");
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || (category === "ALL" ? "tax-analyzer-results.zip" : `${category.toLowerCase()}_transactions.xlsx`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
