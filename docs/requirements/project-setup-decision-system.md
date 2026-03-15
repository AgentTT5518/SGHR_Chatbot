# Requirements: Project Setup Decision System

## Summary

Add a decision system that helps users determine which artifacts to create (skills, evals, brand docs, MCP tools) when starting a new project with this template.

## Problem

The template provides rules, workflows, and templates — but doesn't guide users on **which optional artifacts to set up** based on their project type. Users must discover skills, evals, and brand docs on their own.

## Solution

A layered system with three parts:

1. **Decision guide** (`docs/project-setup-guide.md`) — source of truth; a decision tree mapping project characteristics to artifact recommendations
2. **Setup skill** (`.claude/commands/project-setup.md`) — interactive `/project-setup` command that automates the decision guide
3. **Per-artifact guides + templates** — detailed how-to docs and copy-paste-ready starter files

## Artifacts Covered

| Artifact | When Recommended | Guide | Template |
|----------|-----------------|-------|----------|
| Custom Skills | Repetitive Claude workflows | `docs/skills-guide.md` | `docs/templates/skill-template.md` |
| Evals | Project generates AI outputs | `docs/evals-guide.md` | `docs/templates/eval-template/` |
| Brand Docs | AI outputs face end users or project produces written content | `docs/brand-voice-guide.md` | `docs/templates/brand/` |
| MCP Tools | External service integrations | Guidance in `docs/project-setup-guide.md` | None (too project-specific) |

## Key Decisions

- Decision guide is the source of truth; the skill automates it
- No MCP templates — too project-specific; guidance and links provided instead
- Evals use manual scoring first; automation layered on later
- Brand docs are layered: BRAND-PROFILE → STYLE-GUIDE → TONE-MATRIX
- Skill does not auto-update CLAUDE.md/README/ARCHITECTURE — tells user to do it
- Ambiguous answers default to "No" — user can re-run or scaffold manually

## Files Created

| File | Type |
|------|------|
| `docs/project-setup-guide.md` | Decision guide |
| `docs/skills-guide.md` | Guide |
| `docs/evals-guide.md` | Guide |
| `docs/brand-voice-guide.md` | Guide |
| `docs/templates/skill-template.md` | Template |
| `docs/templates/eval-template/README.md` | Template |
| `docs/templates/eval-template/cases/example-case.json` | Template |
| `docs/templates/eval-template/scoring-rubric.md` | Template |
| `docs/templates/brand/BRAND-PROFILE.md` | Template |
| `docs/templates/brand/STYLE-GUIDE.md` | Template |
| `docs/templates/brand/TONE-MATRIX.md` | Template |
| `.claude/commands/project-setup.md` | Skill |
| `docs/requirements/project-setup-decision-system.md` | Requirements (this file) |
