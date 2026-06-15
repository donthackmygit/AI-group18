import { useCallback, useEffect, useMemo, useState } from "react";

import {
  expireDocument,
  getDocument,
  importDocumentUrl,
  ingestDocument,
  listAllDocumentChunks,
  listDocuments,
  removeDocumentFromSearch,
  rerunDocumentEmbedding,
  updateDocument,
  uploadDocument,
} from "../../api/documentAdminApi.js";

const EMPTY_FORM = {
  document_id: "",
  document_title: "",
  document_number: "",
  document_type: "Thông tư",
  issuing_authority: "",
  issue_date: "",
  effective_date: "",
  expiry_date: "",
  status: "draft",
  source_url: "",
  version: "",
  topics: "",
  notes: "",
};

const STATUS_LABELS = {
  draft: "Bản nháp",
  effective: "Còn hiệu lực",
  partially_effective: "Còn hiệu lực một phần",
  expired: "Hết hiệu lực",
  superseded: "Đã thay thế",
};

const INGESTION_LABELS = {
  uploaded: "Đã tải lên",
  extracted: "Đã trích xuất",
  ingesting: "Đang xử lý",
  indexed: "Đã index",
  error: "Lỗi",
  removed_from_search: "Đã gỡ khỏi search",
};

export default function DocumentAdminPage({ accessToken }) {
  const [documents, setDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectedFile, setSelectedFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const selectedDocumentId = selectedDocument?.document_id || "";

  const stats = useMemo(() => {
    return documents.reduce(
      (summary, document) => {
        summary.total += 1;
        if (document.ingestion_status === "indexed") {
          summary.indexed += 1;
        }
        if (document.ingestion_status === "error") {
          summary.errors += 1;
        }
        summary.chunks += document.search_chunk_count || document.chunk_count || 0;
        return summary;
      },
      { total: 0, indexed: 0, errors: 0, chunks: 0 },
    );
  }, [documents]);

  const refreshDocuments = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await listDocuments(accessToken);
      setDocuments(response.items || []);
    } catch (err) {
      setError(err.message || "Không tải được danh sách tài liệu.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  const loadDocumentDetail = useCallback(
    async (documentId) => {
      if (!documentId || !accessToken) {
        return;
      }

      setIsWorking(true);
      setError(null);
      try {
        const [detailResponse, chunksResponse] = await Promise.all([
          getDocument(documentId, accessToken),
          listAllDocumentChunks(documentId, accessToken),
        ]);
        setSelectedDocument(detailResponse.document);
        setForm(formFromDocument(detailResponse.document));
        setChunks(chunksResponse.items || []);
      } catch (err) {
        setError(err.message || "Không tải được chi tiết tài liệu.");
      } finally {
        setIsWorking(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    refreshDocuments();
  }, [refreshDocuments]);

  const handleSelectDocument = (document) => {
    setSelectedDocument(document);
    setForm(formFromDocument(document));
    loadDocumentDetail(document.document_id);
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: value,
    }));
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!accessToken) {
      setError("Chưa có phiên đăng nhập để dùng API quản trị.");
      return;
    }
    if (!selectedFile) {
      setError("Chọn một file tài liệu trước khi tải lên.");
      return;
    }

    setIsWorking(true);
    setError(null);
    setNotice(null);
    try {
      const contentBase64 = await fileToBase64(selectedFile);
      const payload = compactPayload({
        ...form,
        file_name: selectedFile.name,
        content_base64: contentBase64,
      });
      const response = await uploadDocument(payload, accessToken);
      setSelectedDocument(response.document);
      setForm(formFromDocument(response.document));
      setChunks([]);
      setNotice("Đã tải lên và trích xuất preview.");
      await refreshDocuments();
    } catch (err) {
      setError(err.message || "Không tải lên được tài liệu.");
    } finally {
      setIsWorking(false);
    }
  };

  const handleImportUrl = async () => {
    if (!accessToken) {
      setError("Chưa có phiên đăng nhập để dùng API quản trị.");
      return;
    }
    if (!form.source_url.trim()) {
      setError("Nhập URL nguồn trước khi import.");
      return;
    }

    setIsWorking(true);
    setError(null);
    setNotice(null);
    try {
      const payload = compactPayload({
        ...form,
        file_name: form.document_id ? `${form.document_id}.html` : undefined,
      });
      const response = await importDocumentUrl(payload, accessToken);
      setSelectedDocument(response.document);
      setForm(formFromDocument(response.document));
      setChunks([]);
      setNotice("Đã import URL và trích xuất preview.");
      await refreshDocuments();
    } catch (err) {
      setError(err.message || "Không import được URL tài liệu.");
    } finally {
      setIsWorking(false);
    }
  };

  const handleUpdate = async () => {
    if (!selectedDocumentId || !accessToken) {
      return;
    }

    setIsWorking(true);
    setError(null);
    setNotice(null);
    try {
      const response = await updateDocument(
        selectedDocumentId,
        compactPayload(form, { includeDocumentId: false }),
        accessToken,
      );
      setSelectedDocument(response.document);
      setForm(formFromDocument(response.document));
      setNotice("Đã cập nhật metadata.");
      await refreshDocuments();
    } catch (err) {
      setError(err.message || "Không cập nhật được metadata.");
    } finally {
      setIsWorking(false);
    }
  };

  const runDocumentAction = async (action, successMessage) => {
    if (!selectedDocumentId || !accessToken) {
      return;
    }

    setIsWorking(true);
    setError(null);
    setNotice(null);
    try {
      const response = await action(selectedDocumentId, accessToken);
      const nextDocument = response.document;
      setSelectedDocument(nextDocument);
      setForm(formFromDocument(nextDocument));
      if (nextDocument.search_chunk_count || response.chunk_count) {
        const chunksResponse = await listAllDocumentChunks(selectedDocumentId, accessToken);
        setChunks(chunksResponse.items || []);
      } else {
        setChunks([]);
      }
      setNotice(successMessage);
      await refreshDocuments();
    } catch (err) {
      setError(err.message || "Thao tác không thành công.");
    } finally {
      setIsWorking(false);
    }
  };

  const handleRemoveFromSearch = async () => {
    if (!window.confirm("Gỡ toàn bộ chunk của tài liệu này khỏi kho tìm kiếm?")) {
      return;
    }
    await runDocumentAction(removeDocumentFromSearch, "Đã gỡ tài liệu khỏi kho tìm kiếm.");
  };

  return (
    <section className="admin-page">
      <div className="admin-summary">
        <SummaryMetric label="Tài liệu" value={stats.total} />
        <SummaryMetric label="Đã index" value={stats.indexed} />
        <SummaryMetric label="Chunk" value={stats.chunks} />
        <SummaryMetric label="Lỗi" value={stats.errors} tone={stats.errors ? "error" : "ok"} />
      </div>

      {error ? <div className="chat-error-banner">{error}</div> : null}
      {notice ? <div className="chat-loading-banner">{notice}</div> : null}

      <div className="admin-grid">
        <section className="admin-panel admin-panel--list">
          <div className="section-heading">
            <h3>Kho tài liệu</h3>
            <button
              className="secondary-button"
              type="button"
              onClick={refreshDocuments}
              disabled={isLoading || !accessToken}
            >
              Làm mới
            </button>
          </div>

          <div className="document-list">
            {documents.map((document) => (
              <button
                key={document.document_id}
                className={`document-row ${
                  document.document_id === selectedDocumentId ? "document-row--active" : ""
                }`}
                type="button"
                onClick={() => handleSelectDocument(document)}
              >
                <span className="document-row-title">
                  {document.document_title || document.document_id}
                </span>
                <span className="document-row-meta">
                  {document.document_number || document.document_type || "Chưa có số hiệu"}
                </span>
                <span className="document-row-badges">
                  <StatusBadge label={STATUS_LABELS[document.status] || document.status} />
                  <StatusBadge
                    label={INGESTION_LABELS[document.ingestion_status] || document.ingestion_status}
                    tone={document.ingestion_status === "error" ? "error" : "neutral"}
                  />
                </span>
              </button>
            ))}
            {!documents.length && !isLoading ? (
              <div className="empty-list">Chưa có tài liệu quản trị.</div>
            ) : null}
          </div>
        </section>

        <form className="admin-panel admin-panel--form" onSubmit={handleUpload}>
          <div className="section-heading">
            <h3>Metadata</h3>
            <span>{selectedDocumentId || "Tài liệu mới"}</span>
          </div>

          <div className="admin-form-grid">
            <label>
              Mã tài liệu
              <input
                name="document_id"
                value={form.document_id}
                onChange={handleChange}
                placeholder="VD: CIRCULAR_111_2013_TT_BTC"
              />
            </label>
            <label>
              Tiêu đề
              <input
                name="document_title"
                value={form.document_title}
                onChange={handleChange}
                required
              />
            </label>
            <label>
              Số hiệu
              <input name="document_number" value={form.document_number} onChange={handleChange} />
            </label>
            <label>
              Loại văn bản
              <input name="document_type" value={form.document_type} onChange={handleChange} />
            </label>
            <label>
              Cơ quan ban hành
              <input
                name="issuing_authority"
                value={form.issuing_authority}
                onChange={handleChange}
              />
            </label>
            <label>
              Trạng thái
              <select name="status" value={form.status} onChange={handleChange}>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Ngày ban hành
              <input name="issue_date" type="date" value={form.issue_date} onChange={handleChange} />
            </label>
            <label>
              Ngày hiệu lực
              <input
                name="effective_date"
                type="date"
                value={form.effective_date}
                onChange={handleChange}
              />
            </label>
            <label>
              Ngày hết hiệu lực
              <input
                name="expiry_date"
                type="date"
                value={form.expiry_date}
                onChange={handleChange}
              />
            </label>
            <label>
              Phiên bản
              <input name="version" value={form.version} onChange={handleChange} />
            </label>
            <label className="admin-form-wide">
              URL nguồn
              <input name="source_url" value={form.source_url} onChange={handleChange} />
            </label>
            <label className="admin-form-wide">
              Chủ đề
              <input name="topics" value={form.topics} onChange={handleChange} />
            </label>
            <label className="admin-form-wide">
              Ghi chú
              <textarea name="notes" value={form.notes} onChange={handleChange} rows={3} />
            </label>
          </div>

          <label className="file-drop">
            <span>{selectedFile ? selectedFile.name : "Chọn PDF, Word, HTML, TXT hoặc ảnh"}</span>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
            />
          </label>

          <div className="admin-actions">
            <button className="primary-button" type="submit" disabled={isWorking || !accessToken}>
              Tải lên
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={handleImportUrl}
              disabled={isWorking || !accessToken || !form.source_url.trim()}
            >
              Import URL
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={handleUpdate}
              disabled={isWorking || !selectedDocumentId}
            >
              Lưu metadata
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => runDocumentAction(ingestDocument, "Đã kích hoạt ingestion.")}
              disabled={isWorking || !selectedDocumentId}
            >
              Ingest
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() =>
                runDocumentAction(rerunDocumentEmbedding, "Đã chạy lại embedding.")
              }
              disabled={isWorking || !selectedDocumentId}
            >
              Re-embed
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => runDocumentAction(expireDocument, "Đã đánh dấu hết hiệu lực.")}
              disabled={isWorking || !selectedDocumentId}
            >
              Hết hiệu lực
            </button>
            <button
              className="secondary-button secondary-button--danger"
              type="button"
              onClick={handleRemoveFromSearch}
              disabled={isWorking || !selectedDocumentId}
            >
              Gỡ search
            </button>
          </div>
        </form>

        <section className="admin-panel admin-panel--preview">
          <div className="section-heading">
            <h3>Preview</h3>
            <span>{selectedDocument?.extracted_char_count || 0} ký tự</span>
          </div>

          <div className="document-preview">
            {selectedDocument?.extracted_preview || "Chọn hoặc tải lên tài liệu để xem preview."}
          </div>

          <div className="section-heading section-heading--chunks">
            <h3>Chunk</h3>
            <span>{chunks.length} mục</span>
          </div>

          <div className="chunk-list">
            {chunks.map((chunk) => (
              <article key={chunk.chunk_id} className="chunk-item">
                <div>
                  <strong>{chunk.article || chunk.chunk_id}</strong>
                  <span>{chunk.article_title || chunk.chunk_type || "chunk"}</span>
                </div>
                <p>{chunk.content}</p>
              </article>
            ))}
            {!chunks.length ? <div className="empty-list">Chưa có chunk để hiển thị.</div> : null}
          </div>
        </section>
      </div>
    </section>
  );
}

function SummaryMetric({ label, value, tone = "neutral" }) {
  return (
    <div className={`summary-metric summary-metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusBadge({ label, tone = "neutral" }) {
  return <span className={`admin-status admin-status--${tone}`}>{label || "Không rõ"}</span>;
}

function formFromDocument(document) {
  if (!document) {
    return EMPTY_FORM;
  }

  return {
    document_id: document.document_id || "",
    document_title: document.document_title || "",
    document_number: document.document_number || "",
    document_type: document.document_type || "",
    issuing_authority: document.issuing_authority || "",
    issue_date: dateInputValue(document.issue_date),
    effective_date: dateInputValue(document.effective_date),
    expiry_date: dateInputValue(document.expiry_date),
    status: document.status || "draft",
    source_url: document.source_url || "",
    version: document.version || "",
    topics: document.topics || "",
    notes: document.notes || "",
  };
}

function compactPayload(payload, options = {}) {
  const includeDocumentId = options.includeDocumentId !== false;
  return Object.fromEntries(
    Object.entries(payload)
      .filter(([key]) => includeDocumentId || key !== "document_id")
      .map(([key, value]) => [key, typeof value === "string" ? value.trim() : value])
      .filter(([, value]) => value !== ""),
  );
}

function dateInputValue(value) {
  if (!value) {
    return "";
  }
  return String(value).slice(0, 10);
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
