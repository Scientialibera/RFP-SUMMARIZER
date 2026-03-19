import { useCallback, useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";

export default function useRfps() {
  const [rfps, setRfps] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const response = await authFetch("/api/rfps");
    if (!response.ok) throw new Error("Failed to load RFPs");
    const payload = await response.json();
    setRfps(payload);
    return payload;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch {
        if (!cancelled) {
          setRfps([]);
          setError("Unable to load RFP data.");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [refresh]);

  return { rfps, isLoading, error, refresh };
}
