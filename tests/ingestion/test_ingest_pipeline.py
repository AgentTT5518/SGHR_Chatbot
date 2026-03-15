"""
Tests for backend.ingestion.ingest_pipeline

Mocks scrapers, embedder, chunker, and chromadb so no real I/O or network
calls are made. Tests the branching logic in _load_or_scrape_* helpers and
the full run() orchestration.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.ingestion.ingest_pipeline import (
    _chunk_id,
    _load_or_scrape_employment_act,
    _load_or_scrape_mom,
    _upsert_chunks,
    run,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def _ea_section(num: str = "38") -> dict:
    return {
        "source": "Employment Act",
        "part": "Part IV",
        "division": None,
        "section_number": num,
        "heading": "Hours of work",
        "text": "Not more than 44 hours per week.",
        "url": f"https://sso.agc.gov.sg/Act/EMA1968#pr{num}-",
    }


def _mom_page() -> dict:
    return {
        "title": "Annual Leave",
        "breadcrumb": "MOM > Leave",
        "text": "Employees are entitled to annual leave.",
        "url": "https://www.mom.gov.sg/annual-leave",
        "source": "MOM",
    }


def _ea_chunk(num: str = "38", chunk_index: int = 0) -> dict:
    return {
        "source": "Employment Act",
        "section_number": num,
        "text": "Not more than 44 hours per week.",
        "chunk_index": chunk_index,
    }


def _mom_chunk(chunk_index: int = 0) -> dict:
    return {
        "source": "MOM",
        "title": "Annual Leave",
        "text": "Employees are entitled to annual leave.",
        "chunk_index": chunk_index,
    }


# ── _chunk_id ──────────────────────────────────────────────────────────────────

def test_chunk_id_is_deterministic():
    id1 = _chunk_id("ea", 0, 0)
    id2 = _chunk_id("ea", 0, 0)
    assert id1 == id2


def test_chunk_id_differs_for_different_inputs():
    id1 = _chunk_id("ea", 0, 0)
    id2 = _chunk_id("ea", 0, 1)
    id3 = _chunk_id("mom", 0, 0)
    assert id1 != id2
    assert id1 != id3


def test_chunk_id_returns_hex_string():
    cid = _chunk_id("ea", 1, 2)
    assert isinstance(cid, str)
    int(cid, 16)  # raises if not valid hex


# ── _load_or_scrape_employment_act ────────────────────────────────────────────

class TestLoadOrScrapeEmploymentAct:
    def test_uses_cached_json_when_exists(self, tmp_path):
        sections = [_ea_section()]
        cache = tmp_path / "employment_act.json"
        cache.write_text(json.dumps(sections))

        with patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path):
            result = _load_or_scrape_employment_act(None)

        assert result == sections

    def test_uses_pdf_when_no_cache_and_pdf_provided(self, tmp_path):
        sections = [_ea_section()]
        fake_pdf = tmp_path / "act.pdf"
        fake_pdf.touch()  # file must exist

        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path),
            patch("backend.ingestion.ingest_employment_act_pdf.ingest_pdf", return_value=sections),
        ):
            result = _load_or_scrape_employment_act(fake_pdf)

        assert result == sections

    def test_falls_back_to_web_scrape_when_no_pdf(self, tmp_path):
        sections = [_ea_section()]

        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path),
            patch("backend.ingestion.scraper_employment_act.scrape_and_save", return_value=sections),
        ):
            result = _load_or_scrape_employment_act(None)

        assert result == sections

    def test_exits_when_scrape_returns_empty(self, tmp_path):
        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path),
            patch("backend.ingestion.scraper_employment_act.scrape_and_save", return_value=[]),
            pytest.raises(SystemExit),
        ):
            _load_or_scrape_employment_act(None)


# ── _load_or_scrape_mom ───────────────────────────────────────────────────────

class TestLoadOrScrapeMom:
    def test_uses_cached_json_when_exists(self, tmp_path):
        pages = [_mom_page()]
        cache = tmp_path / "mom_pages.json"
        cache.write_text(json.dumps(pages))

        with patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path):
            result = _load_or_scrape_mom()

        assert result == pages

    def test_calls_scrape_when_no_cache(self, tmp_path):
        pages = [_mom_page()]

        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path),
            patch("backend.ingestion.scraper_mom.scrape_and_save", return_value=(pages, [])),
        ):
            result = _load_or_scrape_mom()

        assert result == pages


# ── _upsert_chunks ────────────────────────────────────────────────────────────

class TestUpsertChunks:
    def test_calls_collection_upsert(self):
        mock_col = MagicMock()
        mock_col.name = "employment_act"
        chunks = [_ea_chunk()]
        embeddings = [[0.1] * 768]

        with patch("backend.ingestion.embedder.embed_documents", return_value=embeddings):
            _upsert_chunks(mock_col, chunks, "employment_act")

        mock_col.upsert.assert_called_once()

    def test_skips_empty_chunks(self):
        mock_col = MagicMock()
        mock_col.name = "employment_act"

        with patch("backend.ingestion.embedder.embed_documents") as mock_embed:
            _upsert_chunks(mock_col, [], "employment_act")

        mock_col.upsert.assert_not_called()
        mock_embed.assert_not_called()

    def test_batches_large_chunk_sets(self):
        mock_col = MagicMock()
        mock_col.name = "ea"
        # 1200 chunks — should be split into 3 batches of 500/500/200
        chunks = [_ea_chunk(str(i), i) for i in range(1200)]
        embeddings = [[0.1] * 768] * 1200

        with patch("backend.ingestion.embedder.embed_documents", return_value=embeddings):
            _upsert_chunks(mock_col, chunks, "ea")

        assert mock_col.upsert.call_count == 3

    def test_none_metadata_values_replaced_with_empty_string(self):
        mock_col = MagicMock()
        mock_col.name = "ea"
        chunks = [{"text": "body", "section_number": "1", "division": None, "chunk_index": 0}]
        embeddings = [[0.1] * 768]

        with patch("backend.ingestion.embedder.embed_documents", return_value=embeddings):
            _upsert_chunks(mock_col, chunks, "ea")

        _, kwargs = mock_col.upsert.call_args
        assert kwargs["metadatas"][0]["division"] == ""


# ── run ───────────────────────────────────────────────────────────────────────

class TestRun:
    def test_run_orchestrates_all_steps(self, tmp_path):
        ea_sections = [_ea_section()]
        mom_pages = [_mom_page()]
        ea_chunks = [_ea_chunk()]
        mom_chunks = [_mom_chunk()]

        mock_ea_col = MagicMock()
        mock_ea_col.name = "employment_act"
        mock_ea_col.count.return_value = 1

        mock_mom_col = MagicMock()
        mock_mom_col.name = "mom_guidelines"
        mock_mom_col.count.return_value = 1

        mock_client = MagicMock()
        mock_client.get_or_create_collection.side_effect = [mock_ea_col, mock_mom_col]

        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", tmp_path),
            patch("backend.ingestion.ingest_pipeline.CHROMA_DIR", tmp_path / "chroma"),
            patch("backend.ingestion.ingest_pipeline._load_or_scrape_employment_act", return_value=ea_sections),
            patch("backend.ingestion.ingest_pipeline._load_or_scrape_mom", return_value=mom_pages),
            patch("backend.ingestion.chunker.chunk_all", return_value=(ea_chunks, mom_chunks)),
            patch("backend.ingestion.embedder.embed_documents", return_value=[[0.1] * 768]),
            patch("chromadb.PersistentClient", return_value=mock_client),
        ):
            run()

        assert mock_ea_col.upsert.call_count >= 1
        assert mock_mom_col.upsert.call_count >= 1

    def test_run_creates_directories(self, tmp_path):
        raw_dir = tmp_path / "raw"
        chroma_dir = tmp_path / "chroma"

        mock_col = MagicMock()
        mock_col.name = "col"
        mock_col.count.return_value = 0
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_col

        with (
            patch("backend.ingestion.ingest_pipeline.RAW_SCRAPED_DIR", raw_dir),
            patch("backend.ingestion.ingest_pipeline.CHROMA_DIR", chroma_dir),
            patch("backend.ingestion.ingest_pipeline._load_or_scrape_employment_act", return_value=[]),
            patch("backend.ingestion.ingest_pipeline._load_or_scrape_mom", return_value=[]),
            patch("backend.ingestion.chunker.chunk_all", return_value=([], [])),
            patch("backend.ingestion.embedder.embed_documents", return_value=[]),
            patch("chromadb.PersistentClient", return_value=mock_client),
        ):
            run()

        assert raw_dir.exists()
        assert chroma_dir.exists()
