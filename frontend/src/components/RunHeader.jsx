import { formatRunDate } from "../utils/format";

export default function RunHeader({ run, rfpName }) {
  if (!run) return null;
  const meta = run.metadata || {};
  const createdAt = formatRunDate(meta.created_at, run.id);

  return (
    <div className="run-header">
      <div className="run-header-left">
        <h1 className="run-title">{rfpName}</h1>
        <div className="run-meta-row">
          <span className="meta-chip">{run.id}</span>
          <span className="meta-chip">{createdAt}</span>
          {meta.chunking_enabled && (
            <span className="meta-chip accent">Chunked</span>
          )}
          {run.has_pdf && <span className="meta-chip teal">PDF available</span>}
          {run.chunk_files?.length > 0 && (
            <span className="meta-chip">
              {run.chunk_files.length} intermediate files
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
