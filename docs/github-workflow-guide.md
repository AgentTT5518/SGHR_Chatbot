# Feature Development Workflow

A step-by-step guide for developing features using Claude Code with git worktrees.

---

## Step 1: Create Worktree & Feature Branch

**You say:** "Create a worktree with feature branch named [name]"

**What happens:**
- A new folder is created (e.g. `../project-[name]`)
- A new branch is created (e.g. `feature/[name]`)
- The folder is a full copy of the project you can work in independently

---

## Step 2: Diagnose / Understand the Task

**You say:** Describe the bug or feature you want

**What happens:**
- AI reads through the relevant code files
- Identifies root causes (for bugs) or requirements (for features)
- Presents findings to you

---

## Step 3: Plan Before Implementing

**You say:** "Provide a plan before implementing"

**What happens:**
- AI writes a detailed plan listing every file that needs changing and why
- You review, give feedback, request changes
- You approve the plan before any code is written

---

## Step 4: Implement the Fixes/Features

**What happens after approval:**
- AI edits the code files in the worktree
- If shared code (`src/shared/`) needs changing, AI asks for boundary approval first
- All work stays in the worktree — main is untouched

---

## Step 5: Write Tests

**What happens:**
- AI writes automated tests that verify the changes work
- Tests cover both the "happy path" and edge cases
- Tests live in the `tests/` folder

---

## Step 6: Verify Everything Passes

**What happens:**
- `pnpm typecheck` — checks all code types are correct
- `pnpm lint` — checks code style and common mistakes
- `pnpm test` — runs all automated tests
- Secret scan — ensures no API keys are exposed
- Dev server starts and app loads without errors

---

## Step 7: Manual Testing

**You say:** "Start the dev server" (if not already running)

**What happens:**
- Dev server starts on localhost:5170 serving the worktree code
- **Important:** `.env.local` must be copied to the worktree (it's not tracked by git)
- You test the feature manually in your browser
- If something's wrong, go back to Step 4

---

## Step 8: Commit & Push

**You say:** "Commit the changes and push"

**What happens:**
- AI runs a secret scan (Rule 1)
- Stages all changed files
- Creates a commit with a descriptive message
- Pushes the feature branch to GitHub

---

## Step 9: Create Pull Request

**You say:** "Do a pull request"

**What happens:**
- AI creates a PR from `feature/[name]` → `main` on GitHub
- PR includes a summary of changes and a test checklist
- You receive the PR link
- CI runs automatically — typecheck, lint, test, and secret scan
- Merge is blocked until all CI checks pass

---

## Step 10: Review & Merge (You Do This on GitHub)

**You do:**
- Open the PR link in your browser
- Review the changes
- Click "Merge pull request"
- Click "Delete branch"

---

## Step 11: Pull Latest Main

**You say:** "Pull latest main"

**What happens:**
- Your local `main` gets updated with the merged changes
- Without this, your next worktree would be based on the old code

---

## Step 12: Close Worktree & Cleanup

**You say:** "Close worktree and cleanup"

**What happens:**
- Dev server is stopped
- Worktree folder is deleted
- Local feature branch is deleted
- `launch.json` is restored to point to main

---

## Quick Reference

| Step | What You Say |
|------|-------------|
| 1 | "Create a worktree with feature branch named [name]" |
| 2 | Describe the bug/feature |
| 3 | "Provide a plan before implementing" |
| 4 | Review plan, give feedback, approve |
| 5-6 | (AI does automatically) |
| 7 | "Start the dev server" → test on localhost:5170 |
| 8 | "Commit the changes and push" |
| 9 | "Do a pull request" |
| 10 | (You on GitHub: review, merge, delete branch) |
| 11-12 | "Pull latest main then close worktree and cleanup" |

---

## Things to Remember

- `.env.local` doesn't carry over to worktrees — AI will copy it when you start the dev server
- Boundary approval is needed before touching shared code (`src/shared/`)
- Tests must pass before committing — AI handles this automatically
- One worktree per task — don't mix multiple features in one branch
