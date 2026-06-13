import { formatDate } from "../../utils/formatDate.js";

export default function Sidebar({
  activeView = "chat",
  conversations,
  currentConversationId,
  health,
  healthError,
  user,
  authError,
  isAuthLoading,
  onSignOut,
  onChangeView,
  onNewConversation,
  onSelectConversation,
}) {
  const handleNewConversation = () => {
    onChangeView?.("chat");
    onNewConversation();
  };

  return (
    <div className="sidebar">
      <div className="sidebar-top">
        <div>
          <div className="brand-mark">TNCN</div>
          <p className="sidebar-title">
            {activeView === "admin" ? "Quản trị tài liệu" : "Hội thoại"}
          </p>
        </div>
        <button className="primary-button" type="button" onClick={handleNewConversation}>
          Chat mới
        </button>
      </div>

      <div className="view-switch" aria-label="Chuyển khu vực">
        <button
          className={`view-switch-button ${activeView === "chat" ? "view-switch-button--active" : ""}`}
          type="button"
          onClick={() => onChangeView?.("chat")}
        >
          Hội thoại
        </button>
        <button
          className={`view-switch-button ${
            activeView === "admin" ? "view-switch-button--active" : ""
          }`}
          type="button"
          onClick={() => onChangeView?.("admin")}
        >
          Tài liệu
        </button>
      </div>

      <div className="backend-panel">
        <span className={`status-dot ${health ? "status-dot--online" : "status-dot--offline"}`} />
        <div>
          <strong>{health ? "Backend online" : "Backend offline"}</strong>
          <p>{health ? health.embedding_model : healthError || "Chưa kết nối được FastAPI."}</p>
        </div>
      </div>

      <div className="backend-panel">
        <span
          className={`status-dot ${user && !authError ? "status-dot--online" : "status-dot--offline"}`}
        />
        <div>
          <strong>{user ? "Supabase Auth online" : "Supabase Auth offline"}</strong>
          <p>
            {isAuthLoading
              ? "Đang đăng nhập..."
              : user
                ? `User: ${user.id}`
                : authError || "Chưa có phiên đăng nhập."}
          </p>
          {user ? (
            <button className="mini-button" type="button" onClick={onSignOut}>
              Đăng xuất
            </button>
          ) : null}
        </div>
      </div>

      <nav className="conversation-list" aria-label="Danh sách hội thoại">
        {conversations.map((conversation) => (
          <button
            key={conversation.id}
            className={`conversation-item ${
              conversation.id === currentConversationId ? "conversation-item--active" : ""
            }`}
            type="button"
            onClick={() => {
              onChangeView?.("chat");
              onSelectConversation(conversation.id);
            }}
          >
            <span>{conversation.title}</span>
            <small>{formatDate(conversation.updatedAt || conversation.createdAt)}</small>
          </button>
        ))}
      </nav>
    </div>
  );
}
