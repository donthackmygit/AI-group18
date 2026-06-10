import { useEffect, useRef } from "react";

import MessageBubble from "./MessageBubble.jsx";

export default function MessageList({ messages, onOpenCitation, onOpenDebug, onSubmitFeedback }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="message-list">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          onOpenCitation={onOpenCitation}
          onOpenDebug={onOpenDebug}
          onSubmitFeedback={onSubmitFeedback}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}
