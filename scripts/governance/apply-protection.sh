#!/usr/bin/env bash
# Apply branch protection to a branch from a version-controlled policy JSON.
# Usage: ./apply-protection.sh <branch> [policy.json] [--dry-run]
# Env:   REPO=owner/name (default dckallos/dbt-diagnostics)
set -euo pipefail

REPO="${REPO:-dckallos/dbt-diagnostics}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

branch="${1:-}"
if [ -z "$branch" ]; then
  echo "usage: $0 <branch> [policy.json] [--dry-run]" >&2
  exit 2
fi
shift

policy="${SCRIPT_DIR}/policies/${branch}.json"
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    *) policy="$arg" ;;
  esac
done

if [ ! -f "$policy" ]; then
  echo "policy file not found: $policy" >&2
  exit 1
fi

command -v gh >/dev/null 2>&1 || {
  echo "gh not found; install GitHub CLI and run 'gh auth login'" >&2
  exit 1
}

echo "repo:   $REPO"
echo "branch: $branch"
echo "policy: $policy"
echo "--- policy body ---"
cat "$policy"
echo "-------------------"

if [ "$dry_run" -eq 1 ]; then
  echo "[dry-run] not applying."
  exit 0
fi

gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  "repos/${REPO}/branches/${branch}/protection" \
  --input "$policy"

echo
echo "applied. current state:"
"${SCRIPT_DIR}/show-protection.sh" "$branch"
