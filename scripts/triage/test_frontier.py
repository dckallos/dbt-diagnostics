from __future__ import annotations

from pathlib import Path

from scripts.triage import frontier


def snapshot(*issues: dict, pulls: list[dict] | None = None) -> dict:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "snapshot_digest": "snap",
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
        "snapshot_digest": "snap",
        "audit_digest": "audit",
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
