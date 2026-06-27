#!/usr/bin/env bash
# Build, inspect, and smoke-test one wheel and one source distribution.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/${CODEX_POLICY_ENVIRONMENT_NAME}-package.XXXXXX")"
dist_dir="${tmp_dir}/dist"
smoke_venv="${tmp_dir}/smoke-venv"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT HUP INT TERM

codex_header "Build wheel and source distribution"
codex_run "$python_path" -m build --outdir "$dist_dir" "$CODEX_REPO_ROOT"

codex_header "Validate package metadata"
codex_run "$python_path" -m twine check "$dist_dir"/*

codex_header "Audit package contents"
codex_run "$python_path" .codex/scripts/check_dist.py "$dist_dir"

wheel=""
for candidate in "$dist_dir"/*.whl; do
  [ -f "$candidate" ] || continue
  wheel="$candidate"
  break
done
[ -n "$wheel" ] || codex_die "build produced no wheel"

codex_header "Installed-wheel smoke test"
codex_run "$python_path" -m venv "$smoke_venv"
codex_run "$smoke_venv/bin/python" -m pip install --quiet "$wheel"
commands="$("$python_path" scripts/triage/repo_config.py cli-commands)" \
  || codex_die "failed to load CLI smoke policy"
if [ -z "$commands" ]; then
  codex_note "SKIP: no package CLI smoke commands configured."
else
  while IFS= read -r command_line; do
    [ -n "$command_line" ] || continue
    eval "set -- $command_line"
    [ "$#" -ge 1 ] || codex_die "empty CLI smoke command"
    command_name="$1"
    shift
    codex_run "$smoke_venv/bin/$command_name" "$@" >/dev/null
  done <<EOF
$commands
EOF
fi
if [ -n "$CODEX_POLICY_CLI_DISTRIBUTION_NAME" ]; then
  codex_run "$smoke_venv/bin/python" -c \
    "import importlib.metadata as m; print('installed version:', m.version('$CODEX_POLICY_CLI_DISTRIBUTION_NAME'))"
else
  codex_note "SKIP: no package distribution name configured."
fi

codex_note "Package check passed."
