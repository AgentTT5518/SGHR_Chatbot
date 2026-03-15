# Command Policy Guide

A guide to defining which operations Claude Code can run automatically, which require confirmation, and which are prohibited.

---

## Why This Matters

- **AI agents execute real commands on real systems.** A misclassified operation can delete data, expose secrets, or push broken code to production. Explicit permission tiers prevent accidents before they happen.
- **Allowlists are the only secure approach.** Denylists have been bypassed via encoding tricks (base64, subshells, quote obfuscation). Define what's allowed, not what's blocked.
- **Principle of least agency.** Grant only the minimum autonomy needed for the current task — expand permissions deliberately, never by default.

## When You Need a Command Policy

| Your Project... | Need a Policy? |
|-----------------|---------------|
| Uses Claude Code for development (any project) | **Yes** — minimum viable policy |
| Has CI/CD pipelines or deployment scripts | **Yes** — protect production |
| Stores sensitive data (user PII, credentials, financial) | **Yes** — strict Tier 2/3 rules |
| Multiple developers using Claude Code | **Yes** — team-wide consistency |
| Solo developer on a throwaway prototype | **Optional** — even a minimal policy prevents accidents |

---

## The Three-Tier Model

| Tier | Name | Behavior | Philosophy |
|------|------|----------|------------|
| **1** | Auto-Approved | Runs without asking | Read-only operations and bounded safe analysis |
| **2** | Requires Confirmation | Claude asks before executing | Operations with side effects or external impact |
| **3** | Prohibited | Claude must never execute | Destructive, irreversible, or security-critical operations |

**How tiers interact with Rule 5 (Feature Boundary):**

- Rule 5 governs **where** Claude can edit (file scope)
- The Command Policy governs **what** Claude can do (operation scope)
- These are independent axes — neither overrides the other

```
Tier 1 operation                            = Auto-approved
Tier 2 operation                            = Confirm
Tier 3 operation                            = Prohibited (always)
Edit inside feature boundary  (Rule 5)      = Allowed
Edit outside feature boundary (Rule 5)      = Confirm
```

---

## Tier 1 — Auto-Approved

Operations that are read-only, non-destructive, and confined to the project workspace.

| Category | Examples | Why Safe |
|----------|----------|----------|
| File reading | `cat`, `head`, `tail`, `less`, Read tool | No side effects |
| File search | `grep`, `find`, `glob`, Grep tool | Read-only |
| Code analysis | `[pm] typecheck`, `[pm] lint` | Read-only checks |
| Test execution | `[pm] test` | Sandboxed, no production impact |
| Build | `[pm] build` | Creates local artifacts, does not deploy |
| Git read operations | `git status`, `git log`, `git diff`, `git branch` | Informational only |
| Dependency info | `[pm] list`, `[pm] outdated` | Read-only |

<!-- Replace [pm] with your package manager -->

## Tier 2 — Requires Confirmation

Operations that modify state, interact with external systems, or affect shared resources. Claude asks before executing.

| Category | Examples | Why Confirm |
|----------|----------|-------------|
| Package installation | `[pm] install`, `[pm] add` | Modifies dependency tree, supply chain risk |
| Git mutations | `git add`, `git commit`, `git push`, `git checkout`, `git merge`, `git stash` | Changes repository state |
| Process execution | Starting servers, running scripts, `npx` | Arbitrary code execution |
| Network requests | `curl`, `wget`, `fetch` | Data exfiltration risk |
| Environment file access | Reading/modifying `.env.local`, `.env` | May expose secrets |
| Security-critical code | Auth logic, encryption, access control, input validation | Vulnerability risk from AI-generated code |
| Publishing / sending | `npm publish`, sending emails, posting to APIs, creating PRs | Irreversible external effects |
| Database writes | `INSERT`, `UPDATE`, migrations | Modifies persistent state |

## Tier 3 — Prohibited

Operations Claude must never execute, even if asked. The user must perform these manually.

| Category | Examples | Why Prohibited |
|----------|----------|---------------|
| Destructive filesystem | `rm -rf`, `find -delete`, emptying trash | Data loss, irreversible |
| Force push to shared branches | `git push --force origin main` | Destroys team history |
| Production deployment | `[pm] deploy`, `vercel --prod`, `aws deploy` | Unreviewed production changes |
| Credential handling | Entering passwords, API keys, tokens into forms or files | Secret exposure |
| Account operations | Creating/deleting accounts, changing access permissions | Identity and access risk |
| Database destructive ops | `DROP TABLE`, `DELETE FROM` without WHERE, `TRUNCATE` | Catastrophic data loss |
| System modification | `sudo`, `chmod 777`, modifying `/etc/`, system package installs | System integrity |
| Secret exposure | Logging secrets, committing `.env`, embedding keys in code | Credential leak |

---

## Classifying New Commands

When you encounter a command not listed above, use this decision table:

| Question | If Yes | If No |
|----------|--------|-------|
| Does it only read data with no side effects? | **Tier 1** | Continue ↓ |
| Does it modify files? | **Tier 2** (also check Rule 5 for scope) | Continue ↓ |
| Does it install packages or dependencies? | **Tier 2** | Continue ↓ |
| Does it touch the network (API calls, downloads)? | **Tier 2** | Continue ↓ |
| Does it start a process or service? | **Tier 2** | Continue ↓ |
| Is it destructive or irreversible? | **Tier 3** | Continue ↓ |
| Does it handle secrets or credentials? | **Tier 3** | Continue ↓ |
| Does it affect production systems? | **Tier 3** | Continue ↓ |
| None of the above? | **Tier 2** (default to confirmation) | — |

**When in doubt, default to Tier 2.** It's cheaper to confirm than to recover from an unintended action.

---

## Step-by-Step: Implementing Your Policy

### Step 1: Review Your Project's Risk Profile

| Project Characteristic | Policy Implication |
|-----------------------|-------------------|
| Handles user data / PII | Strict Tier 2 for all data operations |
| Has CI/CD pipelines | Tier 3 for any deployment command |
| Uses external APIs with costs | Tier 2 for all network requests |
| Multiple developers | Commit `.claude/settings.json` for shared policy |
| Solo / local only | `.claude/settings.local.json` is sufficient |

### Step 2: Configure Claude Code Permissions

Claude Code reads permission rules from two files:

- **`.claude/settings.json`** — team-shared policy (commit to repo)
- **`.claude/settings.local.json`** — personal overrides (gitignored)

Both use the same format with `permissions.allow` and `permissions.deny` arrays. Each entry specifies a **tool name** and a **pattern**:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status*)",
      "Bash(git log*)",
      "Bash(git diff*)",
      "Bash(git branch*)",
      "Bash([pm] typecheck*)",
      "Bash([pm] lint*)",
      "Bash([pm] test*)",
      "Bash([pm] build*)",
      "Read(*)"
    ],
    "deny": [
      "Bash(rm -rf*)",
      "Bash(git push --force*)",
      "Bash(git push -f*)",
      "Bash(sudo *)"
    ]
  }
}
```

<!-- Replace [pm] with your package manager -->

**How this maps to tiers:**

| Settings Array | Tier | Behavior |
|---------------|------|----------|
| `permissions.allow` | Tier 1 | Matched commands run without prompting |
| _(not listed)_ | Tier 2 | Commands not in allow or deny trigger a confirmation prompt |
| `permissions.deny` | Tier 3 | Matched commands are always blocked |

**Scope and limitations:**
- Patterns use glob matching (e.g., `Bash(git status*)` matches `git status`, `git status -u`, etc.)
- Entries are tool-scoped — `Bash(...)`, `Read(...)`, `Edit(...)`, `Write(...)`
- The `deny` list takes precedence over `allow` if a command matches both
- This enforces Tier 1 and Tier 3 at the tool level. Tier 2 is the implicit default for everything else

**Important:** Since `.claude/*` is typically gitignored, you need to explicitly commit the shared settings file:
```bash
git add -f .claude/settings.json
```

### Step 3: Enforce Tier 3 with Hooks

Claude Code supports hooks — shell commands that run before or after tool use. Use a `PreToolUse` hook to hard-block Tier 3 commands even if they bypass the settings file.

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'BLOCKED_PATTERNS=\"rm -rf|git push --force|git push -f|sudo |DROP TABLE|TRUNCATE|DELETE FROM .* WHERE 1|chmod 777|vercel --prod\"; CMD=\"$CLAUDE_TOOL_INPUT\"; if echo \"$CMD\" | grep -qiE \"$BLOCKED_PATTERNS\"; then echo \"BLOCKED: This command matches a Tier 3 prohibited pattern.\" >&2; exit 2; fi'"
          }
        ]
      }
    ]
  }
}
```

**How it works:**
- The hook runs before every `Bash` tool invocation
- It checks the command (`$CLAUDE_TOOL_INPUT`) against blocked patterns
- Exit code `2` blocks the tool and shows the error message to the user
- Exit code `0` allows the tool to proceed

Customize `BLOCKED_PATTERNS` to match your project's Tier 3 list.

**Caveat:** This hook uses simple grep pattern matching, which is susceptible to the same obfuscation techniques the guide warns about (base64 encoding, subshells, quote insertion). Treat hooks as a **defense-in-depth layer**, not a foolproof gate. The `permissions.deny` array in settings is the primary enforcement mechanism — hooks catch what slips through.

### Step 4: Communicate Policy to Your Team

- **Commit** `.claude/settings.json` so all developers share the same Tier 1/3 definitions
- **Reference** this policy from your project's CLAUDE.md (add to Reference Docs section)
- **Personal overrides** go in `.claude/settings.local.json` (gitignored)
- **Review** the policy when adding new tools, services, or deployment targets
- **Align with Rule 5** — review your feature boundary template (`docs/templates/FEATURE-CLAUDE.md`) alongside the command policy to ensure file-scope and operation-scope rules are consistent

---

## Customizing Tiers Per-Project

Teams often need to promote or demote specific commands. Add this table to your project's CLAUDE.md to document overrides:

```markdown
## Command Policy Overrides

| Command | Default Tier | Project Tier | Reason |
|---------|-------------|-------------|--------|
| `npm install` (existing deps) | 2 | 1 | Vetted dependency list in package.json |
| `git commit` | 2 | 1 | Pre-commit hooks enforce quality gates |
| `git push` | 2 | 1 | CI pipeline validates before merge |
| `docker compose up` | 2 | 3 | No containers in this project |
```

**Guidelines for overrides:**
- **Promoting to Tier 1:** Only when automated guardrails exist (pre-commit hooks, CI checks, lockfiles)
- **Demoting to Tier 3:** When a command category has no valid use case in your project
- **Document the reason** — future team members need to understand why

---

## How This Connects to Existing Rules

| CLAUDE.md Rule | Command Policy Connection |
|---------------|--------------------------|
| Rule 1: Secret Protection | Tier 3 prohibits committing secrets, logging tokens. Tier 2 for `.env` file access |
| Rule 2: Test & Review | Tier 1 auto-approves test/lint/typecheck for frictionless quality checks |
| Rule 3: Error Logging | Tier 1 for logger usage within feature scope |
| Rule 4: Update ARCHITECTURE.md | Tier 2 for ARCHITECTURE.md edits (shared file, requires confirmation) |
| Rule 5: Feature Boundary | Orthogonal — Rule 5 controls file scope, Command Policy controls operation scope |

---

## Best Practices

- **Start restrictive, expand deliberately** — promote commands to Tier 1 only after trust is established with automated guardrails
- **Allowlist, never denylist** — define what's safe, not what's dangerous. Denylists have infinite bypass vectors
- **Review quarterly** — as your project adds services, deployment targets, or team members, tiers need updating
- **Log Tier 2 confirmations** — track which operations Claude asks about most to identify candidates for Tier 1 promotion
- **Different policies per environment** — local development can be more permissive than CI or production-adjacent environments
- **Team agreement** — the shared `.claude/settings.json` should be a team decision, not one person's preference
- **Default to Tier 2** — when a new command appears that isn't classified, confirmation is always the safer default

---

## Reference

- Settings file: `.claude/settings.json` (team) / `.claude/settings.local.json` (personal)
- Feature boundary template: `docs/templates/FEATURE-CLAUDE.md`
- CLAUDE.md Rule 5: Feature Boundary
- Decision guide: `docs/project-setup-guide.md`
