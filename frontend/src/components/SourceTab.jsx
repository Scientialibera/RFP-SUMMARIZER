import { useEffect, useState } from "react";
import { authFetch } from "../auth/authFetch";

export default function SourceTab({ runId, hasPdf }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId || !hasPdf) {
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const res = await authFetch(`/api/runs/${runId}/pdf`);
        if (res.ok) {
          const blob = await res.blob();
          if (!cancelled) setBlobUrl(URL.createObjectURL(blob));
        }
      } catch {
        /* PDF load failure is non-critical */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [runId, hasPdf]);

  if (!hasPdf) {
    return <div className="tab-empty">No source PDF for this run.</div>;
  }

  if (loading) {
    return <div className="tab-empty">Loading PDF...</div>;
  }

  return (
    <div className="source-container">
      {blobUrl && (
        <>
          <div className="source-actions">
            <a href={blobUrl} target="_blank" rel="noreferrer" className="btn-primary">
              Open PDF in new tab
            </a>
            <a href={blobUrl} download="source.pdf" className="btn-ghost">
              Download PDF
            </a>
          </div>
          <iframe className="pdf-embed" src={blobUrl} title="Source PDF" />
        </>
      )}
    </div>
  );
}
