import CalculationSummary from "../calculation/CalculationSummary.jsx";
import CitationList from "../citations/CitationList.jsx";
import PipelineSummary from "../debug/PipelineSummary.jsx";
import FeedbackButtons from "../feedback/FeedbackButtons.jsx";
import ConfidenceBadge from "./ConfidenceBadge.jsx";
import WarningBanner from "./WarningBanner.jsx";
import ReactMarkdown from "react-markdown";
function extractAnswerText(value) {
  if (typeof value !== "string") {
    return "";
  }

  const normalized = value.trim();

  if (!normalized) {
    return "";
  }

  const candidates = [
    normalized,
    normalized
      .replace(/^```json\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/\s*```$/i, "")
      .trim(),
  ];

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);

      if (
        parsed &&
        typeof parsed === "object" &&
        typeof parsed.answer === "string"
      ) {
        return parsed.answer.trim();
      }
    } catch {
      // Không phải JSON hợp lệ thì hiển thị như chuỗi bình thường.
    }
  }

  return normalized;
}

function renderAnswerLine(line, index) {
  const normalizedLine = line.trim();

  if (!normalizedLine) {
    return <br key={`empty-${index}`} />;
  }

  if (
    normalizedLine.startsWith("* ") ||
    normalizedLine.startsWith("- ")
  ) {
    return (
      <li key={`item-${index}`}>
        {normalizedLine.slice(2).trim()}
      </li>
    );
  }

  return (
    <p key={`paragraph-${index}`}>
      {normalizedLine}
    </p>
  );
}

export default function AnswerCard({
  message,
  onOpenCitation,
  onOpenDebug,
  onSubmitFeedback,
}) {
  const response = message.response;

  if (message.status === "loading") {
    return (
      <p className="assistant-loading">
        {message.content}
      </p>
    );
  }

  if (message.status === "error") {
    return (
      <div className="answer-card">
        <WarningBanner
          warning={message.content}
          tone="error"
        />
      </div>
    );
  }

  if (!response) {
    const plainAnswer = extractAnswerText(message.content);

    return (
      <div className="plain-message">
        {plainAnswer.split("\n").map(renderAnswerLine)}
      </div>
    );
  }

  const answerText = extractAnswerText(response.answer);
  const warnings = Array.isArray(response.warnings)
    ? response.warnings
    : response.warning
      ? [response.warning]
      : [];

  return (
    <div className="answer-card">
      <div className="answer-toolbar">
        <span
          className={`mode-badge mode-badge--${
            response.mode || "unknown"
          }`}
        >
          {response.mode || "unknown"}
        </span>

        <ConfidenceBadge value={response.confidence} />
      </div>

      {warnings.map((warning, index) => (
        <WarningBanner
          key={`${warning}-${index}`}
          warning={warning}
        />
      ))}

      <div className="answer-text">
        <ReactMarkdown>{answerText}</ReactMarkdown>
      </div>

      <CalculationSummary
        calculation={response.calculation}
      />

      <CitationList
        citations={response.citations || []}
        onOpenCitation={onOpenCitation}
      />

      <PipelineSummary response={response} compact />

      <div className="answer-actions">
        <FeedbackButtons
          messageId={
            response.assistant_message_id ||
            message.persistedId ||
            message.id
          }
          onSubmitFeedback={onSubmitFeedback}
        />

        <button
          className="secondary-button"
          type="button"
          onClick={() => onOpenDebug(response)}
        >
          Xem debug
        </button>
      </div>
    </div>
  );
}