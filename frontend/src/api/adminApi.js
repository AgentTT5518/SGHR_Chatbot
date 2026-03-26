const API_BASE = "";
const ADMIN_KEY_STORAGE = "hr_admin_api_key";

/** Get the stored admin API key from sessionStorage. */
export function getAdminKey() {
  return sessionStorage.getItem(ADMIN_KEY_STORAGE) || "";
}

/** Store the admin API key in sessionStorage. */
export function setAdminKey(key) {
  sessionStorage.setItem(ADMIN_KEY_STORAGE, key);
}

/** Build headers with admin key included. */
function adminHeaders(extra = {}) {
  return {
    "X-Admin-Key": getAdminKey(),
    ...extra,
  };
}

/** GET /health (no admin key needed) */
export async function fetchHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/collections */
export async function fetchCollections() {
  try {
    const res = await fetch(`${API_BASE}/admin/collections`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/health/sources */
export async function fetchSourceHealth() {
  try {
    const res = await fetch(`${API_BASE}/admin/health/sources`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** POST /admin/ingest */
export async function triggerIngest(forceRescrape = false) {
  try {
    const res = await fetch(`${API_BASE}/admin/ingest`, {
      method: "POST",
      headers: adminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ force_rescrape: forceRescrape }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return { error: err.message };
  }
}

/**
 * GET /admin/ingest/stream — SSE stream with real-time ingestion progress.
 * Returns { abort } handle to cancel the fetch from the client side.
 */
export function streamIngest(forceRescrape, { onProgress, onError, onDone, onCancelled }) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(
        `${API_BASE}/admin/ingest/stream?force_rescrape=${!!forceRescrape}`,
        { headers: adminHeaders(), signal: controller.signal },
      );

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        onError?.(body.detail || `HTTP ${res.status}`);
        return;
      }

      const reader = res.body.getReader();
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
            } else if (event.cancelled) {
              onCancelled?.();
            } else if (event.done) {
              onDone?.();
            } else {
              onProgress?.(event);
            }
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        onError?.(err.message);
      }
    }
  })();

  return { abort: () => controller.abort() };
}

/** POST /admin/ingest/cancel */
export async function cancelIngest() {
  try {
    const res = await fetch(`${API_BASE}/admin/ingest/cancel`, {
      method: "POST",
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return { error: err.message };
  }
}

/** GET /admin/feedback?limit=50&offset=0 */
export async function fetchFeedback(limit = 50, offset = 0) {
  try {
    const res = await fetch(`${API_BASE}/admin/feedback?limit=${limit}&offset=${offset}`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/feedback/stats */
export async function fetchFeedbackStats() {
  try {
    const res = await fetch(`${API_BASE}/admin/feedback/stats`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /metrics */
export async function fetchMetrics() {
  try {
    const res = await fetch(`${API_BASE}/metrics`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/verified-answers */
export async function fetchVerifiedAnswers() {
  try {
    const res = await fetch(`${API_BASE}/admin/verified-answers`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** POST /admin/verified-answers */
export async function addVerifiedAnswer(question, answer, sources = []) {
  try {
    const res = await fetch(`${API_BASE}/admin/verified-answers`, {
      method: "POST",
      headers: adminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ question, answer, sources }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return { error: err.message };
  }
}

/** DELETE /admin/verified-answers/:id */
export async function deleteVerifiedAnswer(id) {
  try {
    const res = await fetch(`${API_BASE}/admin/verified-answers/${id}`, {
      method: "DELETE",
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return { error: err.message };
  }
}

/** GET /admin/faq-patterns?days=N */
export async function fetchFaqPatterns(days = 30) {
  try {
    const res = await fetch(`${API_BASE}/admin/faq-patterns?days=${days}`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/feedback/candidates */
export async function fetchCacheCandidates() {
  try {
    const res = await fetch(`${API_BASE}/admin/feedback/candidates`, {
      headers: adminHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}
