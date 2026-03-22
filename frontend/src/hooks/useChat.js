import { useReducer, useEffect, useRef } from "react";
import { sendMessage, fetchHistory, submitFeedback as apiFeedback } from "../api/chatApi";

const SESSION_KEY = "hr_chat_session_id"; // stores the *signed* token from server
const MESSAGES_KEY = "hr_chat_messages";
const USER_KEY = "hr_chat_user_id";

function generateId() {
  return crypto.randomUUID();
}

function getStoredSessionId() {
  // Returns the signed session token or null (server assigns on first message)
  return sessionStorage.getItem(SESSION_KEY) || null;
}

function getOrCreateUserId() {
  let id = localStorage.getItem(USER_KEY);
  if (!id) {
    id = generateId();
    localStorage.setItem(USER_KEY, id);
  }
  return id;
}

const initialState = {
  sessionId: getStoredSessionId(),
  userId: getOrCreateUserId(),
  messages: [],
  isLoading: true, // starts true while hydrating
  error: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "HYDRATE_MESSAGES":
      return { ...state, messages: action.messages, isLoading: false };

    case "SET_LOADING":
      return { ...state, isLoading: action.value };

    case "SEND_MESSAGE": {
      const userMsg = {
        id: generateId(),
        role: "user",
        content: action.content,
        sources: [],
        isStreaming: false,
      };
      const assistantMsg = {
        id: action.assistantId,
        role: "assistant",
        content: "",
        sources: [],
        isStreaming: true,
        thinkingSteps: [],
      };
      return {
        ...state,
        messages: [...state.messages, userMsg, assistantMsg],
        isLoading: true,
        error: null,
      };
    }

    case "STREAM_STATUS": {
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.id
            ? { ...m, thinkingSteps: [...(m.thinkingSteps || []), action.detail] }
            : m
        ),
      };
    }

    case "STREAM_TOKEN": {
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.id ? { ...m, content: m.content + action.token } : m
        ),
      };
    }

    case "STREAM_COMPLETE": {
      const updated = state.messages.map((m) =>
        m.id === action.id
          ? { ...m, isStreaming: false, sources: action.sources || [] }
          : m
      );
      // Persist to sessionStorage
      sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(updated));
      return { ...state, messages: updated, isLoading: false };
    }

    case "SET_ERROR":
      return { ...state, error: action.error, isLoading: false };

    case "SET_SESSION_TOKEN": {
      sessionStorage.setItem(SESSION_KEY, action.token);
      return { ...state, sessionId: action.token };
    }

    case "RESET_SESSION": {
      // Clear signed token — server will assign a new one on next message
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(MESSAGES_KEY);
      return { ...state, sessionId: null, messages: [], error: null };
    }

    default:
      return state;
  }
}

export function useChat(userRole) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const userRoleRef = useRef(userRole);
  userRoleRef.current = userRole;

  // Hydrate: fetch from backend on mount; fallback to sessionStorage if unreachable
  useEffect(() => {
    async function hydrate() {
      const backendHistory = await fetchHistory(state.sessionId);

      if (backendHistory) {
        // Backend has the session — use authoritative history
        const messages = (backendHistory.messages || []).map((m) => ({
          id: generateId(),
          role: m.role,
          content: m.content,
          sources: [],
          isStreaming: false,
        }));
        dispatch({ type: "HYDRATE_MESSAGES", messages });
        sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
      } else if (backendHistory === null) {
        // 404 or network error — try sessionStorage cache
        const cached = sessionStorage.getItem(MESSAGES_KEY);
        if (cached) {
          try {
            dispatch({ type: "HYDRATE_MESSAGES", messages: JSON.parse(cached) });
          } catch {
            dispatch({ type: "HYDRATE_MESSAGES", messages: [] });
          }
        } else {
          dispatch({ type: "HYDRATE_MESSAGES", messages: [] });
        }
      }
    }
    hydrate();
  }, [state.sessionId]);

  async function sendUserMessage(content) {
    if (!content.trim() || state.isLoading) return;
    const assistantId = generateId();
    dispatch({ type: "SEND_MESSAGE", content, assistantId });

    await sendMessage({
      sessionId: state.sessionId,
      userId: state.userId,
      message: content,
      userRole: userRoleRef.current,
      onToken: (token) => dispatch({ type: "STREAM_TOKEN", id: assistantId, token }),
      onStatus: (detail) => dispatch({ type: "STREAM_STATUS", id: assistantId, detail }),
      onSessionToken: (token) => dispatch({ type: "SET_SESSION_TOKEN", token }),
      onError: (err) => {
        dispatch({ type: "STREAM_TOKEN", id: assistantId, token: `\n\n*Error: ${err}*` });
        dispatch({ type: "STREAM_COMPLETE", id: assistantId, sources: [] });
        dispatch({ type: "SET_ERROR", error: err });
      },
    }).then(({ sources }) => {
      dispatch({ type: "STREAM_COMPLETE", id: assistantId, sources });
    });
  }

  function resetSession() {
    dispatch({ type: "RESET_SESSION" });
  }

  async function submitFeedback(messageIndex, rating, comment) {
    await apiFeedback({
      sessionId: state.sessionId,
      messageIndex,
      rating,
      comment,
    });
  }

  return { ...state, sendUserMessage, resetSession, submitFeedback };
}
