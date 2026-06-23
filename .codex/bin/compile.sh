#!/usr/bin/env bash
# Compile every repository-owned Python module without running application code.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

codex_header "Compile Python"
codex_run "$python_path" -m compileall -q -f \
  dbt_diagnostics scripts .codex/scripts .codex/tests
