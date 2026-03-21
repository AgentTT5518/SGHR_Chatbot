"""
Tests for backend.memory.fact_extractor — mock Haiku, verify extraction.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.memory.fact_extractor import extract_profile_facts


def _make_mock_client(response_text: str) -> AsyncMock:
    """Create a mock Anthropic client that returns the given text."""
    client = AsyncMock()
    block = MagicMock()
    block.text = response_text
    response = MagicMock()
    response.content = [block]
    client.messages.create = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_extract_valid_facts():
    client = _make_mock_client('{"employment_type": "full-time", "company": "Acme"}')
    messages = [
        {"role": "user", "content": "I work full-time at Acme"},
        {"role": "assistant", "content": "Got it, you work full-time at Acme."},
    ]
    facts = await extract_profile_facts(messages, client)
    assert facts["employment_type"] == "full-time"
    assert facts["company"] == "Acme"


@pytest.mark.asyncio
async def test_extract_returns_empty_on_non_json():
    client = _make_mock_client("Sorry, I cannot extract facts from this.")
    messages = [{"role": "user", "content": "Hello"}]
    facts = await extract_profile_facts(messages, client)
    assert facts == {}


@pytest.mark.asyncio
async def test_extract_returns_empty_on_api_error():
    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=Exception("API down"))
    messages = [{"role": "user", "content": "Test"}]
    facts = await extract_profile_facts(messages, client)
    assert facts == {}


@pytest.mark.asyncio
async def test_extract_handles_empty_messages():
    client = AsyncMock()
    facts = await extract_profile_facts([], client)
    assert facts == {}


@pytest.mark.asyncio
async def test_extract_only_includes_mentioned_fields():
    client = _make_mock_client('{"company": "MegaCorp"}')
    messages = [
        {"role": "user", "content": "I work at MegaCorp"},
    ]
    facts = await extract_profile_facts(messages, client)
    assert "company" in facts
    assert "employment_type" not in facts
