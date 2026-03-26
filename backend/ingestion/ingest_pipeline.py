"""
from __future__ import annotations

# Main ingestion pipeline. Run once to populate ChromaDB.

Usage:
    python -m backend.ingestion.ingest_pipeline [--pdf path/to/EmploymentAct.pdf]

If --pdf is not provided, attempts web scraping as fallback.
If raw_scraped JSON files already exist, re-uses them (skip scraping).
"""
import argparse
import hashlib
import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from backend.config import RAW_SCRAPED_DIR, CHROMA_DIR
from backend.lib.logger import get_logger

log = get_logger(__name__)


class IngestionCancelled(Exception):
    """Raised when an in-progress ingestion is cancelled via the cancel token."""


def _load_or_scrape_employment_act(pdf_path: Path | None) -> list[dict]:
    cached = RAW_SCRAPED_DIR / "employment_act.json"
    if cached.exists():
        log.info("Using cached Employment Act data", extra={"path": str(cached)})
        with open(cached) as f:
            return json.load(f)

    if pdf_path and pdf_path.exists():
        from backend.ingestion.ingest_employment_act_pdf import ingest_pdf
        return ingest_pdf(pdf_path)
    else:
        log.info("No PDF provided — falling back to web scrape (Playwright)")
        from backend.ingestion.scraper_employment_act import scrape_and_save
        sections = scrape_and_save()
        if not sections:
            log.error("Web scrape failed and no PDF available")
            sys.exit(1)
        return sections


def _load_or_scrape_mom() -> list[dict]:
    cached = RAW_SCRAPED_DIR / "mom_pages.json"
    if cached.exists():
        log.info("Using cached MOM data", extra={"path": str(cached)})
        with open(cached) as f:
            return json.load(f)

    from backend.ingestion.scraper_mom import scrape_and_save
    pages, _ = scrape_and_save()
    return pages


def _chunk_id(source: str, index: int, chunk_index: int) -> str:
    key = f"{source}::{index}::{chunk_index}"
    return hashlib.md5(key.encode()).hexdigest()


def _upsert_chunks(collection, chunks: list[dict], source_label: str):
    if not chunks:
        log.warning("No chunks to upsert", extra={"source": source_label})
        return

    from backend.ingestion.embedder import embed_documents

    texts = [c["text"] for c in chunks]
    log.info("Embedding chunks", extra={"count": len(texts), "source": source_label})
    embeddings = embed_documents(texts)

    ids = [_chunk_id(source_label, i, c.get("chunk_index", i)) for i, c in enumerate(chunks)]
    # ChromaDB metadata values must be str/int/float/bool — clean None values
    metadatas = [
        {k: (v if v is not None else "") for k, v in c.items() if k != "text"}
        for c in chunks
    ]

    batch_size = 500
    for start in range(0, len(chunks), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )
    log.info("Upserted chunks", extra={"count": len(chunks), "collection": collection.name})


def run(
    pdf_path: Path | None = None,
    on_progress: Callable[[dict], None] | None = None,
    cancel_token: threading.Event | None = None,
) -> None:
    """Run the full ingestion pipeline.

    Args:
        pdf_path: Optional path to Employment Act PDF.
        on_progress: Optional callback invoked at each step boundary.
            Receives a dict: {"step", "total_steps", "label", "detail"}.
        cancel_token: Optional threading.Event; if set, pipeline aborts
            with IngestionCancelled before the next step.
    """
    import chromadb
    from backend.ingestion.chunker import chunk_all

    def _check_cancel() -> None:
        if cancel_token and cancel_token.is_set():
            raise IngestionCancelled()

    def _emit(step: int, label: str, detail: str = "") -> None:
        log.info(label, extra={"step": step, "detail": detail})
        if on_progress:
            on_progress({
                "step": step,
                "total_steps": 4,
                "label": label,
                "detail": detail,
            })

    RAW_SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load / scrape Employment Act
    _check_cancel()
    _emit(1, "Loading Employment Act")
    ea_sections = _load_or_scrape_employment_act(pdf_path)
    _emit(1, "Loading Employment Act", f"{len(ea_sections)} sections loaded")

    # 2. Load / scrape MOM pages
    _check_cancel()
    _emit(2, "Loading MOM pages")
    mom_pages = _load_or_scrape_mom()
    _emit(2, "Loading MOM pages", f"{len(mom_pages)} pages loaded")

    # 3. Chunk
    _check_cancel()
    _emit(3, "Chunking text")
    ea_chunks, mom_chunks = chunk_all(ea_sections, mom_pages)
    _emit(3, "Chunking text", f"{len(ea_chunks)} EA + {len(mom_chunks)} MOM chunks")

    # 4. Embed & upsert into ChromaDB
    _check_cancel()
    _emit(4, "Embedding and indexing")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ea_col = client.get_or_create_collection(
        name="employment_act",
        metadata={"hnsw:space": "cosine"},
    )
    mom_col = client.get_or_create_collection(
        name="mom_guidelines",
        metadata={"hnsw:space": "cosine"},
    )

    _upsert_chunks(ea_col, ea_chunks, "employment_act")
    _upsert_chunks(mom_col, mom_chunks, "mom_guidelines")

    ea_count = ea_col.count()
    mom_count = mom_col.count()
    _emit(4, "Complete", f"{ea_count} EA + {mom_count} MOM documents indexed")
    log.info("Ingestion complete", extra={"ea": ea_count, "mom": mom_count})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HR Chatbot ingestion pipeline")
    parser.add_argument("--pdf", type=Path, default=None, help="Path to Employment Act PDF")
    args = parser.parse_args()
    run(pdf_path=args.pdf)
