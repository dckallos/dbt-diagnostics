#!/usr/bin/env bash
# Run the issue-governance audit without applying metadata changes.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"
tool="scripts/triage/triage.py"

if [ ! -f "$tool" ]; then
  cat >&2 <<'MESSAGE'
ERROR: scripts/triage/triage.py does not exist in this checkout.

The Codex action is wired now so its command stays stable. The governance
planner/auditor is a separate scoped deliverable and must not be replaced by a
fake successful audit. Once that tool lands, this action will run exactly:

  python scripts/triage/triage.py audit
MESSAGE
  exit 2
fi

codex_header "Issue metadata audit (read-only)"
codex_run "$python_path" "$tool" audit "$@"
