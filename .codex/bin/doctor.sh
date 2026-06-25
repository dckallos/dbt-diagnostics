#!/usr/bin/env bash
# Report whether the local checkout is ready for Codex work.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"

if python_path="$(codex_venv_python)"; then
  :
else
  python_path="$(codex_find_bootstrap_python)" \
    || codex_die "Python 3.11 or newer is required"
fi

export CODEX_REPO_ROOT CODEX_VENV_DIR
exec "$python_path" .codex/scripts/doctor.py "$@"
