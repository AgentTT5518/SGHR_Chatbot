"""
MOM website scraper.
Scrapes curated employment-related topic pages from www.mom.gov.sg.
Performs URL health checks before scraping and does a shallow crawl (depth=1).

Usage:
    python -m backend.ingestion.scraper_mom
"""
import asyncio
import json
import random
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.config import RAW_SCRAPED_DIR

SEED_URLS = [
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/annual-leave",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/sick-leave",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/maternity-leave",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/paternity-leave",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/childcare-leave",
    "https://www.mom.gov.sg/employment-practices/leave-and-holidays/public-holidays",
    "https://www.mom.gov.sg/employment-practices/salary",
    "https://www.mom.gov.sg/employment-practices/salary/overtime-pay",
    "https://www.mom.gov.sg/employment-practices/employment-rights-conditions",
    "https://www.mom.gov.sg/employment-practices/termination-of-employment",
    "https://www.mom.gov.sg/employment-practices/termination-of-employment/termination-with-notice",
    "https://www.mom.gov.sg/employment-practices/termination-of-employment/wrongful-dismissal",
    "https://www.mom.gov.sg/employment-practices/workplace-fairness",
]

MOM_DOMAIN = "www.mom.gov.sg"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_text(soup: BeautifulSoup, url: str) -> dict:
    """Extract title, breadcrumb, and main body text from a MOM page."""
    # Remove navigation, footer, sidebar elements
    for tag in soup.find_all(["nav", "footer", "header", "aside", "script", "style"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r"nav|menu|sidebar|footer|header|breadcrumb", re.I)):
        tag.decompose()

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Breadcrumb
    bc_tags = soup.find_all(class_=re.compile(r"breadcrumb", re.I))
    breadcrumb = " > ".join(t.get_text(" ", strip=True) for t in bc_tags) if bc_tags else ""

    # Main content
    main = soup.find("main") or soup.find(id=re.compile(r"main|content", re.I)) or soup.find("article")
    body_text = main.get_text(" ", strip=True) if main else soup.get_text(" ", strip=True)
    # Normalise whitespace
    body_text = re.sub(r"\s{3,}", "\n\n", body_text)

    return {"title": title, "breadcrumb": breadcrumb, "text": body_text, "url": url, "source": "MOM"}


def get_child_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract same-subdirectory links (depth=1 crawl)."""
    base_path = urlparse(base_url).path.rstrip("/")
    links = set()
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if (
            parsed.netloc == MOM_DOMAIN
            and parsed.path.startswith(base_path + "/")
            and parsed.path != base_path + "/"
            and "#" not in parsed.path
        ):
            links.add(full.split("#")[0].rstrip("/"))
    return list(links)


async def health_check(client: httpx.AsyncClient, url: str) -> tuple[bool, str]:
    """Check if a URL is reachable and returns relevant content."""
    try:
        r = await client.head(url, timeout=10, follow_redirects=True)
        if r.status_code == 200:
            return True, "ok"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def fetch_page(client: httpx.AsyncClient, url: str) -> dict | None:
    try:
        r = await client.get(url, timeout=15, follow_redirects=True)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        return extract_text(soup, url)
    except Exception as e:
        print(f"  [warn] Failed to fetch {url}: {e}")
        return None


async def scrape_mom() -> tuple[list[dict], list[dict]]:
    """Returns (pages, health_report)."""
    pages: list[dict] = []
    health_report: list[dict] = []
    visited: set[str] = set()

    async with httpx.AsyncClient(headers=HEADERS) as client:
        # Health check all seed URLs first
        print("Running URL health checks...")
        for url in SEED_URLS:
            ok, status = await health_check(client, url)
            health_report.append({"url": url, "status": status, "ok": ok})
            icon = "[ok]" if ok else "[warn]"
            print(f"  {icon} {url} — {status}")

        # Scrape seed URLs and their children
        for seed_url in SEED_URLS:
            if seed_url in visited:
                continue
            visited.add(seed_url)
            await asyncio.sleep(random.uniform(1, 2))

            try:
                r = await client.get(seed_url, timeout=15, follow_redirects=True)
            except Exception as e:
                print(f"  [warn] {seed_url}: {e}")
                continue

            if r.status_code != 200:
                print(f"  [warn] {seed_url}: HTTP {r.status_code}")
                continue

            soup = BeautifulSoup(r.text, "lxml")
            page_data = extract_text(soup, seed_url)
            if page_data["text"]:
                pages.append(page_data)
                print(f"  Scraped: {page_data['title'][:60]}")

            # Shallow crawl: find child links
            children = get_child_links(soup, seed_url)
            for child_url in children:
                if child_url in visited:
                    continue
                visited.add(child_url)
                await asyncio.sleep(random.uniform(1, 2))
                child_data = await fetch_page(client, child_url)
                if child_data and child_data["text"]:
                    pages.append(child_data)
                    print(f"    + {child_data['title'][:55]}")

    print(f"\n  Total pages scraped: {len(pages)}")
    return pages, health_report


def scrape_and_save() -> tuple[list[dict], list[dict]]:
    pages, health_report = asyncio.run(scrape_mom())

    out_path = RAW_SCRAPED_DIR / "mom_pages.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    print(f"  Saved to {out_path}")

    health_path = RAW_SCRAPED_DIR / "mom_health_report.json"
    with open(health_path, "w") as f:
        json.dump(health_report, f, indent=2)
    print(f"  Health report: {health_path}")

    return pages, health_report


if __name__ == "__main__":
    scrape_and_save()
