#!/usr/bin/env python3
# Diff two first-party dbt artifact JSON schemas by CONSUMED-path presence and exit
# nonzero when a field we read disappears without a declared fallback (a CI gate).
"""
Usage:
    python -m scripts.compat.schema_diff BASE.json NEW.json --artifact manifest
    python scripts/compat/schema_diff.py BASE.json NEW.json --artifact run-results

Truth source: pass FIRST-PARTY schemas (dbt-labs/schemas.getdbt.com or generated from
dbt-core). This tool never reads the third-party dbt-artifacts-parser. It reports, for
every path in consumed_paths.REGISTRY, whether the field's presence changed between two
versions, and whether any change is covered by a declared fallback alias.

Exit code: 0 if no consumed field broke (or every break is fallback-covered); 1 if a
consumed field disappeared with no surviving fallback (the build should fail loudly).
"""

from __future__ import annotations

import argparse
import json
import sys

from dbt_diagnostics.compat.consumed_paths import for_artifact
from dbt_diagnostics.compat.path_resolver import present_anywhere
from dbt_diagnostics.compat.schema_model import SchemaDoc


def _load(path: str) -> SchemaDoc:
    with open(path) as fh:
        return SchemaDoc(json.load(fh))


def diff(base_path: str, new_path: str, artifact: str) -> int:
    base, new = _load(base_path), _load(new_path)
    breaks = 0
    for cp in for_artifact(artifact):
        in_base = present_anywhere(base, cp.path)
        in_new = present_anywhere(new, cp.path)
        if in_base and not in_new:
            covered = [
                f"{cp.parent_path}.{alt}" for alt in cp.fallbacks
                if present_anywhere(new, f"{cp.parent_path}.{alt}")
            ]
            if covered:
                print(f"[OK-FALLBACK] {cp.path}: gone in NEW, covered by {covered}")
            else:
                breaks += 1
                print(f"[BREAK] {cp.path}: present in BASE, absent in NEW, "
                      f"no surviving fallback (declared: {cp.fallbacks or '-'}). "
                      f"Live recovery: {cp.live_recovery or 'none -- degrade'}")
        elif in_new and not in_base:
            print(f"[NEW] {cp.path}: appears in NEW only")
        else:
            print(f"[STABLE] {cp.path}")
    print(f"\n{breaks} unguarded break(s) for artifact '{artifact}'.")
    return breaks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diff dbt artifact schemas by consumed path.")
    ap.add_argument("base", help="path to the older first-party schema JSON")
    ap.add_argument("new", help="path to the newer first-party schema JSON")
    ap.add_argument("--artifact", required=True,
                    choices=("manifest", "run-results", "catalog", "sources"))
    args = ap.parse_args(argv)
    return 1 if diff(args.base, args.new, args.artifact) else 0


if __name__ == "__main__":
    raise SystemExit(main())
