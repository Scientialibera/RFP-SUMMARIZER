import { useState } from "react";
import { authFetch } from "../auth/authFetch";

export default function ChunksTab({ runId, chunkFiles }) {
  const [expanded, setExpanded] = useState(null);
  const [data, setData] = useState({});
  const [loading, setLoading] = useState("");

  if (!chunkFiles?.length) {
    return <div className="tab-empty">No intermediate files for this run.</div>;
  }

  const handleToggle = async (filename) => {
    if (expanded === filename) {
      setExpanded(null);
      return;
    }
    setExpanded(filename);
    if (data[filename]) return;

    setLoading(filename);
    try {
      const res = await authFetch(`/api/runs/${runId}/intermediate/${filename}`);
      if (res.ok) {
        const json = await res.json();
        setData((prev) => ({ ...prev, [filename]: json }));
      }
    } catch {
      /* ignore */
    } finally {
      setLoading("");
    }
  };

  const label = (name) => {
    if (name.startsWith("chunk_")) return `Chunk ${name.replace("chunk_", "").replace(".json", "")}`;
    if (name === "reconcile_input.json") return "Reconcile Input";
    if (name === "reconcile_output.json") return "Reconcile Output";
    return name.replace(".json", "");
  };

  return (
    <div className="chunks-list">
      {chunkFiles.map((f) => (
        <div key={f} className={`chunk-item ${expanded === f ? "open" : ""}`}>
          <button className="chunk-toggle" onClick={() => handleToggle(f)}>
            <span className="chunk-label">{label(f)}</span>
            <span className="chunk-filename">{f}</span>
            <span className="chunk-arrow">{expanded === f ? "\u25B2" : "\u25BC"}</span>
          </button>
          {expanded === f && (
            <div className="chunk-content">
              {loading === f ? (
                <p className="chunk-loading">Loading...</p>
              ) : data[f] ? (
                <pre className="chunk-json">{JSON.stringify(data[f], null, 2)}</pre>
              ) : (
                <p className="chunk-loading">Failed to load.</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
