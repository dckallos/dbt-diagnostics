from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.triage import repo_config, triage


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"


@dataclass
class QueueRunner:
    responses: list[triage.CommandResult]
    executable: str = "gh"
    require_executable: bool = False
    calls: list[tuple[str, ...]] = field(default_factory=list)
    inputs: list[str | None] = field(default_factory=list)

    def ensure_executable(self) -> None:
        return None

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        timeout: float | None = None,
        input_text: str | None = None,
    ) -> triage.CommandResult:
        del timeout
        normalized = tuple(str(item) for item in args)
        self.calls.append(normalized)
        self.inputs.append(input_text)
        if not self.responses:
            raise AssertionError(f"unexpected command: {normalized}")
        response = self.responses.pop(0)
        return triage.CommandResult(
            args=normalized,
            returncode=response.returncode,
            stdout=response.stdout,
            stderr=response.stderr,
        )


def response(
    value: Any, *, returncode: int = 0, stderr: str = ""
) -> triage.CommandResult:
    stdout = value if isinstance(value, str) else json.dumps(value)
    return triage.CommandResult(
        args=(), returncode=returncode, stdout=stdout, stderr=stderr
    )


def policy(**audit_overrides: Any) -> dict[str, Any]:
    audit = {
        "require_open_issue_type_label": False,
        "check_title_label_alignment": True,
        "check_issue_references": True,
        "check_closed_checklist_refs": True,
        "check_closed_dependencies": True,
        "check_missing_repo_paths": True,
        "check_dependency_cycles": True,
        "check_release_milestone": True,
        "check_open_pr_base": True,
        "check_project_configuration": True,
        "check_progress_log_staleness": False,
        "recent_closed_days": 90,
    }
    audit.update(audit_overrides)
    return {
        "repository": {
            "owner": "dckallos",
            "name": "dbt-diagnostics",
            "default_branch": "donkey-kong-sandbox",
        },
        "release": {
            "milestone_number": 1,
            "epic_numbers": [4, 48, 68],
            "section_headings": [
                "Initial-release gate",
                "Build order and rollback points",
            ],
            "additional_issue_numbers": [],
            "include_epics": True,
            "include_dependency_closure": True,
        },
        "project": {
            "enabled": False,
            "owner_type": "user",
            "owner": "dckallos",
            "number": 0,
        },
        "labels": {
            "type": ["bug", "enhancement", "docs", "test", "chore", "spike", "epic"],
            "area": [
                "architecture",
                "snowflake",
                "live",
                "compat",
                "lineage",
                "cli",
                "config",
                "output",
                "release",
            ],
            "constraint": [
                "tier-a",
                "tier-b",
                "decision-needed",
                "security",
                "blocked",
            ],
            "priority": ["priority: now", "priority: next", "priority: deferred"],
        },
        "type_inference": {
            "prefixes": {
                "bug": ["fix:"],
                "enhancement": ["feat:", "[Feature]"],
                "docs": ["docs:"],
                "test": ["test:"],
                "chore": ["chore:"],
                "spike": ["spike:"],
                "epic": ["[Epic]"],
                "architecture": ["refactor:"],
            }
        },
        "audit": audit,
        "planning": {
            "default_batch": "remaining",
            "bootstrap_issue_numbers": [68, 69, 70],
            "canary_issue_numbers": [71, 72],
            "remaining_issue_numbers": [],
        },
        "desired": {},
    }


def issue(
    number: int,
    *,
    title: str = "fix: example",
    state: str = "open",
    body: str = "",
    labels: list[str] | None = None,
    milestone: int | None = None,
    updated_at: str = "2026-06-23T12:00:00Z",
    closed_at: str | None = None,
    state_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "state": state,
        "state_reason": state_reason,
        "author": "dckallos",
        "assignees": [],
        "labels": list(labels or []),
        "milestone": None
        if milestone is None
        else {
            "number": milestone,
            "title": "Initial release",
            "state": "open",
            "due_on": None,
            "html_url": "https://example.test/milestone/1",
        },
        "created_at": "2026-06-20T00:00:00Z",
        "updated_at": updated_at,
        "closed_at": closed_at,
        "comments": 0,
        "locked": False,
        "body": body,
        "html_url": f"https://example.test/issues/{number}",
    }


def pull(number: int, *, state: str = "closed", body: str = "") -> dict[str, Any]:
    return {
        **issue(
            number,
            title="test: pull request",
            state=state,
            body=body,
            updated_at="2026-06-22T00:00:00Z",
            closed_at="2026-06-22T00:00:00Z" if state == "closed" else None,
        ),
        "draft": False,
        "merged_at": "2026-06-22T00:00:00Z" if state == "closed" else None,
    }


def snapshot(
    issues: list[dict[str, Any]],
    *,
    pulls: list[dict[str, Any]] | None = None,
    labels: list[str] | None = None,
    milestones: list[dict[str, Any]] | None = None,
    open_pulls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": triage.SNAPSHOT_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": {
            "full_name": "dckallos/dbt-diagnostics",
            "owner": "dckallos",
            "name": "dbt-diagnostics",
            "default_branch": "donkey-kong-sandbox",
            "visibility": "public",
            "archived": False,
            "disabled": False,
            "has_issues": True,
            "html_url": "https://example.test/repo",
            "updated_at": "2026-06-23T00:00:00Z",
            "pushed_at": "2026-06-23T00:00:00Z",
        },
        "policy_sha256": triage.sha256_json(policy()),
        "issues": issues,
        "pull_requests": list(pulls or []),
        "open_pull_requests": list(open_pulls or []),
        "labels": [
            {"name": name, "description": "", "color": "ededed", "default": False}
            for name in (labels or [])
        ],
        "label_usage": [],
        "milestones": list(
            milestones
            if milestones is not None
            else [
                {
                    "number": 1,
                    "title": "Initial release",
                    "description": "",
                    "state": "open",
                    "open_issues": 0,
                    "closed_issues": 0,
                    "due_on": None,
                    "created_at": "2026-06-20T00:00:00Z",
                    "updated_at": "2026-06-20T00:00:00Z",
                    "closed_at": None,
                    "html_url": "https://example.test/milestone/1",
                }
            ]
        ),
        "milestone_usage": [],
        "referenced_closed_items": [],
        "recently_closed_items": [],
        "project": {"configured": False, "status": "not_configured"},
    }
    value["snapshot_sha256"] = triage.sha256_json(triage.snapshot_without_digest(value))
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="ascii")


def operation_for_issue(
    number: int, *, batch: str = "bootstrap"
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = issue(number, labels=["bug"], milestone=None)
    snap = snapshot([current], labels=["bug"], milestones=snapshot([])["milestones"])
    suggestion = {
        "kind": "issue.milestone.set",
        "issue_number": number,
        "milestone_number": 1,
        "batch": batch,
        "reason": "Assign the approved release milestone.",
    }
    operation = triage.operation_from_suggestion(suggestion, snapshot=snap)[0]
    return operation, current


def test_sha_is_stable_for_unordered_dicts() -> None:
    assert triage.sha256_json({"b": 2, "a": 1}) == triage.sha256_json({"a": 1, "b": 2})


def test_api_pagination_is_get_only_and_slurped() -> None:
    runner = QueueRunner([response([[{"number": 1}], [{"number": 2}]])])
    client = triage.GitHubClient(runner=runner, repo="dckallos/dbt-diagnostics")

    values = client.api_paginated(
        "/repos/dckallos/dbt-diagnostics/issues",
        query={"state": "all", "per_page": 100},
    )

    assert values == [{"number": 1}, {"number": 2}]
    call = runner.calls[0]
    assert call[:4] == ("gh", "api", "--method", "GET")
    assert "--paginate" in call
    assert "--slurp" in call
    assert not any(item == "-f" or item.startswith("state=") for item in call)
    assert call[-1].endswith("?state=all&per_page=100")


def test_api_body_is_sent_via_stdin_not_argv() -> None:
    dangerous = "$(touch /tmp/not-run); `echo nope`"
    runner = QueueRunner([response({"ok": True})])
    client = triage.GitHubClient(runner=runner, repo="dckallos/dbt-diagnostics")

    client.api(
        "/repos/dckallos/dbt-diagnostics/issues/1",
        method="PATCH",
        body={"value": dangerous},
    )

    assert dangerous not in " ".join(runner.calls[0])
    assert json.loads(runner.inputs[0] or "{}") == {"value": dangerous}
    assert runner.calls[0][-2:] == ("--input", "-")


def test_collect_snapshot_separates_issues_pulls_and_closed_references() -> None:
    raw_issue = {
        "number": 1,
        "title": "fix: live issue",
        "state": "open",
        "body": "Depends on #2 and PR #10.",
        "labels": [{"name": "bug"}],
        "milestone": None,
        "assignees": [],
        "user": {"login": "dckallos"},
        "updated_at": "2026-06-23T00:00:00Z",
        "created_at": "2026-06-20T00:00:00Z",
        "closed_at": None,
        "comments": 0,
    }
    raw_closed = {
        **raw_issue,
        "number": 2,
        "title": "fix: closed issue",
        "state": "closed",
        "body": "",
        "closed_at": "2026-06-23T00:00:00Z",
    }
    raw_pr = {
        **raw_closed,
        "number": 10,
        "title": "test: merged pull",
        "pull_request": {"merged_at": "2026-06-23T00:00:00Z"},
    }
    runner = QueueRunner(
        [
            response(
                {
                    "full_name": "dckallos/dbt-diagnostics",
                    "default_branch": "donkey-kong-sandbox",
                    "visibility": "public",
                }
            ),
            response([[raw_issue, raw_closed, raw_pr]]),
            response(
                [
                    [
                        {
                            "name": "bug",
                            "description": "",
                            "color": "d73a4a",
                            "default": True,
                        }
                    ]
                ]
            ),
            response([[{"number": 1, "title": "Initial release", "state": "open"}]]),
            response([[]]),
        ]
    )

    result = triage.collect_snapshot(
        runner,
        "dckallos/dbt-diagnostics",
        policy(),
        now=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )

    assert [item["number"] for item in result["issues"]] == [1, 2]
    assert [item["number"] for item in result["pull_requests"]] == [10]
    assert {
        (item["kind"], item["number"]) for item in result["referenced_closed_items"]
    } == {
        ("issue", 2),
        ("pull_request", 10),
    }
    assert result["snapshot_sha256"] == triage.sha256_json(
        triage.snapshot_without_digest(result)
    )
    assert all(call[3] == "GET" for call in runner.calls)


def test_tracker_references_accept_pull_request_numbers() -> None:
    snap = snapshot(
        [issue(1, body="See #10.", labels=["bug"])], pulls=[pull(10)], labels=["bug"]
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    assert not any(item["code"] == "missing-tracker-reference" for item in findings)


def test_missing_tracker_reference_is_reported_for_open_issue_only() -> None:
    snap = snapshot(
        [
            issue(1, body="See #999.", labels=["bug"]),
            issue(
                2,
                state="closed",
                body="Historical #998.",
                labels=["bug"],
                closed_at="2026-06-22T00:00:00Z",
            ),
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    missing = [item for item in findings if item["code"] == "missing-tracker-reference"]
    assert [(item["issue"], item["data"]) for item in missing] == [(1, [999])]


def test_title_label_alignment_suggests_staged_operation() -> None:
    snap = snapshot(
        [issue(70, title="refactor: seam", labels=["snowflake"])],
        labels=["architecture", "snowflake"],
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    finding = next(item for item in findings if item["code"] == "title-label-mismatch")
    assert finding["issue"] == 70
    assert finding["suggested_operation"] == {
        "kind": "issue.labels.add",
        "issue_number": 70,
        "labels": ["architecture"],
        "batch": "bootstrap",
        "reason": "Add the title-inferred label 'architecture'.",
    }


def test_unchecked_line_reports_all_closed_references() -> None:
    snap = snapshot(
        [
            issue(1, body="- [ ] #2 and #3", labels=["bug"]),
            issue(2, state="closed", labels=["bug"], closed_at="2026-06-22T00:00:00Z"),
            issue(3, state="closed", labels=["bug"], closed_at="2026-06-22T00:00:00Z"),
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    finding = next(
        item for item in findings if item["code"] == "unchecked-closed-reference"
    )
    assert [item["number"] for item in finding["data"]] == [2, 3]


def test_qualified_closed_dependency_is_reported_but_supersedes_is_not() -> None:
    snap = snapshot(
        [
            issue(
                1,
                body="Depends on corrected live work: #2\nSupersedes: #3",
                labels=["bug"],
            ),
            issue(2, state="closed", labels=["bug"], closed_at="2026-06-22T00:00:00Z"),
            issue(3, state="closed", labels=["bug"], closed_at="2026-06-22T00:00:00Z"),
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    finding = next(
        item for item in findings if item["code"] == "closed-dependency-reference"
    )
    assert [item["number"] for item in finding["data"]] == [2]


def test_missing_paths_ignore_closed_issues(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "EXISTS.md").write_text("ok", encoding="ascii")
    snap = snapshot(
        [
            issue(1, body="See docs/EXISTS.md and docs/MISSING.md.", labels=["bug"]),
            issue(
                2,
                state="closed",
                body="See docs/OLD.md.",
                labels=["bug"],
                closed_at="2026-06-22T00:00:00Z",
            ),
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(snap, policy(), root=tmp_path)

    missing = [item for item in findings if item["code"] == "missing-repo-path"]
    assert [(item["issue"], item["data"]) for item in missing] == [
        (1, ["docs/MISSING.md"])
    ]


def test_missing_root_file_reference_is_reported(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok", encoding="ascii")
    snap = snapshot(
        [issue(1, body="README.md exists; SECURITY.md does not.", labels=["bug"])],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(snap, policy(), root=tmp_path)

    missing = [item for item in findings if item["code"] == "missing-repo-path"]
    assert [(item["issue"], item["data"]) for item in missing] == [(1, ["SECURITY.md"])]


def test_missing_extensionless_configured_root_file_is_reported(
    tmp_path: Path,
) -> None:
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["reference_roots"] = ["Dockerfile", "Makefile"]  # type: ignore[index]
    active_policy = repo_config.policy_from_mapping(data)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="ascii")
    snap = snapshot(
        [
            issue(
                1,
                body="Dockerfile exists; Makefile does not.",
                labels=["bug"],
            )
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(
        snap,
        policy(),
        root=tmp_path,
        repo_policy=active_policy,
    )

    missing = [item for item in findings if item["code"] == "missing-repo-path"]
    assert [(item["issue"], item["data"]) for item in missing] == [(1, ["Makefile"])]


def test_missing_paths_use_configured_non_dbt_reference_roots(
    tmp_path: Path,
) -> None:
    widgets_policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "widget_check.py").write_text("ok", encoding="ascii")
    snap = snapshot(
        [
            issue(
                1,
                body=(
                    "See scripts/widget_check.py, scripts/missing_widget.py, and "
                    "dbt_diagnostics/fixtures/schemas/manifest/v12.json."
                ),
                labels=["bug"],
            )
        ],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(
        snap,
        policy(),
        root=tmp_path,
        repo_policy=widgets_policy,
    )

    missing = [item for item in findings if item["code"] == "missing-repo-path"]
    assert [(item["issue"], item["data"]) for item in missing] == [
        (1, ["scripts/missing_widget.py"])
    ]


def test_dependency_cycle_detection_is_canonical() -> None:
    cycles = triage.find_cycles({1: {2}, 2: {3}, 3: {1}, 4: set()})
    assert cycles == [[1, 2, 3, 1]]


def test_scoped_audit_excludes_unrelated_dependency_cycle() -> None:
    # `audit --issues 1` must not fail because of a dependency cycle among other
    # issues. The metadata audit is scoped to the same issue filter, so a cycle
    # that does not touch the requested issue is not reported.
    snap = snapshot(
        [
            issue(1, title="fix: a", body="Self-contained.", labels=["bug"]),
            issue(2, title="fix: b", body="Depends on: #3", labels=["bug"]),
            issue(3, title="fix: c", body="Depends on: #2", labels=["bug"]),
        ],
        labels=["bug"],
    )

    audit = triage.make_readiness_audit(snap, policy(), issue_filter={1})

    codes = {finding["code"] for finding in audit["metadata_findings"]}
    assert "dependency-cycle" not in codes


def test_scoped_audit_keeps_cycle_touching_requested_issue() -> None:
    # A cycle that includes the requested issue is still reported.
    snap = snapshot(
        [
            issue(1, title="fix: a", body="Depends on: #2", labels=["bug"]),
            issue(2, title="fix: b", body="Depends on: #1", labels=["bug"]),
        ],
        labels=["bug"],
    )

    audit = triage.make_readiness_audit(snap, policy(), issue_filter={1})

    cycle = [
        finding
        for finding in audit["metadata_findings"]
        if finding["code"] == "dependency-cycle"
    ]
    assert cycle and cycle[0]["level"] == "error"


def test_blocks_relation_reverses_dependency_edge() -> None:
    snap = snapshot(
        [
            issue(1, body="Blocks: #2", labels=["bug"]),
            issue(2, body="", labels=["bug"]),
        ],
        labels=["bug"],
    )
    assert triage.build_dependency_edges(snap) == {1: set(), 2: {1}}


def test_bold_dependency_heading_is_parsed() -> None:
    item = issue(1, body="- **Depends on** corrected work: #2", labels=["bug"])
    assert triage.dependency_refs(item) == {2}


def test_release_derivation_uses_epic_sections_and_dependency_closure() -> None:
    snap = snapshot(
        [
            issue(
                4,
                title="[Epic] Live",
                body="## Initial-release gate\n- [ ] #10",
                labels=["epic"],
            ),
            issue(
                48,
                title="[Epic] Compat",
                body="## Initial-release gate\n- [ ] #20",
                labels=["epic"],
            ),
            issue(
                68,
                title="[Epic] Backend",
                body="## Build order and rollback points\n1. #30",
                labels=["epic"],
            ),
            issue(10, body="Depends on: #11", labels=["bug"]),
            issue(11, labels=["bug"]),
            issue(20, labels=["bug"]),
            issue(30, labels=["bug"]),
        ],
        labels=["bug", "epic"],
    )

    assert triage.derive_release_issue_numbers(snap, policy()) == {
        4,
        10,
        11,
        20,
        30,
        48,
        68,
    }


def test_release_milestone_findings_use_policy_batches() -> None:
    snap = snapshot(
        [
            issue(
                4,
                title="[Epic] Live",
                body="## Initial-release gate\n- [ ] #69\n- [ ] #71\n- [ ] #80",
                labels=["epic"],
            ),
            issue(48, title="[Epic] Compat", body="", labels=["epic"], milestone=1),
            issue(68, title="[Epic] Backend", body="", labels=["epic"]),
            issue(69, title="test: baseline", labels=["test"]),
            issue(71, title="fix: conversion", labels=["bug"]),
            issue(80, title="fix: other", labels=["bug"]),
        ],
        labels=["bug", "epic", "test"],
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))
    batches = {
        item["issue"]: item["suggested_operation"]["batch"]
        for item in findings
        if item["code"] == "release-issue-milestone"
    }

    assert batches[68] == "bootstrap"
    assert batches[69] == "bootstrap"
    assert batches[71] == "canary"
    assert batches[80] == "remaining"


def test_progress_log_reports_date_and_declared_state_drift(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PROGRESS_LOG.md").write_text(
        "# Progress log\n\n## 2026-06-16 -- state\nOpen issues: #1, #2\nOpen PRs: #10\n",
        encoding="ascii",
    )
    snap = snapshot(
        [
            issue(1, labels=["bug"], updated_at="2026-06-23T00:00:00Z"),
            issue(
                2,
                state="closed",
                labels=["bug"],
                updated_at="2026-06-22T00:00:00Z",
                closed_at="2026-06-22T00:00:00Z",
            ),
        ],
        pulls=[pull(10, state="closed")],
        labels=["bug"],
    )

    findings = triage.audit_snapshot(
        snap,
        policy(check_progress_log_staleness=True, check_missing_repo_paths=False),
        root=tmp_path,
    )

    assert any(item["code"] == "progress-log-stale" for item in findings)
    drift = [item for item in findings if item["code"] == "progress-log-state-drift"]
    assert len(drift) == 2


def test_issue_filter_rejects_unknown_number() -> None:
    with pytest.raises(triage.TriageError, match="unknown issue"):
        triage.audit_snapshot(snapshot([issue(1)]), policy(), issue_filter={999})


def test_plan_digest_and_operations_are_deterministic() -> None:
    snap = snapshot(
        [issue(68, title="[Epic] Backend", labels=["epic"])], labels=["epic"]
    )
    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))
    now = datetime(2026, 6, 24, tzinfo=timezone.utc)

    first = triage.make_plan(snap, policy(), findings, now=now)
    second = triage.make_plan(snap, policy(), list(reversed(findings)), now=now)

    assert first == second
    assert first["plan_sha256"] == triage.sha256_json(
        triage.normalized_plan_without_digest(first)
    )
    assert [item["batch"] for item in first["operations"]] == ["bootstrap"]
    assert all(
        item["kind"] in triage.SUPPORTED_OPERATION_KINDS for item in first["operations"]
    )
    assert first["safety"]["body_updates_supported"] is False


def test_operation_id_changes_when_request_changes() -> None:
    operation, _ = operation_for_issue(68)
    changed = json.loads(json.dumps(operation))
    changed["request"]["body"]["milestone"] = 2
    assert triage.operation_id(changed) != operation["operation_id"]


def test_validate_operation_rejects_tampered_request_path() -> None:
    operation, _ = operation_for_issue(68)
    tampered = json.loads(json.dumps(operation))
    tampered["request"]["path"] = "/repos/dckallos/dbt-diagnostics/issues/999"
    tampered["operation_id"] = triage.operation_id(tampered)

    with pytest.raises(triage.TriageError, match="does not match"):
        triage.validate_operation(tampered)


def test_validate_operation_rejects_forbidden_kind() -> None:
    operation, _ = operation_for_issue(68)
    forbidden = json.loads(json.dumps(operation))
    forbidden["kind"] = "issue.body.update"
    forbidden["operation_id"] = triage.operation_id(forbidden)

    with pytest.raises(triage.TriageError, match="unsupported or forbidden"):
        triage.validate_operation(forbidden)


def test_approval_can_cover_multiple_batches_and_select_one() -> None:
    bootstrap, _ = operation_for_issue(68, batch="bootstrap")
    canary, _ = operation_for_issue(71, batch="canary")
    plan = {
        "schema_version": triage.PLAN_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_sha256": "snapshot",
        "policy_sha256": "policy",
        "findings_sha256": "findings",
        "operations": [bootstrap, canary],
        "maintainer_decisions": [],
        "safety": {},
    }
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "schema_version": triage.APPROVAL_SCHEMA_VERSION,
        "repository": "dckallos/dbt-diagnostics",
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap", "canary"],
        "approved_operation_ids": [bootstrap["operation_id"], canary["operation_id"]],
        "allow_destructive": False,
        "approved_by": "maintainer",
        "approved_at": "2026-06-24T00:00:00Z",
    }

    selected = triage.validate_approval(
        plan, approval, plan["plan_sha256"], "bootstrap"
    )

    assert [item["operation_id"] for item in selected] == [bootstrap["operation_id"]]


def test_approval_rejects_wrong_digest() -> None:
    operation, _ = operation_for_issue(68)
    plan = {
        "schema_version": triage.PLAN_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_sha256": "snapshot",
        "policy_sha256": "policy",
        "findings_sha256": "findings",
        "operations": [operation],
        "maintainer_decisions": [],
        "safety": {},
    }
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "schema_version": triage.APPROVAL_SCHEMA_VERSION,
        "repository": "dckallos/dbt-diagnostics",
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": [operation["operation_id"]],
        "allow_destructive": False,
        "approved_by": "maintainer",
        "approved_at": "2026-06-24T00:00:00Z",
    }

    with pytest.raises(triage.TriageError, match="plan digest mismatch"):
        triage.validate_approval(plan, approval, "bad", "bootstrap")


def test_plan_bundle_writes_all_files_as_ascii(tmp_path: Path) -> None:
    snap = snapshot(
        [issue(68, title="[Epic] Backend", labels=["epic"])], labels=["epic"]
    )
    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))
    plan = triage.make_plan(
        snap, policy(), findings, now=datetime(2026, 6, 24, tzinfo=timezone.utc)
    )

    triage.write_plan_bundle(plan, findings, snap, tmp_path)

    names = {path.name for path in tmp_path.iterdir()}
    assert names == {
        "snapshot.json",
        "audit.json",
        "plan.json",
        "plan.md",
        "approval.template.json",
    }
    for path in tmp_path.iterdir():
        path.read_bytes().decode("ascii")
        assert os.stat(path).st_mode & 0o777 == 0o600
    approval = json.loads(
        (tmp_path / "approval.template.json").read_text(encoding="ascii")
    )
    assert approval["approved_batches"] == []
    assert approval["approved_operation_ids"] == []


def test_apply_empty_approved_batch_does_not_read_github(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snap = snapshot([])
    plan = triage.make_plan(
        snap, policy(), [], now=datetime(2026, 6, 24, tzinfo=timezone.utc)
    )
    approval = {
        "schema_version": triage.APPROVAL_SCHEMA_VERSION,
        "repository": plan["repository"],
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": [],
        "allow_destructive": False,
        "approved_by": "maintainer",
        "approved_at": "2026-06-24T00:00:00Z",
    }
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    write_json(plan_path, plan)
    write_json(approval_path, approval)
    runner = QueueRunner([])
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=True,
        execute=False,
        confirm_repo=None,
        lock_path=None,
        receipt=None,
    )

    code = triage.apply_plan(args, runner=runner)

    assert code == 0
    assert runner.calls == []
    assert "No operations selected" in capsys.readouterr().out


def prepare_plan_and_approval(
    tmp_path: Path, *, issue_number: int = 68
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    operation, _ = operation_for_issue(issue_number)
    plan = {
        "schema_version": triage.PLAN_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_sha256": "snapshot",
        "policy_sha256": "policy",
        "findings_sha256": "findings",
        "operations": [operation],
        "maintainer_decisions": [],
        "safety": {},
    }
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "schema_version": triage.APPROVAL_SCHEMA_VERSION,
        "repository": plan["repository"],
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": [operation["operation_id"]],
        "allow_destructive": False,
        "approved_by": "maintainer",
        "approved_at": "2026-06-24T00:00:00Z",
    }
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    write_json(plan_path, plan)
    write_json(approval_path, approval)
    return plan_path, approval_path, plan, operation


def raw_issue(number: int, *, milestone: int | None = None) -> dict[str, Any]:
    return {
        "number": number,
        "title": "[Epic] Backend",
        "state": "open",
        "state_reason": None,
        "body": "",
        "labels": [{"name": "epic"}],
        "milestone": None
        if milestone is None
        else {"number": milestone, "title": "Initial release", "state": "open"},
        "assignees": [],
        "user": {"login": "dckallos"},
        "created_at": "2026-06-20T00:00:00Z",
        "updated_at": "2026-06-23T00:00:00Z",
        "closed_at": None,
        "comments": 0,
        "locked": False,
        "html_url": f"https://example.test/issues/{number}",
    }


def test_apply_dry_run_performs_only_live_get_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    runner = QueueRunner([response(raw_issue(68))])
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=True,
        execute=False,
        confirm_repo=None,
        lock_path=None,
        receipt=None,
    )

    code = triage.apply_plan(args, runner=runner)

    assert code == 0
    assert [call[3] for call in runner.calls] == ["GET"]
    assert "Dry run only" in capsys.readouterr().out


def test_apply_dry_run_blocks_stale_precondition(tmp_path: Path) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    runner = QueueRunner([response({**raw_issue(68), "state": "closed"})])
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=True,
        execute=False,
        confirm_repo=None,
        lock_path=None,
        receipt=None,
    )

    assert triage.apply_plan(args, runner=runner) == 1
    assert [call[3] for call in runner.calls] == ["GET"]


def test_execute_requires_explicit_environment_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    runner = QueueRunner([response(raw_issue(68))])
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=False,
        execute=True,
        confirm_repo="dckallos/dbt-diagnostics",
        lock_path=tmp_path / "lock",
        receipt=tmp_path / "receipt.json",
    )
    monkeypatch.delenv("TRIAGE_ENABLE_GITHUB_WRITES", raising=False)

    with pytest.raises(triage.TriageError, match="TRIAGE_ENABLE_GITHUB_WRITES"):
        triage.apply_plan(args, runner=runner)

    assert [call[3] for call in runner.calls] == ["GET"]


def test_execute_uses_stdin_body_and_verifies_result_with_fake_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, approval_path, plan, operation = prepare_plan_and_approval(tmp_path)
    runner = QueueRunner(
        [
            response(raw_issue(68)),
            response(raw_issue(68)),
            response(raw_issue(68, milestone=1)),
            response(raw_issue(68, milestone=1)),
        ]
    )
    receipt = tmp_path / "receipt.json"
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=False,
        execute=True,
        confirm_repo="dckallos/dbt-diagnostics",
        lock_path=tmp_path / "lock",
        receipt=receipt,
    )
    monkeypatch.setenv("TRIAGE_ENABLE_GITHUB_WRITES", "1")

    code = triage.apply_plan(args, runner=runner)

    assert code == 0
    assert [call[3] for call in runner.calls] == ["GET", "GET", "PATCH", "GET"]
    assert runner.inputs[2] == json.dumps(
        {"milestone": 1}, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    receipt_data = json.loads(receipt.read_text(encoding="ascii"))
    assert receipt_data["executed_operation_ids"] == [operation["operation_id"]]
    assert not (tmp_path / "lock").exists()


def test_parse_issue_filter_is_strict() -> None:
    assert triage.parse_issue_filter("54, 68,54") == {54, 68}
    with pytest.raises(triage.TriageError, match="invalid issue number"):
        triage.parse_issue_filter("54, nope")


def test_validate_policy_rejects_issue_in_multiple_batches() -> None:
    value = policy()
    value["planning"]["canary_issue_numbers"] = [68]
    with pytest.raises(triage.TriageError, match="multiple planning batches"):
        triage.validate_policy(value)


def test_offline_audit_cli_reads_snapshot_without_github(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        (triage.DEFAULT_POLICY).read_text(encoding="ascii"), encoding="ascii"
    )
    snapshot_path = tmp_path / "snapshot.json"
    saved_snapshot = snapshot([issue(54, labels=["bug"], milestone=1)], labels=["bug"])
    saved_snapshot["policy_sha256"] = triage.sha256_json(
        triage.load_policy(policy_path)
    )
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    write_json(snapshot_path, saved_snapshot)
    runner = QueueRunner([])

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "audit",
            "--snapshot",
            str(snapshot_path),
            "--issues",
            "54",
            "--json",
        ],
        runner=runner,
    )

    assert code in {0, 1}
    assert runner.calls == []
    json.loads(capsys.readouterr().out)


def test_validate_snapshot_rejects_tampering() -> None:
    value = snapshot([issue(1, labels=["bug"])], labels=["bug"])
    value["issues"][0]["title"] = "changed after snapshot"

    with pytest.raises(triage.TriageError, match="snapshot digest mismatch"):
        triage.validate_snapshot(value)


def test_missing_live_label_is_a_finding_but_not_a_plannable_operation() -> None:
    snap = snapshot(
        [issue(70, title="refactor: seam", labels=["snowflake"])], labels=["snowflake"]
    )

    findings = triage.audit_snapshot(snap, policy(check_missing_repo_paths=False))

    mismatch = next(item for item in findings if item["code"] == "title-label-mismatch")
    assert "suggested_operation" not in mismatch
    assert any(
        item["code"] == "policy-label-missing" and item["data"] == "architecture"
        for item in findings
    )


def test_approval_requires_named_timestamped_approver() -> None:
    operation, _ = operation_for_issue(68)
    plan = {
        "schema_version": triage.PLAN_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_sha256": "snapshot",
        "policy_sha256": "policy",
        "findings_sha256": "findings",
        "operations": [operation],
        "maintainer_decisions": [],
        "safety": {},
    }
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "schema_version": triage.APPROVAL_SCHEMA_VERSION,
        "repository": plan["repository"],
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": [operation["operation_id"]],
        "allow_destructive": False,
        "approved_by": "",
        "approved_at": "",
    }

    with pytest.raises(triage.TriageError, match="approved_by"):
        triage.validate_approval(plan, approval, plan["plan_sha256"], "bootstrap")


def test_plan_markdown_escapes_non_ascii_dynamic_text() -> None:
    plan = {
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_sha256": "snapshot",
        "plan_sha256": "plan",
        "operations": [],
        "maintainer_decisions": [],
    }
    rendered = triage.render_plan_markdown(
        plan,
        [
            {
                "level": "warning",
                "code": "example",
                "issue": 1,
                "message": "non-ASCII label: caf\u00e9",
            }
        ],
    )

    rendered.encode("ascii")
    assert "caf\\xe9" in rendered


def test_execute_stale_just_in_time_preflight_writes_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    stale = raw_issue(68, milestone=2)
    runner = QueueRunner([response(raw_issue(68)), response(stale)])
    receipt = tmp_path / "receipt.json"
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=False,
        execute=True,
        confirm_repo="dckallos/dbt-diagnostics",
        lock_path=tmp_path / "lock",
        receipt=receipt,
    )
    monkeypatch.setenv("TRIAGE_ENABLE_GITHUB_WRITES", "1")

    with pytest.raises(triage.TriageError, match="became stale"):
        triage.apply_plan(args, runner=runner)

    assert [call[3] for call in runner.calls] == ["GET", "GET"]
    assert json.loads(receipt.read_text(encoding="ascii"))["status"] == "failed"
    assert not (tmp_path / "lock").exists()


def test_execute_write_failure_records_partial_failure_without_raw_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    runner = QueueRunner(
        [
            response(raw_issue(68)),
            response(raw_issue(68)),
            response("", returncode=1, stderr="request rejected"),
        ]
    )
    receipt = tmp_path / "receipt.json"
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=False,
        execute=True,
        confirm_repo="dckallos/dbt-diagnostics",
        lock_path=tmp_path / "lock",
        receipt=receipt,
    )
    monkeypatch.setenv("TRIAGE_ENABLE_GITHUB_WRITES", "1")

    with pytest.raises(triage.TriageError, match="request rejected"):
        triage.apply_plan(args, runner=runner)

    data = json.loads(receipt.read_text(encoding="ascii"))
    assert data["status"] == "failed"
    assert data["executed_operation_ids"] == []
    assert not (tmp_path / "lock").exists()


def test_apply_rejects_plan_for_repository_other_than_policy(tmp_path: Path) -> None:
    plan_path, approval_path, plan, _ = prepare_plan_and_approval(tmp_path)
    args = argparse.Namespace(
        plan=plan_path,
        approval=approval_path,
        plan_sha=plan["plan_sha256"],
        batch="bootstrap",
        dry_run=True,
        execute=False,
        confirm_repo=None,
        lock_path=None,
        receipt=None,
    )

    with pytest.raises(triage.TriageError, match="does not match"):
        triage.apply_plan(
            args,
            runner=QueueRunner([]),
            expected_repo="another/repository",
        )


def test_policy_rejects_same_label_in_add_and_remove() -> None:
    value = policy()
    value["desired"] = {
        "issue": [
            {
                "number": 1,
                "labels_add": ["bug"],
                "labels_remove": ["BUG"],
            }
        ]
    }

    with pytest.raises(triage.TriageError, match="adds and removes"):
        triage.validate_policy(value)


def test_label_add_suggestion_is_split_into_atomic_operations() -> None:
    snap = snapshot(
        [issue(1, title="fix: example", labels=[])],
        labels=["bug", "priority: now"],
    )

    operations = triage.operation_from_suggestion(
        {
            "kind": "issue.labels.add",
            "issue_number": 1,
            "labels": ["bug", "priority: now"],
            "batch": "bootstrap",
            "reason": "Apply approved labels.",
        },
        snapshot=snap,
    )

    assert len(operations) == 2
    assert [item["request"]["body"]["labels"] for item in operations] == [
        ["bug"],
        ["priority: now"],
    ]


def test_explicit_desired_operation_overrides_identical_audit_batch() -> None:
    snap = snapshot(
        [issue(68, title="[Epic] Backend", labels=["epic"])],
        labels=["epic"],
    )
    active_policy = policy(check_missing_repo_paths=False)
    active_policy["desired"] = {
        "issue": [
            {
                "number": 68,
                "batch": "canary",
                "reason": "Maintainer-approved canary assignment.",
                "milestone_number": 1,
            }
        ]
    }
    snap["policy_sha256"] = triage.sha256_json(active_policy)
    snap["snapshot_sha256"] = triage.sha256_json(triage.snapshot_without_digest(snap))
    findings = triage.audit_snapshot(snap, active_policy)

    plan = triage.make_plan(
        snap,
        active_policy,
        findings,
        now=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )

    assert len(plan["operations"]) == 1
    assert plan["operations"][0]["batch"] == "canary"
    assert plan["operations"][0]["reason"] == "Maintainer-approved canary assignment."


def test_conflicting_milestone_desires_stop_plan_generation() -> None:
    current = issue(68, title="[Epic] Backend", labels=["epic"], milestone=2)
    snap = snapshot([current], labels=["epic"])
    active_policy = policy(check_missing_repo_paths=False)
    active_policy["desired"] = {
        "issue": [
            {
                "number": 68,
                "batch": "bootstrap",
                "reason": "Clear the current milestone.",
                "milestone_number": 0,
            }
        ]
    }
    snap["policy_sha256"] = triage.sha256_json(active_policy)
    snap["snapshot_sha256"] = triage.sha256_json(triage.snapshot_without_digest(snap))
    findings = triage.audit_snapshot(snap, active_policy)

    with pytest.raises(triage.TriageError, match="conflicting operations"):
        triage.make_plan(
            snap,
            active_policy,
            findings,
            now=datetime(2026, 6, 24, tzinfo=timezone.utc),
        )


def test_project_snapshot_is_read_only_and_paginated() -> None:
    active_policy = policy()
    active_policy["project"] = {
        "enabled": True,
        "owner_type": "user",
        "owner": "dckallos",
        "number": 7,
    }
    first_page = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "number": 7,
                    "title": "Release",
                    "closed": False,
                    "url": "https://example.test/project/7",
                    "fields": {
                        "nodes": [
                            {"id": "F1", "name": "Status", "dataType": "SINGLE_SELECT"}
                        ]
                    },
                    "items": {
                        "nodes": [{"id": "I1", "type": "ISSUE", "content": None}],
                        "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                    },
                }
            }
        }
    }
    second_page = {
        "data": {
            "user": {
                "projectV2": {
                    "id": "PVT_1",
                    "number": 7,
                    "title": "Release",
                    "closed": False,
                    "url": "https://example.test/project/7",
                    "fields": {"nodes": []},
                    "items": {
                        "nodes": [{"id": "I2", "type": "ISSUE", "content": None}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }
    }
    runner = QueueRunner([response(first_page), response(second_page)])
    client = triage.GitHubClient(runner=runner, repo="dckallos/dbt-diagnostics")

    result = triage.collect_project_snapshot(client, active_policy)

    assert result["configured"] is True
    assert [item["id"] for item in result["items"]] == ["I1", "I2"]
    assert all(call[:3] == ("gh", "api", "graphql") for call in runner.calls)
    payloads = [json.loads(value or "{}") for value in runner.inputs]
    assert payloads[0]["variables"]["after"] is None
    assert payloads[1]["variables"]["after"] == "cursor-1"
    assert all("mutation" not in payload["query"].casefold() for payload in payloads)


def test_project_snapshot_disabled_performs_no_github_call() -> None:
    runner = QueueRunner([])
    client = triage.GitHubClient(runner=runner, repo="dckallos/dbt-diagnostics")

    result = triage.collect_project_snapshot(client, policy())

    assert result == {"configured": False, "status": "not_configured"}
    assert runner.calls == []


def test_cli_error_sanitizer_redacts_common_secret_shapes() -> None:
    value = (
        "Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz "
        "token=github_pat_secretvalue password=hunter2"
    )
    sanitized = triage.sanitize_cli_error(value)
    assert "ghp_" not in sanitized
    assert "github_pat_" not in sanitized
    assert "hunter2" not in sanitized
    assert sanitized.count("<redacted>") >= 3


def cli_contract_body() -> str:
    return """## Summary

I will complete one bounded governance integration.

## Evidence and confidence

I confirmed the command surface in scripts/triage/triage.py and its focused tests.

## Current wrong behavior

The advertised command does not dispatch through the CLI.

## Root cause

The parser does not connect the existing module implementation.

## Expected behavior

I will expose the existing implementation without broadening write authority.

## Acceptance criteria

- A positive offline command succeeds.
- An invalid input is rejected.
- A missing live dependency degrades without a GitHub write.
- Existing metadata planning and apply gates remain unchanged in regression tests.

## Focused test plan

I will run positive, negative, degradation, and regression tests.

## Scope and likely files

- scripts/triage/triage.py
- scripts/triage/test_triage.py

## Explicit non-goals

- I will not mutate an issue body.
- I will not broaden the metadata operation allowlist.

## Dependencies and traceability

- None.
"""


def write_cli_offline_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        triage.DEFAULT_POLICY.read_text(encoding="ascii"), encoding="ascii"
    )
    loaded_policy = triage.load_policy(policy_path)
    configured_labels = sorted(
        {label for values in loaded_policy["labels"].values() for label in values}
    )
    saved_snapshot = snapshot(
        [
            issue(
                101,
                title="fix: wire governance command surface",
                body=cli_contract_body(),
                labels=["bug"],
            )
        ],
        labels=configured_labels,
    )
    saved_snapshot["policy_sha256"] = triage.sha256_json(loaded_policy)
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    snapshot_path = tmp_path / "snapshot.json"
    write_json(snapshot_path, saved_snapshot)

    semantic_path = tmp_path / "semantic.json"
    write_json(
        semantic_path,
        {
            "101": {
                "status": "accepted",
                "source_claims_checked": ["scripts/triage/triage.py"],
                "tests_checked": ["scripts/triage/test_triage.py"],
                "one_pr_coherent": True,
                "confidence": "high",
                "dependency_merge_evidence": True,
            }
        },
    )
    return policy_path, snapshot_path, semantic_path, saved_snapshot


def test_help_lists_and_parses_all_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = {
        "snapshot",
        "audit",
        "plan",
        "apply",
        "contract",
        "review-packet",
        "standardize",
        "frontier",
        "project-plan",
        "backlog-synthesis",
        "synthesis-review-packet",
    }
    parser = triage.build_parser()
    top_help = parser.format_help()
    for command in expected:
        assert command in top_help
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([command, "--help"])
        assert exc.value.code == 0
    capsys.readouterr()


def test_snapshot_and_apply_dispatch_through_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path, _snapshot_path, _semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    calls: list[str] = []

    def fake_resolve_snapshot(*args: object, **kwargs: object) -> dict[str, Any]:
        del args, kwargs
        calls.append("snapshot")
        return saved_snapshot

    def fake_apply_plan(*args: object, **kwargs: object) -> int:
        del args, kwargs
        calls.append("apply")
        return 0

    monkeypatch.setattr(triage, "resolve_snapshot", fake_resolve_snapshot)
    monkeypatch.setattr(triage, "apply_plan", fake_apply_plan)

    assert (
        triage.main(["--policy", str(policy_path), "snapshot"], runner=QueueRunner([]))
        == 0
    )
    json.loads(capsys.readouterr().out)

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "apply",
                "--plan",
                str(tmp_path / "plan.json"),
                "--approval",
                str(tmp_path / "approval.json"),
                "--plan-sha",
                "a" * 64,
                "--batch",
                "bootstrap",
                "--dry-run",
            ],
            runner=QueueRunner([]),
        )
        == 0
    )
    assert calls == ["snapshot", "apply"]


def test_offline_contract_review_and_standardize_are_local_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, _saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    runner = QueueRunner([])

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "contract",
            "--issue",
            "101",
            "--snapshot",
            str(snapshot_path),
            "--json",
        ],
        runner=runner,
    )
    assert code == 0
    contract = json.loads(capsys.readouterr().out)
    assert contract["contract_accepted"] is True

    output_dir = tmp_path / "issue-101"
    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "review-packet",
            "--issue",
            "101",
            "--snapshot",
            str(snapshot_path),
            "--semantic-evidence",
            str(semantic_path),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
        runner=runner,
    )
    assert code == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["issue"]["number"] == 101
    assert packet["issue"]["body_truncated"] is False
    assert (output_dir / "review-packet.json").is_file()
    assert (output_dir / "contract.json").is_file()
    proposed_path = output_dir / "proposed-body.md"
    assert proposed_path.is_file()

    proposed_text = proposed_path.read_text(encoding="ascii")
    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "standardize",
            "--issue",
            "101",
            "--snapshot",
            str(snapshot_path),
            "--proposed-body",
            str(proposed_path),
            "--output-dir",
            str(output_dir),
            "--json",
        ],
        runner=runner,
    )
    assert code == 0
    standardization = json.loads(capsys.readouterr().out)
    assert standardization["local_only"] is True
    assert standardization["github_mutation"] is False
    assert (output_dir / "proposed-body.md").read_text(
        encoding="ascii"
    ) == proposed_text
    assert runner.calls == []


def test_official_docs_review_packet_and_standardize_flow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        triage.DEFAULT_POLICY.read_text(encoding="ascii"), encoding="ascii"
    )
    loaded_policy = triage.load_policy(policy_path)
    configured_labels = sorted(
        {label for values in loaded_policy["labels"].values() for label in values}
    )
    external_body = """## Summary

I will complete one bounded GitHub Actions integration.

## Evidence and confidence

The current issue depends on GitHub Actions workflow dispatch semantics.

## User-visible problem or current gap

The implementation depends on GitHub Actions workflow_dispatch behavior.

## Expected behavior or target outcome

The issue records the official GitHub Actions documentation that supports the claim.

## Acceptance criteria

- A positive offline command succeeds.
- An invalid input is rejected.
- Existing metadata planning remains unchanged in regression tests.

## Focused test plan

I will run positive, negative, and regression tests.

## Scope and likely files

- scripts/triage/triage.py

## Explicit non-goals

- No GitHub metadata mutation.

## Dependencies and traceability

- Parent epic: #93.
"""
    saved_snapshot = snapshot(
        [
            issue(
                115,
                title="feat: verify GitHub Actions workflow dispatch",
                body=external_body,
                labels=["enhancement"],
            )
        ],
        labels=configured_labels,
    )
    saved_snapshot["policy_sha256"] = triage.sha256_json(loaded_policy)
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    snapshot_path = tmp_path / "snapshot.json"
    write_json(snapshot_path, saved_snapshot)

    semantic_path = tmp_path / "semantic.json"
    write_json(
        semantic_path,
        {
            "115": {
                "status": "accepted",
                "source_claims_checked": ["scripts/triage/triage.py"],
                "tests_checked": ["scripts/triage/test_triage.py"],
                "one_pr_coherent": True,
                "confidence": "high",
                "dependency_merge_evidence": True,
            }
        },
    )
    runner = QueueRunner([])
    output_dir = tmp_path / "issue-115"

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "review-packet",
                "--issue",
                "115",
                "--snapshot",
                str(snapshot_path),
                "--semantic-evidence",
                str(semantic_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    capsys.readouterr()
    proposed_path = output_dir / "proposed-body.md"
    proposed = proposed_path.read_text(encoding="ascii")
    assert "## Official documentation evidence" in proposed
    assert triage.issue_contract.UNRESOLVED_PLACEHOLDER in proposed

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "standardize",
                "--issue",
                "115",
                "--snapshot",
                str(snapshot_path),
                "--proposed-body",
                str(proposed_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 1
    )
    unresolved = json.loads(capsys.readouterr().out)
    assert unresolved["accepted"] is False
    assert any(
        item["code"] == "unresolved-placeholder-section"
        and item["section"] == "official_docs"
        for item in unresolved["contract"]["findings"]
    )

    proposed_path.write_text(
        proposed.replace(
            triage.issue_contract.UNRESOLVED_PLACEHOLDER,
            """- Provider: GitHub Actions
- Official URL: https://docs.github.com/en/actions
- Supported claim: GitHub Actions workflow dispatch semantics are external to this repository.
- Docs version or product version: Current hosted GitHub Docs; no pinned product version.
- Retrieval date: 2026-06-27.
- Residual uncertainty: Maintainer review must verify the issue interpretation.""",
        ),
        encoding="ascii",
    )

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "standardize",
                "--issue",
                "115",
                "--snapshot",
                str(snapshot_path),
                "--proposed-body",
                str(proposed_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["accepted"] is True
    assert accepted["local_only"] is True
    assert accepted["github_mutation"] is False
    assert runner.calls == []


def test_unknown_external_docs_review_packet_and_standardize_flow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(
        triage.DEFAULT_POLICY.read_text(encoding="ascii"), encoding="ascii"
    )
    loaded_policy = triage.load_policy(policy_path)
    configured_labels = sorted(
        {label for values in loaded_policy["labels"].values() for label in values}
    )
    external_body = """## Summary

I will complete one bounded AcmeCloud CLI integration.

## Evidence and confidence

The current issue depends on an AcmeCloud CLI contract outside this repository.

## User-visible problem or current gap

The implementation depends on an AcmeCloud CLI flag guarantee.

## Expected behavior or target outcome

The issue records the official source or explicit uncertainty.

## Acceptance criteria

- A positive offline command succeeds.
- An invalid input is rejected.
- Existing metadata planning remains unchanged in regression tests.

## Focused test plan

I will run positive, negative, and regression tests.

## Scope and likely files

- scripts/triage/triage.py

## Explicit non-goals

- No GitHub metadata mutation.

## Dependencies and traceability

- Parent epic: #93.
"""
    saved_snapshot = snapshot(
        [
            issue(
                115,
                title="feat: document AcmeCloud CLI contract",
                body=external_body,
                labels=["enhancement"],
            )
        ],
        labels=configured_labels,
    )
    saved_snapshot["policy_sha256"] = triage.sha256_json(loaded_policy)
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    snapshot_path = tmp_path / "snapshot.json"
    write_json(snapshot_path, saved_snapshot)

    semantic_path = tmp_path / "semantic.json"
    write_json(
        semantic_path,
        {
            "115": {
                "status": "accepted",
                "source_claims_checked": ["scripts/triage/triage.py"],
                "tests_checked": ["scripts/triage/test_triage.py"],
                "one_pr_coherent": True,
                "confidence": "high",
                "dependency_merge_evidence": True,
            }
        },
    )
    runner = QueueRunner([])
    output_dir = tmp_path / "issue-115"

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "review-packet",
                "--issue",
                "115",
                "--snapshot",
                str(snapshot_path),
                "--semantic-evidence",
                str(semantic_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    capsys.readouterr()
    proposed_path = output_dir / "proposed-body.md"
    proposed = proposed_path.read_text(encoding="ascii")
    assert "## Official documentation evidence" in proposed
    assert triage.issue_contract.UNRESOLVED_PLACEHOLDER in proposed

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "standardize",
                "--issue",
                "115",
                "--snapshot",
                str(snapshot_path),
                "--proposed-body",
                str(proposed_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 1
    )
    unresolved = json.loads(capsys.readouterr().out)
    assert unresolved["accepted"] is False
    assert any(
        item["code"] == "unresolved-placeholder-section"
        and item["section"] == "official_docs"
        for item in unresolved["contract"]["findings"]
    )
    assert runner.calls == []


def test_standardize_rejects_unresolved_content_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A fabricated or stale content anchor in an otherwise conformant body must
    # block standardize acceptance, so a fake quote or symbol cannot reach the
    # tracker even when every required section is present.
    policy_path, snapshot_path, semantic_path, _saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    runner = QueueRunner([])
    output_dir = tmp_path / "issue-101"
    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "review-packet",
                "--issue",
                "101",
                "--snapshot",
                str(snapshot_path),
                "--semantic-evidence",
                str(semantic_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    capsys.readouterr()
    proposed_path = output_dir / "proposed-body.md"

    def run_standardize() -> int:
        return triage.main(
            [
                "--policy",
                str(policy_path),
                "standardize",
                "--issue",
                "101",
                "--snapshot",
                str(snapshot_path),
                "--proposed-body",
                str(proposed_path),
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            runner=runner,
        )

    # Control: the conformant body with resolving anchors is accepted.
    assert run_standardize() == 0
    control = json.loads(capsys.readouterr().out)
    assert control["anchors_resolved"] is True
    assert control["accepted"] is True

    # Inject a fabricated symbol anchor against a real repository file.
    base = proposed_path.read_text(encoding="ascii")
    proposed_path.write_text(
        base + "\nSee scripts/triage/contract.py:totally_fake_symbol_xyz here.\n",
        encoding="ascii",
    )
    assert run_standardize() == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["anchors_resolved"] is False
    assert rejected["accepted"] is False
    assert any(
        anchor["path"] == "scripts/triage/contract.py"
        and anchor["anchor"] == "totally_fake_symbol_xyz"
        for anchor in rejected["unresolved_file_anchors"]
    )
    assert runner.calls == []


def test_audit_plan_and_frontier_compose_offline_deterministically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, _saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    runner = QueueRunner([])

    audit_path = tmp_path / "audit-unready.json"
    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "audit",
                "--snapshot",
                str(snapshot_path),
                "--output",
                str(audit_path),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    audit_stdout = json.loads(capsys.readouterr().out)
    assert audit_stdout == json.loads(audit_path.read_text(encoding="ascii"))
    assert "metadata_findings" in audit_stdout
    assert audit_stdout["issues"][0]["implementation_state"] == "needs_semantic_review"

    audit_frontier_args = [
        "--policy",
        str(policy_path),
        "frontier",
        "--mode",
        "audit",
        "--snapshot",
        str(snapshot_path),
        "--audit-file",
        str(audit_path),
        "--json",
    ]
    assert triage.main(audit_frontier_args, runner=runner) == 0
    first = json.loads(capsys.readouterr().out)
    assert triage.main(audit_frontier_args, runner=runner) == 0
    second = json.loads(capsys.readouterr().out)
    assert first == second
    assert first["selected_issue"] == 101

    plan_dir = tmp_path / "plan"
    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "plan",
                "--snapshot",
                str(snapshot_path),
                "--semantic-evidence",
                str(semantic_path),
                "--output-dir",
                str(plan_dir),
            ],
            runner=runner,
        )
        == 0
    )
    capsys.readouterr()
    ready_audit = json.loads((plan_dir / "audit.json").read_text(encoding="ascii"))
    assert ready_audit["issues"][0]["implementation_state"] == "ready"
    triage.validate_readiness_audit(
        ready_audit,
        json.loads(snapshot_path.read_text(encoding="ascii")),
    )

    packet_path = tmp_path / "worker-packet.json"
    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "frontier",
                "--mode",
                "implement",
                "--snapshot",
                str(snapshot_path),
                "--audit-file",
                str(plan_dir / "audit.json"),
                "--packet-output",
                str(packet_path),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    coordinator = json.loads(capsys.readouterr().out)
    assert coordinator["selected_issue"] == 101
    assert packet_path.is_file()
    packet = json.loads(packet_path.read_text(encoding="ascii"))
    assert packet["issue"]["number"] == 101
    assert (
        len(packet["issue"]["body"])
        <= triage.issue_frontier.MAX_WORKER_ISSUE_BODY_CHARS
    )

    empty_packet = tmp_path / "empty-packet.json"
    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "frontier",
                "--mode",
                "implement",
                "--snapshot",
                str(snapshot_path),
                "--audit-file",
                str(plan_dir / "audit.json"),
                "--empty-selection",
                "--packet-output",
                str(empty_packet),
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    empty = json.loads(capsys.readouterr().out)
    assert empty["selected_issue"] is None
    assert not empty_packet.exists()

    assert (
        triage.main(
            [
                "--policy",
                str(policy_path),
                "frontier",
                "--mode",
                "implement",
                "--snapshot",
                str(snapshot_path),
                "--audit-file",
                str(plan_dir / "audit.json"),
                "--issues",
                "none",
                "--json",
            ],
            runner=runner,
        )
        == 0
    )
    empty_by_filter = json.loads(capsys.readouterr().out)
    assert empty_by_filter["selected_issue"] is None
    assert runner.calls == []


def test_project_plan_cli_emits_json_without_github_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
    )
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, readiness)
    runner = QueueRunner([])

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "project-plan",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--json",
        ],
        runner=runner,
    )

    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["schema_version"] == triage.issue_frontier.PROJECT_PLAN_SCHEMA_VERSION
    assert plan["project"]["enabled"] is False
    assert plan["safety"]["github_api_calls"] is False
    assert plan["safety"]["github_mutations"] is False
    assert "operations" not in plan
    assert all("body" not in item and "state" not in item for item in plan["items"])
    assert runner.calls == []


def test_project_plan_cli_rejects_invalid_self_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
    )
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, readiness)
    output_path = tmp_path / "project-plan.json"
    runner = QueueRunner([])

    monkeypatch.setattr(
        triage.issue_frontier,
        "validate_project_plan",
        lambda _plan: ["broken shape"],
    )

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "project-plan",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--output",
            str(output_path),
        ],
        runner=runner,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "project-plan validation failed: broken shape" in captured.err
    assert not output_path.exists()
    assert runner.calls == []


def test_project_plan_cli_rejects_partial_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    saved_snapshot["issues"].append(
        issue(
            102,
            title="fix: second issue",
            body=cli_contract_body(),
            labels=["bug"],
        )
    )
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    write_json(snapshot_path, saved_snapshot)
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
        issue_filter={101},
    )
    audit_path = tmp_path / "partial-audit.json"
    write_json(audit_path, readiness)
    output_path = tmp_path / "project-plan.json"

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "project-plan",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--output",
            str(output_path),
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "readiness audit does not cover the requested project-plan issue(s)" in (
        captured.err
    )
    assert not output_path.exists()


def test_backlog_synthesis_cli_emits_json_without_github_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
    )
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, readiness)
    runner = QueueRunner([])

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "backlog-synthesis",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--json",
        ],
        runner=runner,
    )

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert (
        report["schema_version"]
        == triage.issue_frontier.BACKLOG_SYNTHESIS_SCHEMA_VERSION
    )
    assert report["safety"]["github_api_calls"] is False
    assert report["safety"]["github_mutations"] is False
    assert "operations" not in report
    assert "body" not in json.dumps(report, sort_keys=True)
    assert runner.calls == []


def test_backlog_synthesis_cli_rejects_invalid_self_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
    )
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, readiness)
    output_path = tmp_path / "backlog-synthesis.json"
    runner = QueueRunner([])

    monkeypatch.setattr(
        triage.issue_frontier,
        "validate_backlog_synthesis_report",
        lambda _report: ["broken shape"],
    )

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "backlog-synthesis",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--output",
            str(output_path),
        ],
        runner=runner,
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "backlog-synthesis validation failed: broken shape" in captured.err
    assert not output_path.exists()
    assert runner.calls == []


def test_backlog_synthesis_cli_rejects_partial_audit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    saved_snapshot["issues"].append(
        issue(
            102,
            title="fix: second issue",
            body=cli_contract_body(),
            labels=["bug"],
        )
    )
    saved_snapshot["snapshot_sha256"] = triage.sha256_json(
        triage.snapshot_without_digest(saved_snapshot)
    )
    write_json(snapshot_path, saved_snapshot)
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
        issue_filter={101},
    )
    audit_path = tmp_path / "partial-audit.json"
    write_json(audit_path, readiness)
    output_path = tmp_path / "backlog-synthesis.json"

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "backlog-synthesis",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--output",
            str(output_path),
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "readiness audit does not cover the requested backlog-synthesis issue(s)" in (
        captured.err
    )
    assert not output_path.exists()


def write_synthesis_review_packet_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    policy_path, snapshot_path, semantic_path, saved_snapshot = (
        write_cli_offline_inputs(tmp_path)
    )
    loaded_policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    readiness = triage.make_readiness_audit(
        saved_snapshot,
        loaded_policy,
        semantic_evidence=semantic,
    )
    audit_path = tmp_path / "audit.json"
    write_json(audit_path, readiness)
    report = triage.issue_frontier.build_backlog_synthesis_report(
        saved_snapshot, readiness
    )
    backlog_path = tmp_path / "backlog-synthesis.json"
    write_json(backlog_path, report)
    plan = triage.issue_frontier.build_project_plan(
        saved_snapshot,
        readiness,
        policy=loaded_policy,
    )
    project_plan_path = tmp_path / "project-plan.json"
    write_json(project_plan_path, plan)
    return (
        policy_path,
        snapshot_path,
        audit_path,
        backlog_path,
        project_plan_path,
        saved_snapshot,
        readiness,
        report,
    )


def test_synthesis_review_packet_cli_emits_json_without_github_calls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, _project_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )
    runner = QueueRunner([])

    def fail_collect(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("synthesis-review-packet must not collect live state")

    def fail_subprocess(*_args: object, **_kwargs: object) -> triage.CommandResult:
        raise AssertionError("synthesis-review-packet must not run subprocesses")

    monkeypatch.setattr(triage, "collect_snapshot", fail_collect)
    monkeypatch.setattr(triage.subprocess, "run", fail_subprocess)

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--issues",
            "101",
            "--json",
        ],
        runner=runner,
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    packet = json.loads(captured.out)
    assert (
        packet["schema_version"]
        == triage.issue_frontier.SYNTHESIS_REVIEW_PACKET_SCHEMA_VERSION
    )
    assert packet["packet_scope"]["issue_numbers"] == [101]
    assert packet["source_artifacts"]["snapshot_digest"] == _rest[0]["snapshot_sha256"]
    assert packet["safety"]["github_api_calls"] is False
    assert packet["safety"]["github_mutations"] is False
    assert "operations" not in packet
    assert "body" not in json.dumps(packet, sort_keys=True)
    assert runner.calls == []


def test_synthesis_review_packet_cli_rejects_looser_max_age(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--max-age-hours",
            "169",
            "--json",
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "--max-age-hours cannot exceed the default hard review age" in captured.err
    assert captured.out == ""


def test_synthesis_review_packet_cli_writes_output_and_status_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, project_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )
    output_path = tmp_path / "synthesis-review-packet.json"

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--project-plan",
            str(project_path),
            "--output",
            str(output_path),
            "--json",
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert f"Wrote {output_path}" in captured.err
    stdout_packet = json.loads(captured.out)
    written_packet = json.loads(output_path.read_text(encoding="ascii"))
    assert stdout_packet == written_packet
    project_plan = json.loads(project_path.read_text(encoding="ascii"))
    assert (
        written_packet["source_artifacts"]["project_plan_digest"]
        == project_plan["project_plan_digest"]
    )


def test_synthesis_review_packet_cli_missing_required_file_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )
    backlog_path.unlink()

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--json",
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "backlog-synthesis JSON not found" in captured.err
    assert captured.out == ""


def test_synthesis_review_packet_cli_rejects_invalid_backlog_before_build(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )

    def fail_build(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("builder should not run after invalid backlog input")

    monkeypatch.setattr(
        triage.issue_frontier,
        "build_synthesis_review_packet",
        fail_build,
    )
    monkeypatch.setattr(
        triage.issue_frontier,
        "validate_backlog_synthesis_report",
        lambda _report: ["broken backlog"],
    )

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--output",
            str(tmp_path / "packet.json"),
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "backlog-synthesis validation failed: broken backlog" in captured.err


def test_synthesis_review_packet_cli_rejects_source_digest_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )
    report = json.loads(backlog_path.read_text(encoding="ascii"))
    report["snapshot_digest"] = "9" * 64
    report["backlog_synthesis_digest"] = triage.sha256_json(
        {
            key: value
            for key, value in report.items()
            if key != "backlog_synthesis_digest"
        }
    )
    write_json(backlog_path, report)

    code = triage.main(
        [
            "--policy",
            str(policy_path),
            "synthesis-review-packet",
            "--snapshot",
            str(snapshot_path),
            "--audit-file",
            str(audit_path),
            "--backlog-synthesis",
            str(backlog_path),
            "--json",
        ],
        runner=QueueRunner([]),
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "backlog-synthesis snapshot digest does not match snapshot" in captured.err
    assert captured.out == ""


def test_synthesis_review_packet_cli_output_is_deterministic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy_path, snapshot_path, audit_path, backlog_path, *_rest = (
        write_synthesis_review_packet_inputs(tmp_path)
    )
    args = [
        "--policy",
        str(policy_path),
        "synthesis-review-packet",
        "--snapshot",
        str(snapshot_path),
        "--audit-file",
        str(audit_path),
        "--backlog-synthesis",
        str(backlog_path),
        "--json",
    ]

    left_code = triage.main(args, runner=QueueRunner([]))
    left = capsys.readouterr().out
    right_code = triage.main(args, runner=QueueRunner([]))
    right = capsys.readouterr().out

    assert left_code == 0
    assert right_code == 0
    assert left == right


def test_backlog_synthesis_requires_snapshot_argument() -> None:
    parser = triage.build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["backlog-synthesis", "--json"])

    assert exc.value.code == 2


def test_frontier_rejects_conflicting_audit_sources() -> None:
    parser = triage.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "frontier",
                "--mode",
                "audit",
                "--audit-file",
                "audit.json",
                "--semantic-evidence",
                "semantic.json",
            ]
        )
    assert exc.value.code == 2


def test_metadata_mutation_allowlist_is_exact_and_body_updates_are_forbidden() -> None:
    assert triage.SUPPORTED_OPERATION_KINDS == {
        "issue.labels.add",
        "issue.labels.remove",
        "issue.milestone.set",
        "issue.milestone.clear",
    }
    assert all(
        not kind.startswith("project.") for kind in triage.SUPPORTED_OPERATION_KINDS
    )
    assert "issue.body.update" in triage.FORBIDDEN_OPERATION_KINDS
    assert "issue.title.update" in triage.FORBIDDEN_OPERATION_KINDS
    assert "project.create" in triage.FORBIDDEN_OPERATION_KINDS


def test_audit_coverage_gap_detects_partial_audit() -> None:
    snap = snapshot([issue(1), issue(2)])
    partial = {"issues": [{"issue_number": 1}]}
    # No filter: frontier ranks the whole snapshot, so the uncovered issue 2
    # must be reported (this is the bug the coverage gate prevents).
    assert triage.audit_coverage_gap(partial, snap, None) == [2]
    # A filter matching the audit scope is covered.
    assert triage.audit_coverage_gap(partial, snap, {1}) == []
    # An explicit empty selection requires no coverage.
    assert triage.audit_coverage_gap(partial, snap, set()) == []
    # A full audit covers the whole snapshot.
    full = {"issues": [{"issue_number": 1}, {"issue_number": 2}]}
    assert triage.audit_coverage_gap(full, snap, None) == []


def test_make_readiness_audit_records_scope(tmp_path: Path) -> None:
    policy_path, snapshot_path, semantic_path, saved_snapshot = write_cli_offline_inputs(
        tmp_path
    )
    policy = triage.load_policy(policy_path)
    semantic = triage.load_semantic_evidence(semantic_path)
    full = triage.make_readiness_audit(
        saved_snapshot, policy, semantic_evidence=semantic
    )
    partial = triage.make_readiness_audit(
        saved_snapshot, policy, semantic_evidence=semantic, issue_filter={101}
    )
    assert full["audit_scope"] is None
    assert partial["audit_scope"] == [101]
