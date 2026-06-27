#!/usr/bin/env bash
# Mirror the repository's credential-free compatibility schema checks.

set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

codex_require_repo_layout
cd "$CODEX_REPO_ROOT"
python_path="$(codex_require_venv)"

codex_header "Compatibility schema gate"

records="$("$python_path" scripts/triage/repo_config.py compat-records)" \
  || codex_die "failed to load compatibility schema policy"
if [ -z "$records" ]; then
  codex_note "SKIP: no compatibility schema sets are configured."
  exit 0
fi

first_sentinel="$(printf '%s\n' "$records" | awk -F '	' 'NR == 1 {print $3}')"
if [ ! -f "$first_sentinel" ]; then
  codex_note "SKIP: the committed first-party schema cache is not present."
  codex_note "This matches current CI behavior; issue #58 tracks making the gate mandatory."
  exit 0
fi

printf '%s\n' "$records" | while IFS="$(printf '\t')" read -r name artifact sentinel versions_csv; do
  [ -n "$name" ] || continue
  IFS=',' read -r -a versions <<< "$versions_csv"
  if [ "${#versions[@]}" -eq 1 ]; then
    schema_file="$(dirname "$sentinel")/v${versions[0]}.json"
    [ -f "$schema_file" ] \
      || codex_die "missing cached schema: ${schema_file}"
    codex_run "$python_path" scripts/compat/schema_diff.py \
      "$schema_file" "$schema_file" --artifact "$artifact"
    continue
  fi
  index=0
  while [ "$index" -lt "$((${#versions[@]} - 1))" ]; do
    version="${versions[$index]}"
    next_version="${versions[$((index + 1))]}"
    base="$(dirname "$sentinel")/v${version}.json"
    new="$(dirname "$sentinel")/v${next_version}.json"
    if [ -f "$base" ] && [ -f "$new" ]; then
      codex_run "$python_path" scripts/compat/schema_diff.py \
        "$base" "$new" --artifact "$artifact"
    fi
    index=$((index + 1))
  done
done
