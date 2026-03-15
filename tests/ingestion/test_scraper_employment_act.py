"""
Tests for backend.ingestion.scraper_employment_act

Mocks playwright.async_api.async_playwright so no browser is launched.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ingestion.scraper_employment_act import scrape_and_save


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_playwright_mock(
    section_links: list[dict] | None = None,
    page_title: str = "Section 38 – Hours of work",
    heading_text: str = "Hours of work",
    body_text: str = "An employee shall not work more than 44 hours.",
    cloudflare: bool = False,
):
    """Build a mock async_playwright context that simulates a successful scrape."""
    if section_links is None:
        section_links = [
            {"href": "https://sso.agc.gov.sg/Act/EMA1968#pr38-", "text": "38. Hours of work"}
        ]

    mock_page = AsyncMock()
    mock_page.content.return_value = "Just a moment" if cloudflare else "<html>normal</html>"
    mock_page.eval_on_selector_all.return_value = section_links
    mock_page.evaluate.return_value = page_title  # document.title

    heading_el = AsyncMock()
    heading_el.inner_text.return_value = heading_text
    mock_page.query_selector.return_value = heading_el

    mock_page.query_selector_all.return_value = []  # no breadcrumb

    body_el = AsyncMock()
    body_el.inner_text.return_value = body_text
    # query_selector is called twice: once for h2/h3, once for main/article/…
    mock_page.query_selector.side_effect = [heading_el, body_el]

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_p = AsyncMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.__aenter__.return_value = mock_p
    mock_playwright_cm.__aexit__.return_value = False

    return mock_playwright_cm


# ── scrape_act ────────────────────────────────────────────────────────────────

class TestScrapeAct:
    @pytest.mark.asyncio
    async def test_returns_sections_list(self):
        from backend.ingestion.scraper_employment_act import scrape_act

        mock_cm = _make_playwright_mock()
        with (
            patch("playwright.async_api.async_playwright", return_value=mock_cm),
            patch("backend.ingestion.scraper_employment_act.asyncio.sleep", new=AsyncMock()),
        ):
            sections = await scrape_act()

        assert isinstance(sections, list)

    @pytest.mark.asyncio
    async def test_cloudflare_challenge_returns_empty(self):
        from backend.ingestion.scraper_employment_act import scrape_act

        mock_cm = _make_playwright_mock(cloudflare=True)
        with patch("playwright.async_api.async_playwright", return_value=mock_cm):
            sections = await scrape_act()

        assert sections == []

    @pytest.mark.asyncio
    async def test_section_has_required_fields(self):
        from backend.ingestion.scraper_employment_act import scrape_act

        mock_cm = _make_playwright_mock()
        with (
            patch("playwright.async_api.async_playwright", return_value=mock_cm),
            patch("backend.ingestion.scraper_employment_act.asyncio.sleep", new=AsyncMock()),
        ):
            sections = await scrape_act()

        if sections:
            s = sections[0]
            assert "source" in s
            assert s["source"] == "Employment Act"
            assert "section_number" in s
            assert "heading" in s
            assert "text" in s
            assert "url" in s

    @pytest.mark.asyncio
    async def test_empty_section_links_returns_empty(self):
        from backend.ingestion.scraper_employment_act import scrape_act

        mock_cm = _make_playwright_mock(section_links=[])
        with (
            patch("playwright.async_api.async_playwright", return_value=mock_cm),
            patch("backend.ingestion.scraper_employment_act.asyncio.sleep", new=AsyncMock()),
        ):
            sections = await scrape_act()

        assert sections == []

    @pytest.mark.asyncio
    async def test_skips_failed_navigation(self):
        from backend.ingestion.scraper_employment_act import scrape_act

        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        mock_page.content.return_value = "<html>normal</html>"
        mock_page.eval_on_selector_all.return_value = [
            {"href": "https://sso.agc.gov.sg/Act/EMA1968#pr1-", "text": "1. Scope"}
        ]
        # First goto (TOC) succeeds; second (section page) raises
        mock_page.goto.side_effect = [None, Exception("navigation timeout")]

        mock_context.new_page.return_value = mock_page
        mock_browser.new_context.return_value = mock_context
        mock_p.chromium.launch.return_value = mock_browser

        mock_cm2 = AsyncMock()
        mock_cm2.__aenter__.return_value = mock_p
        mock_cm2.__aexit__.return_value = False

        with (
            patch("playwright.async_api.async_playwright", return_value=mock_cm2),
            patch("backend.ingestion.scraper_employment_act.asyncio.sleep", new=AsyncMock()),
        ):
            sections = await scrape_act()

        # Failed navigation is skipped; no section appended
        assert sections == []


# ── scrape_and_save ───────────────────────────────────────────────────────────

class TestScrapeAndSave:
    def test_saves_json_when_sections_returned(self, tmp_path):
        sections = [
            {
                "source": "Employment Act",
                "part": "Part I",
                "division": None,
                "section_number": "38",
                "heading": "Hours of work",
                "text": "Not more than 44 hours.",
                "url": "https://sso.agc.gov.sg/Act/EMA1968#pr38-",
            }
        ]

        with (
            patch("backend.ingestion.scraper_employment_act.asyncio.run", return_value=sections),
            patch("backend.ingestion.scraper_employment_act.RAW_SCRAPED_DIR", tmp_path),
        ):
            result = scrape_and_save()

        assert result == sections
        assert (tmp_path / "employment_act.json").exists()
        saved = json.loads((tmp_path / "employment_act.json").read_text())
        assert saved[0]["section_number"] == "38"

    def test_does_not_save_when_empty(self, tmp_path):
        with (
            patch("backend.ingestion.scraper_employment_act.asyncio.run", return_value=[]),
            patch("backend.ingestion.scraper_employment_act.RAW_SCRAPED_DIR", tmp_path),
        ):
            result = scrape_and_save()

        assert result == []
        assert not (tmp_path / "employment_act.json").exists()
