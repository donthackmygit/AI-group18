export default function CitationItem({ citation, onOpen }) {
  const title =
    citation.document_name || citation.document_number || citation.citation_id || "Nguồn pháp luật";
  const legalPosition = [citation.article, citation.clause].filter(Boolean).join(", ");

  return (
    <button className="citation-item" type="button" onClick={onOpen}>
      <span className="citation-title">{title}</span>
      {legalPosition ? <span className="citation-position">{legalPosition}</span> : null}
      <span className="citation-preview">{citation.content}</span>
    </button>
  );
}
