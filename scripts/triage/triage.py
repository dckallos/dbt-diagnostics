#!/usr/bin/env python3
"""Read-only issue governance, readiness, and relay coordination tooling."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required.
    tomllib = None  # type: ignore[assignment]

from scripts.triage.common import (  # noqa: E402
    TriageError,
    content_digest,
    issue_map,
    normalize_issue,
    normalize_milestone,
    normalize_pull,
    read_json,
    refs_in_text as refs_in_text,
    sha256_json,
    utc_now,
    write_ascii,
    write_json,
)
from scripts.triage.contract import (  # noqa: E402
    audit_contract,
    propose_normalized_body,
)
from scripts.triage.frontier import (  # noqa: E402
    build_coordinator_result,
    build_worker_packet,
    validate_coordinator_result,
)
from scripts.triage.readiness import (  # noqa: E402
    audit_all_issues,
    find_cycles as find_cycles,
    progress_log_drift,
)

DEFAULT_POLICY = ROOT / "scripts" / "triage" / "policy.toml"
DEFAULT_REPO = "dckallos/dbt-diagnostics"
LOCK_PATH = ROOT / "output" / "triage" / ".metadata-writer.lock"


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

    def run(
        self,
        args: list[str],
        *,
        timeout: float | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(tuple(args))
        process = subprocess.run(
            args,
            cwd=self.cwd,
            text=True,
            input=input_text,
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


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    if tomllib is None:
        raise TriageError("Python 3.11+ with tomllib is required")
    if not path.is_file():
        raise TriageError(f"policy file not found: {path}")
    with path.open("rb") as handle:
        policy = tomllib.load(handle)
    return policy


def gh_json(runner: Runner, args: list[str], *, timeout: float = 60.0) -> Any:
    if shutil.which("gh") is None:
        raise TriageError("GitHub CLI `gh` is required for a live snapshot")
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


def gh_api_paginated(
    runner: Runner,
    path: str,
    fields: Mapping[str, str] | None = None,
) -> list[Any]:
    query: list[str] = []
    for key, value in sorted((fields or {}).items()):
        query.extend(["-f", f"{key}={value}"])
    data = gh_json(
        runner,
        ["api", "--method", "GET", "--paginate", "--slurp", path, *query],
        timeout=120.0,
    )
    if data is None:
        return []
    if not isinstance(data, list):
        raise TriageError(f"paginated endpoint returned a non-list: {path}")
    flattened: list[Any] = []
    for page in data:
        if isinstance(page, list):
            flattened.extend(page)
        else:
            flattened.append(page)
    return flattened


def _normalize_issue_api(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = normalize_issue(raw)
    milestone = raw.get("milestone")
    if isinstance(milestone, Mapping):
        item["milestone"] = normalize_milestone(milestone)
    item["is_pull_request"] = "pull_request" in raw
    return item


def _normalize_pull_api(raw: Mapping[str, Any]) -> dict[str, Any]:
    base = raw.get("base") if isinstance(raw.get("base"), Mapping) else {}
    head = raw.get("head") if isinstance(raw.get("head"), Mapping) else {}
    item = normalize_pull(
        {
            **raw,
            "base_ref": base.get("ref"),
            "head_ref": head.get("ref"),
            "draft": raw.get("draft"),
            "merge_commit_sha": raw.get("merge_commit_sha"),
        }
    )
    return item


def collect_snapshot(
    runner: Runner,
    repo: str,
    policy: Mapping[str, Any],
    *,
    include_comments: bool = False,
) -> dict[str, Any]:
    issues_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/issues",
        {"state": "all", "per_page": "100"},
    )
    pulls_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/pulls",
        {"state": "all", "per_page": "100"},
    )
    labels_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/labels",
        {"per_page": "100"},
    )
    milestones_raw = gh_api_paginated(
        runner,
        f"/repos/{repo}/milestones",
        {"state": "all", "per_page": "100"},
    )

    issues = [
        _normalize_issue_api(item)
        for item in issues_raw
        if isinstance(item, Mapping) and "pull_request" not in item
    ]
    pulls = [
        _normalize_pull_api(item) for item in pulls_raw if isinstance(item, Mapping)
    ]
    if include_comments:
        for issue in issues:
            number = issue.get("number")
            if not isinstance(number, int):
                continue
            comments = gh_api_paginated(
                runner,
                f"/repos/{repo}/issues/{number}/comments",
                {"per_page": "100"},
            )
            issue["comments"] = [
                {
                    "id": comment.get("id"),
                    "body": comment.get("body") or "",
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                    "author": (comment.get("user") or {}).get("login")
                    if isinstance(comment.get("user"), Mapping)
                    else None,
                }
                for comment in comments
                if isinstance(comment, Mapping)
            ]

    labels = []
    for raw in labels_raw:
        if not isinstance(raw, Mapping):
            continue
        labels.append(
            {
                "name": raw.get("name") or "",
                "description": raw.get("description") or "",
                "color": raw.get("color") or "",
            }
        )
    milestones = []
    for raw in milestones_raw:
        if not isinstance(raw, Mapping):
            continue
        milestones.append(
            {
                "number": raw.get("number"),
                "title": raw.get("title") or "",
                "state": raw.get("state") or "",
                "open_issues": raw.get("open_issues"),
                "closed_issues": raw.get("closed_issues"),
                "due_on": raw.get("due_on"),
                "html_url": raw.get("html_url"),
            }
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    recently_closed = []
    for issue in issues:
        closed_at = issue.get("closed_at")
        if issue.get("state") != "closed" or not isinstance(closed_at, str):
            continue
        try:
            parsed = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed >= cutoff:
            recently_closed.append(issue["number"])

    snapshot = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "repository": repo,
        "source": {
            "transport": "gh-rest-read-only",
            "comments_included": include_comments,
            "github_writes_attempted": False,
        },
        "policy_digest": sha256_json(policy),
        "issues": sorted(issues, key=lambda item: int(item.get("number") or 0)),
        "pulls": sorted(pulls, key=lambda item: int(item.get("number") or 0)),
        "labels": sorted(labels, key=lambda item: str(item.get("name", "")).lower()),
        "milestones": sorted(milestones, key=lambda item: int(item.get("number") or 0)),
        "projects": {
            "status": "disabled",
            "reason": "exact Project identity is not configured in policy",
            "items": [],
        },
        "recently_closed_issue_numbers": sorted(recently_closed),
    }
    snapshot["snapshot_digest"] = content_digest(snapshot)
    return snapshot


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot.get("repository"), str):
        raise TriageError("snapshot repository is missing")
    if not isinstance(snapshot.get("issues"), list):
        raise TriageError("snapshot issues must be a list")
    numbers: set[int] = set()
    for raw in snapshot.get("issues") or []:
        if not isinstance(raw, Mapping):
            raise TriageError("snapshot issue entry must be an object")
        issue = normalize_issue(raw)
        number = issue.get("number")
        if not isinstance(number, int):
            raise TriageError("snapshot issue number must be an integer")
        if number in numbers:
            raise TriageError(f"snapshot contains duplicate issue number: {number}")
        numbers.add(number)
    expected = snapshot.get("snapshot_digest")
    if expected is not None and expected != content_digest(snapshot):
        raise TriageError("snapshot_digest does not match snapshot content")


def load_snapshot_or_collect(
    args: argparse.Namespace,
    runner: Runner,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot_path = getattr(args, "snapshot", None)
    if snapshot_path:
        snapshot = read_json(snapshot_path)
        if not isinstance(snapshot, Mapping):
            raise TriageError("snapshot file must contain a JSON object")
        snapshot = dict(snapshot)
    else:
        snapshot = collect_snapshot(
            runner,
            args.repo,
            policy,
            include_comments=bool(getattr(args, "comments", False)),
        )
    validate_snapshot(snapshot)
    return snapshot


def parse_issue_filter(value: str | None) -> set[int] | None:
    if not value:
        return None
    try:
        return {int(part.strip()) for part in value.split(",") if part.strip()}
    except ValueError as exc:
        raise TriageError(
            "--issues must be a comma-separated list of integers"
        ) from exc


def load_semantic_evidence(path: Path | None) -> dict[int, dict[str, Any]]:
    if path is None:
        return {}
    raw = read_json(path)
    if not isinstance(raw, Mapping):
        raise TriageError("semantic evidence file must be an object")
    values = raw.get("issues") if isinstance(raw.get("issues"), Mapping) else raw
    result: dict[int, dict[str, Any]] = {}
    for key, value in values.items():
        try:
            number = int(key)
        except (TypeError, ValueError) as exc:
            raise TriageError(f"invalid semantic evidence issue key: {key!r}") from exc
        if not isinstance(value, Mapping):
            raise TriageError(f"semantic evidence for #{number} must be an object")
        result[number] = dict(value)
    return result


def render_contract_markdown(
    issue: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    lines = [
        f"# Contract audit for #{issue['number']}",
        "",
        f"Title: {issue.get('title') or ''}",
        f"Issue kind: `{result['issue_kind']}`",
        f"Contract: `{result['contract_id']}` version `{result['contract_version']}`",
        f"Governance state: `{result['governance_state']}`",
        "",
        "## Findings",
        "",
    ]
    if not result.get("findings"):
        lines.append("No deterministic contract findings.")
    else:
        for finding in result["findings"]:
            lines.append(
                f"- **{finding['level']}** `{finding['code']}`: {finding['message']}"
            )
    lines.extend(["", "## Coverage", ""])
    for key, value in result.get("acceptance_coverage", {}).items():
        lines.append(f"- {key}: {'represented' if value else 'not explicit'}")
    return "\n".join(lines).rstrip() + "\n"


def render_audit_markdown(audit: Mapping[str, Any]) -> str:
    lines = [
        "# Open issue contract and readiness audit",
        "",
        f"Repository: `{audit.get('repository')}`",
        f"Snapshot digest: `{audit.get('snapshot_digest')}`",
        f"Audit digest: `{audit.get('audit_digest')}`",
        f"Issue count: {audit.get('issue_count')}",
        "",
        "## State summary",
        "",
    ]
    for key, value in (audit.get("implementation_state_counts") or {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Issues", ""])
    for item in audit.get("issues") or []:
        lines.extend(
            [
                f"### #{item['issue_number']} - {item['title']}",
                "",
                f"- Kind: `{item['issue_kind']}`",
                f"- Governance: `{item['governance_state']}`",
                f"- Implementation: `{item['implementation_state']}`",
                f"- Disposition: `{item['recommended_disposition']}`",
                f"- Dependencies: {', '.join(f'#{value}' for value in item['direct_dependencies']) or 'none'}",
                f"- Confidence: `{item['confidence']}`",
            ]
        )
        if item.get("blockers"):
            lines.append("- Blockers: " + "; ".join(item["blockers"]))
        if item.get("required_decisions"):
            lines.append("- Decisions: " + "; ".join(item["required_decisions"]))
        if item.get("missing_repository_paths"):
            lines.append(
                "- Missing paths: " + ", ".join(item["missing_repository_paths"])
            )
        findings = (item.get("contract_findings") or []) + (
            item.get("tracker_findings") or []
        )
        for finding in findings[:8]:
            lines.append(
                f"- Finding `{finding['code']}` ({finding['level']}): {finding['message']}"
            )
        if len(findings) > 8:
            lines.append(f"- Additional findings: {len(findings) - 8}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def audit_snapshot(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
    root: Path = ROOT,
    semantic_evidence: Mapping[int, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible flat findings adapter for older callers."""

    audit = audit_all_issues(
        snapshot,
        policy,
        root=root,
        semantic_evidence=semantic_evidence,
        issue_filter=issue_filter,
    )
    findings: list[dict[str, Any]] = []
    for item in audit["issues"]:
        for finding in item["tracker_findings"] + item["contract_findings"]:
            findings.append({**finding, "issue": item["issue_number"]})
    drift = progress_log_drift(snapshot, root / "docs" / "PROGRESS_LOG.md")
    if drift:
        findings.append({"level": "warning", "issue": None, **drift})
    return findings


def print_audit(findings: list[Mapping[str, Any]]) -> int:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        level = str(finding.get("level") or "info")
        counts[level] = counts.get(level, 0) + 1
        issue = f" #{finding['issue']}" if finding.get("issue") else ""
        print(
            f"[{level.upper()}] {finding.get('code', 'finding')}{issue}: "
            f"{finding.get('message', '')}"
        )
    print(
        "audit summary: "
        f"{counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), "
        f"{counts.get('info', 0)} info item(s)"
    )
    return 1 if counts.get("error", 0) else 0


def make_plan(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    findings: list[Mapping[str, Any]],
) -> dict[str, Any]:
    release = (
        policy.get("release") if isinstance(policy.get("release"), Mapping) else {}
    )
    decisions: list[dict[str, Any]] = []
    if not isinstance(release, Mapping) or not release.get("milestone_number"):
        decisions.append(
            {
                "decision_id": "release.milestone.identity",
                "summary": "Choose the exact initial-release milestone identity before metadata planning.",
            }
        )
    decisions.append(
        {
            "decision_id": "project.identity",
            "summary": "Configure an exact GitHub Project identity before Project audits are enabled.",
        }
    )
    plan = {
        "schema_version": 2,
        "generated_at": snapshot.get("generated_at") or utc_now(),
        "repository": snapshot.get("repository"),
        "snapshot_digest": snapshot.get("snapshot_digest") or content_digest(snapshot),
        "policy_digest": sha256_json(policy),
        "findings_digest": sha256_json(findings),
        "operations": [],
        "maintainer_decisions": decisions,
        "read_only": True,
        "forbidden_operations": [
            "issue.create",
            "issue.close",
            "issue.reopen",
            "issue.body.update",
            "issue.title.update",
            "label.create",
            "milestone.create",
            "project.mutate",
        ],
    }
    plan["plan_sha256"] = sha256_json(normalized_plan_without_digest(plan))
    return plan


def normalized_plan_without_digest(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def validate_approval(
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    expected_sha: str,
    batch: str,
) -> list[dict[str, Any]]:
    actual_sha = sha256_json(normalized_plan_without_digest(plan))
    if actual_sha != expected_sha:
        raise TriageError(
            f"plan digest mismatch: expected {expected_sha}, got {actual_sha}"
        )
    if plan.get("plan_sha256") != actual_sha:
        raise TriageError("embedded plan_sha256 does not match normalized plan")
    if approval.get("plan_sha256") != actual_sha:
        raise TriageError("approval file is for a different plan")
    if batch not in set(approval.get("approved_batches") or []):
        raise TriageError(f"batch is not approved: {batch}")
    approved_ids = set(approval.get("approved_operation_ids") or [])
    allow_destructive = bool(approval.get("allow_destructive"))
    selected: list[dict[str, Any]] = []
    for raw in plan.get("operations") or []:
        if not isinstance(raw, Mapping) or raw.get("batch") != batch:
            continue
        operation = dict(raw)
        operation_id = operation.get("operation_id")
        if operation_id not in approved_ids:
            raise TriageError(f"operation in batch is not approved: {operation_id}")
        if operation.get("destructive") and not allow_destructive:
            raise TriageError(f"destructive operation is not allowed: {operation_id}")
        if operation.get("kind") == "issue.body.update":
            raise TriageError("issue body mutation is forbidden")
        selected.append(operation)
    return selected


def acquire_lock(path: Path = LOCK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise TriageError(f"metadata writer lock already exists: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(f"pid={os.getpid()}\ncreated_at={utc_now()}\n")


def release_lock(path: Path = LOCK_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def apply_plan(args: argparse.Namespace) -> int:
    plan = read_json(args.plan)
    approval = read_json(args.approval)
    if not isinstance(plan, Mapping) or not isinstance(approval, Mapping):
        raise TriageError("plan and approval files must contain JSON objects")
    selected = validate_approval(plan, approval, args.plan_sha, args.batch)
    if not selected:
        print(f"No operations selected for approved batch {args.batch}.")
        return 0
    print("Selected operations:")
    for operation in selected:
        print(json.dumps(operation, sort_keys=True, ensure_ascii=True))
    if args.dry_run or not (args.execute or args.apply):
        print("Dry run only; no GitHub mutations executed.")
        return 0
    raise TriageError(
        "GitHub write execution is intentionally unavailable in this read-only implementation"
    )


def write_plan(
    plan: Mapping[str, Any],
    findings: list[Mapping[str, Any]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "plan.json", plan)
    lines = [
        "# Issue governance plan",
        "",
        f"Repository: `{plan.get('repository')}`",
        f"Plan SHA-256: `{plan.get('plan_sha256')}`",
        "",
        "## Operations",
        "",
        "No GitHub mutations are proposed by this read-only planner.",
        "",
        "## Maintainer decisions",
        "",
    ]
    for decision in plan.get("maintainer_decisions") or []:
        lines.append(f"- `{decision['decision_id']}`: {decision['summary']}")
    lines.extend(["", "## Audit findings", ""])
    for finding in findings:
        issue = f" #{finding['issue']}" if finding.get("issue") else ""
        lines.append(
            f"- **{finding['level']}** `{finding['code']}`{issue}: {finding['message']}"
        )
    write_ascii(output_dir / "plan.md", "\n".join(lines).rstrip() + "\n")
    approval = {
        "schema_version": 1,
        "repository": plan.get("repository"),
        "plan_sha256": plan.get("plan_sha256"),
        "approved_batches": [],
        "approved_operation_ids": [],
        "allow_destructive": False,
        "approved_by": "",
        "approved_at": "",
    }
    write_json(output_dir / "approval.template.json", approval)


def _load_audit(
    args: argparse.Namespace,
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    path = getattr(args, "audit_file", None)
    if path:
        audit = read_json(path)
        if not isinstance(audit, Mapping):
            raise TriageError("audit file must contain a JSON object")
        return dict(audit)
    semantic = load_semantic_evidence(getattr(args, "semantic_evidence", None))
    return audit_all_issues(
        snapshot,
        policy,
        root=ROOT,
        semantic_evidence=semantic,
        issue_filter=parse_issue_filter(getattr(args, "issues", None)),
    )


def _review_markdown(review: Mapping[str, Any]) -> str:
    issue = review["issue"]
    audit = review["audit"]
    lines = [
        f"# Issue review packet: #{issue['number']}",
        "",
        f"Title: {issue['title']}",
        f"Contract: `{audit['contract_id']}` version `{audit['contract_version']}`",
        f"Governance: `{audit['governance_state']}`",
        f"Implementation: `{audit['implementation_state']}`",
        f"Recommended disposition: `{audit['recommended_disposition']}`",
        "",
        "## Deterministic facts",
        "",
        f"- Direct dependencies: {', '.join(f'#{item}' for item in audit['direct_dependencies']) or 'none'}",
        f"- Parent epics: {', '.join(f'#{item}' for item in audit['parent_epics']) or 'none'}",
        f"- Release gate: {'yes' if audit['release_gate'] else 'no'}",
        f"- Referenced paths: {len(audit['referenced_paths'])}",
        "",
        "## Remaining uncertainty",
        "",
    ]
    values = (
        audit.get("blockers")
        + audit.get("required_decisions")
        + audit.get("required_external_evidence")
        + audit.get("semantic_review_notes")
    )
    if values:
        lines.extend(f"- {item}" for item in values)
    else:
        lines.append("No remaining uncertainty is recorded.")
    lines.extend(["", "## Proposed body", "", "See `proposed-body.md`.", ""])
    return "\n".join(lines)


def write_review_packet(
    issue_number: int,
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    output_dir: Path,
) -> None:
    issues = issue_map(snapshot)
    entries = {
        item["issue_number"]: item
        for item in audit.get("issues") or []
        if isinstance(item, Mapping) and isinstance(item.get("issue_number"), int)
    }
    if issue_number not in issues or issue_number not in entries:
        raise TriageError(f"issue #{issue_number} is not present in snapshot and audit")
    issue = issues[issue_number]
    entry = entries[issue_number]
    proposed = propose_normalized_body(issue)
    proposed_issue = {**issue, "body": proposed}
    proposed_audit = audit_contract(proposed_issue)
    review = {
        "schema_version": 1,
        "repository": snapshot.get("repository"),
        "snapshot_digest": snapshot.get("snapshot_digest"),
        "issue": {
            "number": issue_number,
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "labels": issue.get("labels"),
            "milestone": issue.get("milestone"),
            "body_digest": sha256_json(issue.get("body") or ""),
        },
        "audit": entry,
        "proposed_body_digest": sha256_json(proposed),
        "proposed_contract_audit": proposed_audit,
        "github_mutation_permitted": False,
    }
    review["review_digest"] = sha256_json(review)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "review.json", review)
    write_ascii(output_dir / "review.md", _review_markdown(review))
    write_ascii(output_dir / "proposed-body.md", proposed)
    write_json(output_dir / "contract-audit.json", proposed_audit)


def standardize_body(
    issue_number: int,
    snapshot: Mapping[str, Any],
    proposed_body_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    issues = issue_map(snapshot)
    if issue_number not in issues:
        raise TriageError(f"issue #{issue_number} is absent from the snapshot")
    try:
        proposed = proposed_body_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TriageError(
            f"proposed body file not found: {proposed_body_path}"
        ) from exc
    issue = {**issues[issue_number], "body": proposed}
    audit = audit_contract(issue)
    result = {
        "schema_version": 1,
        "repository": snapshot.get("repository"),
        "issue_number": issue_number,
        "source_body_digest": sha256_json(issues[issue_number].get("body") or ""),
        "proposed_body_digest": sha256_json(proposed),
        "contract_audit": audit,
        "github_mutation_permitted": False,
    }
    result["standardization_digest"] = sha256_json(result)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_ascii(output_dir / "proposed-body.md", proposed)
    write_json(output_dir / "contract-audit.json", audit)
    write_json(output_dir / "standardization.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help="GitHub repository, owner/name"
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser(
        "snapshot", help="collect a read-only GitHub metadata snapshot"
    )
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--comments", action="store_true")

    contract = sub.add_parser("contract", help="audit one issue against contract v1")
    contract.add_argument("--issue", type=int, required=True)
    contract.add_argument("--snapshot", type=Path)
    contract.add_argument("--json", action="store_true")

    audit = sub.add_parser(
        "audit", help="audit governance and implementation readiness"
    )
    audit.add_argument("--snapshot", type=Path)
    audit.add_argument("--semantic-evidence", type=Path)
    audit.add_argument("--issues", help="comma-separated issue numbers")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--output", type=Path)
    audit.add_argument("--output-dir", type=Path)

    review = sub.add_parser(
        "review-packet", help="write a bounded single-issue review packet"
    )
    review.add_argument("--issue", type=int, required=True)
    review.add_argument("--snapshot", type=Path)
    review.add_argument("--audit-file", type=Path)
    review.add_argument("--semantic-evidence", type=Path)
    review.add_argument("--output-dir", type=Path, required=True)

    standardize = sub.add_parser(
        "standardize", help="validate and package a proposed issue body locally"
    )
    standardize.add_argument("--issue", type=int, required=True)
    standardize.add_argument("--snapshot", type=Path)
    standardize.add_argument("--proposed-body", type=Path, required=True)
    standardize.add_argument("--output-dir", type=Path, required=True)

    frontier = sub.add_parser(
        "frontier", help="select the deterministic audit or implementation frontier"
    )
    frontier.add_argument("--mode", choices=["audit", "implement"], required=True)
    frontier.add_argument("--snapshot", type=Path)
    frontier.add_argument("--audit-file", type=Path)
    frontier.add_argument("--semantic-evidence", type=Path)
    frontier.add_argument("--issues", help="comma-separated issue numbers")
    frontier.add_argument("--json", action="store_true")
    frontier.add_argument("--output", type=Path)
    frontier.add_argument("--packet-output", type=Path)

    plan = sub.add_parser("plan", help="write a conservative read-only metadata plan")
    plan.add_argument("--snapshot", type=Path)
    plan.add_argument("--semantic-evidence", type=Path)
    plan.add_argument("--output-dir", type=Path, default=ROOT / "output" / "triage")

    apply = sub.add_parser(
        "apply", help="validate an approved plan; execution remains disabled"
    )
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--approval", type=Path, required=True)
    apply.add_argument("--plan-sha", required=True)
    apply.add_argument(
        "--batch", required=True, choices=["bootstrap", "canary", "remaining"]
    )
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument(
        "--apply", action="store_true", help="compatibility alias for --execute"
    )
    apply.add_argument(
        "--execute",
        action="store_true",
        help="request execution; intentionally rejected",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = Runner()
    try:
        policy = load_policy(args.policy)
        if args.command == "apply":
            return apply_plan(args)

        snapshot = load_snapshot_or_collect(args, runner, policy)
        if args.command == "snapshot":
            if args.output:
                write_json(args.output, snapshot)
            else:
                print(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True))
            return 0

        if args.command == "contract":
            issue = issue_map(snapshot).get(args.issue)
            if issue is None:
                raise TriageError(f"issue #{args.issue} is absent from the snapshot")
            result = audit_contract(issue)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
            else:
                print(render_contract_markdown(issue, result), end="")
            return (
                1
                if result["governance_state"] in {"needs_contract_revision", "unsafe"}
                else 0
            )

        audit = _load_audit(args, snapshot, policy)
        if args.command == "audit":
            if args.output:
                write_json(args.output, audit)
            if args.output_dir:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                write_json(args.output_dir / "audit.json", audit)
                write_ascii(args.output_dir / "audit.md", render_audit_markdown(audit))
            if args.json:
                print(json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=True))
            else:
                print(render_audit_markdown(audit), end="")
            severe = {
                "unsafe",
                "unknown",
            }
            return (
                1
                if any(
                    item.get("governance_state") in severe
                    for item in audit.get("issues") or []
                )
                else 0
            )

        if args.command == "review-packet":
            write_review_packet(args.issue, snapshot, audit, args.output_dir)
            print(f"Wrote {args.output_dir / 'review.json'}")
            return 0

        if args.command == "standardize":
            result = standardize_body(
                args.issue,
                snapshot,
                args.proposed_body,
                args.output_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
            return (
                1 if result["contract_audit"]["governance_state"] != "conformant" else 0
            )

        if args.command == "frontier":
            result = build_coordinator_result(
                args.mode,
                snapshot,
                audit,
                issue_filter=parse_issue_filter(args.issues),
            )
            errors = validate_coordinator_result(result)
            if errors:
                raise TriageError("invalid coordinator result: " + "; ".join(errors))
            if args.output:
                write_json(args.output, result)
            if args.packet_output and result.get("selected_issue") is not None:
                packet = build_worker_packet(
                    int(result["selected_issue"]),
                    snapshot,
                    audit,
                    root=ROOT,
                    branch_state={},
                    progress_context=None,
                )
                write_json(args.packet_output, packet)
            if args.json or not args.output:
                print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
            else:
                print(
                    f"{args.mode} frontier: "
                    + (
                        f"#{result['selected_issue']} - {result['selection_reason']}"
                        if result.get("selected_issue") is not None
                        else "empty"
                    )
                )
            return 0

        if args.command == "plan":
            findings = audit_snapshot(
                snapshot,
                policy,
                root=ROOT,
                semantic_evidence=load_semantic_evidence(args.semantic_evidence),
            )
            plan_data = make_plan(snapshot, policy, findings)
            write_plan(plan_data, findings, args.output_dir)
            write_json(args.output_dir / "snapshot.json", snapshot)
            write_json(args.output_dir / "audit.json", audit)
            print(f"Wrote {args.output_dir / 'plan.json'}")
            print(f"Plan SHA-256: {plan_data['plan_sha256']}")
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (TriageError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
