# Project Setup

Walk the user through initial project setup by determining which artifacts they need and scaffolding them from templates.

**Source of truth:** `docs/project-setup-guide.md`

## Steps

### 1. Check the CLAUDE.md Setup Checklist

Read `CLAUDE.md` and check if the Setup Checklist items are complete:
- Project Identity table filled in (no `[placeholders]` remaining)
- `[pm]` replaced with actual package manager
- Project Structure updated
- Code conventions added
- SECRET_SCAN_PATTERNS defined
- `.gitignore` includes `.env*` and `!.env.example`
- Logger template copied to `src/lib/logger.ts`
- ARCHITECTURE.md populated

**If incomplete:** Walk the user through completing the checklist first. Do not proceed to artifact questions until the checklist is done.

### 2. Ask Diagnostic Questions

Ask the following questions **one at a time**. Wait for each answer before proceeding.

**Question 1:** "Does your project generate AI outputs? (text, code, summaries, recommendations)"
- Yes → mark EVALS as recommended
- No → skip to Question 3

**Question 2:** "Are those AI outputs visible to end users (not just developers)?"
- Yes → mark BRAND_DOCS as recommended
- No → BRAND_DOCS optional

**Question 3:** "Are there Claude Code workflows you repeat often? (scaffolding, reviewing, generating boilerplate)"
- Yes → mark SKILLS as recommended
- No → SKILLS optional

**Question 4:** "Does your project integrate external services that Claude should access during development? (APIs, databases, search)"
- Yes → mark MCP as recommended
- No → MCP not needed

**Question 5:** "Does your project produce user-facing written content? (blog posts, emails, documentation, error messages)"
- Yes → mark BRAND_DOCS as recommended (even if Question 2 was "No")
- No → no change

**Question 6:** "Are multiple people using Claude Code on this repo?"
- Yes → mark SKILLS as recommended (even if Question 3 was "No") — team skills ensure consistent workflows across developers
- No → no change

**Edge case handling:** If the user gives an ambiguous answer (e.g., "maybe", "not sure", "kind of"), default to "No" for that question. Tell them: "No problem — you can always add this later by following the guide at `docs/project-setup-guide.md` or re-running `/project-setup`."

### 3. Present Recommendations

Show a summary table:

```
| Artifact        | Recommended? | Reason                          |
|-----------------|-------------|----------------------------------|
| Custom Skills   | [Yes/No]    | [Based on Q3/Q6]                 |
| Evals           | [Yes/No]    | [Based on Q1]                    |
| Brand Docs      | [Yes/No]    | [Based on Q2/Q5]                 |
| MCP Tools       | [Yes/No]    | [Based on Q4]                    |
```

Ask: "Should I scaffold the recommended artifacts? You can add or remove items from this list."

### 4. Scaffold Confirmed Artifacts

For each confirmed artifact, create the files:

**If SKILLS confirmed:**
```bash
mkdir -p .claude/commands
```
- Copy `docs/templates/skill-template.md` to `.claude/commands/example.md`
- Tell the user: "Rename `.claude/commands/example.md` to match your workflow (e.g., `review.md` → `/review`). Customize following `docs/skills-guide.md`."

**If EVALS confirmed:**
- Ask the user: "What AI feature should this eval test? (e.g., 'blog-quality', 'chat-tone', 'summary-accuracy')"
- Use the answer as `[name]`
```bash
mkdir -p eval-[name]/cases
```
- Copy `docs/templates/eval-template/README.md` to `eval-[name]/README.md`
- Copy `docs/templates/eval-template/cases/example-case.json` to `eval-[name]/cases/example-case.json`
- Copy `docs/templates/eval-template/scoring-rubric.md` to `eval-[name]/scoring-rubric.md`
- Replace `[Eval Name]` placeholders with the user's chosen name
- Tell the user: "Add test cases and customize the scoring rubric. See `docs/evals-guide.md`."

**If BRAND_DOCS confirmed:**
```bash
mkdir -p docs/brand
```
- Copy `docs/templates/brand/BRAND-PROFILE.md` to `docs/brand/BRAND-PROFILE.md`
- Copy `docs/templates/brand/STYLE-GUIDE.md` to `docs/brand/STYLE-GUIDE.md`
- Copy `docs/templates/brand/TONE-MATRIX.md` to `docs/brand/TONE-MATRIX.md`
- Tell the user: "Start with `docs/brand/BRAND-PROFILE.md` — the exemplars section is the most impactful. See `docs/brand-voice-guide.md`."

**If MCP confirmed:**
- Do NOT scaffold any files (MCP configs are too project-specific)
- Tell the user: "MCP tool setup is project-specific. Configure servers in `.claude/settings.json` under `mcpServers`. See the official Claude Code MCP documentation for setup instructions."

### 5. Post-Setup Guidance

Tell the user to update their project references:
- "Add your new artifacts to the Reference Docs section in `CLAUDE.md`"
- "Log this setup in your `ARCHITECTURE.md` Feature Log"
- "List available skills in your project README so team members know what's available"

### 6. Print Summary

```
Setup complete! Here's what was created:

[List each artifact that was scaffolded with its path]

Next steps for each:
- Skills: Rename and customize .claude/commands/example.md → docs/skills-guide.md
- Evals: Add test cases to eval-[name]/cases/ → docs/evals-guide.md
- Brand: Fill in docs/brand/BRAND-PROFILE.md first → docs/brand-voice-guide.md

Full decision reference: docs/project-setup-guide.md
You can re-run /project-setup any time to add more artifacts.
```

## Rules

- Always reference `docs/project-setup-guide.md` as the source of truth
- Never skip the diagnostic questions — they determine what gets scaffolded
- Do not scaffold MCP files — only provide guidance and links
- If CLAUDE.md Setup Checklist is incomplete, complete it first
- Ask for confirmation before creating any files
- Ambiguous answers default to "No" — tell user they can add later
- Do not modify CLAUDE.md, README.md, or ARCHITECTURE.md automatically — tell the user to update references manually
