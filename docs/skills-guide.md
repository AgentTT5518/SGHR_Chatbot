# Custom Skills Guide

A guide to creating reusable Claude Code slash commands for your project.

---

## What Are Custom Skills?

Skills are markdown files in `.claude/commands/` that define workflows Claude follows when you type `/[skill-name]`. They turn multi-step, repetitive Claude interactions into single commands that any team member can run consistently.

- **Project skills:** `.claude/commands/` — available in this project only
- **Personal skills:** `~/.claude/commands/` — available across all your projects

The filename becomes the command: `review.md` becomes `/review`.

## When to Create a Skill

| Signal | Example | Skill Idea |
|--------|---------|------------|
| You repeat the same prompt 3+ times | "Generate a migration for this schema change" | `/migrate` |
| A workflow has multiple steps to remember | Code review → lint → test → secret scan | `/review` |
| You want consistent output format | API endpoint scaffolding with tests | `/scaffold-endpoint` |
| Team members do the same task differently | Feature setup with logger and boundary file | `/new-feature` |
| You want guardrails on a risky operation | Deploy with pre-checks | `/deploy-check` |

**Rule of thumb:** If you've explained the same workflow to Claude more than twice, it should be a skill.

## Anatomy of a Skill File

A skill file has 6 sections:

| Section | Required? | Purpose |
|---------|-----------|---------|
| Description | Yes | 1-sentence summary — Claude reads this to understand intent |
| Trigger | Yes | When and how the skill activates |
| Steps | Yes | Ordered actions Claude should take |
| Inputs | If needed | Arguments the user provides |
| Output | Yes | What Claude produces — format, location, content |
| Rules | Yes | Constraints and guardrails |
| Examples | Recommended | Input → output pairs for Claude to pattern-match |

See `docs/templates/skill-template.md` for the full annotated template.

---

## Step-by-Step: Creating Your First Skill

### Step 1: Identify the Workflow

Look for patterns in your Claude Code usage:
- What prompts do you type repeatedly?
- What multi-step tasks do you walk Claude through?
- Where does output quality vary when different people run the same task?

Write down the steps in plain language before creating the file.

### Step 2: Create the File

```bash
mkdir -p .claude/commands
cp docs/templates/skill-template.md .claude/commands/[name].md
```

Replace `[name]` with a short, descriptive kebab-case name (e.g., `new-feature`, `review-pr`, `scaffold-api`).

### Step 3: Write the Instructions

Open `.claude/commands/[name].md` and fill in each section.

**Tips for writing clear skill instructions:**
- Be specific about file paths — use `src/features/[name]/` not "the feature folder"
- Specify output format explicitly — "Return a markdown table" not "summarize the results"
- Reference project files — "Follow CLAUDE.md Rule 1 (secret scan)" not "check for secrets"
- Include examples — Claude pattern-matches against examples better than abstract rules
- Set boundaries — "Only modify files in `.claude/commands/`" prevents scope creep

### Step 4: Test the Skill

Run `/[name]` in Claude Code and observe:
- Does Claude follow each step in order?
- Is the output in the expected format?
- Does it handle edge cases (missing files, empty input)?
- Does it respect the rules you set?

### Step 5: Iterate

Common refinements after first test:
- Add missing steps Claude skipped or guessed at
- Tighten output format if Claude improvised
- Add edge case rules if Claude made assumptions
- Include more examples if output quality varies

---

## Best Practices

- **One workflow per skill** — a skill that does 5 things is 5 skills
- **Include example outputs** — Claude follows examples more reliably than abstract instructions
- **Reference project files** — point to CLAUDE.md rules, templates, and conventions
- **Version control skills** — commit `.claude/commands/` alongside your code
- **Document in README** — list available skills so team members know what's available
- **Start simple** — a 10-line skill that works beats a 100-line skill that's fragile

## Common Skill Patterns

| Pattern | Use When | Structure |
|---------|----------|-----------|
| **Scaffolder** | Creating boilerplate for new [things] | Steps that create files + fill templates |
| **Reviewer** | Checking code/content against criteria | Checklist → read files → report pass/fail |
| **Generator** | Producing content from inputs | Input list → transformation rules → output format |
| **Investigator** | Analyzing codebase to answer questions | Search strategy → read files → structured summary |
| **Workflow** | Multi-step process with decision points | Ordered steps with conditional branches |

---

## Reference

- Template: `docs/templates/skill-template.md`
- Skills directory: `.claude/commands/`
- Decision guide: `docs/project-setup-guide.md`
