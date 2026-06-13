import { useState } from "react";

import { useChat } from "../../hooks/useChat.js";
import { useHealth } from "../../hooks/useHealth.js";
import DocumentAdminPage from "../admin/DocumentAdminPage.jsx";
import AppShell from "../layout/AppShell.jsx";
import Header from "../layout/Header.jsx";
import Sidebar from "../layout/Sidebar.jsx";
import CitationDrawer from "../citations/CitationDrawer.jsx";
import DebugPanel from "../debug/DebugPanel.jsx";
import ChatWindow from "./ChatWindow.jsx";

export default function ChatPage() {
  const chat = useChat();
  const health = useHealth();
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [debugPayload, setDebugPayload] = useState(null);
  const [activeView, setActiveView] = useState("chat");

  return (
    <AppShell
      sidebar={
        <Sidebar
          activeView={activeView}
          conversations={chat.conversations}
          currentConversationId={chat.currentConversationId}
          health={health.health}
          healthError={health.error}
          user={chat.user}
          authError={chat.authError}
          isAuthLoading={chat.isAuthLoading}
          onSignOut={chat.signOut}
          onChangeView={setActiveView}
          onNewConversation={chat.newConversation}
          onSelectConversation={chat.selectConversation}
        />
      }
      header={
        <Header
          eyebrow={activeView === "admin" ? "Quản trị dữ liệu Thuế TNCN" : undefined}
          title={
            activeView === "admin"
              ? "Quản trị tài liệu pháp luật"
              : "Trợ lý hỏi đáp Thuế thu nhập cá nhân"
          }
          health={health.health}
          healthError={health.error}
          isChecking={health.isChecking}
          onRefresh={health.refresh}
        />
      }
    >
      {activeView === "admin" ? (
        <DocumentAdminPage accessToken={chat.session?.access_token || null} />
      ) : (
        <>
          <ChatWindow
            conversation={chat.currentConversation}
            isSending={chat.isSending || chat.isAuthLoading}
            chatError={chat.chatError || chat.authError}
            isLoadingMessages={chat.isLoadingMessages}
            onSendMessage={chat.sendMessage}
            onOpenCitation={setSelectedCitation}
            onOpenDebug={setDebugPayload}
            onSubmitFeedback={chat.submitFeedback}
          />
          <CitationDrawer citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
          <DebugPanel payload={debugPayload} onClose={() => setDebugPayload(null)} />
        </>
      )}
    </AppShell>
  );
}
