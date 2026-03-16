import { useState, useEffect, useCallback } from "react";
import {
  fetchHealth,
  fetchCollections,
  fetchSourceHealth,
  triggerIngest,
  fetchFeedback,
  fetchFeedbackStats,
  fetchMetrics,
} from "../api/adminApi";

const TABS = ["Health", "Ingestion", "Feedback", "Metrics"];

export function AdminDashboard({ onClose }) {
  const [activeTab, setActiveTab] = useState("Health");

  return (
    <div className="admin-page">
      <header className="admin-header">
        <h1 className="admin-title">Admin Dashboard</h1>
        <button className="admin-close-btn" onClick={onClose}>
          ← Back to Chat
        </button>
      </header>

      <nav className="admin-tabs">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`admin-tab-btn ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      <main className="admin-content">
        {activeTab === "Health" && <HealthTab />}
        {activeTab === "Ingestion" && <IngestionTab />}
        {activeTab === "Feedback" && <FeedbackTab />}
        {activeTab === "Metrics" && <MetricsTab />}
      </main>
    </div>
  );
}

/* ── Health Tab ──────────────────────────────────────────────────────────────*/

function HealthTab() {
  const [health, setHealth] = useState(null);
  const [collections, setCollections] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchHealth(), fetchCollections()]).then(([h, c]) => {
      setHealth(h);
      setCollections(c);
      setLoading(false);
    });
  }, []);

  if (loading) return <Spinner />;

  return (
    <div className="admin-section">
      <h2 className="admin-section-title">System Health</h2>
      {health ? (
        <table className="admin-table">
          <tbody>
            <tr>
              <td>Status</td>
              <td><Badge ok={health.status === "ok"}>{health.status}</Badge></td>
            </tr>
            <tr>
              <td>Embedding Model</td>
              <td><Badge ok={health.model === "loaded"}>{health.model}</Badge></td>
            </tr>
            <tr>
              <td>ChromaDB</td>
              <td><Badge ok={health.chroma === "ready"}>{health.chroma}</Badge></td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="admin-error">Could not reach backend.</p>
      )}

      {collections && (
        <>
          <h2 className="admin-section-title" style={{ marginTop: 24 }}>Document Counts</h2>
          <table className="admin-table">
            <tbody>
              <tr><td>Employment Act chunks</td><td>{collections.employment_act ?? "—"}</td></tr>
              <tr><td>MOM Guidelines chunks</td><td>{collections.mom_guidelines ?? "—"}</td></tr>
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/* ── Ingestion Tab ───────────────────────────────────────────────────────────*/

function IngestionTab() {
  const [status, setStatus] = useState(null);
  const [sourceHealth, setSourceHealth] = useState(null);
  const [loadingSources, setLoadingSources] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  async function handleCheckSources() {
    setLoadingSources(true);
    setSourceHealth(await fetchSourceHealth());
    setLoadingSources(false);
  }

  async function handleIngest(forceRescrape) {
    setIngesting(true);
    const result = await triggerIngest(forceRescrape);
    setStatus(result);
    setIngesting(false);
  }

  return (
    <div className="admin-section">
      <h2 className="admin-section-title">Source Health</h2>
      <button
        className="admin-btn-primary"
        onClick={handleCheckSources}
        disabled={loadingSources}
      >
        {loadingSources ? "Checking…" : "Check MOM URLs"}
      </button>

      {sourceHealth && (
        <div style={{ marginTop: 12 }}>
          <p>
            <Badge ok={sourceHealth.failed === 0}>
              {sourceHealth.ok}/{sourceHealth.total} URLs reachable
            </Badge>
          </p>
          <ul className="admin-source-list">
            {sourceHealth.results.map((r, i) => (
              <li key={i}>
                <Badge ok={r.ok}>{r.ok ? "OK" : "FAIL"}</Badge>{" "}
                <span className="admin-url">{r.url}</span>
                {r.error && <span className="admin-error-inline"> — {r.error}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <h2 className="admin-section-title" style={{ marginTop: 24 }}>Trigger Ingestion</h2>
      <div className="admin-btn-row">
        <button
          className="admin-btn-primary"
          onClick={() => handleIngest(false)}
          disabled={ingesting}
        >
          {ingesting ? "Running…" : "Run Ingestion"}
        </button>
        <button
          className="admin-btn-secondary"
          onClick={() => handleIngest(true)}
          disabled={ingesting}
        >
          Force Re-scrape
        </button>
      </div>

      {status && (
        <p className="admin-status-msg">
          {status.error ? `Error: ${status.error}` : status.message}
        </p>
      )}
    </div>
  );
}

/* ── Feedback Tab ────────────────────────────────────────────────────────────*/

function FeedbackTab() {
  const [stats, setStats] = useState(null);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([fetchFeedbackStats(), fetchFeedback(50, 0)]).then(([s, f]) => {
      setStats(s);
      setRecords(f?.records ?? []);
      setLoading(false);
    });
  }, []);

  if (loading) return <Spinner />;

  return (
    <div className="admin-section">
      <h2 className="admin-section-title">Feedback Summary</h2>
      {stats && (
        <table className="admin-table">
          <tbody>
            <tr><td>Total</td><td>{stats.total}</td></tr>
            <tr><td>👍 Helpful</td><td>{stats.up}</td></tr>
            <tr><td>👎 Not helpful</td><td>{stats.down}</td></tr>
          </tbody>
        </table>
      )}

      <h2 className="admin-section-title" style={{ marginTop: 24 }}>Recent Feedback</h2>
      {records.length === 0 ? (
        <p className="admin-empty">No feedback yet.</p>
      ) : (
        <table className="admin-table admin-table-full">
          <thead>
            <tr>
              <th>Rating</th>
              <th>Session</th>
              <th>Msg #</th>
              <th>Comment</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>{r.rating === "up" ? "👍" : "👎"}</td>
                <td className="admin-session-id">{r.session_id.slice(0, 8)}…</td>
                <td>{r.message_index}</td>
                <td>{r.comment || "—"}</td>
                <td>{new Date(r.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ── Metrics Tab ─────────────────────────────────────────────────────────────*/

function MetricsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchMetrics().then((m) => {
      setData(m);
      setLoading(false);
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner />;
  if (!data) return <p className="admin-error">Could not load metrics.</p>;

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2 className="admin-section-title">Request Metrics</h2>
        <button className="admin-btn-secondary" onClick={load}>Refresh</button>
      </div>

      <table className="admin-table">
        <tbody>
          <tr><td>Total Requests</td><td>{data.total_requests}</td></tr>
          <tr><td>Total Errors</td><td>{data.total_errors}</td></tr>
          <tr><td>Avg Latency</td><td>{data.avg_latency_ms} ms</td></tr>
        </tbody>
      </table>

      {data.feedback && data.feedback.total > 0 && (
        <>
          <h2 className="admin-section-title" style={{ marginTop: 24 }}>Feedback</h2>
          <table className="admin-table">
            <tbody>
              <tr><td>Total</td><td>{data.feedback.total}</td></tr>
              <tr><td>👍 Up</td><td>{data.feedback.up}</td></tr>
              <tr><td>👎 Down</td><td>{data.feedback.down}</td></tr>
            </tbody>
          </table>
        </>
      )}

      {data.endpoints && Object.keys(data.endpoints).length > 0 && (
        <>
          <h2 className="admin-section-title" style={{ marginTop: 24 }}>Requests by Endpoint</h2>
          <table className="admin-table admin-table-full">
            <thead>
              <tr><th>Path</th><th>Count</th></tr>
            </thead>
            <tbody>
              {Object.entries(data.endpoints)
                .sort(([, a], [, b]) => b - a)
                .map(([path, count]) => (
                  <tr key={path}>
                    <td className="admin-url">{path}</td>
                    <td>{count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/* ── Shared UI helpers ───────────────────────────────────────────────────────*/

function Badge({ ok, children }) {
  return <span className={`admin-badge ${ok ? "ok" : "fail"}`}>{children}</span>;
}

function Spinner() {
  return <div className="admin-spinner">Loading…</div>;
}
