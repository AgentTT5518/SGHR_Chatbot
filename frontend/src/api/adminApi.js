const API_BASE = "";

/** GET /health */
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
    const res = await fetch(`${API_BASE}/admin/collections`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/health/sources */
export async function fetchSourceHealth() {
  try {
    const res = await fetch(`${API_BASE}/admin/health/sources`);
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
      headers: { "Content-Type": "application/json" },
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
    const res = await fetch(`${API_BASE}/admin/feedback?limit=${limit}&offset=${offset}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /admin/feedback/stats */
export async function fetchFeedbackStats() {
  try {
    const res = await fetch(`${API_BASE}/admin/feedback/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

/** GET /metrics */
export async function fetchMetrics() {
  try {
    const res = await fetch(`${API_BASE}/metrics`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}
