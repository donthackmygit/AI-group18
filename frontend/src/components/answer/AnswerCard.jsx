import CalculationSummary from "../calculation/CalculationSummary.jsx";
import CitationList from "../citations/CitationList.jsx";
import PipelineSummary from "../debug/PipelineSummary.jsx";
import FeedbackButtons from "../feedback/FeedbackButtons.jsx";
import ConfidenceBadge from "./ConfidenceBadge.jsx";
import WarningBanner from "./WarningBanner.jsx";

export default function AnswerCard({ message, onOpenCitation, onOpenDebug, onSubmitFeedback }) {
  const response = message.response;

  if (message.status === "loading") {
    return <p className="assistant-loading">{message.content}</p>;
  }

  if (message.status === "error") {
    return (
      <div className="answer-card">
        <WarningBanner warning={message.content} tone="error" />
      </div>
    );
  }

  if (!response) {
    return <p className="plain-message">{message.content}</p>;
  }

  return (
    <div className="answer-card">
      <div className="answer-toolbar">
        <span className={`mode-badge mode-badge--${response.mode || "unknown"}`}>
          {response.mode || "unknown"}
        </span>
        <ConfidenceBadge value={response.confidence} />
      </div>

      <WarningBanner warning={response.warning} />

      <div className="answer-text">
        {response.answer.split("\n").map((line, index) => (
          <p key={`${line}-${index}`}>{line || "\u00a0"}</p>
        ))}
      </div>

      <CalculationSummary calculation={response.calculation} />

      <CitationList citations={response.citations || []} onOpenCitation={onOpenCitation} />

      <PipelineSummary response={response} compact />

      <div className="answer-actions">
        <FeedbackButtons
          messageId={response.assistant_message_id || message.persistedId || message.id}
          onSubmitFeedback={onSubmitFeedback}
        />
        <button className="secondary-button" type="button" onClick={() => onOpenDebug(response)}>
          Xem debug
        </button>
      </div>
    </div>
  );
}
