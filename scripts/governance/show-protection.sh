#!/usr/bin/env bash
# Show current branch protection for a branch (the "determine current state" step).
# Usage: ./show-protection.sh <branch>
# Env:   REPO=owner/name (default dckallos/dbt-diagnostics)
set -euo pipefail

REPO="${REPO:-dckallos/dbt-diagnostics}"
branch="${1:-}"
if [ -z "$branch" ]; then
  echo "usage: $0 <branch>" >&2
  exit 2
fi

command -v gh >/dev/null 2>&1 || {
  echo "gh not found; install GitHub CLI and run 'gh auth login'" >&2
  exit 1
}

if ! gh api "repos/${REPO}/branches/${branch}/protection" 2>/dev/null; then
  echo "no branch protection on ${REPO}@${branch} (or insufficient access)." >&2
  exit 0
fi
