"""
Retrieval tools: wrap the vector search pipeline as Claude tool-use handlers.
Each handler returns formatted text with source citations.
"""
from __future__ import annotations

from typing import Any

from backend.chat.prompts import format_context
from backend.lib.logger import get_logger
from backend.retrieval.retriever import (
    retrieve,
    retrieve_from_collection,
    get_section_2,
)

log = get_logger("chat.tools.retrieval_tools")

_NO_RESULTS = "No relevant documents found for this query."


def _format_results(chunks: list[dict]) -> str:
    """Format retrieval results into readable text with source citations."""
    if not chunks:
        return _NO_RESULTS
    return format_context(chunks)


async def search_employment_act(tool_input: dict[str, Any]) -> str:
    """Search the Employment Act collection with optional section filter."""
    query: str = tool_input["query"]
    section_filter: str | None = tool_input.get("section_filter")

    log.info(
        "Searching Employment Act",
        extra={"query": query, "section_filter": section_filter},
    )
    chunks = retrieve_from_collection(
        query=query,
        collection="employment_act",
        section_filter=section_filter,
    )
    return _format_results(chunks)


async def search_mom_guidelines(tool_input: dict[str, Any]) -> str:
    """Search the MOM guidelines collection."""
    query: str = tool_input["query"]

    log.info("Searching MOM guidelines", extra={"query": query})
    chunks = retrieve_from_collection(query=query, collection="mom_guidelines")
    return _format_results(chunks)


async def search_all_policies(tool_input: dict[str, Any]) -> str:
    """Search across both Employment Act and MOM guidelines."""
    query: str = tool_input["query"]

    log.info("Searching all policies", extra={"query": query})
    chunks = retrieve(query=query)
    return _format_results(chunks)


async def get_legal_definitions(tool_input: dict[str, Any]) -> str:
    """Retrieve Section 2 definitions from the Employment Act."""
    term: str = tool_input["term"]

    log.info("Looking up legal definition", extra={"term": term})
    section_2 = get_section_2()
    if section_2 is None:
        return (
            f"Could not find the legal definition of '{term}'. "
            "The Employment Act Section 2 (Definitions) is not available in the knowledge base."
        )

    text = section_2.get("text", "")
    meta = section_2.get("metadata", {})
    source = "Employment Act, Section 2 — Interpretation"
    url = meta.get("url", "")
    header = f"Source: {source}"
    if url:
        header += f"\nURL: {url}"

    return f"{header}\n\n{text}"


def register_retrieval_tools() -> None:
    """Register all retrieval tool handlers in the tool registry."""
    from backend.chat.tools.registry import register_tool

    register_tool("search_employment_act", search_employment_act)
    register_tool("search_mom_guidelines", search_mom_guidelines)
    register_tool("search_all_policies", search_all_policies)
    register_tool("get_legal_definitions", get_legal_definitions)
