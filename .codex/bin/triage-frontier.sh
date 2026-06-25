#!/usr/bin/env bash
# Select the read-only audit or implementation frontier.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() {
  cat <<'USAGE'
usage: bash .codex/bin/triage-frontier.sh <audit|implement> [triage options]

Examples:
  bash .codex/bin/triage-frontier.sh audit --json
  bash .codex/bin/triage-frontier.sh implement --json \
    --snapshot output/triage/snapshot.json \
    --audit-file output/triage/audit.json
USAGE
}

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"
tool="scripts/triage/triage.py"

mode="${1:-}"
case "$mode" in
  audit|implement)
    shift
    ;;
  help|-h|--help|"")
    usage
    exit 0
    ;;
  *)
    usage >&2
    codex_die "frontier mode must be audit or implement"
    ;;
esac

[ -f "$tool" ] || codex_die "missing governance tool: $tool"

codex_header "${mode} frontier (read-only)"
exec "$python_path" "$tool" frontier --mode "$mode" "$@"
