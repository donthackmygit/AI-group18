import { useState } from "react";

export default function FeedbackButtons({ messageId, onSubmitFeedback }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [notice, setNotice] = useState(null);

  async function submit(nextValue, rating) {
    setIsSaving(true);
    setError(null);
    setNotice(null);

    try {
      if (onSubmitFeedback) {
        await onSubmitFeedback(messageId, rating);
      }

      setValue(nextValue);
      setNotice(
        nextValue === "useful"
          ? "Đã ghi nhận: câu trả lời hữu ích."
          : "Đã ghi nhận: câu trả lời chưa rõ."
      );
    } catch (err) {
      setError(err.message || "Không lưu được đánh giá.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="feedback">
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

      {notice ? <p className="feedback-status">{notice}</p> : null}
      {error ? <p className="feedback-error">{error}</p> : null}
    </div>
  );
}