import { useState } from "react";

import { useChat } from "../../hooks/useChat.js";
import { useHealth } from "../../hooks/useHealth.js";
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

  return (
    <AppShell
      sidebar={
        <Sidebar
          conversations={chat.conversations}
          currentConversationId={chat.currentConversationId}
          health={health.health}
          healthError={health.error}
          user={chat.user}
          authError={chat.authError}
          isAuthLoading={chat.isAuthLoading}
          onSignOut={chat.signOut}
          onNewConversation={chat.newConversation}
          onSelectConversation={chat.selectConversation}
        />
      }
      header={
        <Header
          health={health.health}
          healthError={health.error}
          isChecking={health.isChecking}
          onRefresh={health.refresh}
        />
      }
    >
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
    </AppShell>
  );
}
