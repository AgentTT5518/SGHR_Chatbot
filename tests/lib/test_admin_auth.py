"""
Unit tests for backend.lib.admin_auth — admin API key dependency.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.lib.admin_auth import require_admin
from fastapi import HTTPException


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request with configurable headers."""
    request = MagicMock()
    request.headers = {}
    request.method = "GET"
    request.url.path = "/admin/test"
    request.client.host = "127.0.0.1"
    return request


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, mock_request):
        mock_request.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_key_returns_401(self, mock_request):
        mock_request.headers = {"X-Admin-Key": ""}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_returns_403(self, mock_request):
        mock_request.headers = {"X-Admin-Key": "wrong-key"}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_correct_key_passes(self, mock_request):
        mock_request.headers = {"X-Admin-Key": "dev-only-key"}
        # Should not raise
        result = await require_admin(mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_audit_log_emitted_on_success(self, mock_request):
        mock_request.headers = {"X-Admin-Key": "dev-only-key"}
        with patch("backend.lib.admin_auth.log") as mock_log:
            await require_admin(mock_request)
        mock_log.info.assert_called_once()
        call_args = mock_log.info.call_args
        assert "Admin action authorised" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_audit_log_on_failure(self, mock_request):
        mock_request.headers = {"X-Admin-Key": "wrong"}
        with patch("backend.lib.admin_auth.log") as mock_log:
            with pytest.raises(HTTPException):
                await require_admin(mock_request)
        mock_log.info.assert_not_called()
