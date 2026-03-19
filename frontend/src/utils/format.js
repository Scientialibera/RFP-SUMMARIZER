export function formatRunDate(dateStr, fallback = "") {
  if (!dateStr) return fallback;
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return fallback;
  }
}
