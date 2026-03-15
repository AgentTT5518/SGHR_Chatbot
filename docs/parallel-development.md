# Parallel Development Guide

## Git Worktree Setup
```bash
# Create isolated workspaces per feature
git worktree add ../project-auth feature/auth
git worktree add ../project-payments feature/payments

# One Claude Code session per worktree — never share
# When done, clean up after merge
git worktree remove ../project-auth
```

## Rules

1. **Scope by feature, not by file.** Each person owns a vertical slice. If two people need the same file, one goes first, the other rebases.

2. **Small, frequent PRs.** The longer a branch lives, the worse the merge.

3. **Shared contracts first.** Agree on types/interfaces and merge to `main` before feature work.

4. **Lock critical shared resources.** Only one person modifies `src/app/` routes or migrations at a time.

5. **Rebase before PR:**
   ```bash
   git fetch origin && git rebase origin/main
   [pm] typecheck && [pm] lint && [pm] test
   ```

6. **One Claude Code session per worktree.** Never run two sessions in the same directory.

## How the Layers Work Together

| Layer | Prevents | Mechanism |
|-------|----------|-----------|
| Git worktrees | Physical file conflicts | Separate directories per branch |
| Feature CLAUDE.md (Rule 5) | AI editing wrong feature | Boundary alert + user approval |
| Shared contracts first | Integration mismatches | Types merged to main before features |
| Small PRs + rebase | Merge nightmares | Frequent integration |

## Multi-Developer Flow
```
Developer A                          Developer B
-----------                          -----------
git worktree add ../proj-auth        git worktree add ../proj-payments
cd ../proj-auth                      cd ../proj-payments
claude                               claude
  -- works in src/features/auth/       -- works in src/features/payments/
  -- asks before touching shared/      -- asks before touching shared/
git push -> PR to main               git push -> PR to main
  -- merge first                       -- rebase on updated main, then merge
git worktree remove ../proj-auth     git worktree remove ../proj-payments
```
