"""
Chunking logic for Employment Act sections and MOM pages.
Uses the BGE tokenizer for accurate token counting.
"""
import re
from typing import Optional

from transformers import AutoTokenizer

_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-base-en-v1.5")
    return _tokenizer


def count_tokens(text: str) -> int:
    tok = get_tokenizer()
    return len(tok.encode(text, add_special_tokens=False))


# Subsection boundary pattern: (1), (2), (a), (b), (i), etc.
SUBSECTION_PATTERN = re.compile(r"(\(\d+\)|\([a-z]\)|\([ivx]+\))")

TARGET_TOKENS = 600
MAX_TOKENS = 800


def chunk_employment_act_section(section: dict) -> list[dict]:
    """
    Chunk a single Employment Act section.
    Sections within MAX_TOKENS are returned as-is.
    Longer sections are split at subsection boundaries.
    """
    base_meta = {
        "source": section["source"],
        "part": section.get("part", ""),
        "division": section.get("division") or "",
        "section_number": section["section_number"],
        "heading": section["heading"],
        "url": section["url"],
    }
    text = section["text"].strip()
    if not text:
        return []

    if count_tokens(text) <= MAX_TOKENS:
        return [{**base_meta, "text": text, "chunk_index": 0}]

    # Split at subsection boundaries
    parts = SUBSECTION_PATTERN.split(text)
    # Re-join split markers with their following text
    # parts alternates: [pre, marker, content, marker, content, ...]
    chunks = []
    current = ""
    chunk_idx = 0

    i = 0
    while i < len(parts):
        segment = parts[i]
        if i + 1 < len(parts) and SUBSECTION_PATTERN.match(parts[i + 1]):
            # Combine marker with its content
            marker = parts[i + 1]
            content = parts[i + 2] if i + 2 < len(parts) else ""
            segment = segment + marker + content
            i += 3
        else:
            i += 1

        segment = segment.strip()
        if not segment:
            continue

        candidate = (current + " " + segment).strip()
        if count_tokens(candidate) <= MAX_TOKENS:
            current = candidate
        else:
            if current:
                chunks.append({**base_meta, "text": current, "chunk_index": chunk_idx})
                chunk_idx += 1
            # If single segment is too long, force-include it
            current = segment

    if current:
        chunks.append({**base_meta, "text": current, "chunk_index": chunk_idx})

    return chunks


def chunk_mom_page(page: dict) -> list[dict]:
    """
    Chunk a MOM page using paragraph-accumulation with overlap.
    Target: ~TARGET_TOKENS per chunk. Overlap: carry last paragraph of prev chunk.
    """
    base_meta = {
        "source": "MOM",
        "title": page.get("title", ""),
        "breadcrumb": page.get("breadcrumb", ""),
        "url": page["url"],
    }
    text = page.get("text", "").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    chunks = []
    chunk_idx = 0
    current_paras: list[str] = []
    current_tokens = 0
    last_para: Optional[str] = None  # overlap carrier

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # Start new chunk with overlap from previous if applicable
        if not current_paras and last_para:
            current_paras = [last_para]
            current_tokens = count_tokens(last_para)

        if current_tokens + para_tokens > MAX_TOKENS and current_paras:
            chunk_text = "\n\n".join(current_paras)
            chunks.append({**base_meta, "text": chunk_text, "chunk_index": chunk_idx})
            chunk_idx += 1
            last_para = current_paras[-1]
            current_paras = []
            current_tokens = 0

        current_paras.append(para)
        current_tokens += para_tokens

    if current_paras:
        chunk_text = "\n\n".join(current_paras)
        chunks.append({**base_meta, "text": chunk_text, "chunk_index": chunk_idx})

    return chunks


def chunk_all(employment_act_sections: list[dict], mom_pages: list[dict]) -> tuple[list[dict], list[dict]]:
    ea_chunks = []
    for section in employment_act_sections:
        ea_chunks.extend(chunk_employment_act_section(section))

    mom_chunks = []
    for page in mom_pages:
        mom_chunks.extend(chunk_mom_page(page))

    print(f"  Employment Act: {len(ea_chunks)} chunks from {len(employment_act_sections)} sections")
    print(f"  MOM: {mom_chunks.__len__()} chunks from {len(mom_pages)} pages")
    return ea_chunks, mom_chunks
