import secrets
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
    # Query expansion settings (Phase 4A)
    use_query_expansion: bool = False
    query_expansion_count: int = 3
    # Contextual compression settings (Phase 4B)
    use_contextual_compression: bool = True
    compression_threshold: float = 0.35
    # Retriever tuning constants (Phase 5 — Retrieval Tuning)
    threshold_floor: float = 0.25
    threshold_multiplier: float = 1.5
    rrf_k: int = 60
    max_retrieval_results: int = 8
    # Environment & deployment (Phase 5 — Auth Hardening)
    environment: str = "dev"  # "dev" | "staging" | "prod"
    allowed_origins: str = "http://localhost:5173"
    admin_api_key: str = "dev-only-key"
    session_secret_key: str = ""
    enforce_https: bool = False
    session_signing_enforced: bool = False
    # Rate limits for additional endpoints
    feedback_rate_limit: str = "5/minute"
    profile_rate_limit: str = "10/minute"

    class Config:
        env_file = BASE_DIR.parent / ".env"
        env_file_encoding = "utf-8"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def effective_secret_key(self) -> str:
        if self.session_secret_key:
            return self.session_secret_key
        # Lazy-generate and cache a runtime key for dev (lost on restart)
        if not hasattr(self, "_runtime_secret"):
            object.__setattr__(self, "_runtime_secret", secrets.token_hex(32))
        return self._runtime_secret  # type: ignore[attr-defined]


settings = Settings()
