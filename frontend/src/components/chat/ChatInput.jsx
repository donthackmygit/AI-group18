import { useState } from "react";

export default function ChatInput({ isSending, onSendMessage }) {
  const [value, setValue] = useState("");

  function submitMessage() {
    const question = value.trim();
    if (!question || isSending) {
      return;
    }
    onSendMessage(question);
    setValue("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitMessage();
    }
  }

  return (
    <form
      className="chat-input"
      onSubmit={(event) => {
        event.preventDefault();
        submitMessage();
      }}
    >
      <textarea
        aria-label="Nhập câu hỏi Thuế TNCN"
        placeholder="Nhập câu hỏi về Thuế TNCN, ví dụ: Lương 30 triệu có 2 người phụ thuộc thì nộp bao nhiêu thuế?"
        rows={3}
        value={value}
        disabled={isSending}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button className="send-button" type="submit" disabled={isSending || !value.trim()}>
        {isSending ? "Đang gửi" : "Gửi"}
      </button>
    </form>
  );
}
