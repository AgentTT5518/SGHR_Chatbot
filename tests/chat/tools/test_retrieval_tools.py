"""Tests for retrieval tools: mock the enhanced retrieval pipeline."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.chat.tools.retrieval_tools import (
    search_employment_act,
    search_mom_guidelines,
    search_all_policies,
    get_legal_definitions,
    _enhanced_retrieve,
)

# Sample chunk matching the shape returned by vector_store.query
_EA_CHUNK = {
    "id": "ea_1",
    "text": "An employee is entitled to annual leave after completing 3 months of service.",
    "metadata": {
        "source": "Employment Act",
        "part": "Part IV",
        "section_number": "43",
        "heading": "Annual leave",
        "url": "",
    },
    "distance": 0.1,
}

_MOM_CHUNK = {
    "id": "mom_1",
    "text": "To file a salary claim, visit the TADM website.",
    "metadata": {
        "source": "MOM",
        "title": "Filing salary claims",
        "url": "https://www.mom.gov.sg/claims",
    },
    "distance": 0.15,
}

_SECTION_2_CHUNK = {
    "id": "ea_s2",
    "text": "'employee' means a person who has entered into a contract of service...",
    "metadata": {
        "source": "Employment Act",
        "section_number": "2",
        "heading": "Interpretation",
        "url": "",
    },
    "distance": 0.05,
}

FAKE_EMBEDDING = [0.1] * 768


class TestSearchEmploymentAct:

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools._enhanced_retrieve")
    async def test_returns_formatted_results(self, mock_retrieve):
        mock_retrieve.return_value = [_EA_CHUNK]
        result = await search_employment_act({"query": "annual leave"})
        assert "annual leave" in result.lower()
        mock_retrieve.assert_called_once_with(
            query="annual leave",
            collection="employment_act",
            section_filter=None,
        )

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools._enhanced_retrieve")
    async def test_passes_section_filter(self, mock_retrieve):
        mock_retrieve.return_value = [_EA_CHUNK]
        await search_employment_act({"query": "overtime", "section_filter": "Part IV"})
        mock_retrieve.assert_called_once_with(
            query="overtime",
            collection="employment_act",
            section_filter="Part IV",
        )

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools._enhanced_retrieve")
    async def test_empty_results(self, mock_retrieve):
        mock_retrieve.return_value = []
        result = await search_employment_act({"query": "something obscure"})
        assert "No relevant documents" in result


class TestSearchMomGuidelines:

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools._enhanced_retrieve")
    async def test_returns_formatted_results(self, mock_retrieve):
        mock_retrieve.return_value = [_MOM_CHUNK]
        result = await search_mom_guidelines({"query": "salary claim"})
        assert "salary claim" in result.lower() or "TADM" in result
        mock_retrieve.assert_called_once_with(
            query="salary claim", collection="mom_guidelines",
        )


class TestSearchAllPolicies:

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools._enhanced_retrieve")
    async def test_returns_formatted_results(self, mock_retrieve):
        mock_retrieve.return_value = [_EA_CHUNK, _MOM_CHUNK]
        result = await search_all_policies({"query": "leave"})
        assert "annual leave" in result.lower()
        mock_retrieve.assert_called_once_with(query="leave")


class TestGetLegalDefinitions:

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.get_section_2")
    async def test_returns_section_2(self, mock_get):
        mock_get.return_value = _SECTION_2_CHUNK
        result = await get_legal_definitions({"term": "employee"})
        assert "contract of service" in result
        assert "Section 2" in result

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.get_section_2")
    async def test_not_found(self, mock_get):
        mock_get.return_value = None
        result = await get_legal_definitions({"term": "unknown_term"})
        assert "Could not find" in result


class TestEnhancedRetrieve:

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.compress")
    @patch("backend.chat.tools.retrieval_tools._embed_query", return_value=FAKE_EMBEDDING)
    @patch("backend.chat.tools.retrieval_tools.retrieve_multi")
    @patch("backend.chat.tools.retrieval_tools.expand")
    @patch("backend.chat.tools.retrieval_tools.settings")
    async def test_expansion_enabled_uses_retrieve_multi(
        self, mock_settings, mock_expand, mock_multi, mock_embed, mock_compress,
    ):
        mock_settings.use_contextual_compression = False
        mock_expand.return_value = ["q1", "q2", "q3"]
        mock_multi.return_value = [_EA_CHUNK]

        result = await _enhanced_retrieve("q1", collection="employment_act")

        mock_expand.assert_called_once_with("q1")
        mock_multi.assert_called_once()
        assert result == [_EA_CHUNK]

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.compress")
    @patch("backend.chat.tools.retrieval_tools._embed_query", return_value=FAKE_EMBEDDING)
    @patch("backend.chat.tools.retrieval_tools.retrieve_from_collection")
    @patch("backend.chat.tools.retrieval_tools.expand")
    @patch("backend.chat.tools.retrieval_tools.settings")
    async def test_single_query_uses_retrieve_from_collection(
        self, mock_settings, mock_expand, mock_retrieve, mock_embed, mock_compress,
    ):
        mock_settings.use_contextual_compression = False
        mock_expand.return_value = ["q1"]  # no expansion
        mock_retrieve.return_value = [_EA_CHUNK]

        result = await _enhanced_retrieve("q1", collection="employment_act")

        mock_retrieve.assert_called_once()
        assert result == [_EA_CHUNK]

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.compress", return_value=[_EA_CHUNK])
    @patch("backend.chat.tools.retrieval_tools._embed_query", return_value=FAKE_EMBEDDING)
    @patch("backend.chat.tools.retrieval_tools.retrieve_from_collection")
    @patch("backend.chat.tools.retrieval_tools.expand")
    @patch("backend.chat.tools.retrieval_tools.settings")
    async def test_compression_enabled_calls_compress(
        self, mock_settings, mock_expand, mock_retrieve, mock_embed, mock_compress,
    ):
        mock_settings.use_contextual_compression = True
        mock_expand.return_value = ["q1"]
        mock_retrieve.return_value = [_EA_CHUNK]

        result = await _enhanced_retrieve("q1", collection="employment_act")

        mock_compress.assert_called_once_with(FAKE_EMBEDDING, [_EA_CHUNK])
        assert result == [_EA_CHUNK]

    @pytest.mark.asyncio
    @patch("backend.chat.tools.retrieval_tools.compress")
    @patch("backend.chat.tools.retrieval_tools._embed_query", return_value=FAKE_EMBEDDING)
    @patch("backend.chat.tools.retrieval_tools.retrieve")
    @patch("backend.chat.tools.retrieval_tools.expand")
    @patch("backend.chat.tools.retrieval_tools.settings")
    async def test_no_collection_uses_retrieve(
        self, mock_settings, mock_expand, mock_retrieve, mock_embed, mock_compress,
    ):
        mock_settings.use_contextual_compression = False
        mock_expand.return_value = ["q1"]
        mock_retrieve.return_value = [_EA_CHUNK]

        result = await _enhanced_retrieve("q1")

        mock_retrieve.assert_called_once()
