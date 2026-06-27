#!/usr/bin/env bash
# Stable command surface for Codex app actions and local terminal use.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

usage() {
  cat <<'USAGE'
usage: bash .codex/bin/action.sh <action> [arguments]

Actions:
  setup          Create or refresh the credential-free worktree environment
  context [N]    Print live issue N plus local context; infer N from the branch
  doctor         Verify local readiness without changing the checkout
  check          Run the normal credential-free implementation gate
  compile        Byte-compile repository-owned Python
  fast           Run tests except live and chaos tiers
  offline        Run every credential-free test, including chaos
  full           Run the repository's exact pytest -q suite
  unit           Run tests marked unit
  last-failed    Re-run the last credential-free pytest failures
  compat         Run the local compatibility schema gate
  audit          Run the read-only issue governance/readiness audit
  frontier MODE Select the read-only audit or implementation frontier
  project-plan   Emit the read-only advisory Project plan
  package        Build, inspect, install, and smoke-test wheel and sdist
  help           Show this message
USAGE
}

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"

action="${1:-help}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$action" in
  setup)
    exec bash .codex/bin/setup.sh "$@"
    ;;
  context)
    exec bash .codex/bin/task-context.sh "$@"
    ;;
  doctor)
    exec bash .codex/bin/doctor.sh "$@"
    ;;
  check|preflight)
    exec bash .codex/bin/check.sh "$@"
    ;;
  compile)
    exec bash .codex/bin/compile.sh "$@"
    ;;
  fast|offline|full|unit|last-failed)
    exec bash .codex/bin/test.sh "$action" "$@"
    ;;
  compat)
    exec bash .codex/bin/compat.sh "$@"
    ;;
  audit)
    exec bash .codex/bin/triage-audit.sh "$@"
    ;;
  frontier)
    exec bash .codex/bin/triage-frontier.sh "$@"
    ;;
  project-plan)
    exec bash .codex/bin/triage-project-plan.sh "$@"
    ;;
  package)
    exec bash .codex/bin/package.sh "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    codex_die "unknown action: ${action}"
    ;;
esac
