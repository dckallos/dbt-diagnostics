#!/usr/bin/env bash
# Print a read-only live issue plus local-checkout context packet.

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

if [ "$#" -eq 0 ] && codex_is_git_checkout; then
  inferred="$(codex_branch_issue_number)"
  if [ -n "$inferred" ]; then
    set -- "$inferred"
  fi
fi

export CODEX_REPO_ROOT
exec "$python_path" .codex/scripts/task_context.py "$@"
