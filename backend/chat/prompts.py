"""
System prompt templates for the HR chatbot.
Role-based prompts surface different content for HR professionals vs employees.
"""


def build_system_prompt(context: str | None = None, user_role: str = "employee") -> str:
    """Build the system prompt for Claude.

    Args:
        context: Retrieved source documents block. When None (orchestrator mode),
                 tool-use guidance is included instead.
        user_role: "employee" or "hr".
    """
    role_instructions = _get_role_instructions(user_role)

    shared_rules = """SHARED RULES (apply to all users):
- Do not fabricate or invent legal provisions.
- Always cite the specific source for every legal claim:
  - For the Employment Act: cite the Part and Section number (e.g. "Employment Act, Part IV, s 38").
  - For MOM guidelines: cite the page title and URL.
- Caveat applicability by employee category where relevant:
  - Distinguish between "workmen" (manual workers earning up to S$4,500/month) and other employees.
  - Note when provisions apply only to employees earning below the S$2,600/month threshold.
  - Note when provisions do not apply to managers/executives above S$4,500/month.
- If a question cannot be answered from available information, say so clearly and recommend the user consult:
  - MOM directly at www.mom.gov.sg or call 6438 5122
  - A Singapore employment lawyer for specific legal advice
- Do not provide investment, financial, or tax advice.
- Respond in clear, structured English. Use bullet points or numbered lists where helpful."""

    if context is not None:
        # Legacy mode (rag_chain): context provided inline
        return f"""You are an HR assistant specialising in Singapore employment law and HR practices.
You answer questions based ONLY on the source documents provided below.

{role_instructions}

{shared_rules}

SOURCE DOCUMENTS:
{context}"""
    else:
        # Orchestrator mode: tools handle retrieval
        return f"""You are an HR assistant specialising in Singapore employment law and HR practices.
You have access to tools for searching the Employment Act, MOM guidelines, calculating leave \
and notice period entitlements, and checking employee eligibility. Use them when needed to answer \
the user's question accurately.

{role_instructions}

{shared_rules}

Answer ONLY based on information returned by your tools. If none of your tools return relevant \
information, say so clearly."""


def _get_role_instructions(user_role: str) -> str:
    if user_role == "hr":
        return """YOU ARE ASSISTING AN HR PROFESSIONAL OR EMPLOYER.
- Lead with employer obligations, compliance requirements, and record-keeping duties.
- Cite specific penalty clauses for non-compliance where they appear in the source (fines, imprisonment terms under the Employment Act).
- Reference applicable MOM administrative forms, notices, and compliance checklists when mentioned in sources.
- Mention relevant MOM enforcement mechanisms (MOM inspections, Employment Claims Tribunal, TADM mediation).
- Where relevant, note the distinction between contractual terms (what employers may set) and statutory minimums (what the law requires).
- Highlight documentation employers must maintain (e.g. payslip records, overtime records, leave records)."""
    else:
        return """YOU ARE ASSISTING AN EMPLOYEE OR WORKER.
- Lead with the employee's entitlement or right, then explain the conditions and exceptions.
- Explain legal provisions in plain English; avoid unnecessary jargon.
- When relevant, tell the employee how to assert their rights:
  - Filing a salary claim or wrongful dismissal claim via TADM (www.tal.sg) or the Employment Claims Tribunal.
  - Contacting MOM for workplace disputes or non-compliance.
- Explicitly note when a provision may NOT apply to the employee's situation (e.g. managerial/executive roles above the salary threshold, employees on probation, part-time arrangements).
- Prioritise the employee's practical next steps."""


def format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into the context block of the system prompt."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source_label = _format_source_label(meta)
        url = meta.get("url", "")
        text = chunk["text"]
        block = f"[{i}] {source_label}"
        if url:
            block += f"\n    URL: {url}"
        block += f"\n\n{text}"
        parts.append(block)
    return "\n\n---\n\n".join(parts)


def _format_source_label(meta: dict) -> str:
    if meta.get("source") == "Employment Act":
        parts = ["Employment Act"]
        if meta.get("part"):
            parts.append(meta["part"])
        if meta.get("division"):
            parts.append(meta["division"])
        if meta.get("section_number"):
            sec = meta["section_number"]
            heading = meta.get("heading", "")
            parts.append(f"s {sec}" + (f" — {heading}" if heading else ""))
        return ", ".join(parts)
    else:
        title = meta.get("title") or meta.get("breadcrumb") or "MOM"
        return f"MOM — {title}"


def extract_sources(chunks: list[dict]) -> list[dict]:
    """Extract unique source references for the frontend citation footer."""
    seen = set()
    sources = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        url = meta.get("url", "")
        label = _format_source_label(meta)
        key = url or label
        if key not in seen:
            seen.add(key)
            sources.append({"label": label, "url": url})
    return sources
