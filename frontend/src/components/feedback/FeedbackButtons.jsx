import { useState } from "react";

export default function FeedbackButtons({ messageId, onSubmitFeedback }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const [pendingValue, setPendingValue] = useState(null);

  const cannotSave = !messageId || !onSubmitFeedback;

  async function submit(nextValue, rating) {
    if (cannotSave) {
      setError("Chưa có mã câu trả lời để lưu đánh giá.");
      return;
    }

    setIsSaving(true);
    setPendingValue(nextValue);
    setError(null);
    setNotice(null);

    try {
      await onSubmitFeedback(messageId, rating);

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
      setPendingValue(null);
    }
  }

  return (
    <div className="feedback">
      <p className="feedback-label">Đánh giá câu trả lời</p>
      <div className="feedback-group" aria-label="Đánh giá câu trả lời">
        <button
          className={`feedback-button ${value === "useful" ? "feedback-button--active" : ""}`}
          type="button"
          disabled={isSaving || cannotSave}
          onClick={() => submit("useful", 1)}
          aria-pressed={value === "useful"}
        >
          {isSaving && pendingValue === "useful" ? "Đang lưu..." : "Hữu ích"}
        </button>

        <button
          className={`feedback-button ${value === "unclear" ? "feedback-button--active" : ""}`}
          type="button"
          disabled={isSaving || cannotSave}
          onClick={() => submit("unclear", -1)}
          aria-pressed={value === "unclear"}
        >
          {isSaving && pendingValue === "unclear" ? "Đang lưu..." : "Chưa rõ"}
        </button>

        <span className="sr-only">Feedback Supabase cho message {messageId}</span>
      </div>

      {cannotSave ? (
        <p className="feedback-help">Câu trả lời này chưa được lưu vào lịch sử nên chưa thể đánh giá.</p>
      ) : null}
      {notice ? <p className="feedback-status" role="status">{notice}</p> : null}
      {error ? <p className="feedback-error" role="alert">{error}</p> : null}
    </div>
  );
}
