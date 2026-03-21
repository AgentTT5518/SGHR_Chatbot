from pathlib import Path
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
SESSIONS_DB = DATA_DIR / "sessions.db"
RAW_SCRAPED_DIR = DATA_DIR / "raw_scraped"


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    claude_model: str = "claude-sonnet-4-6"
    max_tokens: int = 2048
    session_ttl_hours: int = 2
    session_history_pairs: int = 10
    retrieval_mode: str = "hybrid"   # "semantic" | "hybrid"
    chat_rate_limit: str = "20/minute"
    admin_rate_limit: str = "10/minute"
    # Token budget settings (Phase 1)
    context_window: int = 200_000  # claude-sonnet-4-6
    max_output_tokens: int = 4_096
    history_budget_ratio: float = 0.4
    # Context manager settings
    haiku_model: str = "claude-haiku-4-5-20251001"
    summary_recent_pairs: int = 3  # keep last N pairs verbatim
    # Orchestrator settings (Phase 2)
    use_orchestrator: bool = True
    max_tool_iterations: int = 5
    # Profile memory settings (Phase 3)
    profile_retention_years: int = 2
    # Semantic cache settings (Phase 3)
    cache_high_threshold: float = 0.95
    cache_medium_threshold: float = 0.88

    class Config:
        env_file = BASE_DIR.parent / ".env"
        env_file_encoding = "utf-8"


settings = Settings()
