#!/usr/bin/env bash
# ==============================================================================
# Worktree Isolation Manager for World of ClaudeCraft
# Manages isolated git worktrees under .worktrees/ for subagent task execution.
# Protects the primary branch (release/china) and prevents file loss/conflicts.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
cd "$REPO_ROOT" 
WORKTREES_DIR="${REPO_ROOT}/.worktrees"
DEFAULT_BASE_BRANCH="release/china"

usage() {
  cat << USAGE
Usage: $0 <command> [arguments]

Commands:
  create <name> [base-branch]  Create a new worktree at .worktrees/<name> based on base-branch (default: ${DEFAULT_BASE_BRANCH})
  list                         List active git worktrees
  path <name>                  Print the absolute path to a worktree
  merge <name> [target-branch] Merge task branch into target branch (default: ${DEFAULT_BASE_BRANCH})
  remove <name> [--keep-branch] Remove a worktree and prune metadata

Examples:
  $0 create fix-login-timeout release/china
  $0 list
  $0 merge fix-login-timeout
  $0 remove fix-login-timeout
USAGE
  exit 1
}

cmd_create() {
  local name="${1:-}"
  local base="${2:-$DEFAULT_BASE_BRANCH}"

  if [ -z "$name" ]; then
    echo "Error: Worktree task name required." >&2
    usage
  fi

  local target_dir="${WORKTREES_DIR}/${name}"
  local branch_name="task/${name}"

  if [ -d "$target_dir" ]; then
    echo "Error: Target directory already exists: $target_dir" >&2
    exit 1
  fi

  # Ensure base branch or commit exists
  if ! git rev-parse --verify "$base" >/dev/null 2>&1; then
    echo "Error: Base branch or commit '$base' does not exist." >&2
    exit 1
  fi

  mkdir -p "$WORKTREES_DIR"

  echo "==> Creating git worktree at '$target_dir' on branch '$branch_name' (base: $base)..."
  if git rev-parse --verify "$branch_name" >/dev/null 2>&1; then
    git worktree add "$target_dir" "$branch_name"
  else
    git worktree add -b "$branch_name" "$target_dir" "$base"
  fi

  # Setup fast dependencies via symlink if node_modules exists in root
  if [ -d "${REPO_ROOT}/node_modules" ] && [ ! -e "${target_dir}/node_modules" ]; then
    echo "==> Symlinking node_modules from repo root to avoid re-install..."
    ln -s "${REPO_ROOT}/node_modules" "${target_dir}/node_modules"
  fi

  # Symlink .env if present in root
  if [ -f "${REPO_ROOT}/.env" ] && [ ! -e "${target_dir}/.env" ]; then
    echo "==> Linking .env for environment configuration..."
    ln -s "${REPO_ROOT}/.env" "${target_dir}/.env"
  fi

  echo "==> Worktree successfully initialized!"
  echo "    Path:   $target_dir"
  echo "    Branch: $branch_name"
}

cmd_list() {
  git worktree list
}

cmd_path() {
  local name="${1:-}"
  if [ -z "$name" ]; then
    echo "Error: Task name required." >&2
    usage
  fi
  echo "${WORKTREES_DIR}/${name}"
}

cmd_merge() {
  local name="${1:-}"
  local target="${2:-$DEFAULT_BASE_BRANCH}"

  if [ -z "$name" ]; then
    echo "Error: Task name required." >&2
    usage
  fi

  local branch_name="task/${name}"

  if ! git rev-parse --verify "$branch_name" >/dev/null 2>&1; then
    echo "Error: Branch '$branch_name' does not exist." >&2
    exit 1
  fi

  echo "==> Merging '$branch_name' into '$target'..."
  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"

  if [ "$current_branch" != "$target" ]; then
    git checkout "$target"
  fi

  git merge --no-ff -m "Merge branch '$branch_name' into $target" "$branch_name"
  echo "==> Successfully merged '$branch_name' into '$target'."
}

cmd_remove() {
  local name="${1:-}"
  local keep_branch="${2:-}"

  if [ -z "$name" ]; then
    echo "Error: Worktree task name required." >&2
    usage
  fi

  local target_dir="${WORKTREES_DIR}/${name}"
  local branch_name="task/${name}"

  if [ -d "$target_dir" ]; then
    echo "==> Removing worktree: $target_dir..."
    git worktree remove --force "$target_dir" 2>/dev/null || rm -rf "$target_dir"
    git worktree prune
  else
    echo "Warning: Worktree directory '$target_dir' not found. Pruning git worktree metadata..."
    git worktree prune
  fi

  if [ "$keep_branch" != "--keep-branch" ]; then
    if git rev-parse --verify "$branch_name" >/dev/null 2>&1; then
      echo "==> Deleting local branch '$branch_name'..."
      git branch -D "$branch_name" || true
    fi
  fi

  echo "==> Cleanup completed for task '$name'."
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  create) cmd_create "$@" ;;
  list)   cmd_list ;;
  path)   cmd_path "$@" ;;
  merge)  cmd_merge "$@" ;;
  remove) cmd_remove "$@" ;;
  *)      usage ;;
esac
