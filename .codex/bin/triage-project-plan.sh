#!/usr/bin/env bash
# Emit the read-only advisory GitHub Project plan.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"
tool="scripts/triage/triage.py"

[ -f "$tool" ] || codex_die "missing governance tool: $tool"

codex_header "Project plan (read-only)"
exec "$python_path" "$tool" project-plan "$@"
