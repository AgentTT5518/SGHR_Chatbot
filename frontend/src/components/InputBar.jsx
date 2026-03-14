import { useState } from "react";

export function InputBar({ onSend, disabled }) {
  const [text, setText] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSubmit(e);
    }
  }

  return (
    <form className="input-bar" onSubmit={handleSubmit}>
      <textarea
        className="input-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about employment rights, leave entitlements, salary requirements…"
        rows={2}
        disabled={disabled}
      />
      <button className="send-btn" type="submit" disabled={disabled || !text.trim()}>
        Send
      </button>
    </form>
  );
}
