import { useState } from "react";

export default function FeedbackButtons({ messageId, onSubmitFeedback }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);

  async function submit(nextValue, rating) {
    if (!onSubmitFeedback) {
      setValue(nextValue);
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await onSubmitFeedback(messageId, rating);
      setValue(nextValue);
    } catch (err) {
      setError(err.message || "Không lưu được feedback.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div>
      <div className="feedback-group" aria-label="Đánh giá câu trả lời">
        <button
          className={`feedback-button ${value === "useful" ? "feedback-button--active" : ""}`}
          type="button"
          disabled={isSaving}
          onClick={() => submit("useful", 1)}
          aria-pressed={value === "useful"}
        >
          Hữu ích
        </button>
        <button
          className={`feedback-button ${value === "unclear" ? "feedback-button--active" : ""}`}
          type="button"
          disabled={isSaving}
          onClick={() => submit("unclear", -1)}
          aria-pressed={value === "unclear"}
        >
          Chưa rõ
        </button>
        <span className="sr-only">Feedback Supabase cho message {messageId}</span>
      </div>
      {error ? <p className="feedback-error">{error}</p> : null}
    </div>
  );
}
