"""
Tests for backend.lib.logger

Verifies the JSON formatter, extra fields, exc_info, and get_logger scoping.
"""
from __future__ import annotations

import json
import logging

import pytest

from backend.lib.logger import _JsonFormatter, get_logger


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_record(
    name: str = "test",
    level: int = logging.INFO,
    msg: str = "hello",
    exc_info=None,
    extra: dict | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name, level=level, pathname="", lineno=0,
        msg=msg, args=(), exc_info=exc_info,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


# ── _JsonFormatter ────────────────────────────────────────────────────────────

class TestJsonFormatter:
    def setup_method(self):
        self.fmt = _JsonFormatter()

    def test_output_is_valid_json(self):
        record = _make_record()
        output = self.fmt.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self):
        record = _make_record(name="mymodule", msg="test message")
        parsed = json.loads(self.fmt.format(record))
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "mymodule"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed

    def test_level_names(self):
        for level, name in [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
        ]:
            record = _make_record(level=level)
            parsed = json.loads(self.fmt.format(record))
            assert parsed["level"] == name

    def test_extra_fields_included(self):
        record = _make_record(extra={"session_id": "abc-123", "user_role": "hr"})
        parsed = json.loads(self.fmt.format(record))
        assert parsed["session_id"] == "abc-123"
        assert parsed["user_role"] == "hr"

    def test_exc_info_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc = sys.exc_info()

        record = _make_record(exc_info=exc)
        parsed = json.loads(self.fmt.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]
        assert "boom" in parsed["exc_info"]

    def test_exc_info_is_none_when_no_exception(self):
        # exc_info=None is a standard LogRecord instance field; the formatter
        # may include it as null — it must never be a traceback string
        record = _make_record()
        parsed = json.loads(self.fmt.format(record))
        assert parsed.get("exc_info") is None


# ── get_logger ────────────────────────────────────────────────────────────────

class TestGetLogger:
    def test_returns_logger_instance(self):
        log = get_logger("test.module")
        assert isinstance(log, logging.Logger)

    def test_logger_name_matches(self):
        log = get_logger("backend.chat.rag_chain")
        assert log.name == "backend.chat.rag_chain"

    def test_same_name_returns_same_instance(self):
        log1 = get_logger("backend.same")
        log2 = get_logger("backend.same")
        assert log1 is log2

    def test_different_names_are_different_loggers(self):
        log1 = get_logger("backend.module_a")
        log2 = get_logger("backend.module_b")
        assert log1 is not log2

    def test_logger_can_log_without_error(self, caplog):
        log = get_logger("test.tier1")
        with caplog.at_level(logging.INFO, logger="test.tier1"):
            log.info("Tier 1 test message")
        assert "Tier 1 test message" in caplog.text
