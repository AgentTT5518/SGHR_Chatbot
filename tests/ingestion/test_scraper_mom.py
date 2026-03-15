"""
Tests for backend.ingestion.scraper_mom

Mocks httpx.AsyncClient so no real HTTP requests are made.
BeautifulSoup is exercised with inline HTML fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest
from bs4 import BeautifulSoup

from backend.ingestion.scraper_mom import (
    extract_text,
    get_child_links,
    health_check,
    fetch_page,
    scrape_and_save,
)


# ── HTML fixtures ──────────────────────────────────────────────────────────────

SIMPLE_HTML = """
<html>
  <head><title>Annual Leave | MOM</title></head>
  <body>
    <nav>Navigation bar</nav>
    <header>Site header</header>
    <main>
      <h1>Annual Leave</h1>
      <p>Employees are entitled to annual leave after completing 3 months of service.</p>
      <p>The entitlement increases with years of service.</p>
    </main>
    <footer>Footer content</footer>
  </body>
</html>
"""

HTML_WITH_LINKS = """
<html>
  <body>
    <main>
      <h1>Leave and Holidays</h1>
      <p>Overview of leave types.</p>
      <a href="/employment-practices/leave-and-holidays/annual-leave">Annual Leave</a>
      <a href="/employment-practices/leave-and-holidays/sick-leave">Sick Leave</a>
      <a href="/employment-practices/salary">Salary</a>
      <a href="https://external.com/other">External Link</a>
    </main>
  </body>
</html>
"""

HTML_NO_MAIN = """
<html>
  <body>
    <h1>Overtime Pay</h1>
    <p>Overtime is calculated at 1.5x the basic rate.</p>
  </body>
</html>
"""


# ── extract_text ───────────────────────────────────────────────────────────────

class TestExtractText:
    def test_extracts_title_from_h1(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/annual-leave")
        assert result["title"] == "Annual Leave"

    def test_extracts_body_text(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/annual-leave")
        assert "annual leave" in result["text"].lower()
        assert "3 months" in result["text"]

    def test_removes_nav_and_footer(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/annual-leave")
        assert "Navigation bar" not in result["text"]
        assert "Footer content" not in result["text"]
        assert "Site header" not in result["text"]

    def test_url_preserved(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        url = "https://www.mom.gov.sg/annual-leave"
        result = extract_text(soup, url)
        assert result["url"] == url

    def test_source_is_mom(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/annual-leave")
        assert result["source"] == "MOM"

    def test_fallback_when_no_main_tag(self):
        soup = BeautifulSoup(HTML_NO_MAIN, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/overtime")
        assert "Overtime" in result["text"]

    def test_title_falls_back_to_title_tag(self):
        html = "<html><head><title>Page Title</title></head><body><p>Content</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/page")
        assert result["title"] == "Page Title"

    def test_returns_dict_with_required_keys(self):
        soup = BeautifulSoup(SIMPLE_HTML, "lxml")
        result = extract_text(soup, "https://www.mom.gov.sg/annual-leave")
        assert set(result.keys()) >= {"title", "breadcrumb", "text", "url", "source"}


# ── get_child_links ────────────────────────────────────────────────────────────

class TestGetChildLinks:
    BASE = "https://www.mom.gov.sg/employment-practices/leave-and-holidays"

    def test_returns_same_subdirectory_links(self):
        soup = BeautifulSoup(HTML_WITH_LINKS, "lxml")
        links = get_child_links(soup, self.BASE)
        assert any("annual-leave" in l for l in links)
        assert any("sick-leave" in l for l in links)

    def test_excludes_parent_and_sibling_paths(self):
        soup = BeautifulSoup(HTML_WITH_LINKS, "lxml")
        links = get_child_links(soup, self.BASE)
        # /employment-practices/salary is a sibling, not a child
        assert not any(l.endswith("/salary") for l in links)

    def test_excludes_external_links(self):
        soup = BeautifulSoup(HTML_WITH_LINKS, "lxml")
        links = get_child_links(soup, self.BASE)
        assert not any("external.com" in l for l in links)

    def test_returns_list(self):
        soup = BeautifulSoup(HTML_WITH_LINKS, "lxml")
        result = get_child_links(soup, self.BASE)
        assert isinstance(result, list)

    def test_no_duplicates(self):
        html = """<html><body>
          <a href="/employment-practices/leave-and-holidays/annual-leave">AL</a>
          <a href="/employment-practices/leave-and-holidays/annual-leave">AL again</a>
        </body></html>"""
        soup = BeautifulSoup(html, "lxml")
        links = get_child_links(soup, self.BASE)
        assert len(links) == len(set(links))


# ── health_check ───────────────────────────────────────────────────────────────

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.head.return_value = mock_resp

        ok, status = await health_check(mock_client, "https://www.mom.gov.sg/page")
        assert ok is True
        assert status == "ok"

    @pytest.mark.asyncio
    async def test_returns_false_on_non_200(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.head.return_value = mock_resp

        ok, status = await health_check(mock_client, "https://www.mom.gov.sg/missing")
        assert ok is False
        assert "404" in status

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        mock_client = AsyncMock()
        mock_client.head.side_effect = Exception("connection refused")

        ok, status = await health_check(mock_client, "https://www.mom.gov.sg/page")
        assert ok is False
        assert "connection refused" in status


# ── fetch_page ────────────────────────────────────────────────────────────────

class TestFetchPage:
    @pytest.mark.asyncio
    async def test_returns_dict_on_200(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SIMPLE_HTML
        mock_client.get.return_value = mock_resp

        result = await fetch_page(mock_client, "https://www.mom.gov.sg/annual-leave")
        assert result is not None
        assert result["title"] == "Annual Leave"

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_client.get.return_value = mock_resp

        result = await fetch_page(mock_client, "https://www.mom.gov.sg/forbidden")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("timeout")

        result = await fetch_page(mock_client, "https://www.mom.gov.sg/page")
        assert result is None


# ── scrape_and_save ───────────────────────────────────────────────────────────

class TestScrapeAndSave:
    def test_saves_pages_and_health_report(self, tmp_path):
        pages = [{"title": "Annual Leave", "text": "leave text", "url": "https://u", "source": "MOM", "breadcrumb": ""}]
        health = [{"url": "https://u", "status": "ok", "ok": True}]

        with (
            patch("backend.ingestion.scraper_mom.asyncio.run", return_value=(pages, health)),
            patch("backend.ingestion.scraper_mom.RAW_SCRAPED_DIR", tmp_path),
        ):
            result_pages, result_health = scrape_and_save()

        assert result_pages == pages
        assert result_health == health
        assert (tmp_path / "mom_pages.json").exists()
        assert (tmp_path / "mom_health_report.json").exists()

    def test_saved_json_is_valid(self, tmp_path):
        pages = [{"title": "T", "text": "body", "url": "https://u", "source": "MOM", "breadcrumb": ""}]
        health = []

        with (
            patch("backend.ingestion.scraper_mom.asyncio.run", return_value=(pages, health)),
            patch("backend.ingestion.scraper_mom.RAW_SCRAPED_DIR", tmp_path),
        ):
            scrape_and_save()

        saved = json.loads((tmp_path / "mom_pages.json").read_text())
        assert saved[0]["title"] == "T"
