const API_BASE = ""; // Vite proxy routes /api, /health, /admin to localhost:8000

/**
 * Send a chat message and stream the response via fetch ReadableStream.
 * Calls onToken(text) for each streamed token.
 * Returns { sources } on completion.
 */
export async function sendMessage({ sessionId, userId, message, userRole, onToken, onStatus, onError }) {
  let sources = [];
  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        user_id: userId,
        message,
        user_role: userRole,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        try {
          const event = JSON.parse(raw);
          if (event.error) {
            onError?.(event.error);
            return { sources: [] };
          }
          if (event.status) {
            onStatus?.(event.detail || event.status);
          }
          if (event.token) {
            onToken(event.token);
          }
          if (event.done) {
            sources = event.sources || [];
          }
        } catch {
          // malformed SSE line — skip
        }
      }
    }
  } catch (err) {
    onError?.(err.message || "Network error");
  }
  return { sources };
}

/**
 * Fetch conversation history for a session from the backend.
 * Returns null if session not found (404) or on network error.
 */
export async function fetchHistory(sessionId) {
  try {
    const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch {
    return null;
  }
}

/** Check backend health. Returns the health object or null on error. */
export async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Submit thumbs-up or thumbs-down feedback for an assistant message.
 * @param {Object} opts
 * @param {string} opts.sessionId
 * @param {number} opts.messageIndex - array index of the message in the conversation
 * @param {"up"|"down"} opts.rating
 * @param {string} [opts.comment]
 * @returns {Promise<boolean>} true on success
 */
export async function submitFeedback({ sessionId, messageIndex, rating, comment }) {
  try {
    const response = await fetch(`${API_BASE}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message_index: messageIndex,
        rating,
        comment: comment ?? null,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}
