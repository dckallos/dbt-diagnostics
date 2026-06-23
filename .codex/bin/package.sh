#!/usr/bin/env bash
# Build, inspect, and smoke-test one wheel and one source distribution.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/dbt-diagnostics-package.XXXXXX")"
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
codex_run "$smoke_venv/bin/dbt-diagnostics" --help >/dev/null
codex_run "$smoke_venv/bin/python" -c \
  'import importlib.metadata as m; print("installed version:", m.version("dbt-diagnostics"))'

codex_note "Package check passed."
