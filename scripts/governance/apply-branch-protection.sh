#!/usr/bin/env bash
#
# apply-branch-protection.sh
#
# Apply the version-controlled classic branch-protection policy to each covered
# branch. The policy bodies live next to this script as
# policy.<branch>.json and are the single source of truth.
#
# This is idempotent: PUT .../protection replaces the entire protection config,
# so re-running converges to the committed policy. Before applying, the current
# state is exported to scripts/governance/exports/ so there is always a
# before-state to roll back to.
#
# Usage:
#   ./scripts/governance/apply-branch-protection.sh [--dry-run] [--branch <name>]
#
#   --dry-run   Print the target and JSON body for each branch; change nothing.
#   --branch    Apply to a single branch instead of all covered branches.
#
# Requires: gh (authenticated, admin on the repo). --dry-run also needs no auth.

set -euo pipefail

REPO="dckallos/dbt-diagnostics"
BRANCHES="donkey-kong-sandbox main"
DRY_RUN=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --branch) BRANCHES="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for b in ${BRANCHES}; do
  body="${HERE}/policy.${b}.json"
  if [ ! -f "${body}" ]; then
    echo "missing policy file: ${body}" >&2
    exit 1
  fi

  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "== DRY RUN: ${b} =="
    echo "PUT repos/${REPO}/branches/${b}/protection"
    cat "${body}"
    echo
    continue
  fi

  echo "exporting current state for ${b} before applying"
  "${HERE}/export-branch-protection.sh" --branch "${b}"

  echo "applying policy to ${b}"
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "repos/${REPO}/branches/${b}/protection" \
    --input "${body}" > /dev/null
  echo "  applied."
done

echo "done."
