export default function Header({
  eyebrow = "Chatbot RAG Thuế TNCN",
  title = "Trợ lý hỏi đáp Thuế thu nhập cá nhân",
  health,
  healthError,
  isChecking,
  onRefresh,
}) {
  const statusLabel = health
    ? `Backend sẵn sàng - ${health.app_version}`
    : healthError || "Đang kiểm tra backend";

  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      <div className="header-status">
        <span
          className={`status-dot ${health ? "status-dot--online" : "status-dot--offline"}`}
          aria-hidden="true"
        />
        <span>{isChecking ? "Đang kiểm tra..." : statusLabel}</span>
        <button className="icon-text-button" type="button" onClick={onRefresh}>
          Kiểm tra
        </button>
      </div>
    </header>
  );
}
