"""
Locust load-test scenarios for the SGHR Chatbot.

Covers:
  - ChatUser:     POST /api/chat  (SSE stream consumption)
  - AdminUser:    GET  /admin/*   (requires X-Admin-Key header)
  - FeedbackUser: POST /api/feedback (requires an existing session)

Default host: http://localhost:8000

IMPORTANT — Mocking the Anthropic client
-----------------------------------------
Running load tests against a live Anthropic API would be expensive and
rate-limited. Before starting a load run, mock the Anthropic client on
the server side so that the RAG chain returns a canned SSE response
without making real API calls.

One approach: set an env var (e.g. MOCK_LLM=1) that your backend reads
at startup to swap the real Anthropic client for a stub that yields
deterministic streamed tokens.
"""

from __future__ import annotations

import json
import uuid

from locust import HttpUser, between, tag, task


# ---------------------------------------------------------------------------
# Chat user — exercises the main RAG endpoint
# ---------------------------------------------------------------------------
class ChatUser(HttpUser):
    """Simulates an employee or HR manager asking questions via SSE chat."""

    wait_time = between(1, 5)
    weight = 6  # Most traffic comes from chat

    SAMPLE_QUESTIONS: list[str] = [
        "What is the maximum probation period under the Employment Act?",
        "How many days of annual leave am I entitled to?",
        "What are the rules for overtime pay?",
        "Can my employer deduct salary without consent?",
        "What is the notice period for termination?",
        "How does maternity leave work in Singapore?",
        "What are the public holidays in Singapore?",
        "Is my employer required to provide medical benefits?",
    ]

    def on_start(self) -> None:
        self._question_idx = 0
        self._session_id: str | None = None

    def _next_question(self) -> str:
        q = self.SAMPLE_QUESTIONS[self._question_idx % len(self.SAMPLE_QUESTIONS)]
        self._question_idx += 1
        return q

    @tag("chat")
    @task
    def send_chat_message(self) -> None:
        """POST /api/chat and consume the full SSE stream."""
        payload: dict = {
            "message": self._next_question(),
            "user_role": "employee",
        }
        if self._session_id:
            payload["session_id"] = self._session_id

        with self.client.post(
            "/api/chat",
            json=payload,
            stream=True,
            catch_response=True,
            name="/api/chat",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Chat returned {resp.status_code}")
                return

            # Consume the SSE stream fully
            token_count = 0
            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if decoded.startswith("data: "):
                    raw = decoded[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        if event.get("token"):
                            token_count += 1
                        # Capture the signed session for subsequent requests
                        if event.get("signed_session_id"):
                            self._session_id = event["signed_session_id"]
                        if event.get("session_id") and not self._session_id:
                            self._session_id = event["session_id"]
                    except (json.JSONDecodeError, TypeError):
                        pass

            if token_count == 0:
                resp.failure("SSE stream produced zero tokens")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# Admin user — exercises admin / monitoring endpoints
# ---------------------------------------------------------------------------
class AdminUser(HttpUser):
    """Simulates an admin polling dashboards and monitoring endpoints."""

    wait_time = between(2, 8)
    weight = 2

    ADMIN_HEADERS: dict[str, str] = {"X-Admin-Key": "dev-only-key"}

    @tag("admin")
    @task(3)
    def get_collections(self) -> None:
        """GET /admin/collections — document counts from ChromaDB."""
        self.client.get(
            "/admin/collections",
            headers=self.ADMIN_HEADERS,
            name="/admin/collections",
        )

    @tag("admin")
    @task(2)
    def get_feedback_list(self) -> None:
        """GET /admin/feedback — paginated feedback records."""
        self.client.get(
            "/admin/feedback",
            headers=self.ADMIN_HEADERS,
            name="/admin/feedback",
        )

    @tag("admin")
    @task(1)
    def get_feedback_stats(self) -> None:
        """GET /admin/feedback/stats — aggregate up/down counts."""
        self.client.get(
            "/admin/feedback/stats",
            headers=self.ADMIN_HEADERS,
            name="/admin/feedback/stats",
        )


# ---------------------------------------------------------------------------
# Feedback user — submits thumbs-up / thumbs-down ratings
# ---------------------------------------------------------------------------
class FeedbackUser(HttpUser):
    """Simulates a user submitting feedback after receiving a chat answer.

    On start, this user sends one chat message to obtain a valid session ID,
    then repeatedly submits feedback against that session.
    """

    wait_time = between(3, 10)
    weight = 2

    def on_start(self) -> None:
        """Create a session via the chat endpoint before submitting feedback."""
        self._session_id: str | None = None

        payload = {
            "message": "What is the Employment Act?",
            "user_role": "employee",
        }
        with self.client.post(
            "/api/chat",
            json=payload,
            stream=True,
            catch_response=True,
            name="/api/chat [setup]",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Setup chat returned {resp.status_code}")
                return

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if decoded.startswith("data: "):
                    raw = decoded[6:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                        if event.get("signed_session_id"):
                            self._session_id = event["signed_session_id"]
                        if event.get("session_id") and not self._session_id:
                            self._session_id = event["session_id"]
                    except (json.JSONDecodeError, TypeError):
                        pass

            resp.success()

        if not self._session_id:
            # Fallback: use a random UUID (will likely get 404, but keeps
            # the test running so we can observe the failure rate)
            self._session_id = str(uuid.uuid4())

    @tag("feedback")
    @task
    def submit_feedback(self) -> None:
        """POST /api/feedback with a thumbs-up or thumbs-down."""
        # Alternate between up and down ratings
        rating = "up" if hash(self._session_id) % 2 == 0 else "down"

        # Strip the HMAC signature to get the raw session ID for the body.
        # Signed tokens have the format "<uuid>.<signature>".
        raw_id = self._session_id
        if raw_id and "." in raw_id:
            raw_id = raw_id.rsplit(".", 1)[0]

        payload = {
            "session_id": raw_id,
            "message_index": 0,
            "rating": rating,
            "comment": "Load test feedback",
        }

        headers: dict[str, str] = {}
        if self._session_id:
            headers["X-Session-Token"] = self._session_id

        with self.client.post(
            "/api/feedback",
            json=payload,
            headers=headers,
            catch_response=True,
            name="/api/feedback",
        ) as resp:
            if resp.status_code == 201:
                resp.success()
            elif resp.status_code == 404:
                resp.failure("Session not found — setup may have failed")
            else:
                resp.failure(f"Feedback returned {resp.status_code}")
