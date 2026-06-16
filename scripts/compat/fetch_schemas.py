#!/usr/bin/env python3
# Acquire FIRST-PARTY dbt artifact JSON schemas into the offline fixture cache and
# record provenance. Run where network is available (dev/CI); never at runtime.
# Co-authored with CoCo
"""
Downloads the canonical schemas published at schemas.getdbt.com (generated from
dbt-core) into dbt_diagnostics/fixtures/schemas/<artifact>/v<N>.json and writes a
PROVENANCE.json recording the source URL and a content hash for every file. This is
the Tier-1 source of truth for scripts/compat/schema_diff.py.

This script is the ONLY place that touches the network, and it is offline-decoupled
from the tool's runtime (the diagnosis path never fetches anything). dbt-artifacts-parser
is deliberately NOT used here.

Usage:
    python scripts/compat/fetch_schemas.py            # fetch the default version set
    python scripts/compat/fetch_schemas.py --manifest 12 --run-results 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

BASE_URL = "https://schemas.getdbt.com/dbt"
CACHE = Path(__file__).resolve().parents[2] / "dbt_diagnostics" / "fixtures" / "schemas"

# Default version sets to cache (manifest v4-v12, run-results v4-v6, catalog v1, sources v3).
DEFAULTS: dict[str, tuple[int, ...]] = {
    "manifest": tuple(range(4, 13)),
    "run-results": (4, 5, 6),
    "catalog": (1,),
    "sources": (3,),
}


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:  # nosec - first-party host
        return resp.read()


def fetch(versions: dict[str, tuple[int, ...]]) -> dict:
    provenance: dict = {}
    for artifact, majors in versions.items():
        out_dir = CACHE / artifact
        out_dir.mkdir(parents=True, exist_ok=True)
        for major in majors:
            url = f"{BASE_URL}/{artifact}/v{major}.json"
            try:
                raw = _fetch(url)
            except Exception as exc:  # noqa: BLE001 - acquisition is best-effort per version
                provenance[f"{artifact}/v{major}"] = {"url": url, "error": str(exc)}
                print(f"SKIP {artifact} v{major}: {exc}")
                continue
            dest = out_dir / f"v{major}.json"
            dest.write_bytes(raw)
            provenance[f"{artifact}/v{major}"] = {
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            print(f"OK   {artifact} v{major} ({len(raw)} bytes)")
    (CACHE / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2, sort_keys=True))
    return provenance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cache first-party dbt artifact schemas.")
    for art in DEFAULTS:
        ap.add_argument(f"--{art}", type=int, nargs="*", default=None,
                        help=f"{art} majors to fetch (default: {DEFAULTS[art]})")
    args = ap.parse_args(argv)
    chosen = {art: tuple(getattr(args, art.replace('-', '_')) or DEFAULTS[art]) for art in DEFAULTS}
    fetch(chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
