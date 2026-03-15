# [Skill Name]
<!-- Copy this file to .claude/commands/[name].md -->
<!-- Replace all [placeholders] with actual values -->
<!-- The filename becomes the slash command: my-skill.md → /my-skill -->
<!-- DELETE these comments once you've customized the skill -->

[Description: 1 sentence — what this skill does when invoked]

## Trigger

When the user runs `/[name]`, do the following:

## Steps

1. [First action Claude should take]
2. [Second action]
3. [Continue as needed]

<!-- Tips for writing good steps:
  - Be specific about what Claude should read, create, or modify
  - Include file paths where applicable
  - Reference project files (CLAUDE.md rules, templates) when relevant
  - Specify output format if consistency matters
-->

## Inputs
<!-- List any information the skill needs from the user -->
<!-- These can be provided as arguments: /[name] [arg1] [arg2] -->

- [Input 1]: [description]
- [Input 2]: [description]

## Output
<!-- Describe what the skill produces when done -->

[What Claude should output or create — be specific about format, location, and content]

## Rules
<!-- Constraints and guardrails for this skill -->

- [Rule 1]
- [Rule 2]
- Never modify files outside the scope of this skill without asking
- Follow all CLAUDE.md mandatory rules (secret scan, testing, logging)

## Examples
<!-- Show expected input → output pairs so Claude can pattern-match -->

**Input:** `/[name] [example arguments]`

**Output:**
```
[Example of what Claude should produce]
```
