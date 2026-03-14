import { useReducer, useEffect, useRef } from "react";
import { sendMessage, fetchHistory } from "../api/chatApi";

const SESSION_KEY = "hr_chat_session_id";
const MESSAGES_KEY = "hr_chat_messages";

function generateId() {
  return crypto.randomUUID();
}

function getOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = generateId();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

const initialState = {
  sessionId: getOrCreateSessionId(),
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
      };
      return {
        ...state,
        messages: [...state.messages, userMsg, assistantMsg],
        isLoading: true,
        error: null,
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

    case "RESET_SESSION": {
      const newId = generateId();
      sessionStorage.setItem(SESSION_KEY, newId);
      sessionStorage.removeItem(MESSAGES_KEY);
      return { ...state, sessionId: newId, messages: [], error: null };
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
      message: content,
      userRole: userRoleRef.current,
      onToken: (token) => dispatch({ type: "STREAM_TOKEN", id: assistantId, token }),
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

  return { ...state, sendUserMessage, resetSession };
}
