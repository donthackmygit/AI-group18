import PipelineSummary from "./PipelineSummary.jsx";

export default function DebugPanel({ payload, onClose }) {
  if (!payload) {
    return null;
  }

  const debug = normalizeDebugPayload(payload);
  const summaryPayload = { ...payload, ...debug };
  const hasDebug = Object.values(debug).some(Boolean);

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

        {!hasDebug ? (
          <div className="debug-empty">
            Chưa có dữ liệu debug cho câu trả lời này. Hãy hỏi một câu mới sau khi backend đã chạy bản mới.
          </div>
        ) : (
          <>
            <PipelineSummary response={summaryPayload} />
            <DebugOverview response={payload} debug={debug} />
            <QuestionDebug question={debug.processed_question} />
            <RetrievalDebug retrieval={debug.retrieval} context={debug.context} />
            <RerankingDebug reranking={debug.reranking} />
            <TaxDebug calculation={debug.tax_calculation || payload.tax_calculation || payload.calculation} />
            <ModelValidationDebug llm={debug.llm} validation={debug.response_validation} />
          </>
        )}
      </aside>
    </div>
  );
}

function normalizeDebugPayload(payload) {
  const debug = payload.debug && typeof payload.debug === "object" ? payload.debug : {};
  return {
    processed_question: debug.processed_question || payload.processed_question || null,
    classification: debug.classification || payload.classification || null,
    routing: debug.routing || payload.routing || null,
    query_embedding: debug.query_embedding || payload.query_embedding || null,
    retrieval: debug.retrieval || payload.retrieval || null,
    reranking: debug.reranking || payload.reranking || null,
    tax_calculation: debug.tax_calculation || payload.tax_calculation || null,
    context: debug.context || payload.context || null,
    llm: debug.llm || payload.llm || null,
    response_validation: debug.response_validation || payload.response_validation || null,
    response_formatter: debug.response_formatter || payload.response_formatter || null,
  };
}

function DebugOverview({ response, debug }) {
  const classification = debug.classification;
  const routing = debug.routing;
  const retrieval = debug.retrieval;
  const reranking = debug.reranking;
  const validation = debug.response_validation;

  const items = [
    ["Chế độ trả lời", response.mode || "Không rõ"],
    ["Intent", classification?.intent || "Không rõ"],
    ["Route", routing?.route || "Không rõ"],
    ["Độ tin cậy", formatPercent(response.confidence)],
    [
      "Nguồn truy xuất",
      retrieval ? `${retrieval.returned_count || 0}/${retrieval.requested_top_k || 0}` : "Không có",
    ],
    [
      "Rerank",
      reranking ? `${reranking.output_count || 0}/${reranking.input_count || 0}` : "Không có",
    ],
    ["Validation", validation?.status || "Chưa kiểm tra"],
  ];

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>Tổng quan</h3>
        <StatusPill value={validation?.is_valid === false ? "Cần kiểm tra" : "Ổn"} tone={validation?.is_valid === false ? "warn" : "ok"} />
      </div>
      <KeyValueGrid items={items} />
    </section>
  );
}

function QuestionDebug({ question }) {
  if (!question) {
    return null;
  }

  const entities = question.entities || {};
  const entityItems = Object.entries(entities).filter(([, value]) => value !== null && value !== undefined && value !== "");

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>Câu hỏi đã xử lý</h3>
      </div>
      <div className="debug-text-block">
        <span>Câu hỏi độc lập</span>
        <strong>{question.standalone_question || question.normalized_question || question.original_question}</strong>
      </div>
      {question.retrieval_query ? (
        <div className="debug-text-block">
          <span>Truy vấn tìm kiếm</span>
          <strong>{question.retrieval_query}</strong>
        </div>
      ) : null}
      <KeyValueGrid
        items={[
          ["Chủ đề", question.topic || "Không rõ"],
          ["Intent sơ bộ", question.intent || "Không rõ"],
        ]}
      />
      {entityItems.length ? (
        <div className="debug-chip-row" aria-label="Thông tin trích xuất">
          {entityItems.map(([key, value]) => (
            <span className="debug-chip" key={key}>
              {humanizeKey(key)}: {formatDebugValue(value)}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RetrievalDebug({ retrieval, context }) {
  if (!retrieval && !context) {
    return null;
  }

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>Truy xuất tài liệu</h3>
        {retrieval?.strategy ? <StatusPill value={retrieval.strategy} /> : null}
      </div>
      <KeyValueGrid
        items={[
          ["Nguồn dữ liệu", retrieval?.source || "Không rõ"],
          ["Bảng", retrieval?.table || "Không rõ"],
          ["Semantic candidates", retrieval?.semantic_count ?? "Không có"],
          ["Keyword candidates", retrieval?.keyword_count ?? "Không có"],
          ["Similarity trung bình", formatNumber(retrieval?.similarity_avg)],
          ["Context tokens", context?.estimated_tokens ?? "Không có"],
          ["Nguồn đưa vào prompt", context?.included_count ?? "Không có"],
          ["RAG framework", context?.rag_framework || "Custom pipeline"],
        ]}
      />
      {context?.sources?.length ? (
        <div className="debug-source-list">
          {context.sources.slice(0, 5).map((source) => (
            <article key={source.citation_id} className="debug-source-row">
              <strong>{source.citation_id}</strong>
              <span>{source.document_number || source.document_title || source.chunk_id}</span>
              <small>{source.article || source.article_title || "Không rõ điều/khoản"}</small>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RerankingDebug({ reranking }) {
  if (!reranking) {
    return null;
  }

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>Xếp hạng lại</h3>
        <StatusPill value={reranking.strategy || "Rerank"} />
      </div>
      <KeyValueGrid
        items={[
          ["Ứng viên đầu vào", reranking.input_count],
          ["Nguồn giữ lại", reranking.output_count],
          ["Điểm thấp nhất", formatNumber(reranking.score_min)],
          ["Điểm cao nhất", formatNumber(reranking.score_max)],
          ["Điểm trung bình", formatNumber(reranking.score_avg)],
        ]}
      />
      {reranking.candidates?.length ? (
        <div className="debug-rank-list">
          {reranking.candidates.slice(0, 5).map((candidate) => (
            <article key={candidate.chunk_id} className="debug-rank-row">
              <div>
                <strong>#{candidate.rerank_rank} {candidate.chunk_id}</strong>
                <span>
                  Hybrid {formatNumber(candidate.hybrid_score)} · Keyword {formatNumber(candidate.keyword_score)}
                </span>
              </div>
              <StatusPill value={formatNumber(candidate.rerank_score)} tone="neutral" />
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function TaxDebug({ calculation }) {
  if (!calculation) {
    return null;
  }

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>Tính thuế</h3>
        <StatusPill value={calculation.applied === false ? "Thiếu dữ liệu" : "Đã tính"} tone={calculation.applied === false ? "warn" : "ok"} />
      </div>
      <KeyValueGrid
        items={[
          ["Phương pháp", calculation.method || "Không rõ"],
          ["Rule", calculation.rule_id || "Không rõ"],
          ["Thu nhập tính thuế", formatMoney(calculation.taxable_income)],
          ["Giảm trừ bản thân", formatMoney(calculation.personal_deduction)],
          ["Giảm trừ phụ thuộc", formatMoney(calculation.dependent_deduction)],
          ["Thuế tạm tính", formatMoney(calculation.tax_amount)],
        ]}
      />
      {calculation.missing_fields?.length ? (
        <p className="debug-note">Thiếu: {calculation.missing_fields.join(", ")}</p>
      ) : null}
    </section>
  );
}

function ModelValidationDebug({ llm, validation }) {
  if (!llm && !validation) {
    return null;
  }

  return (
    <section className="debug-card">
      <div className="debug-card-header">
        <h3>LLM và kiểm tra câu trả lời</h3>
        {validation?.status ? <StatusPill value={validation.status} tone={validation.is_valid === false ? "warn" : "ok"} /> : null}
      </div>
      <KeyValueGrid
        items={[
          ["Model", llm?.model || "Không rõ"],
          ["Provider", llm?.provider || "Không rõ"],
          ["Prompt tokens", llm?.prompt_tokens ?? llm?.prompt_estimated_tokens ?? "Không có"],
          ["Output tokens", llm?.completion_tokens ?? "Không có"],
          ["Tổng tokens", llm?.total_tokens ?? "Không có"],
          ["Chi phí ước tính", formatUsd(llm?.estimated_cost_usd)],
          ["Nguồn đã trích", validation?.cited_source_ids?.length ?? "Không có"],
          ["Kết quả tính đúng", validation?.calculation_valid === false ? "Cần kiểm tra" : "Ổn"],
        ]}
      />
      {validation?.issues?.length ? (
        <div className="debug-issue-list">
          {validation.issues.map((issue, index) => (
            <article key={`${issue.code}-${index}`} className="debug-issue-row">
              <strong>{issue.code}</strong>
              <span>{issue.message}</span>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function KeyValueGrid({ items }) {
  const visibleItems = items.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!visibleItems.length) {
    return null;
  }

  return (
    <dl className="debug-kv-grid">
      {visibleItems.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{formatDebugValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function StatusPill({ value, tone = "neutral" }) {
  return <span className={`debug-pill debug-pill--${tone}`}>{value}</span>;
}

function formatDebugValue(value) {
  if (typeof value === "boolean") {
    return value ? "Có" : "Không";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "Không có";
  }
  if (typeof value === "number") {
    return formatNumber(value);
  }
  return String(value);
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Không có";
  }
  const number = Number(value);
  if (Math.abs(number) < 1 && number !== 0) {
    return number.toFixed(4);
  }
  return number.toLocaleString("vi-VN", { maximumFractionDigits: 4 });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Không có";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Không có";
  }
  return `${Number(value).toLocaleString("vi-VN")} VND`;
}

function formatUsd(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Không có";
  }
  return `$${Number(value).toFixed(6)}`;
}

function humanizeKey(key) {
  const labels = {
    income: "Thu nhập",
    income_period: "Kỳ thu nhập",
    insurance: "Bảo hiểm",
    dependents: "Người phụ thuộc",
    resident_status: "Cư trú",
    tax_year: "Năm thuế",
    days_in_vietnam: "Ngày ở Việt Nam",
    nationality: "Quốc tịch",
  };
  return labels[key] || key.replaceAll("_", " ");
}
