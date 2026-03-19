const FIELD_CONFIG = [
  { key: "summary", label: "Summary", type: "summary" },
  { key: "fee", label: "Fee", type: "list" },
  { key: "date", label: "Dates", type: "list" },
  { key: "best_lead_org", label: "Best Lead Org", type: "list" },
  { key: "cross_sell_opps", label: "Cross-Sell Opportunities", type: "list" },
  { key: "capabilities_for_rfp", label: "Capabilities for RFP", type: "list" },
  { key: "diversity_allocation", label: "Diversity Allocation", type: "single" },
];

export default function ResultsTab({ result }) {
  if (!result) {
    return <div className="tab-empty">No extraction results available.</div>;
  }

  return (
    <div className="results-grid">
      {FIELD_CONFIG.map(({ key, label, type }) => (
        <FieldCard key={key} label={label} type={type} fieldKey={key} data={result} />
      ))}
    </div>
  );
}

function FieldCard({ label, type, fieldKey, data }) {
  const value = data[fieldKey];
  const isEmpty = !value || (Array.isArray(value) && value.length === 0);

  return (
    <div className={`field-card ${isEmpty ? "empty" : ""}`}>
      <div className="field-card-header">
        <h3>{label}</h3>
        {!isEmpty && <span className="field-tag">Extracted</span>}
      </div>
      <div className="field-card-body">
        {type === "summary" && <SummaryBody value={value} />}
        {type === "list" && <ListBody value={value} fieldKey={fieldKey} />}
        {type === "single" && <SingleBody value={value} />}
      </div>
    </div>
  );
}

function SummaryBody({ value }) {
  if (!value) return <p className="no-data">No summary extracted.</p>;
  const text = typeof value === "string" ? value : value.summary || "";
  const snippets = Array.isArray(value?.snippets) ? value.snippets : [];
  return (
    <>
      <p className="summary-text">{text}</p>
      <SnippetList snippets={snippets} />
    </>
  );
}

function ListBody({ value, fieldKey }) {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  if (!items.length) return <p className="no-data">Not found in document.</p>;

  return items.map((item, i) => {
    const mainValue =
      item?.fee ?? item?.date ?? item?.best_lead_org ??
      item?.cross_sell_opps ?? item?.capabilities_for_rfp ?? "";
    const typeLabel =
      item?.fee_type ?? item?.date_type ?? "";
    const snippets = Array.isArray(item?.snippets) ? item.snippets : [];

    return (
      <div key={`${fieldKey}-${i}`} className="list-entry">
        <div className="entry-meta">
          {typeLabel && <span className="entry-pill">{typeLabel}</span>}
          {item?.pages?.length > 0 && (
            <span className="entry-pages">
              p. {item.pages.join(", ")}
            </span>
          )}
        </div>
        <p className="entry-value">{mainValue}</p>
        {item?.reason && (
          <div className="entry-reason">
            <span>Reason</span>
            <p>{item.reason}</p>
          </div>
        )}
        <SnippetList snippets={snippets} />
      </div>
    );
  });
}

function SingleBody({ value }) {
  if (!value) return <p className="no-data">Not found in document.</p>;
  const snippets = Array.isArray(value?.snippets) ? value.snippets : [];
  return (
    <div className="list-entry">
      <div className="entry-meta">
        <span className="entry-pill">
          {value.diversity_allocation ? "Required" : "Not required"}
        </span>
        {value?.pages?.length > 0 && (
          <span className="entry-pages">p. {value.pages.join(", ")}</span>
        )}
      </div>
      {value.reason && (
        <div className="entry-reason">
          <span>Reason</span>
          <p>{value.reason}</p>
        </div>
      )}
      <SnippetList snippets={snippets} />
    </div>
  );
}

function SnippetList({ snippets }) {
  if (!snippets?.length) return null;
  return (
    <details className="snippet-block">
      <summary>Snippets ({snippets.length})</summary>
      <div className="snippet-items">
        {snippets.map((s, i) => (
          <div key={i} className="snippet-item">{s}</div>
        ))}
      </div>
    </details>
  );
}
