import useAuthFetch from "../hooks/useAuthFetch";

export default function ContextTab({ runId, hasContext }) {
  const { data: text, loading } = useAuthFetch(
    runId ? `/api/runs/${runId}/context` : null,
    { skip: !hasContext, as: "text" },
  );

  if (!hasContext) {
    return <div className="tab-empty">No context file for this run.</div>;
  }

  if (loading) {
    return <div className="tab-empty">Loading context...</div>;
  }

  return (
    <div className="context-container">
      <div className="context-header">
        <span>fed_context.txt</span>
        <span className="context-size">
          {((text?.length ?? 0) / 1024).toFixed(1)} KB
        </span>
      </div>
      <pre className="context-text">{text}</pre>
    </div>
  );
}
