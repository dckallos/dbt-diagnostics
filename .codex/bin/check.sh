#!/usr/bin/env bash
# Fast, credential-free gate for normal implementation work.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

codex_header "Codex command surface"
for script in .codex/bin/*.sh; do
  codex_run bash -n "$script"
done
codex_run "$python_path" -m py_compile .codex/scripts/*.py .codex/tests/*.py
codex_run "$python_path" -m pytest -q .codex/tests
codex_run "$python_path" .codex/scripts/doctor.py --config-only
codex_run "$python_path" -m pip check

if codex_is_git_checkout; then
  codex_header "Git hygiene"
  codex_run git diff --check
  codex_run git diff --cached --check
  codex_run "$python_path" .codex/scripts/check_ascii.py
  if [ -f scripts/governance/check_no_attribution.sh ]; then
    codex_run bash scripts/governance/check_no_attribution.sh
  fi
else
  codex_note "SKIP: git history checks require a real git checkout."
  codex_run "$python_path" .codex/scripts/check_ascii.py \
    --path .codex --path AGENTS.md
fi

codex_header "Compile"
codex_run "$python_path" -m compileall -q -f \
  dbt_diagnostics scripts .codex/scripts .codex/tests

codex_header "Tests (normal offline gate)"
codex_run "$python_path" -m pytest -q -m "not live and not chaos"

codex_run bash .codex/bin/compat.sh
