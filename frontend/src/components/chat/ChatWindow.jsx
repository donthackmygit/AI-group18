import ChatInput from "./ChatInput.jsx";
import ExamplePrompts from "./ExamplePrompts.jsx";
import MessageList from "./MessageList.jsx";

export default function ChatWindow({
  conversation,
  isSending,
  chatError,
  isLoadingMessages,
  onSendMessage,
  onOpenCitation,
  onOpenDebug,
  onSubmitFeedback,
}) {
  const messages = conversation?.messages || [];

  return (
    <section className="chat-window" aria-label="Khu vực chat">
      <div className="chat-scroll">
        {chatError ? <div className="chat-error-banner">{chatError}</div> : null}
        {isLoadingMessages ? <div className="chat-loading-banner">Đang tải tin nhắn...</div> : null}
        {messages.length === 0 ? (
          <ExamplePrompts onPickPrompt={onSendMessage} isDisabled={isSending} />
        ) : (
          <MessageList
            messages={messages}
            onOpenCitation={onOpenCitation}
            onOpenDebug={onOpenDebug}
            onSubmitFeedback={onSubmitFeedback}
          />
        )}
      </div>
      <ChatInput isSending={isSending} onSendMessage={onSendMessage} />
    </section>
  );
}
