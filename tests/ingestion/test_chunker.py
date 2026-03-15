"""
Tests for backend.ingestion.chunker

Mocks the BGE tokenizer so tests run without downloading the 440 MB model.
Token count is approximated as len(text.split()) for the mock.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import backend.ingestion.chunker as chunker_mod
from backend.ingestion.chunker import (
    chunk_all,
    chunk_employment_act_section,
    chunk_mom_page,
    count_tokens,
)


# ── Fixtures / Helpers ────────────────────────────────────────────────────────

def _word_count_tokenizer():
    """Fake tokenizer: token count = word count (fast, deterministic)."""
    tok = MagicMock()
    tok.encode.side_effect = lambda text, **kwargs: text.split()
    return tok


@pytest.fixture(autouse=True)
def mock_tokenizer(monkeypatch):
    """Replace the global _tokenizer singleton with the word-count mock."""
    monkeypatch.setattr(chunker_mod, "_tokenizer", _word_count_tokenizer())


def _ea_section(text: str, section_number: str = "38", heading: str = "Hours") -> dict:
    return {
        "source": "Employment Act",
        "part": "Part IV",
        "division": "",
        "section_number": section_number,
        "heading": heading,
        "url": "https://sso.agc.gov.sg/act/ea",
        "text": text,
    }


def _mom_page(text: str, title: str = "Annual Leave") -> dict:
    return {
        "title": title,
        "breadcrumb": "MOM > Leave",
        "url": "https://www.mom.gov.sg/annual-leave",
        "text": text,
    }


# ── count_tokens ──────────────────────────────────────────────────────────────

def test_count_tokens_uses_tokenizer():
    result = count_tokens("hello world foo")
    assert result == 3  # word-count mock


def test_count_tokens_empty_string():
    assert count_tokens("") == 0


# ── chunk_employment_act_section ──────────────────────────────────────────────

class TestChunkEmploymentActSection:
    def test_empty_text_returns_empty(self):
        section = _ea_section("")
        assert chunk_employment_act_section(section) == []

    def test_short_section_single_chunk(self):
        text = "Employees shall not work more than 44 hours per week."
        chunks = chunk_employment_act_section(_ea_section(text))
        assert len(chunks) == 1
        assert chunks[0]["text"] == text
        assert chunks[0]["chunk_index"] == 0

    def test_metadata_preserved(self):
        chunks = chunk_employment_act_section(_ea_section("short text", "10", "Termination"))
        assert chunks[0]["source"] == "Employment Act"
        assert chunks[0]["part"] == "Part IV"
        assert chunks[0]["section_number"] == "10"
        assert chunks[0]["heading"] == "Termination"

    def test_long_section_split_at_subsections(self):
        # Build text > MAX_TOKENS (800 words) with subsection markers
        base = "word " * 200  # 200 tokens per subsection
        text = f"intro {base}(1) {base}(2) {base}(3) {base}(4) {base}"
        chunks = chunk_employment_act_section(_ea_section(text))
        assert len(chunks) > 1
        # Each chunk should be within MAX_TOKENS
        for c in chunks:
            assert count_tokens(c["text"]) <= chunker_mod.MAX_TOKENS

    def test_chunk_indices_are_sequential(self):
        base = "word " * 300
        text = f"(1) {base}(2) {base}(3) {base}"
        chunks = chunk_employment_act_section(_ea_section(text))
        for i, c in enumerate(chunks):
            assert c["chunk_index"] == i

    def test_whitespace_only_text_returns_empty(self):
        section = _ea_section("   \n  \t  ")
        assert chunk_employment_act_section(section) == []


# ── chunk_mom_page ────────────────────────────────────────────────────────────

class TestChunkMomPage:
    def test_empty_text_returns_empty(self):
        assert chunk_mom_page(_mom_page("")) == []

    def test_single_short_paragraph_one_chunk(self):
        text = "Annual leave entitlement is 7 days for the first year."
        chunks = chunk_mom_page(_mom_page(text))
        assert len(chunks) == 1
        assert chunks[0]["text"] == text

    def test_metadata_preserved(self):
        chunks = chunk_mom_page(_mom_page("some text", title="Overtime Pay"))
        assert chunks[0]["source"] == "MOM"
        assert chunks[0]["title"] == "Overtime Pay"
        assert chunks[0]["url"] == "https://www.mom.gov.sg/annual-leave"

    def test_multiple_paragraphs_accumulate(self):
        # 3 short paragraphs — all fit in one chunk
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = chunk_mom_page(_mom_page(text))
        assert len(chunks) == 1
        assert "Para one" in chunks[0]["text"]
        assert "Para three" in chunks[0]["text"]

    def test_long_page_split_into_multiple_chunks(self):
        # Each paragraph is 300 words; two together exceed MAX_TOKENS (800)
        para = "word " * 300
        text = f"{para}\n\n{para}\n\n{para}"
        chunks = chunk_mom_page(_mom_page(text))
        assert len(chunks) > 1

    def test_overlap_carries_last_paragraph(self):
        # Paragraph A fills chunk, paragraph B starts next chunk with overlap
        para_a = "word " * 400  # 400 tokens
        para_b = "word " * 400  # 400 tokens — together exceed MAX_TOKENS
        para_c = "final paragraph"
        text = f"{para_a}\n\n{para_b}\n\n{para_c}"
        chunks = chunk_mom_page(_mom_page(text))
        # chunk 1 ends with para_a; chunk 2 starts with para_a as overlap
        assert len(chunks) >= 2
        assert chunks[1]["chunk_index"] == 1

    def test_chunk_indices_sequential(self):
        para = "word " * 400
        text = "\n\n".join([para] * 4)
        chunks = chunk_mom_page(_mom_page(text))
        for i, c in enumerate(chunks):
            assert c["chunk_index"] == i

    def test_whitespace_only_returns_empty(self):
        assert chunk_mom_page(_mom_page("   \n\n   ")) == []


# ── chunk_all ─────────────────────────────────────────────────────────────────

class TestChunkAll:
    def test_returns_tuple_of_two_lists(self):
        ea, mom = chunk_all([], [])
        assert ea == []
        assert mom == []

    def test_processes_both_inputs(self):
        ea_sections = [_ea_section("short ea text", "1", "Definition")]
        mom_pages = [_mom_page("short mom text")]
        ea_chunks, mom_chunks = chunk_all(ea_sections, mom_pages)
        assert len(ea_chunks) >= 1
        assert len(mom_chunks) >= 1

    def test_multiple_sections_aggregated(self):
        sections = [
            _ea_section("text one", "1", "A"),
            _ea_section("text two", "2", "B"),
            _ea_section("text three", "3", "C"),
        ]
        ea_chunks, _ = chunk_all(sections, [])
        assert len(ea_chunks) == 3
