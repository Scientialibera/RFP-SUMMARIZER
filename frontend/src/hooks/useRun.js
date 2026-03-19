import { useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";

export default function useRun(runId) {
  const [run, setRun] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) {
      setRun(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    setError("");

    (async () => {
      try {
        const res = await authFetch(`/api/runs/${runId}`);
        if (!res.ok) throw new Error("Failed to load run");
        const data = await res.json();
        if (!cancelled) setRun(data);
      } catch {
        if (!cancelled) setError("Failed to load run details.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [runId]);

  return { run, isLoading, error };
}
