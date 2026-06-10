export default function PipelineSummary({ response, compact = false }) {
  if (!response) {
    return null;
  }

  const classification = response.classification;
  const routing = response.routing;
  const retrieval = response.retrieval;
  const reranking = response.reranking;

  if (!classification && !routing && !retrieval && !reranking) {
    return null;
  }

  const items = [
    ["Intent", classification?.intent],
    ["Route", routing?.route],
    ["Retrieval", retrieval ? `${retrieval.returned_count}/${retrieval.requested_top_k}` : null],
    ["Rerank", reranking ? `${reranking.output_count}/${reranking.input_count}` : null],
  ].filter(([, value]) => value !== null && value !== undefined);

  return (
    <section className={`pipeline-summary ${compact ? "pipeline-summary--compact" : ""}`}>
      {!compact ? <h3>Pipeline backend</h3> : null}
      <div className="pipeline-grid">
        {items.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
