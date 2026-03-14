"""
PRIMARY ingestor for the Singapore Employment Act.
Parses the official PDF from AGC and extracts structured sections.

Usage:
    python -m backend.ingestion.ingest_employment_act_pdf path/to/EmploymentAct.pdf
"""
import json
import re
import sys
from pathlib import Path
from typing import Optional

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar

from backend.config import RAW_SCRAPED_DIR

# Base URL for generating citation links per section
ACT_BASE_URL = "https://sso.agc.gov.sg/Act/EMA1968"

# Patterns to detect structural boundaries in the PDF text
PART_PATTERN = re.compile(r"^PART\s+([\w]+)\b", re.IGNORECASE)
DIVISION_PATTERN = re.compile(r"^Division\s+(\d+)\b", re.IGNORECASE)
# Section heading: e.g. "38.  Rest days" or "2A.  Definitions"
SECTION_PATTERN = re.compile(r"^(\d+[A-Z]?)\.\s+(.+)")


def extract_font_sizes(page_layout) -> list[tuple[str, float]]:
    """Extract (text, avg_font_size) per text container on a page."""
    results = []
    for element in page_layout:
        if isinstance(element, LTTextContainer):
            text = element.get_text().strip()
            if not text:
                continue
            sizes = [
                char.size
                for line in element
                for char in line
                if isinstance(char, LTChar)
            ]
            avg_size = sum(sizes) / len(sizes) if sizes else 0
            results.append((text, avg_size))
    return results


def parse_pdf(pdf_path: Path) -> list[dict]:
    """
    Parse the Employment Act PDF into structured section dicts.
    Returns a list of:
        {source, part, division, section_number, heading, text, url}
    """
    sections = []
    current_part = "Part I"
    current_division: Optional[str] = None
    current_section_number: Optional[str] = None
    current_heading: Optional[str] = None
    current_lines: list[str] = []

    def flush_section():
        if current_section_number and current_lines:
            body = " ".join(current_lines).strip()
            url = f"{ACT_BASE_URL}#pr{current_section_number}-"
            sections.append({
                "source": "Employment Act",
                "part": current_part,
                "division": current_division,
                "section_number": current_section_number,
                "heading": current_heading or "",
                "text": body,
                "url": url,
            })

    for page_layout in extract_pages(str(pdf_path)):
        items = extract_font_sizes(page_layout)
        for text, font_size in items:
            # Skip page numbers and headers/footers (short lines, large/small font)
            if len(text) < 3:
                continue

            # Detect PART headings (typically larger font, all-caps)
            part_match = PART_PATTERN.match(text)
            if part_match and font_size >= 10:
                flush_section()
                current_section_number = None
                current_lines = []
                current_part = text.strip()
                current_division = None
                continue

            # Detect Division headings
            div_match = DIVISION_PATTERN.match(text)
            if div_match and font_size >= 9:
                current_division = text.strip()
                continue

            # Detect Section headings
            sec_match = SECTION_PATTERN.match(text)
            if sec_match and font_size >= 9:
                flush_section()
                current_section_number = sec_match.group(1)
                current_heading = sec_match.group(2).strip()
                current_lines = []
                continue

            # Accumulate body text
            if current_section_number is not None:
                current_lines.append(text)

    flush_section()
    return sections


def ingest_pdf(pdf_path: Path) -> list[dict]:
    print(f"Parsing Employment Act PDF: {pdf_path}")
    sections = parse_pdf(pdf_path)
    print(f"  Extracted {len(sections)} sections")

    out_path = RAW_SCRAPED_DIR / "employment_act.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    print(f"  Saved to {out_path}")
    return sections


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.ingestion.ingest_employment_act_pdf <path_to_pdf>")
        sys.exit(1)
    ingest_pdf(Path(sys.argv[1]))
