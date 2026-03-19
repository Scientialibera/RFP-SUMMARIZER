import { useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";

export default function useUser() {
  const [roles, setRoles] = useState([]);
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch("/api/me");
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setRoles(data.roles || []);
            setName(data.name || "");
          }
        }
      } catch {
        /* non-critical */
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const isAdmin = roles.includes("RFP.Admin");
  const isReader = roles.includes("RFP.Reader") || isAdmin;

  return { roles, name, isAdmin, isReader, loaded };
}
