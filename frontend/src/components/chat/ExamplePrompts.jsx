const EXAMPLE_PROMPTS = [
  "Mức giảm trừ gia cảnh cho bản thân và người phụ thuộc là bao nhiêu?",
  "Lương 30 triệu mỗi tháng, có 2 người phụ thuộc thì nộp thuế TNCN bao nhiêu?",
  "Thu nhập từ tiền lương có phải chịu thuế TNCN không?",
  "Đăng ký người phụ thuộc cần lưu ý điều gì?",
];

export default function ExamplePrompts({ onPickPrompt, isDisabled }) {
  return (
    <div className="empty-state">
      <div>
        <p className="eyebrow">Sẵn sàng hỏi đáp</p>
        <h2>Đặt câu hỏi về Thuế thu nhập cá nhân</h2>
        <p>
          Câu trả lời sẽ được backend tổng hợp từ RAG, tính thuế nếu có dữ liệu và kèm nguồn
          pháp luật để đối chiếu.
        </p>
      </div>
      <div className="prompt-grid">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            className="prompt-button"
            type="button"
            disabled={isDisabled}
            onClick={() => onPickPrompt(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
