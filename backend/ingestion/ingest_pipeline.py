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
from pathlib import Path

from backend.config import RAW_SCRAPED_DIR, CHROMA_DIR


def _load_or_scrape_employment_act(pdf_path: Path | None) -> list[dict]:
    cached = RAW_SCRAPED_DIR / "employment_act.json"
    if cached.exists():
        print(f"Using cached Employment Act data: {cached}")
        with open(cached) as f:
            return json.load(f)

    if pdf_path and pdf_path.exists():
        from backend.ingestion.ingest_employment_act_pdf import ingest_pdf
        return ingest_pdf(pdf_path)
    else:
        print("No PDF provided — falling back to web scrape (Playwright).")
        from backend.ingestion.scraper_employment_act import scrape_and_save
        sections = scrape_and_save()
        if not sections:
            print("[error] Web scrape failed and no PDF available. Exiting.")
            sys.exit(1)
        return sections


def _load_or_scrape_mom() -> list[dict]:
    cached = RAW_SCRAPED_DIR / "mom_pages.json"
    if cached.exists():
        print(f"Using cached MOM data: {cached}")
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
        print(f"  [warn] No chunks to upsert for {source_label}")
        return

    from backend.ingestion.embedder import embed_documents

    texts = [c["text"] for c in chunks]
    print(f"  Embedding {len(texts)} {source_label} chunks...")
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
    print(f"  Upserted {len(chunks)} chunks into '{collection.name}'")


def run(pdf_path: Path | None = None):
    import chromadb
    from backend.ingestion.chunker import chunk_all

    RAW_SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load / scrape source data
    print("\n[1/4] Loading Employment Act...")
    ea_sections = _load_or_scrape_employment_act(pdf_path)
    print(f"      {len(ea_sections)} sections loaded")

    print("\n[2/4] Loading MOM pages...")
    mom_pages = _load_or_scrape_mom()
    print(f"      {len(mom_pages)} pages loaded")

    # 2. Chunk
    print("\n[3/4] Chunking...")
    ea_chunks, mom_chunks = chunk_all(ea_sections, mom_pages)

    # 3. Embed & upsert into ChromaDB
    print("\n[4/4] Embedding and indexing...")
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

    print("\n=== Ingestion complete ===")
    print(f"  employment_act collection: {ea_col.count()} documents")
    print(f"  mom_guidelines collection: {mom_col.count()} documents")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HR Chatbot ingestion pipeline")
    parser.add_argument("--pdf", type=Path, default=None, help="Path to Employment Act PDF")
    args = parser.parse_args()
    run(pdf_path=args.pdf)
