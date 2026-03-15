# Feature: [FEATURE_NAME]
<!-- REQUIRED: Replace every [FEATURE_NAME] in this file with the actual feature name -->
<!-- REQUIRED: Fill in Owner and Description before writing any code -->

## Owner
[Developer name or "unassigned"]

## Scope
This feature owns all files within `src/features/[FEATURE_NAME]/`.

## Description
[1-2 sentences: what this feature does.]

## Boundary Rules
**HARD BLOCK: Do NOT edit files outside this folder without explicit user approval.**

- ONLY modify files within `src/features/[FEATURE_NAME]/` freely
- ASK before modifying: `src/shared/`, `src/app/`, other features, `package.json`, config files, schemas
- When a cross-boundary edit is needed:
  ```
  BOUNDARY ALERT
  File:   [path]
  Reason: [why]
  Change: [what]
  Risk:   [Low/Med/High]
  Proceed? (yes/no)
  ```

## Dependencies
**Shared modules:** [list imports from src/shared/]
**External packages:** [list feature-specific npm packages]
**Other features (read-only):** [list — never modify from here]

## Safe to Edit (no approval needed)
- `src/features/[FEATURE_NAME]/**`
- `tests/**/[FEATURE_NAME]/**`
- `docs/requirements/[FEATURE_NAME].md`
- This file

## Always Requires Approval
- `src/features/[OTHER]/*`, `src/shared/*`, `src/app/*`
- `package.json`, `tsconfig.json`, `ARCHITECTURE.md`, `.env.example`
- Database schemas, migrations, CI/CD config

## Progress
- [ ] CLAUDE.md created (this file)
- [ ] Feature logger created: `src/features/[FEATURE_NAME]/logger.ts`
- [ ] Requirements written
- [ ] Architecture updated
- [ ] Implementation complete
- [ ] All try-catch blocks use `log.error()`
- [ ] All API routes log entry + errors
- [ ] All external service calls log failures
- [ ] Tests passing
- [ ] Secret scan passed
- [ ] Self-review completed
- [ ] ARCHITECTURE.md Feature Log updated
- [ ] Cross-boundary edits logged below

## Cross-Boundary Edit Log
| Date | File | Change | Approved By |
|------|------|--------|-------------|
