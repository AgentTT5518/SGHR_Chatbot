import { useState, useEffect, useCallback } from "react";
import {
  fetchHealth,
  fetchCollections,
  fetchSourceHealth,
  triggerIngest,
  fetchFeedback,
  fetchFeedbackStats,
  fetchMetrics,
  fetchVerifiedAnswers,
  addVerifiedAnswer,
  deleteVerifiedAnswer,
  fetchCacheCandidates,
  fetchFaqPatterns,
} from "../api/adminApi";

const TABS = ["Health", "Ingestion", "Feedback", "Verified Answers", "FAQ Patterns", "Metrics"];

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
        {activeTab === "Verified Answers" && <VerifiedAnswersTab />}
        {activeTab === "FAQ Patterns" && <FaqPatternsTab />}
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

/* ── Verified Answers Tab ────────────────────────────────────────────────────*/

function VerifiedAnswersTab() {
  const [answers, setAnswers] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([fetchVerifiedAnswers(), fetchCacheCandidates()]).then(
      ([a, c]) => {
        setAnswers(a?.answers ?? []);
        setCandidates(c?.candidates ?? []);
        setLoading(false);
      }
    );
  }, []);

  useEffect(() => { load(); }, [load]); // eslint-disable-line react-hooks/set-state-in-effect

  async function handleApprove(candidate) {
    setActionLoading(`approve-${candidate.feedback_id}`);
    await addVerifiedAnswer(candidate.question, candidate.answer, []);
    setActionLoading(null);
    load();
  }

  async function handleDelete(id) {
    setActionLoading(`delete-${id}`);
    await deleteVerifiedAnswer(id);
    setActionLoading(null);
    load();
  }

  if (loading) return <Spinner />;

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2 className="admin-section-title">Cached Verified Answers</h2>
        <button className="admin-btn-secondary" onClick={load}>
          Refresh
        </button>
      </div>

      {answers.length === 0 ? (
        <p className="admin-empty">No verified answers in cache yet.</p>
      ) : (
        <table className="admin-table admin-table-full">
          <thead>
            <tr>
              <th>Question</th>
              <th>Answer</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {answers.map((a) => (
              <tr key={a.id}>
                <td>{a.question}</td>
                <td className="admin-answer-preview">
                  {a.answer.length > 120
                    ? a.answer.slice(0, 120) + "..."
                    : a.answer}
                </td>
                <td>
                  <button
                    className="admin-btn-danger"
                    onClick={() => handleDelete(a.id)}
                    disabled={actionLoading === `delete-${a.id}`}
                  >
                    {actionLoading === `delete-${a.id}`
                      ? "Removing..."
                      : "Remove"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 className="admin-section-title" style={{ marginTop: 24 }}>
        Candidates (Thumbs-Up Answers)
      </h2>
      {candidates.length === 0 ? (
        <p className="admin-empty">
          No thumbs-up answers available for caching.
        </p>
      ) : (
        <table className="admin-table admin-table-full">
          <thead>
            <tr>
              <th>Question</th>
              <th>Answer</th>
              <th>Date</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.feedback_id}>
                <td>{c.question}</td>
                <td className="admin-answer-preview">
                  {c.answer.length > 120
                    ? c.answer.slice(0, 120) + "..."
                    : c.answer}
                </td>
                <td>{new Date(c.created_at).toLocaleDateString()}</td>
                <td>
                  <button
                    className="admin-btn-primary"
                    onClick={() => handleApprove(c)}
                    disabled={
                      actionLoading === `approve-${c.feedback_id}`
                    }
                  >
                    {actionLoading === `approve-${c.feedback_id}`
                      ? "Approving..."
                      : "Approve"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ── FAQ Patterns Tab ───────────────────────────────────────────────────────*/

const DAYS_OPTIONS = [7, 14, 30, 60];

function FaqPatternsTab() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const load = useCallback((d) => {
    setLoading(true);
    fetchFaqPatterns(d).then((result) => {
      setData(result);
      setExpanded({});
      setLoading(false);
    });
  }, []);

  useEffect(() => { load(days); }, [load, days]); // eslint-disable-line react-hooks/set-state-in-effect

  function toggleExpand(key) {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  if (loading) return <Spinner />;
  if (!data) return <p className="admin-error">Could not load FAQ patterns.</p>;

  return (
    <div className="admin-section">
      <div className="admin-section-header">
        <h2 className="admin-section-title">FAQ Patterns</h2>
        <div className="admin-btn-row">
          <select
            className="admin-select"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {DAYS_OPTIONS.map((d) => (
              <option key={d} value={d}>Last {d} days</option>
            ))}
          </select>
          <button className="admin-btn-secondary" onClick={() => load(days)}>
            Refresh
          </button>
        </div>
      </div>

      <h3 className="admin-section-title" style={{ marginTop: 16 }}>
        Top Question Clusters
      </h3>
      {data.top_patterns.length === 0 ? (
        <p className="admin-empty">No query patterns found in this period.</p>
      ) : (
        <table className="admin-table admin-table-full">
          <thead>
            <tr>
              <th>Representative Query</th>
              <th>Count</th>
              <th>Samples</th>
            </tr>
          </thead>
          <tbody>
            {data.top_patterns.map((c) => (
              <tr key={`pattern-${c.cluster_id}`}>
                <td>{c.representative_query}</td>
                <td>{c.count}</td>
                <td>
                  <button
                    className="admin-btn-link"
                    onClick={() => toggleExpand(`p-${c.cluster_id}`)}
                  >
                    {expanded[`p-${c.cluster_id}`] ? "Hide" : `Show (${c.sample_queries.length})`}
                  </button>
                  {expanded[`p-${c.cluster_id}`] && (
                    <ul className="admin-sample-list">
                      {c.sample_queries.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="admin-section-title" style={{ marginTop: 24 }}>
        Knowledge Gaps
      </h3>
      {data.knowledge_gaps.length === 0 ? (
        <p className="admin-empty">No knowledge gaps detected in this period.</p>
      ) : (
        <table className="admin-table admin-table-full">
          <thead>
            <tr>
              <th>Gap Type</th>
              <th>Representative Query</th>
              <th>Count</th>
              <th>Samples</th>
            </tr>
          </thead>
          <tbody>
            {data.knowledge_gaps.map((g) => (
              <tr key={`gap-${g.cluster_id}`}>
                <td>
                  <Badge ok={false}>
                    {g.gap_type === "thumbs_down" ? "Thumbs Down" : "Escalation"}
                  </Badge>
                </td>
                <td>{g.representative_query}</td>
                <td>{g.count}</td>
                <td>
                  <button
                    className="admin-btn-link"
                    onClick={() => toggleExpand(`g-${g.cluster_id}`)}
                  >
                    {expanded[`g-${g.cluster_id}`] ? "Hide" : `Show (${g.sample_queries.length})`}
                  </button>
                  {expanded[`g-${g.cluster_id}`] && (
                    <ul className="admin-sample-list">
                      {g.sample_queries.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
