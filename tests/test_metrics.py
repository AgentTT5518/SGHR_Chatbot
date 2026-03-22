"""
Tests for backend.lib.metrics and the /metrics endpoint.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.lib import metrics as metrics_module
from backend.main import app
from tests.conftest import ADMIN_HEADERS


@pytest.fixture(autouse=True)
def reset_metrics():
    metrics_module.reset()
    yield
    metrics_module.reset()


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── metrics module unit tests ─────────────────────────────────────────────────

def test_initial_snapshot_is_zero():
    snap = metrics_module.get_snapshot()
    assert snap["total_requests"] == 0
    assert snap["total_errors"] == 0
    assert snap["avg_latency_ms"] == 0.0
    assert snap["endpoints"] == {}


def test_record_request_increments_total():
    metrics_module.record_request("/api/chat", 120.0)
    snap = metrics_module.get_snapshot()
    assert snap["total_requests"] == 1
    assert snap["total_errors"] == 0


def test_record_error_increments_error_count():
    metrics_module.record_request("/api/chat", 50.0, is_error=True)
    snap = metrics_module.get_snapshot()
    assert snap["total_errors"] == 1


def test_avg_latency_calculated_correctly():
    metrics_module.record_request("/a", 100.0)
    metrics_module.record_request("/b", 200.0)
    snap = metrics_module.get_snapshot()
    assert snap["avg_latency_ms"] == 150.0


def test_endpoint_counts_tracked():
    metrics_module.record_request("/api/chat", 100.0)
    metrics_module.record_request("/api/chat", 80.0)
    metrics_module.record_request("/health", 5.0)
    snap = metrics_module.get_snapshot()
    assert snap["endpoints"]["/api/chat"] == 2
    assert snap["endpoints"]["/health"] == 1


def test_reset_clears_all():
    metrics_module.record_request("/api/chat", 100.0)
    metrics_module.reset()
    snap = metrics_module.get_snapshot()
    assert snap["total_requests"] == 0
    assert snap["endpoints"] == {}


# ── /metrics endpoint ─────────────────────────────────────────────────────────

def test_metrics_endpoint_returns_200(client):
    with patch(
        "backend.chat.session_manager.get_feedback_stats",
        new=AsyncMock(return_value={"total": 0, "up": 0, "down": 0}),
    ):
        resp = client.get("/metrics", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_metrics_endpoint_includes_feedback(client):
    fake_stats = {"total": 3, "up": 2, "down": 1}
    with patch(
        "backend.chat.session_manager.get_feedback_stats",
        new=AsyncMock(return_value=fake_stats),
    ):
        resp = client.get("/metrics", headers=ADMIN_HEADERS)
    data = resp.json()
    assert "feedback" in data
    assert data["feedback"]["total"] == 3


def test_metrics_endpoint_has_required_keys(client):
    with patch(
        "backend.chat.session_manager.get_feedback_stats",
        new=AsyncMock(return_value={}),
    ):
        resp = client.get("/metrics", headers=ADMIN_HEADERS)
    data = resp.json()
    for key in ("total_requests", "total_errors", "avg_latency_ms", "endpoints"):
        assert key in data


def test_metrics_requires_admin_key(client):
    resp = client.get("/metrics")
    assert resp.status_code == 401
