import CitationItem from "./CitationItem.jsx";

export default function CitationList({ citations, onOpenCitation }) {
  if (!citations.length) {
    return null;
  }

  return (
    <section className="citation-section">
      <div className="section-heading">
        <h3>Nguồn pháp luật</h3>
        <span>{citations.length} nguồn</span>
      </div>
      <div className="citation-list">
        {citations.map((citation) => (
          <CitationItem
            key={citation.citation_id}
            citation={citation}
            onOpen={() => onOpenCitation(citation)}
          />
        ))}
      </div>
    </section>
  );
}
