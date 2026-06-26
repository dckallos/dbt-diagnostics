#!/usr/bin/env python3
"""Anchor-check a draft proposed issue body before it is applied (read-only).

The deterministic content-anchor verifier (scripts/triage/readiness.py
verify_file_anchors) only runs over an applied issue body during the readiness
audit. This wrapper runs the same verifier over a local draft file so the
issue-governance self-verify step is reproducible instead of done by hand. It
mutates nothing.

Usage:
  python .codex/scripts/anchor_check.py output/triage/issues/74/proposed-body.md
  python .codex/scripts/anchor_check.py <draft> --root /path/to/repo

Exit status is 0 when every path:symbol and path "snippet" anchor resolves in
the current files and no cited line is past end-of-file; 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposed_body", type=Path, help="path to the draft body")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root the anchors resolve against (default: cwd)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not args.proposed_body.is_file():
        print(f"ERROR: draft not found: {args.proposed_body}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(root))
    try:
        from scripts.triage.common import parse_file_references
        from scripts.triage.readiness import verify_file_anchors
    except ImportError as exc:
        print(
            f"ERROR: cannot import the triage verifier from {root}: {exc}",
            file=sys.stderr,
        )
        return 2

    text = args.proposed_body.read_text(encoding="utf-8", errors="replace")
    anchored = [ref for ref in parse_file_references(text) if ref.is_anchored]
    report = verify_file_anchors({"body": text}, root)
    unresolved = report["unresolved_anchors"]
    past_eof = report["line_citations_past_eof"]

    print(
        f"anchored refs: {len(anchored)}; unresolved: {len(unresolved)}; "
        f"past EOF: {len(past_eof)}"
    )
    for item in unresolved:
        print(
            f"  UNRESOLVED {item['path']} :: {item['anchor']} "
            f"({item['anchor_type']})",
            file=sys.stderr,
        )
    for item in past_eof:
        print(
            f"  PAST-EOF {item['path']}:{item['line']} "
            f"(file has {item['line_count']} lines)",
            file=sys.stderr,
        )

    return 0 if not unresolved and not past_eof else 1


if __name__ == "__main__":
    raise SystemExit(main())
