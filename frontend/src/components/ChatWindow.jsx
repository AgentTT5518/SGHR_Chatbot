import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";

const WELCOME = `Welcome to the **HR Assistant**. I can help you with questions about:
- Singapore Employment Act rights and obligations
- Leave entitlements (annual, sick, maternity, paternity, childcare)
- Salary requirements and overtime rules
- Termination and notice period rules
- Workplace fairness guidelines

Ask your question below. Toggle your role above for tailored answers.`;

export function ChatWindow({ messages, isLoading, sessionId, onFeedback }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-window">
      {messages.length === 0 && !isLoading && (
        <div className="welcome-message">
          <MessageBubble
            message={{ id: "welcome", role: "assistant", content: WELCOME, sources: [], isStreaming: false }}
          />
        </div>
      )}

      {isLoading && messages.length === 0 && (
        <div className="loading-skeleton">
          <div className="skeleton-line" />
          <div className="skeleton-line short" />
        </div>
      )}

      {messages.map((msg, index) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          messageIndex={index}
          sessionId={sessionId}
          onFeedback={onFeedback}
        />
      ))}

      <div ref={bottomRef} />
    </div>
  );
}
