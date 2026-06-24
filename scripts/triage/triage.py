#!/usr/bin/env python3
"""Read-only issue governance tooling with guarded apply scaffolding.

The tool deliberately treats GitHub as the live source of truth. It uses the
local `gh` command so it runs with the maintainer's ordinary GitHub identity and
permissions. Snapshot, audit, and plan never mutate GitHub. Apply requires an
approved plan digest and explicit operation approval before it can run.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required here.
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "scripts" / "triage" / "policy.toml"
DEFAULT_REPO = "dckallos/dbt-diagnostics"
LOCK_PATH = ROOT / "output" / "triage" / ".metadata-writer.lock"

ISSUE_REF_RE = re.compile(r"(?<![A-Za-z0-9_])#(?P<number>[1-9][0-9]*)")
PATH_REF_RE = re.compile(
    r"(?P<path>(?:dbt_diagnostics|docs|scripts|\.github|\.codex)/"
    r"[A-Za-z0-9_./@+\-]+)(?::(?P<line>[0-9]+))?"
)
DEPENDENCY_HEADER_RE = re.compile(
    r"(?im)^(?:depends on|blocked by|blocks|supersedes|parent epic|related):\s*(?P<refs>.*)$"
)


class TriageError(RuntimeError):
    """Raised for controlled user-facing failures."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class Runner:
    cwd: Path = ROOT
    timeout: float = 60.0
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, args: list[str], *, timeout: float | None = None) -> CommandResult:
        self.calls.append(tuple(args))
        process = subprocess.run(
            args,
            cwd=self.cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout or self.timeout,
            check=False,
        )
        return CommandResult(
            args=tuple(args),
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    if tomllib is None:
        raise TriageError("Python 3.11+ with tomllib is required")
    if not path.is_file():
        raise TriageError(f"policy file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def gh_json(runner: Runner, args: list[str], *, timeout: float = 60.0) -> Any:
    if shutil.which("gh") is None:
        raise TriageError("GitHub CLI `gh` is required")
    result = runner.run(["gh", *args], timeout=timeout)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise TriageError(f"gh {' '.join(args)}: {detail}")
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TriageError(f"gh {' '.join(args)} returned non-JSON output") from exc


def gh_api_paginated(runner: Runner, path: str, fields: dict[str, str] | None = None) -> list[Any]:
    query: list[str] = []
    for key, value in (fields or {}).items():
        query.extend(["-f", f"{key}={value}"])
    data = gh_json(runner, ["api", "--paginate", path, *query], timeout=120)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    # gh concatenates page arrays for JSON endpoints; object responses should be
    # uncommon here but are still preserved as a one-item result.
    return [data]


def normalize_issue(raw: dict[str, Any]) -> dict[str, Any]:
    labels = raw.get("labels") or []
    milestone = raw.get("milestone")
    return {
        "number": raw.get("number"),
        "title": raw.get("title") or "",
        "state": raw.get("state") or "",
        "state_reason": raw.get("state_reason"),
        "updated_at": raw.get("updated_at"),
        "closed_at": raw.get("closed_at"),
        "labels": sorted(
            label.get("name", "") for label in labels if isinstance(label, dict)
        ),
        "milestone": None
        if milestone is None
        else {
            "number": milestone.get("number"),
            "title": milestone.get("title"),
            "state": milestone.get("state"),
        },
        "assignees": sorted(
            assignee.get("login", "")
            for assignee in (raw.get("assignees") or [])
            if isinstance(assignee, dict)
        ),
        "body": raw.get("body") or "",
        "html_url": raw.get("html_url") or raw.get("url"),
        "updated_timestamp": raw.get("updated_at"),
    }


def normalize_label(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": raw.get("name") or "",
        "description": raw.get("description") or "",
        "color": raw.get("color") or "",
    }


def normalize_milestone(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": raw.get("number"),
        "title": raw.get("title") or "",
        "state": raw.get("state") or "",
        "open_issues": raw.get("open_issues"),
        "closed_issues": raw.get("closed_issues"),
        "due_on": raw.get("due_on"),
        "html_url": raw.get("html_url"),
    }


def collect_snapshot(runner: Runner, repo: str, policy: dict[str, Any]) -> dict[str, Any]:
    issues_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/issues",
        {"state": "all", "per_page": "100"},
    )
    labels_raw = gh_api_paginated(runner, f"/repos/{repo}/labels", {"per_page": "100"})
    milestones_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/milestones",
        {"state": "all", "per_page": "100"},
    )

    issues = [
        normalize_issue(issue)
        for issue in issues_raw
        if isinstance(issue, dict) and "pull_request" not in issue
    ]
    labels = [normalize_label(label) for label in labels_raw if isinstance(label, dict)]
    milestones = [
        normalize_milestone(milestone)
        for milestone in milestones_raw
        if isinstance(milestone, dict)
    ]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": repo,
        "policy_digest": sha256_json(policy),
        "issues": sorted(issues, key=lambda item: int(item["number"] or 0)),
        "labels": sorted(labels, key=lambda item: item["name"].lower()),
        "milestones": sorted(milestones, key=lambda item: int(item["number"] or 0)),
    }


def issue_map(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {
        int(issue["number"]): issue
        for issue in snapshot.get("issues", [])
        if isinstance(issue.get("number"), int)
    }


def refs_in_text(text: str) -> set[int]:
    return {int(match.group("number")) for match in ISSUE_REF_RE.finditer(text or "")}


def dependency_refs(issue: dict[str, Any]) -> set[int]:
    body = issue.get("body") or ""
    refs: set[int] = set()
    for match in DEPENDENCY_HEADER_RE.finditer(body):
        refs.update(refs_in_text(match.group("refs")))
    return refs


def find_cycles(edges: dict[int, set[int]]) -> list[list[int]]:
    cycles: list[list[int]] = []
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def visit(node: int) -> None:
        if node in visiting:
            index = stack.index(node)
            cycles.append(stack[index:] + [node])
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for dep in sorted(edges.get(node, set())):
            if dep in edges:
                visit(dep)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node)
    deduped: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()
    for cycle in cycles:
        key = tuple(cycle)
        if key not in seen:
            seen.add(key)
            deduped.append(cycle)
    return deduped


def classify_labels(policy: dict[str, Any]) -> dict[str, set[str]]:
    configured = policy.get("labels", {})
    return {
        key: set(value if isinstance(value, list) else [])
        for key, value in configured.items()
    }


def audit_snapshot(
    snapshot: dict[str, Any],
    policy: dict[str, Any],
    *,
    issue_filter: set[int] | None = None,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    issues_by_number = issue_map(snapshot)
    allowed_labels = set().union(*classify_labels(policy).values()) if policy.get("labels") else set()
    audit_policy = policy.get("audit", {})

    def add(level: str, code: str, message: str, *, issue: int | None = None, data: Any = None) -> None:
        if issue_filter is not None and issue is not None and issue not in issue_filter:
            return
        findings.append(
            {
                "level": level,
                "code": code,
                "message": message,
                "issue": issue,
                "data": data,
            }
        )

    label_names = [label["name"] for label in snapshot.get("labels", [])]
    duplicate_labels = sorted({name.lower() for name in label_names if label_names.count(name) > 1})
    for name in duplicate_labels:
        add("error", "duplicate-label", f"duplicate label name after normalization: {name}")

    if allowed_labels:
        for issue in snapshot.get("issues", []):
            if issue.get("state") != "open":
                continue
            unknown = sorted(label for label in issue.get("labels", []) if label not in allowed_labels)
            if unknown:
                add(
                    "info",
                    "unclassified-label",
                    f"open issue has labels outside current policy: {', '.join(unknown)}",
                    issue=issue.get("number"),
                    data=unknown,
                )

    if audit_policy.get("require_open_issue_type_label"):
        type_labels = classify_labels(policy).get("type", set())
        for issue in snapshot.get("issues", []):
            if issue.get("state") != "open":
                continue
            present = sorted(set(issue.get("labels", [])) & type_labels)
            if len(present) != 1:
                add(
                    "error",
                    "type-label-count",
                    "open issue must have exactly one type label",
                    issue=issue.get("number"),
                    data=present,
                )

    if audit_policy.get("check_issue_references", True):
        for issue in snapshot.get("issues", []):
            refs = refs_in_text(issue.get("body") or "")
            missing = sorted(ref for ref in refs if ref not in issues_by_number)
            if missing:
                add(
                    "warning",
                    "missing-issue-reference",
                    f"issue body references nonexistent issue(s): {missing}",
                    issue=issue.get("number"),
                    data=missing,
                )

    if audit_policy.get("check_missing_repo_paths", True):
        for issue in snapshot.get("issues", []):
            body = issue.get("body") or ""
            missing_paths: list[str] = []
            for match in PATH_REF_RE.finditer(body):
                path = match.group("path").rstrip(".,;)]")
                if not (root / path).exists():
                    missing_paths.append(path)
            if missing_paths:
                add(
                    "warning",
                    "missing-repo-path",
                    "issue body references repository paths that do not exist",
                    issue=issue.get("number"),
                    data=sorted(set(missing_paths)),
                )

    if audit_policy.get("check_dependency_cycles", True):
        edges = {
            int(issue["number"]): dependency_refs(issue)
            for issue in snapshot.get("issues", [])
            if issue.get("state") == "open" and isinstance(issue.get("number"), int)
        }
        for cycle in find_cycles(edges):
            add("error", "dependency-cycle", f"dependency cycle detected: {cycle}", data=cycle)

    if audit_policy.get("check_progress_log_staleness", True):
        progress = root / "docs" / "PROGRESS_LOG.md"
        if progress.is_file():
            text = progress.read_text(encoding="utf-8", errors="replace")
            dates = re.findall(r"(?m)^## (20\d\d-\d\d-\d\d)", text)
            if dates:
                latest = dates[-1]
                newer_issue_updates = [
                    issue["number"]
                    for issue in snapshot.get("issues", [])
                    if isinstance(issue.get("updated_at"), str)
                    and issue["updated_at"][:10] > latest
                ]
                if newer_issue_updates:
                    add(
                        "warning",
                        "progress-log-stale",
                        f"progress log latest entry is {latest}, but live issues were updated later",
                        data=sorted(newer_issue_updates)[:50],
                    )

    return findings


def print_audit(findings: list[dict[str, Any]]) -> int:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        counts[finding["level"]] = counts.get(finding["level"], 0) + 1
        issue = f" #{finding['issue']}" if finding.get("issue") else ""
        print(f"[{finding['level'].upper()}] {finding['code']}{issue}: {finding['message']}")
        if finding.get("data") is not None:
            print(f"  data: {json.dumps(finding['data'], sort_keys=True, ensure_ascii=True)}")
    print(
        "audit summary: "
        f"{counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), "
        f"{counts.get('info', 0)} info item(s)"
    )
    return 1 if counts.get("error", 0) else 0


def make_plan(snapshot: dict[str, Any], policy: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    # The initial planner is intentionally conservative: it records decisions and
    # observations but proposes no writes unless future issue-specific code adds
    # exact, preflightable operations.
    decisions: list[dict[str, Any]] = []
    milestone_title = (policy.get("release", {}) or {}).get("milestone_title") or ""
    if not milestone_title:
        decisions.append(
            {
                "decision_id": "release.milestone.identity",
                "summary": "Choose the exact initial-release milestone identity before release gating.",
            }
        )
    decisions.append(
        {
            "decision_id": "project.identity",
            "summary": "Choose or create the GitHub Project before enabling Project item audits.",
        }
    )

    plan = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": snapshot.get("repository"),
        "snapshot_digest": sha256_json(snapshot),
        "policy_digest": sha256_json(policy),
        "findings_digest": sha256_json(findings),
        "operations": [],
        "maintainer_decisions": decisions,
    }
    plan["plan_sha256"] = sha256_json({k: v for k, v in plan.items() if k != "plan_sha256"})
    return plan


def write_plan(plan: dict[str, Any], findings: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    lines = [
        "# Issue governance plan",
        "",
        f"Repository: `{plan['repository']}`",
        f"Plan SHA-256: `{plan['plan_sha256']}`",
        "",
        "## Operations",
        "",
    ]
    if not plan["operations"]:
        lines.append("No metadata mutations are proposed by this conservative seed planner.")
    else:
        for op in plan["operations"]:
            lines.append(f"- `{op['operation_id']}`: {op['reason']}")
    lines.extend(["", "## Maintainer decisions", ""])
    for decision in plan["maintainer_decisions"]:
        lines.append(f"- `{decision['decision_id']}`: {decision['summary']}")
    lines.extend(["", "## Audit findings", ""])
    if not findings:
        lines.append("No audit findings.")
    else:
        for finding in findings:
            issue = f" #{finding['issue']}" if finding.get("issue") else ""
            lines.append(f"- **{finding['level']}** `{finding['code']}`{issue}: {finding['message']}")
    (output_dir / "plan.md").write_text("\n".join(lines) + "\n", encoding="ascii")


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TriageError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TriageError(f"invalid JSON file: {path}") from exc


def normalized_plan_without_digest(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def validate_approval(plan: dict[str, Any], approval: dict[str, Any], expected_sha: str, batch: str) -> list[dict[str, Any]]:
    actual_sha = sha256_json(normalized_plan_without_digest(plan))
    if actual_sha != expected_sha:
        raise TriageError(f"plan digest mismatch: expected {expected_sha}, got {actual_sha}")
    if plan.get("plan_sha256") != actual_sha:
        raise TriageError("embedded plan_sha256 does not match normalized plan")
    if approval.get("plan_sha256") != actual_sha:
        raise TriageError("approval file is for a different plan")
    if batch not in set(approval.get("approved_batches") or []):
        raise TriageError(f"batch is not approved: {batch}")

    approved_ids = set(approval.get("approved_operation_ids") or [])
    allow_destructive = bool(approval.get("allow_destructive"))
    selected: list[dict[str, Any]] = []
    for op in plan.get("operations") or []:
        if op.get("batch") != batch:
            continue
        op_id = op.get("operation_id")
        if op_id not in approved_ids:
            raise TriageError(f"operation in batch is not approved: {op_id}")
        if op.get("destructive") and not allow_destructive:
            raise TriageError(f"destructive operation is not allowed: {op_id}")
        selected.append(op)
    return selected


def acquire_lock(path: Path = LOCK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags)
    except FileExistsError as exc:
        raise TriageError(f"metadata writer lock already exists: {path}") from exc
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(f"pid={os.getpid()}\n")
        handle.write(f"created_at={datetime.now(timezone.utc).isoformat()}\n")


def release_lock(path: Path = LOCK_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def apply_plan(args: argparse.Namespace) -> int:
    plan = load_json_file(args.plan)
    approval = load_json_file(args.approval)
    selected = validate_approval(plan, approval, args.plan_sha, args.batch)

    if not selected:
        print(f"No operations selected for approved batch {args.batch}.")
        return 0

    print("Selected operations:")
    for op in selected:
        print(json.dumps(op, sort_keys=True, ensure_ascii=True))

    if args.dry_run or not args.apply:
        print("Dry run only; no GitHub mutations executed.")
        return 0

    acquire_lock()
    try:
        # This seed tool intentionally refuses unknown mutation operations. Future
        # issue-specific work should add exact implementations here with tests.
        unsupported = [op.get("operation_id") for op in selected]
        raise TriageError(
            "write execution is not implemented for these operation IDs: "
            + ", ".join(str(item) for item in unsupported)
        )
    finally:
        release_lock()


def parse_issue_filter(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repository, owner/name")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="print a live GitHub metadata snapshot")
    snapshot.add_argument("--output", type=Path)

    audit = sub.add_parser("audit", help="run read-only governance checks")
    audit.add_argument("--issues", help="comma-separated issue numbers to display")
    audit.add_argument("--json", action="store_true", help="emit findings as JSON")

    plan = sub.add_parser("plan", help="write a conservative metadata plan")
    plan.add_argument("--output-dir", type=Path, default=ROOT / "output" / "triage")

    apply = sub.add_parser("apply", help="apply an approved batch from a plan")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--approval", type=Path, required=True)
    apply.add_argument("--plan-sha", required=True)
    apply.add_argument("--batch", required=True, choices=["bootstrap", "canary", "remaining"])
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--apply", action="store_true", help="required for writes")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = Runner()

    try:
        policy = load_policy(args.policy)
        if args.command == "apply":
            return apply_plan(args)

        snapshot = collect_snapshot(runner, args.repo, policy)
        if args.command == "snapshot":
            text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="ascii")
            else:
                print(text, end="")
            return 0

        findings = audit_snapshot(
            snapshot,
            policy,
            issue_filter=parse_issue_filter(getattr(args, "issues", None)),
            root=ROOT,
        )
        if args.command == "audit":
            if args.json:
                print(json.dumps(findings, indent=2, sort_keys=True, ensure_ascii=True))
                return 1 if any(finding["level"] == "error" for finding in findings) else 0
            return print_audit(findings)

        if args.command == "plan":
            plan_data = make_plan(snapshot, policy, findings)
            write_plan(plan_data, findings, args.output_dir)
            print(f"Wrote {args.output_dir / 'plan.json'}")
            print(f"Wrote {args.output_dir / 'plan.md'}")
            print(f"Plan SHA-256: {plan_data['plan_sha256']}")
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except TriageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
