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
