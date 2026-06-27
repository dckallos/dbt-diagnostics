#!/usr/bin/env bash
# Run repository-specific Codex semantic quality gates.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

codex_run "$python_path" .codex/scripts/codex_quality.py "$@"
