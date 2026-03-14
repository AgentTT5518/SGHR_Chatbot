"""
One-time setup script. Run before anything else:
    python setup.py
"""
import subprocess
import sys
from pathlib import Path


def create_dirs():
    dirs = [
        "backend/data/chroma_db",
        "backend/data/raw_scraped",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        print(f"  [ok] {d}")


def download_bge_model():
    print("\nPre-downloading BGE embedding model (~440MB, first run only)...")
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("BAAI/bge-base-en-v1.5")
    print("  [ok] BAAI/bge-base-en-v1.5 cached")


def install_playwright():
    print("\nInstalling Playwright Chromium (fallback scraper)...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("  [ok] Playwright Chromium installed")
    else:
        print(f"  [warn] Playwright install returned: {result.stderr.strip()}")
        print("         This is only needed for the Employment Act web-scrape fallback.")


def init_sqlite():
    print("\nInitialising SQLite session database...")
    import sqlite3
    db_path = Path("backend/data/sessions.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()
    print(f"  [ok] {db_path}")


if __name__ == "__main__":
    print("=== HR Chatbot Setup ===\n")
    print("Creating directories...")
    create_dirs()
    download_bge_model()
    install_playwright()
    init_sqlite()
    print("\n=== Setup complete. Next: run the ingestion pipeline ===")
    print("  python -m backend.ingestion.ingest_pipeline")
