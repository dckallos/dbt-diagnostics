#!/usr/bin/env python3
"""Run repository-specific Codex quality gates and write a local receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_governance_boundary


SCHEMA_VERSION = 1
DEFAULT_RECEIPT = Path("output/codex/quality-receipt.json")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def run_quality(
    *,
    root: Path | None = None,
    receipt_path: Path | None = None,
    paths: Sequence[Path] | None = None,
) -> dict[str, object]:
    root = (root or Path.cwd()).resolve()
    receipt_path = receipt_path or (root / DEFAULT_RECEIPT)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path

    governance_result = check_governance_boundary.run_check(paths, root=root)
    checks = [
        {
            "name": "governance-boundary",
            "status": "passed" if governance_result.passed else "failed",
            "checked_files": list(governance_result.checked_files),
            "findings": [
                violation.to_json() for violation in governance_result.violations
            ],
        }
    ]
    passed = all(check["status"] == "passed" for check in checks)
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "tool": "codex-quality",
        "passed": passed,
        "checks": checks,
    }

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit receipt JSON")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    paths = [Path(item) for item in args.path] if args.path else None
    receipt = run_quality(root=root, receipt_path=args.receipt, paths=paths)

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True))
    elif receipt["passed"]:
        print("OK: codex-quality passed.")
    else:
        print("ERROR: codex-quality failed.", file=sys.stderr)
        for check in receipt["checks"]:  # type: ignore[index]
            if check["status"] != "passed":
                print(f"- {check['name']} failed", file=sys.stderr)
        return 1

    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
