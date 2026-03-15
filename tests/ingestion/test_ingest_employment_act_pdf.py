"""
Tests for backend.ingestion.ingest_employment_act_pdf

Mocks pdfminer.high_level.extract_pages so no real PDF is parsed.
Exercises parse_pdf structural detection (parts, divisions, sections)
and ingest_pdf file I/O.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from backend.ingestion.ingest_employment_act_pdf import (
    PART_PATTERN,
    DIVISION_PATTERN,
    SECTION_PATTERN,
    extract_font_sizes,
    parse_pdf,
    ingest_pdf,
)


# ── Pattern tests ─────────────────────────────────────────────────────────────

class TestPatterns:
    def test_part_pattern_matches_part_heading(self):
        assert PART_PATTERN.match("PART IV General")
        assert PART_PATTERN.match("Part I Preliminary")

    def test_part_pattern_does_not_match_body_text(self):
        assert not PART_PATTERN.match("participation in the scheme")
        assert not PART_PATTERN.match("An employer shall")

    def test_division_pattern_matches_division_heading(self):
        assert DIVISION_PATTERN.match("Division 1 Leave")
        assert DIVISION_PATTERN.match("division 2 Hours")

    def test_section_pattern_matches_section_heading(self):
        m = SECTION_PATTERN.match("38.  Hours of work")
        assert m is not None
        assert m.group(1) == "38"
        assert "Hours" in m.group(2)

    def test_section_pattern_matches_alpha_suffix(self):
        m = SECTION_PATTERN.match("2A.  Definitions")
        assert m is not None
        assert m.group(1) == "2A"


# ── extract_font_sizes ────────────────────────────────────────────────────────

class TestExtractFontSizes:
    def _make_text_container(self, text: str, char_size: float):
        """Build a mock LTTextContainer with chars of a given font size."""
        from pdfminer.layout import LTTextContainer, LTChar

        char = MagicMock(spec=LTChar)
        char.size = char_size

        line = MagicMock()
        line.__iter__ = MagicMock(return_value=iter([char]))

        container = MagicMock(spec=LTTextContainer)
        container.get_text.return_value = text
        container.__iter__ = MagicMock(return_value=iter([line]))
        return container

    def test_returns_text_and_avg_size(self):
        container = self._make_text_container("Sample text", 10.0)
        page_layout = [container]
        results = extract_font_sizes(page_layout)
        assert len(results) == 1
        assert results[0][0] == "Sample text"
        assert results[0][1] == pytest.approx(10.0)

    def test_skips_empty_text(self):
        container = self._make_text_container("   ", 10.0)
        results = extract_font_sizes([container])
        assert results == []

    def test_non_text_elements_ignored(self):
        non_text = MagicMock()
        # Not an LTTextContainer instance
        del non_text.get_text
        results = extract_font_sizes([non_text])
        assert results == []


# ── parse_pdf ─────────────────────────────────────────────────────────────────

def _make_page(items: list[tuple[str, float]]):
    """Mock page_layout yielding (text, font_size) items via extract_font_sizes."""
    return items  # extract_font_sizes will be patched to return these directly


class TestParsePdf:
    def _parse_with_items(self, pages_items: list[list[tuple[str, float]]]) -> list[dict]:
        """Run parse_pdf with mocked extract_pages + extract_font_sizes."""
        # Each element in pages_items is one page's list of (text, font_size)
        with (
            patch("backend.ingestion.ingest_employment_act_pdf.extract_pages", return_value=pages_items),
            patch(
                "backend.ingestion.ingest_employment_act_pdf.extract_font_sizes",
                side_effect=lambda page: page,  # page IS the items list
            ),
        ):
            return parse_pdf(Path("fake.pdf"))

    def test_single_section_extracted(self):
        pages = [
            [
                ("38.  Hours of work", 10.0),
                ("An employee shall not work more than 44 hours per week.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert len(sections) == 1
        assert sections[0]["section_number"] == "38"
        assert sections[0]["heading"] == "Hours of work"
        assert "44 hours" in sections[0]["text"]

    def test_multiple_sections_extracted(self):
        pages = [
            [
                ("1.  Scope of Act", 10.0),
                ("This Act applies to all workmen.", 9.0),
                ("2.  Definitions", 10.0),
                ("employer means any person who employs.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert len(sections) == 2
        assert sections[0]["section_number"] == "1"
        assert sections[1]["section_number"] == "2"

    def test_part_heading_updates_current_part(self):
        pages = [
            [
                ("PART IV General", 12.0),
                ("38.  Hours of work", 10.0),
                ("Not more than 44 hours.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert sections[0]["part"] == "PART IV General"

    def test_division_heading_captured(self):
        pages = [
            [
                ("Division 1 Leave", 10.0),
                ("38.  Annual Leave", 10.0),
                ("Employees are entitled to leave.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert sections[0]["division"] == "Division 1 Leave"

    def test_short_text_skipped(self):
        pages = [
            [
                ("38", 10.0),  # len < 3 — should be skipped as page number
                ("38.  Hours of work", 10.0),
                ("Body text here.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert len(sections) == 1

    def test_url_constructed_from_section_number(self):
        pages = [
            [
                ("38.  Hours of work", 10.0),
                ("Body.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert "pr38-" in sections[0]["url"]

    def test_empty_pdf_returns_empty_list(self):
        sections = self._parse_with_items([[]])
        assert sections == []

    def test_section_source_is_employment_act(self):
        pages = [
            [
                ("2.  Definitions", 10.0),
                ("employer means any person.", 9.0),
            ]
        ]
        sections = self._parse_with_items(pages)
        assert sections[0]["source"] == "Employment Act"


# ── ingest_pdf ────────────────────────────────────────────────────────────────

class TestIngestPdf:
    def test_saves_json_and_returns_sections(self, tmp_path):
        sections = [
            {
                "source": "Employment Act",
                "part": "Part I",
                "division": None,
                "section_number": "2",
                "heading": "Definitions",
                "text": "employer means any person who employs another.",
                "url": "https://sso.agc.gov.sg/Act/EMA1968#pr2-",
            }
        ]

        with (
            patch("backend.ingestion.ingest_employment_act_pdf.parse_pdf", return_value=sections),
            patch("backend.ingestion.ingest_employment_act_pdf.RAW_SCRAPED_DIR", tmp_path),
        ):
            result = ingest_pdf(Path("fake.pdf"))

        assert result == sections
        out_path = tmp_path / "employment_act.json"
        assert out_path.exists()
        saved = json.loads(out_path.read_text())
        assert saved[0]["section_number"] == "2"

    def test_creates_output_directory(self, tmp_path):
        nested = tmp_path / "nested" / "raw"

        with (
            patch("backend.ingestion.ingest_employment_act_pdf.parse_pdf", return_value=[]),
            patch("backend.ingestion.ingest_employment_act_pdf.RAW_SCRAPED_DIR", nested),
        ):
            ingest_pdf(Path("fake.pdf"))

        assert nested.exists()
