import { formatDate } from "../../utils/formatDate.js";
import AnswerCard from "../answer/AnswerCard.jsx";

export default function MessageBubble({
  message,
  onOpenCitation,
  onOpenDebug,
  onSubmitFeedback,
}) {
  const isUser = message.role === "user";

  return (
    <article className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      <div className={`message-bubble ${isUser ? "message-bubble--user" : ""}`}>
        <div className="message-meta">
          <span>{isUser ? "Bạn" : "Trợ lý Thuế TNCN"}</span>
          <time>{formatDate(message.createdAt)}</time>
        </div>

        {isUser ? (
          <p className="plain-message">{message.content}</p>
        ) : (
          <AnswerCard
            message={message}
            onOpenCitation={onOpenCitation}
            onOpenDebug={onOpenDebug}
            onSubmitFeedback={onSubmitFeedback}
          />
        )}
      </div>
    </article>
  );
}
