import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MessageBubble({ message, messageIndex, sessionId, onFeedback }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [feedback, setFeedback] = useState(null); // "up" | "down" | null
  const isUser = message.role === "user";
  const canRate = !isUser && !message.isStreaming && message.content;

  function handleFeedback(rating) {
    if (feedback === rating) return; // already rated
    setFeedback(rating);
    onFeedback?.(messageIndex, rating);
  }

  return (
    <div className={`message-bubble ${isUser ? "user" : "assistant"}`}>
      <div className="message-role">{isUser ? "You" : "HR Assistant"}</div>
      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content || (message.isStreaming ? "▋" : "")}
        </ReactMarkdown>
      </div>

      {!isUser && message.sources && message.sources.length > 0 && (
        <div className="sources-section">
          <button
            className="sources-toggle"
            onClick={() => setSourcesOpen((o) => !o)}
          >
            {sourcesOpen ? "▾" : "▸"} Sources ({message.sources.length})
          </button>
          {sourcesOpen && (
            <ul className="sources-list">
              {message.sources.map((src, i) => (
                <li key={i}>
                  {src.url ? (
                    <a href={src.url} target="_blank" rel="noopener noreferrer">
                      {src.label}
                    </a>
                  ) : (
                    <span>{src.label}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {canRate && (
        <div className="feedback-bar">
          <button
            className={`feedback-btn ${feedback === "up" ? "active" : ""}`}
            onClick={() => handleFeedback("up")}
            title="Helpful"
            aria-label="Mark as helpful"
          >
            👍
          </button>
          <button
            className={`feedback-btn ${feedback === "down" ? "active" : ""}`}
            onClick={() => handleFeedback("down")}
            title="Not helpful"
            aria-label="Mark as not helpful"
          >
            👎
          </button>
          {feedback && (
            <span className="feedback-thanks">Thanks for the feedback!</span>
          )}
        </div>
      )}
    </div>
  );
}
