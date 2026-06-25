#!/usr/bin/env bash
# Run named pytest tiers with the worktree virtual environment.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

mode="${1:-fast}"
case "$mode" in
  fast)
    shift || true
    args=(-q -m "not live and not chaos" "$@")
    ;;
  offline)
    shift || true
    args=(-q -m "not live" "$@")
    ;;
  full)
    shift || true
    args=(-q "$@")
    ;;
  unit|contract|property|robustness|e2e|chaos|live)
    shift || true
    args=(-q -m "$mode" "$@")
    ;;
  last-failed)
    shift || true
    args=(-q --last-failed -m "not live" "$@")
    ;;
  help|-h|--help)
    cat <<'USAGE'
usage: bash .codex/bin/test.sh [mode] [pytest arguments]

modes:
  fast         Credential-free suite excluding high-volume chaos tests (default)
  offline      Every credential-free test, including chaos
  full         Exact repository suite: pytest -q
  unit         Tests marked unit
  contract     Tests marked contract
  property     Tests marked property
  robustness   Tests marked robustness
  e2e          Tests marked e2e
  chaos        Tests marked chaos
  live         Tests marked live; credentials and explicit approval are external
  last-failed  Re-run previous credential-free failures

An unrecognized first argument is passed directly to pytest, supporting focused
commands such as:

  bash .codex/bin/test.sh -q dbt_diagnostics/tests/test_runtime_error.py
USAGE
    exit 0
    ;;
  *)
    args=("$mode" "$@")
    ;;
esac

codex_header "Pytest"
codex_run "$python_path" -m pytest "${args[@]}"
