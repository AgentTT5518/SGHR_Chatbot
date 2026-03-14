import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MessageBubble({ message }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const isUser = message.role === "user";

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
    </div>
  );
}
