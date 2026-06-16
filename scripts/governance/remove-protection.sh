#!/usr/bin/env bash
# Remove (roll back) all branch protection from a branch.
# Usage: ./remove-protection.sh <branch>
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

gh api --method DELETE "repos/${REPO}/branches/${branch}/protection"
echo "removed protection from ${REPO}@${branch}."
