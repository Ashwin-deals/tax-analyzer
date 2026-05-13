export const categories = [
  { key: "GST", label: "GST", tone: "green" },
  { key: "POSSIBLE_GST", label: "POSSIBLE GST", tone: "lime" },
  { key: "TDS", label: "TDS", tone: "amber" },
  { key: "NORMAL", label: "NORMAL", tone: "blue" },
];

export function formatNumber(value) {
  return new Intl.NumberFormat("en-IN").format(Number(value || 0));
}

export function formatMoney(value) {
  return `INR ${new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0))}`;
}

export function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function categoryTone(category) {
  return categories.find((item) => item.key === category)?.tone || "slate";
}
