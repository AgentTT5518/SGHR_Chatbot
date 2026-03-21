"""
Tests for backend.chat.prompts

All functions are pure (no I/O), so no fixtures needed.
"""
from __future__ import annotations

import pytest

from backend.chat.prompts import (
    build_system_prompt,
    extract_sources,
    format_context,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ea_chunk(section_number: str, heading: str, text: str, part: str = "Part IV") -> dict:
    return {
        "text": text,
        "metadata": {
            "source": "Employment Act",
            "part": part,
            "section_number": section_number,
            "heading": heading,
        },
    }


def _mom_chunk(title: str, url: str, text: str) -> dict:
    return {
        "text": text,
        "metadata": {
            "source": "MOM",
            "title": title,
            "url": url,
        },
    }


# ── build_system_prompt ───────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_contains_context_legacy_mode(self):
        prompt = build_system_prompt("SOME CONTEXT", "employee")
        assert "SOME CONTEXT" in prompt
        assert "SOURCE DOCUMENTS" in prompt

    def test_employee_role_instructions(self):
        prompt = build_system_prompt("ctx", "employee")
        assert "EMPLOYEE" in prompt.upper()
        assert "entitlement" in prompt.lower() or "right" in prompt.lower()

    def test_hr_role_instructions(self):
        prompt = build_system_prompt("ctx", "hr")
        assert "HR PROFESSIONAL" in prompt.upper() or "EMPLOYER" in prompt.upper()
        assert "compliance" in prompt.lower() or "obligation" in prompt.lower()

    def test_unknown_role_defaults_to_employee(self):
        prompt_unknown = build_system_prompt("ctx", "unknown_role")
        prompt_employee = build_system_prompt("ctx", "employee")
        assert prompt_unknown == prompt_employee

    def test_shared_rules_always_present(self):
        for role in ("employee", "hr"):
            prompt = build_system_prompt("ctx", role)
            assert "mom.gov.sg" in prompt
            assert "fabricate" in prompt.lower() or "invent" in prompt.lower()

    def test_prompt_is_string(self):
        assert isinstance(build_system_prompt("ctx", "employee"), str)

    def test_orchestrator_mode_no_context(self):
        prompt = build_system_prompt(None, "employee")
        assert "SOURCE DOCUMENTS" not in prompt
        assert "tools" in prompt.lower()
        assert "EMPLOYEE" in prompt.upper()

    def test_orchestrator_mode_hr(self):
        prompt = build_system_prompt(None, "hr")
        assert "tools" in prompt.lower()
        assert "HR PROFESSIONAL" in prompt.upper() or "EMPLOYER" in prompt.upper()

    def test_orchestrator_mode_shared_rules(self):
        for role in ("employee", "hr"):
            prompt = build_system_prompt(None, role)
            assert "mom.gov.sg" in prompt
            assert "fabricate" in prompt.lower() or "invent" in prompt.lower()


# ── format_context ────────────────────────────────────────────────────────────

class TestFormatContext:
    def test_empty_chunks_returns_empty_string(self):
        assert format_context([]) == ""

    def test_single_employment_act_chunk(self):
        chunk = _ea_chunk("38", "Hours of work", "Employees shall not work more than 44 hours per week.")
        result = format_context([chunk])
        assert "Employment Act" in result
        assert "s 38" in result
        assert "Hours of work" in result
        assert "44 hours" in result

    def test_single_mom_chunk(self):
        chunk = _mom_chunk("Annual Leave", "https://www.mom.gov.sg/annual-leave", "Annual leave entitlement...")
        result = format_context([chunk])
        assert "MOM" in result
        assert "Annual Leave" in result
        assert "https://www.mom.gov.sg/annual-leave" in result

    def test_multiple_chunks_are_numbered(self):
        chunks = [
            _ea_chunk("38", "Hours of work", "text one"),
            _mom_chunk("Leave", "https://mom.gov.sg/leave", "text two"),
        ]
        result = format_context(chunks)
        assert "[1]" in result
        assert "[2]" in result

    def test_chunks_separated_by_divider(self):
        chunks = [
            _ea_chunk("38", "Hours", "text one"),
            _ea_chunk("39", "Overtime", "text two"),
        ]
        result = format_context(chunks)
        assert "---" in result

    def test_chunk_without_url_omits_url_line(self):
        chunk = _ea_chunk("10", "Termination", "text")
        result = format_context([chunk])
        assert "URL:" not in result

    def test_mom_chunk_url_included(self):
        chunk = _mom_chunk("Overtime", "https://mom.gov.sg/overtime", "text")
        result = format_context([chunk])
        assert "URL: https://mom.gov.sg/overtime" in result


# ── extract_sources ───────────────────────────────────────────────────────────

class TestExtractSources:
    def test_empty_chunks_returns_empty_list(self):
        assert extract_sources([]) == []

    def test_single_ea_source(self):
        chunk = _ea_chunk("38", "Hours of work", "text")
        sources = extract_sources([chunk])
        assert len(sources) == 1
        assert sources[0]["url"] == ""
        assert "Employment Act" in sources[0]["label"]
        assert "s 38" in sources[0]["label"]

    def test_single_mom_source(self):
        chunk = _mom_chunk("Annual Leave", "https://mom.gov.sg/al", "text")
        sources = extract_sources([chunk])
        assert len(sources) == 1
        assert sources[0]["url"] == "https://mom.gov.sg/al"
        assert "MOM" in sources[0]["label"]

    def test_deduplicates_same_url(self):
        chunk = _mom_chunk("Leave", "https://mom.gov.sg/leave", "text")
        sources = extract_sources([chunk, chunk])
        assert len(sources) == 1

    def test_deduplicates_same_ea_section(self):
        chunk = _ea_chunk("38", "Hours", "text one")
        chunk2 = _ea_chunk("38", "Hours", "different text, same section")
        sources = extract_sources([chunk, chunk2])
        assert len(sources) == 1

    def test_different_sections_are_separate_sources(self):
        chunks = [
            _ea_chunk("38", "Hours of work", "text"),
            _ea_chunk("39", "Overtime pay", "text"),
        ]
        sources = extract_sources(chunks)
        assert len(sources) == 2

    def test_mixed_sources(self):
        chunks = [
            _ea_chunk("38", "Hours", "text"),
            _mom_chunk("Leave", "https://mom.gov.sg/leave", "text"),
        ]
        sources = extract_sources(chunks)
        assert len(sources) == 2
        labels = [s["label"] for s in sources]
        assert any("Employment Act" in l for l in labels)
        assert any("MOM" in l for l in labels)
