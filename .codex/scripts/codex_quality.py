#!/usr/bin/env python3
"""Run repository-specific Codex quality gates and write a local receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import check_governance_boundary
import check_artifact_contracts
import check_agent_regression
import codex_surface
from scripts.triage import repo_config


SCHEMA_VERSION = 1
FALLBACK_RECEIPT = Path("output/codex/quality-receipt.json")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def receipt_digest(receipt: dict[str, object]) -> str:
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key != "quality_receipt_digest"
    }
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def changed_paths_from_git(root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        return ()
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            paths.extend(part for part in path.split(" -> ") if part)
        elif path:
            paths.append(path)
    return tuple(paths)


def semantically_checked_protected_paths(
    *,
    root: Path,
    checked_files: Sequence[str],
    repo_policy: repo_config.RepoPolicy | None = None,
) -> tuple[str, ...]:
    existing_checked_files = [
        path
        for path in checked_files
        if path and (root / codex_surface.normalize_path(path)).exists()
    ]
    return codex_surface.protected_paths(
        existing_checked_files, repo_policy=repo_policy
    )


def freshness_bound_protected_paths(
    *,
    root: Path,
    requested_paths: Sequence[Path] | None,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> tuple[str, ...]:
    if requested_paths is None:
        candidates = list(changed_paths_from_git(root))
    else:
        candidates = [
            codex_surface.normalize_requested_path(path, root=root)
            for path in requested_paths
        ]

    existing_candidates = [
        path
        for path in candidates
        if path and (root / codex_surface.normalize_path(path)).exists()
    ]
    return codex_surface.protected_paths(existing_candidates, repo_policy=repo_policy)


def governance_check_entry(
    result: check_governance_boundary.CheckResult,
) -> dict[str, object]:
    return {
        "name": "governance-boundary",
        "status": "passed" if result.passed else "failed",
        "checked_files": list(result.checked_files),
        "findings": [violation.to_json() for violation in result.violations],
    }


def artifact_contracts_check_entry(
    result: check_artifact_contracts.ArtifactContractResult,
) -> dict[str, object]:
    return {
        "name": "artifact-contracts",
        "status": "passed" if result.passed else "failed",
        "checked_files": list(result.checked_files),
        "findings": [finding.to_json() for finding in result.findings],
    }


def agent_regression_check_entry(
    result: check_agent_regression.AgentRegressionResult,
) -> dict[str, object]:
    return {
        "name": "agent-regression",
        "status": "passed" if result.passed else "failed",
        "checked_files": list(result.checked_files),
        "case_results": [
            case_result.to_json() for case_result in result.case_results
        ],
        "findings": [finding.to_json() for finding in result.findings],
    }


def build_quality_receipt(
    *,
    root: Path,
    checks: Sequence[dict[str, object]],
    semantically_checked_files: Sequence[str],
    requested_paths: Sequence[Path] | None,
    repo_policy: repo_config.RepoPolicy,
    generated_at: str | None = None,
) -> dict[str, object]:
    semantically_checked_paths = semantically_checked_protected_paths(
        root=root,
        checked_files=semantically_checked_files,
        repo_policy=repo_policy,
    )
    freshness_bound_paths = freshness_bound_protected_paths(
        root=root,
        requested_paths=requested_paths,
        repo_policy=repo_policy,
    )
    passed = all(check["status"] == "passed" for check in checks)
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now(),
        "tool": "codex-quality",
        "passed": passed,
        "freshness_bound_protected_paths": list(freshness_bound_paths),
        "semantically_checked_protected_paths": list(semantically_checked_paths),
        "checks": list(checks),
    }
    receipt["quality_receipt_digest"] = receipt_digest(receipt)
    return receipt


def run_quality(
    *,
    root: Path | None = None,
    receipt_path: Path | None = None,
    paths: Sequence[Path] | None = None,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> dict[str, object]:
    root = (root or Path.cwd()).resolve()
    active_policy = repo_policy or repo_config.load_repo_policy()
    receipt_path = receipt_path or (root / active_policy.codex.quality_receipt_path)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path

    governance_result = check_governance_boundary.run_check(
        paths, root=root, repo_policy=active_policy
    )
    artifact_result = check_artifact_contracts.run_check(root=root)
    agent_regression_result = check_agent_regression.run_check(root=root)
    checks = [
        governance_check_entry(governance_result),
        artifact_contracts_check_entry(artifact_result),
        agent_regression_check_entry(agent_regression_result),
    ]
    receipt = build_quality_receipt(
        root=root,
        checks=checks,
        semantically_checked_files=(
            tuple(governance_result.checked_files)
            + tuple(artifact_result.checked_files)
            + tuple(agent_regression_result.checked_files)
        ),
        requested_paths=paths,
        repo_policy=active_policy,
    )

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit receipt JSON")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    paths = [Path(item) for item in args.path] if args.path else None
    try:
        active_policy = repo_config.load_repo_policy()
    except repo_config.RepoConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    receipt = run_quality(
        root=root,
        receipt_path=args.receipt,
        paths=paths,
        repo_policy=active_policy,
    )

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
