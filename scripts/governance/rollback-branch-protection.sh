#!/usr/bin/env bash
#
# rollback-branch-protection.sh
#
# Restore the before-state captured by export-branch-protection.sh. For each
# covered branch:
#   - if exports/<branch>.json is "null", DELETE protection (the branch was
#     unprotected before we applied the policy);
#   - otherwise re-apply that saved config via PUT.
#
# Run export-branch-protection.sh (or apply-branch-protection.sh, which exports
# first) at least once before relying on this.
#
# Usage:
#   ./scripts/governance/rollback-branch-protection.sh [--dry-run] [--branch <name>]
#
# Requires: gh (authenticated, admin on the repo).

set -euo pipefail

REPO="dckallos/dbt-diagnostics"
BRANCHES="donkey-kong-sandbox main"
DRY_RUN=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${HERE}/exports"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --branch) BRANCHES="$2"; shift 2 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

for b in ${BRANCHES}; do
  snap="${OUT_DIR}/${b}.json"
  if [ ! -f "${snap}" ]; then
    echo "no snapshot for ${b} at ${snap}; run export-branch-protection.sh first" >&2
    exit 1
  fi

  if [ "$(tr -d '[:space:]' < "${snap}")" = "null" ]; then
    if [ "${DRY_RUN}" -eq 1 ]; then
      echo "== DRY RUN: ${b} == DELETE protection (was unprotected)"
      continue
    fi
    echo "deleting protection on ${b} (restoring unprotected before-state)"
    gh api --method DELETE "repos/${REPO}/branches/${b}/protection" > /dev/null || true
    echo "  deleted."
  else
    if [ "${DRY_RUN}" -eq 1 ]; then
      echo "== DRY RUN: ${b} == PUT restore from ${snap}"
      cat "${snap}"
      echo
      continue
    fi
    echo "restoring saved protection on ${b} from ${snap}"
    gh api \
      --method PUT \
      -H "Accept: application/vnd.github+json" \
      "repos/${REPO}/branches/${b}/protection" \
      --input "${snap}" > /dev/null
    echo "  restored."
  fi
done

echo "done."
