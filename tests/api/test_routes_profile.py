"""
Tests for backend.api.routes_profile — profile API endpoints.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.conftest import ADMIN_HEADERS, make_signed_session


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── GET /api/profile/{user_id} ──────────────────────────────────────────────


def test_get_profile_found(client):
    _, signed = make_signed_session()
    mock_profile = {
        "user_id": "user-1",
        "employment_type": "full-time",
        "salary_bracket": "$3000-$4000",
        "tenure_years": 2.5,
        "company": "Acme",
        "topics": [],
        "preferences": {},
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }
    with patch("backend.memory.profile_store.get_profile", new_callable=AsyncMock, return_value=mock_profile):
        resp = client.get("/api/profile/user-1", headers={"X-Session-Token": signed})
    assert resp.status_code == 200
    assert resp.json()["company"] == "Acme"


def test_get_profile_with_admin_key(client):
    mock_profile = {"user_id": "user-1", "company": "Acme"}
    with patch("backend.memory.profile_store.get_profile", new_callable=AsyncMock, return_value=mock_profile):
        resp = client.get("/api/profile/user-1", headers=ADMIN_HEADERS)
    assert resp.status_code == 200


def test_get_profile_not_found(client):
    _, signed = make_signed_session()
    with patch("backend.memory.profile_store.get_profile", new_callable=AsyncMock, return_value=None):
        resp = client.get("/api/profile/nonexistent", headers={"X-Session-Token": signed})
    assert resp.status_code == 404


def test_get_profile_403_without_auth(client):
    resp = client.get("/api/profile/user-1")
    assert resp.status_code == 403


# ── DELETE /api/profile/{user_id} ────────────────────────────────────────────


def test_delete_profile(client):
    with patch("backend.memory.profile_store.delete_profile", new_callable=AsyncMock) as mock_del:
        resp = client.delete("/api/profile/user-1", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_del.assert_awaited_once_with("user-1")


def test_delete_profile_requires_admin(client):
    _, signed = make_signed_session()
    resp = client.delete("/api/profile/user-1", headers={"X-Session-Token": signed})
    assert resp.status_code == 401


def test_delete_profile_wrong_admin_key(client):
    resp = client.delete("/api/profile/user-1", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403
