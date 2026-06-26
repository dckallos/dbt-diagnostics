from __future__ import annotations

import json
from pathlib import Path

from scripts.triage import frontier


def snapshot(*issues: dict, pulls: list[dict] | None = None) -> dict:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "snapshot_digest": "a" * 64,
        "repository": "dckallos/dbt-diagnostics",
        "issues": list(issues),
        "pulls": pulls or [],
    }


def issue(
    number: int,
    *,
    title: str | None = None,
    labels: list[str] | None = None,
    state: str = "open",
    body: str = "",
) -> dict:
    return {
        "number": number,
        "title": title or f"fix: issue {number}",
        "labels": labels or ["bug"],
        "state": state,
        "body": body,
        "html_url": f"https://github.com/dckallos/dbt-diagnostics/issues/{number}",
    }


def audit(*entries: dict) -> dict:
    return {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_digest": "a" * 64,
        "audit_digest": "b" * 64,
        "issues": list(entries),
    }


def entry(
    number: int,
    *,
    governance: str = "conformant",
    implementation: str = "ready",
    release_gate: bool = False,
    dependencies: list[int] | None = None,
    impact: int = 0,
    **extra: object,
) -> dict:
    value: dict[str, object] = {
        "issue_number": number,
        "title": f"fix: issue {number}",
        "issue_kind": "bug_fix",
        "contract_id": "dbt-diagnostics.issue-contract.v1",
        "contract_version": "1.0",
        "body_digest": f"body-{number}",
        "governance_state": governance,
        "contract_accepted": governance == "conformant",
        "implementation_state": implementation,
        "release_gate": release_gate,
        "dependency_impact": impact,
        "direct_dependencies": dependencies or [],
        "dependency_merge_evidence": not bool(dependencies),
        "dependency_cycles": [],
        "required_decisions": [],
        "required_external_evidence": [],
        "missing_repository_paths": [],
        "active_pr_conflicts": [],
        "overlap_conflicts": [],
        "blockers": [],
        "parent_epics": [4],
        "referenced_paths": [],
        "source_claims_checked": [],
        "semantic_review_notes": [],
    }
    value.update(extra)
    return value


def test_merged_pull_request_dependency_is_implementable() -> None:
    # A ready issue whose only direct dependency is a merged pull request must be
    # a candidate. The PR lives in the pulls map, not issues, so the closure
    # check must consult pull_map instead of rejecting it as not closed.
    snap = snapshot(
        issue(1),
        pulls=[
            {
                "number": 73,
                "state": "closed",
                "state_reason": None,
                "title": "land it",
            }
        ],
    )
    results = audit(entry(1, dependencies=[73], dependency_merge_evidence=True))
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert [item["issue_number"] for item in candidates] == [1]
    assert rejected == []


def test_open_pull_request_dependency_is_not_implementable() -> None:
    # An open PR dependency is not closed, so the issue is rejected. This guards
    # the closed-versus-open distinction the pull-aware check must preserve.
    snap = snapshot(
        issue(1),
        pulls=[
            {"number": 73, "state": "open", "state_reason": None, "title": "wip"}
        ],
    )
    results = audit(entry(1, dependencies=[73], dependency_merge_evidence=True))
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert candidates == []
    assert any(
        "direct dependencies are not closed" in reason
        for item in rejected
        for reason in item["reasons"]
    )


def test_worker_packet_resolves_merged_pull_request_dependency(tmp_path: Path) -> None:
    # The worker packet must show a merged-PR dependency with its real closed
    # state, not "unknown", which it would report if it consulted only issues.
    snap = snapshot(
        issue(1),
        pulls=[
            {
                "number": 73,
                "state": "closed",
                "state_reason": None,
                "title": "land it",
            }
        ],
    )
    results = audit(entry(1, dependencies=[73], dependency_merge_evidence=True))
    packet = frontier.build_worker_packet(1, snap, results, root=tmp_path)
    dependency = next(
        item for item in packet["dependencies"] if item["issue_number"] == 73
    )
    assert dependency["state"] == "closed"
    assert dependency["title"] == "land it"


def test_audit_frontier_prioritizes_unsafe_release_work() -> None:
    snap = snapshot(
        issue(1, labels=["bug", "priority: now"]),
        issue(2, labels=["bug", "priority: now"]),
    )
    results = audit(
        entry(1, governance="unsafe", implementation="unsafe", release_gate=False),
        entry(2, governance="stale", implementation="stale", release_gate=True),
    )
    candidates = frontier.audit_frontier_candidates(snap, results)
    assert candidates[0]["issue_number"] == 1


def test_audit_frontier_tie_breaks_by_issue_number() -> None:
    snap = snapshot(issue(2), issue(1))
    results = audit(
        entry(
            2,
            governance="needs_contract_revision",
            implementation="needs_contract_revision",
        ),
        entry(
            1,
            governance="needs_contract_revision",
            implementation="needs_contract_revision",
        ),
    )
    candidates = frontier.audit_frontier_candidates(snap, results)
    assert [item["issue_number"] for item in candidates] == [1, 2]


def test_implementation_frontier_requires_ready_and_accepted() -> None:
    snap = snapshot(issue(1), issue(2))
    results = audit(
        entry(1, governance="conformant", implementation="ready"),
        entry(2, governance="needs_contract_revision", implementation="ready"),
    )
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert [item["issue_number"] for item in candidates] == [1]
    assert rejected[0]["issue_number"] == 2


def test_implementation_frontier_rejects_open_dependency() -> None:
    snap = snapshot(issue(1), issue(2))
    results = audit(entry(1, dependencies=[2]), entry(2))
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert 1 not in [item["issue_number"] for item in candidates]
    rejected_one = next(item for item in rejected if item["issue_number"] == 1)
    assert any("not closed" in reason for reason in rejected_one["reasons"])


def test_implementation_frontier_requires_merge_evidence_for_closed_dependency() -> (
    None
):
    snap = snapshot(issue(1), issue(2, state="closed"))
    results = audit(entry(1, dependencies=[2], dependency_merge_evidence=False))
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert candidates == []
    assert any("merge evidence" in reason for reason in rejected[0]["reasons"])


def test_implementation_frontier_accepts_closed_merged_dependency() -> None:
    snap = snapshot(issue(1), issue(2, state="closed"))
    results = audit(entry(1, dependencies=[2], dependency_merge_evidence=True))
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert [item["issue_number"] for item in candidates] == [1]
    assert rejected == []


def test_implementation_frontier_rejects_decision_external_path_pr_and_cycle() -> None:
    snap = snapshot(issue(1))
    results = audit(
        entry(
            1,
            required_decisions=["choose"],
            required_external_evidence=["fixture"],
            missing_repository_paths=["docs/MISSING.md"],
            active_pr_conflicts=[10],
            dependency_cycles=[[1, 1]],
        )
    )
    candidates, rejected = frontier.implementation_frontier_candidates(snap, results)
    assert candidates == []
    assert len(rejected[0]["reasons"]) >= 5


def test_empty_frontier_returns_explicit_no_selection() -> None:
    result = frontier.build_coordinator_result(
        "implement",
        snapshot(issue(1)),
        audit(entry(1, implementation="blocked", blockers=["blocked"])),
    )
    assert result["selected_issue"] is None
    assert result["selection_reason"] == "frontier is empty"
    assert frontier.validate_coordinator_result(result) == []


def test_coordinator_json_is_deterministic() -> None:
    snap = snapshot(issue(1, labels=["bug", "priority: now"]))
    results = audit(entry(1, release_gate=True, impact=3))
    first = frontier.build_coordinator_result("implement", snap, results)
    second = frontier.build_coordinator_result("implement", snap, results)
    assert first == second
    assert first["selected_issue"] == 1
    assert first["suggested_branch"].startswith("fix/1-")
    assert frontier.validate_coordinator_result(first) == []


def test_coordinator_digest_validation_detects_mutation() -> None:
    result = frontier.build_coordinator_result(
        "implement", snapshot(issue(1)), audit(entry(1))
    )
    result["selection_reason"] = "tampered"
    assert "coordinator_digest mismatch" in frontier.validate_coordinator_result(result)


def test_worker_packet_is_bounded_to_selected_issue(tmp_path: Path) -> None:
    body = """## Summary

Implement one issue.

## Acceptance criteria

- Positive case succeeds.

## Explicit non-goals

- No unrelated work.
"""
    snap = snapshot(
        issue(1, body=body),
        issue(4, title="[Epic] Parent", labels=["epic"], body="- [ ] #1 child"),
        issue(99, body="secret unrelated tracker body"),
    )
    results = audit(entry(1, parent_epics=[4], referenced_paths=[]))
    packet = frontier.build_worker_packet(1, snap, results, root=tmp_path)
    encoded = str(packet)
    assert packet["issue"]["number"] == 1
    assert "secret unrelated tracker body" not in encoded
    assert packet["acceptance_criteria"]
    assert packet["non_goals"]
    assert packet["historical_progress_is_authoritative"] is False
    assert frontier.validate_worker_packet(packet) == []


def test_frontier_has_no_worktree_or_github_side_effect(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("side effect attempted")

    monkeypatch.setattr("subprocess.run", fail)
    result = frontier.build_coordinator_result(
        "audit",
        snapshot(issue(1)),
        audit(entry(1, governance="stale", implementation="stale")),
    )
    assert result["selected_issue"] == 1
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_project_plan_is_read_only_and_flags_dependency_inversion(
    monkeypatch,
) -> None:
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("side effect attempted")

    monkeypatch.setattr("subprocess.run", fail)
    snap = snapshot(
        issue(10, title="feat: dependent"),
        issue(20, title="feat: blocker"),
    )
    results = audit(
        entry(10, dependencies=[20]),
        entry(20),
    )

    plan = frontier.build_project_plan(
        snap,
        results,
        policy={"project": {"enabled": False}},
    )

    assert plan["schema_version"] == frontier.PROJECT_PLAN_SCHEMA_VERSION
    assert plan["project"]["enabled"] is False
    assert [column["id"] for column in plan["columns"]][:2] == [
        "ready",
        "needs_semantic_review",
    ]
    assert [
        {
            "issue_number": item["issue_number"],
            "column_id": item["column_id"],
            "position": item["position"],
            "column_position": item["column_position"],
        }
        for item in plan["items"]
    ] == [
        {
            "issue_number": 10,
            "column_id": "ready",
            "position": 1,
            "column_position": 1,
        },
        {
            "issue_number": 20,
            "column_id": "ready",
            "position": 2,
            "column_position": 2,
        },
    ]
    assert plan["ordering_conflicts"] == [
        {
            "code": "dependency-inversion",
            "issue_number": 10,
            "dependency_issue_number": 20,
            "issue_position": 1,
            "dependency_position": 2,
            "message": "#10 is ordered before its dependency #20",
        }
    ]
    assert plan["safety"] == {
        "read_only": True,
        "github_api_calls": False,
        "github_mutations": False,
        "project_writes_supported": False,
        "metadata_operations_supported": False,
        "contains_issue_content": False,
        "contains_state_changes": False,
    }
    assert "operations" not in plan
    assert all("body" not in item and "state" not in item for item in plan["items"])
    assert calls == []


def test_project_plan_json_and_digest_are_deterministic() -> None:
    snap = snapshot(
        issue(10, title="feat: dependent"),
        issue(20, title="feat: blocker"),
    )
    results = audit(
        entry(10, dependencies=[20]),
        entry(20),
    )

    first = frontier.build_project_plan(
        snap,
        results,
        policy={"project": {"enabled": False}},
    )
    second = frontier.build_project_plan(
        snap,
        results,
        policy={"project": {"enabled": False}},
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    changed_results = json.loads(json.dumps(results))
    changed_results["issues"][0]["dependency_impact"] = 1
    changed = frontier.build_project_plan(
        snap,
        changed_results,
        policy={"project": {"enabled": False}},
    )

    assert changed["project_plan_digest"] != first["project_plan_digest"]


def test_project_plan_validation_accepts_built_plan_without_side_effects(
    monkeypatch,
) -> None:
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("side effect attempted")

    monkeypatch.setattr("subprocess.run", fail)
    plan = frontier.build_project_plan(
        snapshot(issue(10)),
        audit(entry(10)),
        policy={"project": {"enabled": False}},
    )

    assert frontier.validate_project_plan(plan) == []
    assert calls == []


def test_project_plan_validation_rejects_integrity_errors() -> None:
    plan = frontier.build_project_plan(
        snapshot(issue(10)),
        audit(entry(10)),
        policy={"project": {"enabled": False}},
    )

    missing_key = json.loads(json.dumps(plan))
    missing_key.pop("repository")
    assert "missing keys: repository" in frontier.validate_project_plan(missing_key)

    tampered = json.loads(json.dumps(plan))
    tampered["items"][0]["title"] = "tampered"
    assert "project_plan_digest mismatch" in frontier.validate_project_plan(tampered)


def test_project_plan_validation_rejects_mutation_shape() -> None:
    plan = frontier.build_project_plan(
        snapshot(issue(10)),
        audit(entry(10)),
        policy={"project": {"enabled": False}},
    )

    unsafe = json.loads(json.dumps(plan))
    unsafe["operations"] = []
    unsafe["items"][0]["body"] = "do not ship issue content"
    unsafe["items"][0]["state"] = "closed"

    errors = frontier.validate_project_plan(unsafe)

    assert "operations key is forbidden" in errors
    assert "items[0].body is forbidden" in errors
    assert "items[0].state is forbidden" in errors


def test_project_plan_validation_accepts_empty_well_formed_plan() -> None:
    plan = frontier.build_project_plan(
        snapshot(),
        audit(),
        policy={"project": {"enabled": False}},
    )

    assert plan["items"] == []
    assert plan["ordering_conflicts"] == []
    assert frontier.validate_project_plan(plan) == []


def test_coordinator_uses_live_snapshot_repository_and_digest_shapes() -> None:
    snap = snapshot(issue(1))
    snap.pop("snapshot_digest")
    snap["snapshot_sha256"] = "c" * 64
    snap["repository"] = {
        "full_name": "dckallos/dbt-diagnostics",
        "owner": "dckallos",
        "name": "dbt-diagnostics",
    }
    results = audit(entry(1))
    results["snapshot_digest"] = "c" * 64

    result = frontier.build_coordinator_result("implement", snap, results)

    assert result["repository"] == "dckallos/dbt-diagnostics"
    assert result["snapshot_digest"] == "c" * 64
    assert frontier.validate_coordinator_result(result) == []


def test_coordinator_validation_rejects_bad_identity_fields() -> None:
    result = frontier.build_coordinator_result(
        "implement", snapshot(issue(1)), audit(entry(1))
    )
    result["repository"] = {"full_name": "dckallos/dbt-diagnostics"}
    result["snapshot_digest"] = None
    result["coordinator_digest"] = "not-a-digest"

    errors = frontier.validate_coordinator_result(result)

    assert "repository must be owner/name" in errors
    assert "snapshot_digest must be a lowercase SHA-256 digest" in errors
    assert "coordinator_digest must be a lowercase SHA-256 digest" in errors
    assert "coordinator_digest mismatch" in errors


def test_worker_packet_enforces_body_and_progress_bounds(tmp_path: Path) -> None:
    long_body = "x" * (frontier.MAX_WORKER_ISSUE_BODY_CHARS + 100)
    long_progress = "p" * (frontier.MAX_PROGRESS_CONTEXT_CHARS + 100)
    snap = snapshot(issue(1, body=long_body))
    results = audit(entry(1))

    packet = frontier.build_worker_packet(
        1,
        snap,
        results,
        root=tmp_path,
        progress_context=long_progress,
    )

    assert len(packet["issue"]["body"]) == frontier.MAX_WORKER_ISSUE_BODY_CHARS
    assert packet["issue"]["body_truncated"] is True
    assert (
        len(packet["historical_progress_context"])
        == frontier.MAX_PROGRESS_CONTEXT_CHARS
    )
    assert packet["historical_progress_truncated"] is True
    assert frontier.validate_worker_packet(packet) == []


def test_suggested_branch_strips_conventional_commit_scope() -> None:
    entry = {"issue_kind": "bug_fix", "issue_number": 7}
    branch = frontier.suggested_branch(entry, "fix(cli): resolve crash")
    assert branch.startswith("fix/7-")
    assert "cli" not in branch
    assert "resolve-crash" in branch
