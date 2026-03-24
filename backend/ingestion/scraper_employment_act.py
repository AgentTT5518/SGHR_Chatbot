"""
FALLBACK ingestor for the Singapore Employment Act.
Uses Playwright to scrape the SSO website when PDF is unavailable.

Usage:
    python -m backend.ingestion.scraper_employment_act
"""
import asyncio
import json
import random
import re

from backend.config import RAW_SCRAPED_DIR

ACT_URL = "https://sso.agc.gov.sg/Act/EMA1968"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


async def scrape_act() -> list[dict]:
    from playwright.async_api import async_playwright

    sections = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        print(f"Loading TOC: {ACT_URL}")
        await page.goto(ACT_URL, wait_until="networkidle", timeout=30000)

        # Detect Cloudflare or bot challenge
        content = await page.content()
        if "cf-browser-verification" in content or "Just a moment" in content:
            print("  [warn] Cloudflare challenge detected — aborting web scrape.")
            print("         Please use the PDF ingestor instead.")
            await browser.close()
            return []

        # Extract all section links from the TOC
        section_links = await page.eval_on_selector_all(
            "a[href*='#pr']",
            "els => els.map(e => ({href: e.href, text: e.textContent.trim()}))"
        )
        print(f"  Found {len(section_links)} section links")

        current_part = "Part I"
        current_division = None
        part_pattern = re.compile(r"PART\s+([\w]+)\b", re.IGNORECASE)
        div_pattern = re.compile(r"Division\s+(\d+)\b", re.IGNORECASE)

        for i, link in enumerate(section_links):
            href = link["href"]
            await asyncio.sleep(random.uniform(2, 4))

            try:
                await page.goto(href, wait_until="networkidle", timeout=20000)
            except Exception as e:
                print(f"  [warn] Failed to load {href}: {e}")
                continue

            # Check for rate limiting
            status = await page.evaluate("() => document.title")
            if "429" in status or "Too Many Requests" in status:
                print("  [warn] HTTP 429 detected — pausing 30s")
                await asyncio.sleep(30)
                continue

            # Extract section content
            try:
                heading_el = await page.query_selector("h2, h3")
                heading = (await heading_el.inner_text()).strip() if heading_el else ""

                # Try to extract breadcrumb for part/division context
                breadcrumb_els = await page.query_selector_all(".breadcrumb li, nav li")
                breadcrumb = [await el.inner_text() for el in breadcrumb_els]
                for crumb in breadcrumb:
                    if part_pattern.search(crumb):
                        current_part = crumb.strip()
                    if div_pattern.search(crumb):
                        current_division = crumb.strip()

                # Extract main body text
                body_el = await page.query_selector("main, article, .content, #content")
                body_text = (await body_el.inner_text()).strip() if body_el else ""

                # Parse section number from URL fragment or heading
                sec_match = re.search(r"pr(\d+[A-Z]?)-", href)
                sec_num = sec_match.group(1) if sec_match else str(i + 1)

                sections.append({
                    "source": "Employment Act",
                    "part": current_part,
                    "division": current_division,
                    "section_number": sec_num,
                    "heading": heading,
                    "text": body_text,
                    "url": href,
                })
                if i % 10 == 0:
                    print(f"  [{i+1}/{len(section_links)}] section {sec_num}: {heading[:50]}")

            except Exception as e:
                print(f"  [warn] Error parsing section at {href}: {e}")

        await browser.close()

    print(f"  Scraped {len(sections)} sections")
    return sections


def scrape_and_save() -> list[dict]:
    sections = asyncio.run(scrape_act())
    if sections:
        out_path = RAW_SCRAPED_DIR / "employment_act.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sections, f, ensure_ascii=False, indent=2)
        print(f"  Saved to {out_path}")
    return sections


if __name__ == "__main__":
    scrape_and_save()
