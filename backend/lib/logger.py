"""
backend/lib/logger.py
Structured logger factory — creates module-scoped loggers.
See CLAUDE.md Rule 3 for usage requirements.

SETUP PER MODULE:
  from backend.lib.logger import get_logger
  log = get_logger(__name__)        # e.g. "backend.chat.rag_chain"

  # Then use:
  log.info("Session created", extra={"session_id": sid})
  log.error("Claude API failed", exc_info=True, extra={"model": model})
"""
import json
import logging
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
        }
        # Include any extra fields passed via extra={...}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _configure_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # Already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger scoped to the given name.

    Usage:
        log = get_logger(__name__)
        log.info("Startup complete")
        log.warning("ChromaDB collections empty", extra={"collection": "employment_act"})
        log.error("Retrieval failed", exc_info=True, extra={"query": query})
    """
    return logging.getLogger(name)
