import PipelineSummary from "./PipelineSummary.jsx";

export default function DebugPanel({ payload, onClose }) {
  if (!payload) {
    return null;
  }

  const sections = [
    ["Processed question", payload.processed_question],
    ["Classification", payload.classification],
    ["Routing", payload.routing],
    ["Retrieval", payload.retrieval],
    ["Reranking", payload.reranking],
    ["Tax calculation raw", payload.tax_calculation],
    ["Response validation", payload.response_validation],
  ].filter(([, value]) => value);

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="drawer drawer--wide">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Debug</p>
            <h2>Chi tiết pipeline</h2>
          </div>
          <button className="drawer-close-button" type="button" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </div>

        <PipelineSummary response={payload} />

        <div className="debug-section-list">
          {sections.map(([title, value]) => (
            <details key={title} className="debug-section" open={title === "Classification"}>
              <summary>{title}</summary>
              <pre>{JSON.stringify(value, null, 2)}</pre>
            </details>
          ))}
        </div>
      </aside>
    </div>
  );
}
