#!/usr/bin/env bash
# Mirror the repository's credential-free compatibility schema checks.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"
sentinel="dbt_diagnostics/fixtures/schemas/manifest/v12.json"

codex_header "Compatibility schema gate"

if [ ! -f "$sentinel" ]; then
  codex_note "SKIP: the committed first-party schema cache is not present."
  codex_note "This matches current CI behavior; issue #58 tracks making the gate mandatory."
  exit 0
fi

for version in 4 5 6 7 8 9 10 11; do
  next_version=$((version + 1))
  base="dbt_diagnostics/fixtures/schemas/manifest/v${version}.json"
  new="dbt_diagnostics/fixtures/schemas/manifest/v${next_version}.json"
  if [ -f "$base" ] && [ -f "$new" ]; then
    codex_run "$python_path" scripts/compat/schema_diff.py \
      "$base" "$new" --artifact manifest
  fi
done

for version in 4 5; do
  next_version=$((version + 1))
  base="dbt_diagnostics/fixtures/schemas/run-results/v${version}.json"
  new="dbt_diagnostics/fixtures/schemas/run-results/v${next_version}.json"
  if [ -f "$base" ] && [ -f "$new" ]; then
    codex_run "$python_path" scripts/compat/schema_diff.py \
      "$base" "$new" --artifact run-results
  fi
done

for spec in catalog/v1 sources/v3; do
  schema_file="dbt_diagnostics/fixtures/schemas/${spec}.json"
  artifact="${spec%%/*}"
  [ -f "$schema_file" ] \
    || codex_die "missing cached schema: ${schema_file}"
  codex_run "$python_path" scripts/compat/schema_diff.py \
    "$schema_file" "$schema_file" --artifact "$artifact"
done
