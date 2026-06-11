export default function CitationDrawer({ citation, onClose }) {
  if (!citation) {
    return null;
  }

  const rows = [
    ["Mã nguồn", citation.citation_id],
    ["Tên văn bản", citation.document_name],
    ["Số văn bản", citation.document_number],
    ["Điều", citation.article],
    ["Khoản", citation.clause],
    ["Trạng thái", citation.status],
  ].filter(([, value]) => value);

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="drawer">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Nguồn trích dẫn</p>
            <h2>{citation.document_name || citation.document_number || citation.citation_id}</h2>
          </div>
          <button className="drawer-close-button" type="button" onClick={onClose} aria-label="Đóng">
            ×
          </button>
        </div>

        <dl className="metadata-list">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>

        <div className="source-content">
          <h3>Nội dung trích dẫn</h3>
          <p>{citation.content}</p>
        </div>

        {citation.source_url ? (
          <a className="source-link" href={citation.source_url} target="_blank" rel="noreferrer">
            Mở nguồn
          </a>
        ) : null}
      </aside>
    </div>
  );
}
