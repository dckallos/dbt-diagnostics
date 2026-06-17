#!/usr/bin/env bash
# Fail if automated-authorship markers appear in source files (AGENTS.md voice rule).
# Scans only tracked *.py/*.sql/*.ipynb so prose mentions in docs/AGENTS.md are ignored.
set -euo pipefail

if git grep -nI \
    -e "Co-authored with CoCo" \
    -e "Co-authored with Cortex Code" \
    -e "Co-Authored-By" \
    -- '*.py' '*.sql' '*.ipynb'; then
  echo "ERROR: automated-authorship marker found in source (AGENTS.md Voice and authorship rule forbids it)." >&2
  exit 1
fi
echo "OK: no authorship markers in source files."
