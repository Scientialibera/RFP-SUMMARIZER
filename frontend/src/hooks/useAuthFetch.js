import { useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";

/**
 * Fetches a URL with auth and cancellation handling.
 * @param {string|null} url - URL to fetch, or null/empty to skip.
 * @param {object} options
 * @param {boolean} [options.skip] - Skip the fetch entirely.
 * @param {"json"|"text"|"blob"} [options.as] - Response type (default "json").
 */
export default function useAuthFetch(url, { skip = false, as = "json" } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!url || skip) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");

    (async () => {
      try {
        const res = await authFetch(url);
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        let result;
        if (as === "text") result = await res.text();
        else if (as === "blob") result = await res.blob();
        else result = await res.json();
        if (!cancelled) setData(result);
      } catch (e) {
        if (!cancelled) setError(e.message || "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [url, skip, as]);

  return { data, loading, error };
}
