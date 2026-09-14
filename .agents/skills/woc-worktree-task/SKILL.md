---
name: woc-worktree-task
description: >-
  Use this skill when handling any development task (bug fix, feature, refactor, etc.)
  that should NOT be done directly on the release/china branch. This skill creates an
  isolated git worktree, runs the task in a sub-agent within that worktree, and merges
  the result back — preventing conflicts and file loss on the shared mainline branch.
  Activate when the user requests isolated task execution, worktree-based development,
  or when the task involves risky changes that could disrupt the current working tree.
---

# Worktree-Isolated Task Execution

Execute development tasks in isolated git worktrees to protect the primary
**release/china** branch from conflicts, half-finished changes, and accidental file
loss.

## Why Use This Skill

This project has a single mainline branch (**release/china**). Making all changes
directly on it causes:

- Merge conflicts between concurrent tasks
- Accidental file overwrites or deletions
- Difficulty separating unrelated changes
- Risk of breaking the working tree mid-task

This skill solves these problems by:

1. Creating a separate git worktree for each task
2. Running all changes inside that worktree (via sub-agent)
3. Committing work on a dedicated `task/<name>` branch
4. Merging back to release/china only after verification

## Workflow

### Step 1 — Determine Task Name and Scope

Ask the user (if not already clear) for:
- A short, descriptive **task name** (e.g., `fix-login-timeout`, `add-npc-dialog`)
- The **base branch** to fork from (default: `release/china`)
- A clear description of what needs to be done

### Step 2 — Create the Worktree

Run the worktree creation script:

```bash
bash .agents/skills/woc-worktree-task/scripts/worktree.sh create <task-name> [base-branch]
```

This will:
- Create `.worktrees/<task-name>/` as an isolated checkout
- Create a new branch `task/<task-name>` based on the base branch
- Symlink `node_modules` and `.env` from the repo root to avoid re-installation

### Step 3 — Execute the Task

**All code changes must be made inside the worktree directory**, NOT in the main repo
root. The worktree path is:

```
.worktrees/<task-name>/
```

To get the absolute path programmatically:

```bash
bash .agents/skills/woc-worktree-task/scripts/worktree.sh path <task-name>
```

**Important rules for the sub-agent / task execution:**

- `cd` into the worktree directory before making any edits
- All file paths in tool calls must point to files within `.worktrees/<task-name>/`
- Do NOT modify files in the main repo root
- Commit frequently with meaningful messages on the `task/<task-name>` branch
- Run builds and tests from within the worktree directory

### Step 4 — Verify the Work

Before merging, verify that the changes are correct:

1. Review the diff:
   ```bash
   cd .worktrees/<task-name>
   git diff release/china...task/<task-name> --stat
   git log release/china..task/<task-name> --oneline
   ```

2. Run relevant tests or builds if applicable:
   ```bash
   cd .worktrees/<task-name>
   pnpm run build  # or relevant test/lint commands
   ```

3. Show the user a summary of changes and ask for approval before merging.

### Step 5 — Merge Back to Mainline

Once the user approves, merge the task branch into the target branch:

```bash
bash .agents/skills/woc-worktree-task/scripts/worktree.sh merge <task-name> [target-branch]
```

This performs a `--no-ff` merge to preserve the task branch history.

### Step 6 — Cleanup

After a successful merge, remove the worktree:

```bash
bash .agents/skills/woc-worktree-task/scripts/worktree.sh remove <task-name>
```

Add `--keep-branch` if you want to preserve the task branch for reference:

```bash
bash .agents/skills/woc-worktree-task/scripts/worktree.sh remove <task-name> --keep-branch
```

## Quick Reference: Available Script Commands

| Command | Description |
|---------|-------------|
| `create <name> [base]` | Create worktree + branch |
| `list` | List all active worktrees |
| `path <name>` | Print worktree absolute path |
| `merge <name> [target]` | Merge task branch into target |
| `remove <name> [--keep-branch]` | Remove worktree and optionally keep branch |

## Safety Rules

1. **Never** edit files directly on `release/china` when a worktree task is active
2. **Always** commit work in the worktree before attempting a merge
3. **Always** get user approval before merging back to mainline
4. If a merge conflict occurs, resolve it in the worktree or ask the user for guidance
5. If the user cancels a task, clean up with `remove` to avoid stale worktrees

## Troubleshooting

- **Worktree already exists**: A previous task with the same name was not cleaned up.
  Run `remove <name>` first, then `create <name>` again.
- **Branch already exists**: The script will attach to the existing branch. This is
  safe if the branch was from a previous incomplete task.
- **node_modules issues**: The symlink may break if the main repo's dependencies change.
  Run `pnpm install` inside the worktree if needed.
