"""
Tests for backend.retrieval.query_expander

Mocks the Anthropic client to avoid real API calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.retrieval.query_expander import expand


def _mock_haiku_response(text: str) -> MagicMock:
    """Create a mock Anthropic response with the given text."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class TestExpand:

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    @patch("backend.retrieval.query_expander.anthropic.AsyncAnthropic")
    async def test_returns_original_plus_rephrasings(self, mock_client_cls, mock_settings):
        mock_settings.use_query_expansion = True
        mock_settings.query_expansion_count = 3
        mock_settings.haiku_model = "claude-haiku-4-5-20251001"
        mock_settings.anthropic_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = _mock_haiku_response(
            "What is my vacation entitlement?\n"
            "How much PTO am I entitled to?\n"
            "What are my paid time off days?"
        )
        mock_client_cls.return_value = mock_client

        result = await expand("How many annual leave days do I get?")

        assert len(result) == 4  # original + 3
        assert result[0] == "How many annual leave days do I get?"
        assert "vacation" in result[1].lower()

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    @patch("backend.retrieval.query_expander.anthropic.AsyncAnthropic")
    async def test_caps_at_expansion_count(self, mock_client_cls, mock_settings):
        mock_settings.use_query_expansion = True
        mock_settings.query_expansion_count = 2
        mock_settings.haiku_model = "claude-haiku-4-5-20251001"
        mock_settings.anthropic_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = _mock_haiku_response(
            "rephrasing 1\nrephrasing 2\nrephrasing 3\nrephrasing 4"
        )
        mock_client_cls.return_value = mock_client

        result = await expand("test query")

        # original + 2 (capped)
        assert len(result) == 3

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    async def test_disabled_returns_original_only(self, mock_settings):
        mock_settings.use_query_expansion = False

        result = await expand("annual leave entitlement")

        assert result == ["annual leave entitlement"]

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    @patch("backend.retrieval.query_expander.anthropic.AsyncAnthropic")
    async def test_api_error_returns_original(self, mock_client_cls, mock_settings):
        mock_settings.use_query_expansion = True
        mock_settings.query_expansion_count = 3
        mock_settings.haiku_model = "claude-haiku-4-5-20251001"
        mock_settings.anthropic_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        result = await expand("test query")

        assert result == ["test query"]

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    @patch("backend.retrieval.query_expander.anthropic.AsyncAnthropic")
    async def test_empty_response_returns_original(self, mock_client_cls, mock_settings):
        mock_settings.use_query_expansion = True
        mock_settings.query_expansion_count = 3
        mock_settings.haiku_model = "claude-haiku-4-5-20251001"
        mock_settings.anthropic_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = _mock_haiku_response("")
        mock_client_cls.return_value = mock_client

        result = await expand("test query")

        assert result == ["test query"]

    @pytest.mark.asyncio
    @patch("backend.retrieval.query_expander.settings")
    @patch("backend.retrieval.query_expander.anthropic.AsyncAnthropic")
    async def test_strips_blank_lines(self, mock_client_cls, mock_settings):
        mock_settings.use_query_expansion = True
        mock_settings.query_expansion_count = 3
        mock_settings.haiku_model = "claude-haiku-4-5-20251001"
        mock_settings.anthropic_api_key = "test-key"

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = _mock_haiku_response(
            "\n  \nrephrasing one\n\nrephrasing two\n  \n"
        )
        mock_client_cls.return_value = mock_client

        result = await expand("query")

        assert len(result) == 3  # original + 2 (blank lines stripped)
        assert result[1] == "rephrasing one"
        assert result[2] == "rephrasing two"
