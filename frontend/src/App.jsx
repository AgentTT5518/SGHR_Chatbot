import { useState } from "react";
import { useChat } from "./hooks/useChat";
import { ChatWindow } from "./components/ChatWindow";
import { InputBar } from "./components/InputBar";
import { RoleToggle, getStoredRole } from "./components/RoleToggle";
import { StatusBanner } from "./components/StatusBanner";
import { AdminDashboard } from "./pages/AdminDashboard";
import "./styles/index.css";

export default function App() {
  const [role, setRole] = useState(getStoredRole);
  const [showAdmin, setShowAdmin] = useState(false);
  const { messages, isLoading, error, sendUserMessage, resetSession, sessionId, submitFeedback } = useChat(role);

  if (showAdmin) {
    return <AdminDashboard onClose={() => setShowAdmin(false)} />;
  }

  return (
    <div className="app">
      <StatusBanner />

      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">HR Assistant</h1>
          <span className="app-subtitle">Singapore Employment Act &amp; MOM Guidelines</span>
        </div>
        <div className="header-right">
          <RoleToggle role={role} onChange={setRole} />
          <button className="new-chat-btn" onClick={resetSession} title="Start new conversation">
            New Chat
          </button>
          <button className="admin-btn" onClick={() => setShowAdmin(true)} title="Admin dashboard">
            Admin
          </button>
        </div>
      </header>

      <main className="app-main">
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          sessionId={sessionId}
          onFeedback={submitFeedback}
        />
      </main>

      {error && (
        <div className="error-toast">
          &#9888; {error}
        </div>
      )}

      <footer className="app-footer">
        <InputBar onSend={sendUserMessage} disabled={isLoading} />
        <p className="disclaimer">
          This assistant provides general information only. For legal advice, consult a Singapore
          employment lawyer or contact{" "}
          <a href="https://www.mom.gov.sg" target="_blank" rel="noopener noreferrer">
            MOM
          </a>.
        </p>
      </footer>
    </div>
  );
}
