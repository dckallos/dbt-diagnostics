#!/usr/bin/env bash
#
# export-branch-protection.sh
#
# Snapshot the CURRENT classic branch-protection config for each covered branch
# into scripts/governance/exports/<branch>.json. These snapshots are the
# committed before-state and the input that rollback-branch-protection.sh
# restores. A branch with no protection is recorded as a literal "null" file so
# rollback knows to delete protection rather than re-apply a config.
#
# Usage:
#   ./scripts/governance/export-branch-protection.sh [--branch <name>]
#
# Requires: gh (authenticated, admin on the repo), jq.

set -euo pipefail

REPO="dckallos/dbt-diagnostics"
BRANCHES="donkey-kong-sandbox main"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${HERE}/exports"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --branch) BRANCHES="$2"; shift 2 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${OUT_DIR}"

for b in ${BRANCHES}; do
  out="${OUT_DIR}/${b}.json"
  echo "exporting protection for ${b} -> ${out}"
  if gh api "repos/${REPO}/branches/${b}/protection" > "${out}.tmp" 2>/dev/null; then
    jq -S . "${out}.tmp" > "${out}"
    rm -f "${out}.tmp"
  else
    # No protection set (404). Record null so rollback deletes protection.
    echo "null" > "${out}"
    rm -f "${out}.tmp"
    echo "  (no protection currently set; recorded as null)"
  fi
done

echo "done."
