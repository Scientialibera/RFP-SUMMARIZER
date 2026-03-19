import { formatRunDate } from "../utils/format";

export default function Sidebar({
  rfps,
  selectedRfpId,
  selectedRunId,
  isLoading,
  onSelectRun,
}) {
  if (isLoading) {
    return (
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>RFP Library</h2>
        </div>
        <div className="sidebar-empty">Loading...</div>
      </aside>
    );
  }

  if (!rfps.length) {
    return (
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>RFP Library</h2>
        </div>
        <div className="sidebar-empty">No processed RFPs found.</div>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>RFP Library</h2>
        <span className="count">{rfps.length} RFPs</span>
      </div>
      <nav className="sidebar-list">
        {rfps.map((rfp) => (
          <div
            key={rfp.id}
            className={`sidebar-group ${rfp.id === selectedRfpId ? "active" : ""}`}
          >
            <div className="sidebar-rfp-name">
              <span className="rfp-name-text">{rfp.name}</span>
              <span className="run-badge">{rfp.run_count} runs</span>
            </div>
            <div className="sidebar-runs">
              {(rfp.runs ?? []).map((run) => {
                const date = formatRunDate(run.created_at, run.id);
                return (
                  <button
                    key={run.id}
                    className={`sidebar-run ${run.id === selectedRunId ? "active" : ""}`}
                    onClick={() => onSelectRun(rfp.id, run.id)}
                  >
                    <span className="run-time">{date}</span>
                    <span className="run-meta">
                      {run.chunk_count > 0 && `${run.chunk_count} chunks`}
                      {run.has_pdf && " \u00b7 PDF"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
