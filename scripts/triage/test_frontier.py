from __future__ import annotations

import json
from pathlib import Path

from scripts.triage import frontier
from scripts.triage import repo_config


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"
RECALL_FIXTURE_LABELS = (
    "likely-duplicate-true-positive",
    "likely-duplicate-false-positive-control",
    "close-duplicate-near-miss",
    "backlog-omission-id-preservation",
    "split-candidate",
    "no-split-control",
    "dependency-order-inversion",
    "no-dependency-order-inversion-control",
    "semantic-disposition-evidence",
    "insufficient-evidence-verdict",
    "fresh-packet-under-warning",
    "warning-only-packet",
    "hard-stale-packet",
    "stricter-max-age-packet",
    "invalid-lineage-packet",
    "unknown-diagnostic-ref",
)


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
        "recommended_disposition": "implement",
        "semantic_disposition_hypothesis": None,
        "semantic_disposition_evidence": [],
    }
    value.update(extra)
    return value


def signals_by_type(report: dict, signal_type: str) -> list[dict]:
    return [
        signal
        for signal in report["signals"]
        if signal["signal_type"] == signal_type
    ]


def backlog_report_digest(report: dict) -> str:
    unsigned = json.loads(json.dumps(report))
    unsigned.pop("backlog_synthesis_digest", None)
    return frontier.sha256_json(unsigned)


def near_misses_by_type(report: dict, near_miss_type: str) -> list[dict]:
    return [
        near_miss
        for near_miss in report["near_misses"]
        if near_miss["near_miss_type"] == near_miss_type
    ]


def test_backlog_synthesis_schema_matches_read_only_forbidden_boundary() -> None:
    schema = json.loads(
        (ROOT / "docs" / "backlog-synthesis-signals-schema-v1.json").read_text()
    )

    forbidden = {
        tuple(item["required"])
        for item in schema["$defs"]["forbiddenReadOnlyShape"]["not"]["anyOf"]
    }
    expected_single_keys = (
        {"operations", "body", "state"}
        | frontier.READ_ONLY_GITHUB_REQUEST_KEYS
        | frontier.READ_ONLY_COMMENT_KEYS
        | frontier.READ_ONLY_METADATA_MUTATION_KEYS
    )

    assert schema["allOf"] == [{"$ref": "#/$defs/safeObject"}]
    for key in expected_single_keys:
        assert (key,) in forbidden
    assert ("issues", "pulls") in forbidden
    assert ("issues", "pull_requests") in forbidden
    assert schema["properties"]["near_misses"]["items"]["allOf"] == [
        {"$ref": "#/$defs/safeObject"}
    ]
    assert schema["properties"]["omissions"]["items"]["allOf"] == [
        {"$ref": "#/$defs/safeObject"}
    ]


def packet_digest(packet: dict) -> str:
    unsigned = json.loads(json.dumps(packet))
    unsigned.pop("synthesis_review_packet_digest", None)
    return frontier.sha256_json(unsigned)


def verdict_digest(verdict: dict) -> str:
    unsigned = json.loads(json.dumps(verdict))
    unsigned.pop("backlog_review_verdict_digest", None)
    return frontier.sha256_json(unsigned)


def sign_packet(packet: dict) -> dict:
    packet["synthesis_review_packet_digest"] = packet_digest(packet)
    return packet


def sign_verdict(verdict: dict) -> dict:
    verdict["backlog_review_verdict_digest"] = verdict_digest(verdict)
    return verdict


def synthesis_review_packet(**overrides: object) -> dict:
    value: dict[str, object] = {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "generated_at": "2026-06-24T01:00:00Z",
        "source_generated_at": "2026-06-24T00:00:00Z",
        "source_artifacts": {
            "snapshot_digest": "a" * 64,
            "audit_digest": "b" * 64,
            "backlog_synthesis_digest": "c" * 64,
        },
        "packet_scope": {
            "review_task": "backlog-synthesis",
            "issue_numbers": [],
            "candidate_set_ids": [],
        },
        "candidate_sets": [],
        "evidence_items": [],
        "near_misses": [],
        "omissions": [],
        "comments_included": False,
        "comment_evidence_status": "not_collected",
        "budget": {
            "serialized_bytes": 1024,
            "target_bytes": 204800,
            "hard_bytes": 307200,
            "estimated_tokens": 90000,
            "target_estimated_tokens": 50000,
            "hard_estimated_tokens": 75000,
            "token_estimate_method": "bytes_div_4",
            "budget_warnings": ["estimated_tokens_exceeds_target"],
        },
        "staleness": {
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-24T01:00:00Z",
            "source_age_hours": 1.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "fresh",
            "freshness_warnings": [],
            "stale": False,
            "llm_review_allowed": True,
        },
        "safety": {
            "read_only": True,
            "github_api_calls": False,
            "github_mutations": False,
            "contains_executable_operations": False,
            "contains_full_tracker_snapshot": False,
            "contains_issue_comments": False,
            "comments_included": False,
            "llm_verdicts_are_advisory": True,
        },
    }
    value.update(overrides)
    return sign_packet(value)


def synthesis_review_packet_with_refs(**overrides: object) -> dict:
    value = synthesis_review_packet(
        evidence_items=[
            {
                "evidence_id": "evidence-001",
                "source": "candidate_sets[0]",
                "excerpt": "bounded evidence excerpt",
            }
        ],
        near_misses=[
            {
                "near_miss_id": (
                    "near-miss-possible-duplicate-001-002-"
                    "title-similarity-below-threshold"
                ),
                "near_miss_type": "possible-duplicate",
                "issue_numbers": [1, 2],
                "score": 0.667,
                "reason_not_signaled": "title similarity below threshold",
                "shared_evidence": ["shared parent epic: #93"],
                "details": {
                    "reason_category": "title_similarity_below_threshold",
                },
            }
        ],
        omissions=[
            {
                "omission_id": "omission-no-issue-body-in-signals",
                "omission_type": "no_issue_body_in_signals",
                "reason": "read-only signal report excludes full issue body",
                "details": {"reason_category": "bounded_signal_report"},
            }
        ],
    )
    value.update(overrides)
    return sign_packet(value)


def backlog_review_verdict(
    *,
    packet: dict | None = None,
    verdicts: list[dict] | None = None,
    future_apply_recommendations: list[dict] | None = None,
    uncertainty: list[dict] | None = None,
    required_maintainer_checks: list[str] | None = None,
    **overrides: object,
) -> dict:
    source_packet = packet or synthesis_review_packet_with_refs()
    source_artifacts = source_packet["source_artifacts"]
    default_verdicts = [
        {
            "verdict_id": "verdict-likely-duplicate-001-002",
            "verdict_type": "likely-duplicate",
            "issue_numbers": [1, 2],
            "recommendation": "Maintainer should review #1 and #2 as duplicates.",
            "confidence": "medium",
            "evidence_refs": ["evidence-001"],
            "near_miss_refs": [
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ],
            "omission_refs": ["omission-no-issue-body-in-signals"],
            "rationale": "The bounded packet evidence cites shared context.",
            "risks": ["The issues may describe separable implementation work."],
            "required_maintainer_checks": [
                "Confirm duplicate disposition before any tracker mutation."
            ],
            "future_apply_recommendation_ref": "future-apply-001",
        }
    ]
    value: dict[str, object] = {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "generated_at": "2026-06-24T01:30:00Z",
        "source_packet_digest": source_packet["synthesis_review_packet_digest"],
        "source_snapshot_digest": source_artifacts["snapshot_digest"],
        "source_audit_digest": source_artifacts["audit_digest"],
        "source_backlog_synthesis_digest": source_artifacts[
            "backlog_synthesis_digest"
        ],
        "packet_reviewability": {
            "source_packet_digest": source_packet["synthesis_review_packet_digest"],
            "source_snapshot_digest": source_artifacts["snapshot_digest"],
            "source_audit_digest": source_artifacts["audit_digest"],
            "source_backlog_synthesis_digest": source_artifacts[
                "backlog_synthesis_digest"
            ],
            "freshness_status": source_packet["staleness"]["freshness_status"],
            "freshness_warnings": list(
                source_packet["staleness"]["freshness_warnings"]
            ),
            "packet_stale": source_packet["staleness"]["stale"],
            "llm_review_allowed": source_packet["staleness"][
                "llm_review_allowed"
            ],
            "invalid_lineage": False,
        },
        "verdicts": default_verdicts if verdicts is None else verdicts,
        "future_apply_recommendations": (
            [
                {
                    "recommendation_id": "future-apply-001",
                    "summary": "Maintainer may close the duplicate after review.",
                    "rationale": "The verdict is advisory and not executable.",
                    "advisory_only": True,
                }
            ]
            if future_apply_recommendations is None
            else future_apply_recommendations
        ),
        "uncertainty": [] if uncertainty is None else uncertainty,
        "required_maintainer_checks": (
            [] if required_maintainer_checks is None else required_maintainer_checks
        ),
        "safety": {
            "read_only": True,
            "github_api_calls": False,
            "github_mutations": False,
            "contains_executable_operations": False,
            "contains_github_request_payloads": False,
            "contains_issue_write_payloads": False,
            "future_apply_recommendations_are_advisory": True,
            "maintainer_decides": True,
            "llm_verdicts_are_advisory": True,
        },
    }
    value.update(overrides)
    return sign_verdict(value)


def review_artifacts(
    snap: dict,
    results: dict,
    *,
    evaluated_at: str | None = None,
    max_age_hours: int = frontier.DEFAULT_SYNTHESIS_REVIEW_MAX_AGE_HOURS,
) -> tuple[dict, dict]:
    report = frontier.build_backlog_synthesis_report(snap, results)
    assert frontier.validate_backlog_synthesis_report(report) == []
    assert frontier.validate_synthesis_review_packet_sources(snap, results, report) == []
    packet = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at=evaluated_at,
        max_age_hours=max_age_hours,
    )
    return report, packet


def review_verdict_item(
    *,
    verdict_type: str,
    issue_numbers: tuple[int, ...],
    evidence_refs: tuple[str, ...] = (),
    near_miss_refs: tuple[str, ...] = (),
    omission_refs: tuple[str, ...] = (),
    confidence: str = "medium",
) -> dict:
    return {
        "verdict_id": "verdict-" + verdict_type + "-" + "-".join(
            f"{number:03d}" for number in issue_numbers
        ),
        "verdict_type": verdict_type,
        "issue_numbers": list(issue_numbers),
        "recommendation": f"Maintainer should review {verdict_type}.",
        "confidence": confidence,
        "evidence_refs": list(evidence_refs),
        "near_miss_refs": list(near_miss_refs),
        "omission_refs": list(omission_refs),
        "rationale": "Hand-labeled bounded review recall fixture.",
        "risks": ["Synthetic fixture coverage is not a maintainer decision."],
        "required_maintainer_checks": [
            "Confirm the advisory verdict before tracker action."
        ],
    }


def review_verdict(
    packet: dict,
    *,
    verdict_type: str,
    issue_numbers: tuple[int, ...],
    evidence_refs: tuple[str, ...] = (),
    near_miss_refs: tuple[str, ...] = (),
    omission_refs: tuple[str, ...] = (),
    uncertainty: list[dict] | None = None,
    required_maintainer_checks: list[str] | None = None,
    **overrides: object,
) -> dict:
    return backlog_review_verdict(
        packet=packet,
        verdicts=[
            review_verdict_item(
                verdict_type=verdict_type,
                issue_numbers=issue_numbers,
                evidence_refs=evidence_refs,
                near_miss_refs=near_miss_refs,
                omission_refs=omission_refs,
            )
        ],
        future_apply_recommendations=[],
        uncertainty=[] if uncertainty is None else uncertainty,
        required_maintainer_checks=(
            [] if required_maintainer_checks is None else required_maintainer_checks
        ),
        **overrides,
    )


def assert_verdict_validates_against_packet(verdict: dict, packet: dict) -> None:
    assert frontier.validate_backlog_review_verdict(verdict) == []
    assert frontier.validate_backlog_review_verdict_against_packet(
        verdict, packet
    ) == []


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


def test_backlog_synthesis_reports_duplicate_pair_with_evidence() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    duplicates = signals_by_type(report, "likely-duplicate")
    assert len(duplicates) == 1
    assert duplicates[0]["issue_numbers"] == [1, 2]
    assert duplicates[0]["confidence"] == "high"
    assert any("shared title tokens" in item for item in duplicates[0]["evidence"])
    assert report["near_misses"] == []
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_reports_duplicate_near_miss_below_threshold() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog review"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    assert signals_by_type(report, "likely-duplicate") == []
    near_misses = near_misses_by_type(report, "possible-duplicate")
    assert near_misses == [
        {
            "near_miss_id": (
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ),
            "near_miss_type": "possible-duplicate",
            "issue_numbers": [1, 2],
            "score": 0.5,
            "reason_not_signaled": (
                "title similarity below likely-duplicate threshold"
            ),
            "shared_evidence": [
                "shared title tokens: backlog, deterministic",
                "shared referenced paths: scripts/triage/frontier.py",
                "shared parent epics: #93",
                "shared issue kind: feature_enhancement",
            ],
            "details": {
                "reason_category": "title_similarity_below_threshold",
                "title_similarity": 0.5,
                "shared_title_tokens": ["backlog", "deterministic"],
                "shared_paths": ["scripts/triage/frontier.py"],
                "shared_parent_epics": [93],
                "shared_issue_kind": "feature_enhancement",
            },
        }
    ]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_avoids_unrelated_duplicate_suggestions() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="fix: pull request dependency resolution"),
    )
    results = audit(
        entry(1, referenced_paths=["scripts/triage/frontier.py"]),
        entry(2, referenced_paths=["scripts/triage/readiness.py"]),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    assert signals_by_type(report, "likely-duplicate") == []
    assert report["near_misses"] == []
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_does_not_emit_weak_title_near_miss() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="fix: deterministic project ordering"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    assert signals_by_type(report, "likely-duplicate") == []
    assert report["near_misses"] == []
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_reports_split_candidate_marker() -> None:
    snap = snapshot(
        issue(
            1,
            title="feat: oversized governance workflow",
            body="This issue describes multiple coherent PRs and separable workstreams.",
        ),
    )
    results = audit(entry(1))

    report = frontier.build_backlog_synthesis_report(snap, results)

    splits = signals_by_type(report, "split-candidate")
    assert len(splits) == 1
    assert splits[0]["issue_numbers"] == [1]
    assert any("split marker" in item for item in splits[0]["evidence"])
    assert "multiple coherent PRs" not in json.dumps(report, sort_keys=True)
    assert report["omissions"] == [
        {
            "omission_id": "omission-no-issue-body-in-signals",
            "omission_type": "no_issue_body_in_signals",
            "reason": "read-only signal report excludes full issue body",
            "details": {"reason_category": "bounded_signal_report"},
        }
    ]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_reports_dependency_inversion_signal() -> None:
    snap = snapshot(
        issue(10, title="feat: dependent"),
        issue(20, title="feat: blocker"),
    )
    results = audit(
        entry(10, dependencies=[20]),
        entry(20),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    inversions = signals_by_type(report, "dependency-inversion")
    assert inversions == [
        {
            "signal_type": "dependency-inversion",
            "issue_numbers": [10, 20],
            "confidence": "high",
            "summary": "#10 is ordered before its dependency #20",
            "evidence": [
                "issue position 1 is before dependency position 2",
                "direct dependency: #10 depends on #20",
            ],
            "details": {
                "issue_number": 10,
                "dependency_issue_number": 20,
                "issue_position": 1,
                "dependency_position": 2,
            },
        }
    ]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_sorts_dependency_inversion_issue_numbers() -> None:
    snap = snapshot(
        issue(10, title="feat: blocker"),
        issue(20, title="feat: dependent"),
    )
    results = audit(
        entry(20, dependencies=[10]),
        entry(10, implementation="blocked", blockers=["blocked"]),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    inversions = signals_by_type(report, "dependency-inversion")
    assert inversions[0]["issue_numbers"] == [10, 20]
    assert inversions[0]["details"]["issue_number"] == 20
    assert inversions[0]["details"]["dependency_issue_number"] == 10
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_does_not_invent_dependency_near_miss() -> None:
    snap = snapshot(
        issue(10, title="feat: blocker"),
        issue(20, title="feat: dependent"),
    )
    results = audit(
        entry(10),
        entry(20, dependencies=[10]),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    assert signals_by_type(report, "dependency-inversion") == []
    assert report["near_misses"] == []
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_reads_explicit_overlap_conflicting_issues() -> None:
    snap = snapshot(
        issue(1, title="feat: owner one"),
        issue(2, title="feat: owner two"),
    )
    results = audit(
        entry(
            1,
            overlap_conflicts=[
                {
                    "claim": "same artifact",
                    "conflicting_issues": [2],
                }
            ],
        ),
        entry(2),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    overlaps = signals_by_type(report, "explicit-overlap")
    assert len(overlaps) == 1
    assert overlaps[0]["issue_numbers"] == [1, 2]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_semantic_disposition_overrides_mechanical_map() -> None:
    snap = snapshot(issue(1, title="feat: duplicate"), issue(2, title="feat: owner"))
    results = audit(
        entry(
            1,
            recommended_disposition="implement",
            semantic_disposition_hypothesis="likely-duplicate-of #2",
            semantic_disposition_evidence=["semantic review points at #2 as the owner"],
        ),
        entry(2),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    first = next(
        item for item in report["issue_dispositions"] if item["issue_number"] == 1
    )
    assert first["mechanical_disposition"] == "implement"
    assert first["semantic_hypothesis"] == "likely-duplicate-of #2"
    assert first["recommended_disposition"] == "likely-duplicate-of #2"
    assert first["semantic_evidence_status"] == "provided"
    semantic = signals_by_type(report, "semantic-disposition")
    assert semantic[0]["issue_numbers"] == [1, 2]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_semantic_disposition_parses_issue_urls() -> None:
    snap = snapshot(issue(1, title="feat: duplicate"), issue(2, title="feat: owner"))
    results = audit(
        entry(
            1,
            recommended_disposition="implement",
            semantic_disposition_hypothesis=(
                "likely-duplicate-of "
                "https://github.com/dckallos/dbt-diagnostics/issues/2"
            ),
            semantic_disposition_evidence=["semantic review points at the owner URL"],
        ),
        entry(2),
    )

    report = frontier.build_backlog_synthesis_report(snap, results)

    semantic = signals_by_type(report, "semantic-disposition")
    assert semantic[0]["issue_numbers"] == [1, 2]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_degrades_without_semantic_evidence() -> None:
    report = frontier.build_backlog_synthesis_report(
        snapshot(issue(1, title="feat: one")),
        audit(entry(1)),
    )

    disposition = report["issue_dispositions"][0]
    assert disposition["mechanical_disposition"] == "implement"
    assert disposition["semantic_hypothesis"] is None
    assert disposition["recommended_disposition"] == "implement"
    assert disposition["semantic_evidence_status"] == "unknown"
    assert report["near_misses"] == []
    assert report["omissions"] == [
        {
            "omission_id": "omission-no-issue-body-in-signals",
            "omission_type": "no_issue_body_in_signals",
            "reason": "read-only signal report excludes full issue body",
            "details": {"reason_category": "bounded_signal_report"},
        }
    ]
    assert frontier.validate_backlog_synthesis_report(report) == []


def test_backlog_synthesis_is_read_only_and_rejects_mutation_shape(monkeypatch) -> None:
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("side effect attempted")

    monkeypatch.setattr("subprocess.run", fail)
    report = frontier.build_backlog_synthesis_report(
        snapshot(issue(1)),
        audit(entry(1)),
    )

    assert report["safety"] == {
        "read_only": True,
        "github_api_calls": False,
        "github_mutations": False,
        "contains_issue_content": False,
        "contains_state_changes": False,
        "verdicts_are_advisory": True,
    }
    assert "operations" not in report
    assert calls == []

    unsafe = json.loads(json.dumps(report))
    unsafe["operations"] = []
    unsafe["safety"]["github_mutations"] = True
    unsafe["signals"][0:0] = [
        {
            "signal_type": "unsafe",
            "issue_numbers": [1],
            "confidence": "high",
            "summary": "unsafe",
            "evidence": ["unsafe"],
            "details": {"body": "do not ship issue content"},
        }
    ]
    unsafe["near_misses"] = [
        {
            "near_miss_id": (
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ),
            "near_miss_type": "possible-duplicate",
            "issue_numbers": [1, 2],
            "score": 0.6,
            "reason_not_signaled": (
                "title similarity below likely-duplicate threshold"
            ),
            "shared_evidence": ["unsafe"],
            "details": {
                "reason_category": "title_similarity_below_threshold",
                "state": "closed",
            },
        }
    ]
    unsafe["omissions"] = [
        {
            "omission_id": "omission-no-issue-body-in-signals",
            "omission_type": "no_issue_body_in_signals",
            "reason": "read-only signal report excludes full issue body",
            "details": {"github_request": {"method": "PATCH"}},
        }
    ]

    errors = frontier.validate_backlog_synthesis_report(unsafe)
    assert "operations key is forbidden" in errors
    assert "safety.github_mutations must be false" in errors
    assert "signals[0].details.body is forbidden" in errors
    assert "near_misses[0].details.state is forbidden" in errors
    assert "omissions[0].details.github_request is forbidden" in errors


def test_backlog_synthesis_diagnostics_are_sorted_and_deterministic() -> None:
    snap = snapshot(
        issue(3, title="feat: deterministic backlog synthesis"),
        issue(1, title="feat: deterministic backlog review"),
        issue(2, title="feat: deterministic backlog planning"),
    )
    results = audit(
        entry(3, issue_kind="feature_enhancement", parent_epics=[93]),
        entry(1, issue_kind="feature_enhancement", parent_epics=[93]),
        entry(2, issue_kind="feature_enhancement", parent_epics=[93]),
    )

    left = frontier.build_backlog_synthesis_report(snap, results)
    right = frontier.build_backlog_synthesis_report(snap, results)

    assert [item["near_miss_id"] for item in left["near_misses"]] == sorted(
        item["near_miss_id"] for item in left["near_misses"]
    )
    assert [item["omission_id"] for item in left["omissions"]] == sorted(
        item["omission_id"] for item in left["omissions"]
    )
    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    assert frontier.validate_backlog_synthesis_report(left) == []


def test_backlog_synthesis_validation_rejects_malformed_diagnostics() -> None:
    report = frontier.build_backlog_synthesis_report(
        snapshot(issue(1), issue(2)),
        audit(entry(1), entry(2)),
    )

    bad_arrays = json.loads(json.dumps(report))
    bad_arrays["near_misses"] = {}
    bad_arrays["omissions"] = {}

    duplicate_ids = json.loads(json.dumps(report))
    duplicate_ids["near_misses"] = [
        {
            "near_miss_id": (
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ),
            "near_miss_type": "possible-duplicate",
            "issue_numbers": [1, 2],
            "score": 0.6,
            "reason_not_signaled": (
                "title similarity below likely-duplicate threshold"
            ),
            "shared_evidence": ["shared issue kind: feature_enhancement"],
            "details": {"reason_category": "title_similarity_below_threshold"},
        },
        {
            "near_miss_id": (
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ),
            "near_miss_type": "possible-duplicate",
            "issue_numbers": [2, 1],
            "score": 0.6,
            "reason_not_signaled": (
                "title similarity below likely-duplicate threshold"
            ),
            "shared_evidence": ["shared issue kind: feature_enhancement"],
            "details": {"reason_category": "title_similarity_below_threshold"},
        },
    ]
    duplicate_ids["omissions"] = [
        {
            "omission_id": "omission-no-issue-body-in-signals",
            "omission_type": "no_issue_body_in_signals",
            "reason": "read-only signal report excludes full issue body",
            "details": {"reason_category": "bounded_signal_report"},
        },
        {
            "omission_id": "omission-no-issue-body-in-signals",
            "omission_type": "no_issue_body_in_signals",
            "reason": "read-only signal report excludes full issue body",
            "details": {"reason_category": "bounded_signal_report"},
        },
    ]
    duplicate_ids["backlog_synthesis_digest"] = backlog_report_digest(duplicate_ids)

    bad_array_errors = frontier.validate_backlog_synthesis_report(bad_arrays)
    duplicate_errors = frontier.validate_backlog_synthesis_report(duplicate_ids)

    assert "near_misses must be an array" in bad_array_errors
    assert "omissions must be an array" in bad_array_errors
    assert "near_misses contains duplicate near_miss_id" in duplicate_errors
    assert "near_misses[1].issue_numbers must be sorted and unique" in duplicate_errors
    assert "omissions contains duplicate omission_id" in duplicate_errors


def test_backlog_synthesis_digest_changes_when_diagnostics_change() -> None:
    report = frontier.build_backlog_synthesis_report(
        snapshot(issue(1), issue(2)),
        audit(entry(1), entry(2)),
    )

    changed_near_miss = json.loads(json.dumps(report))
    changed_near_miss["near_misses"] = [
        {
            "near_miss_id": (
                "near-miss-possible-duplicate-001-002-"
                "title-similarity-below-threshold"
            ),
            "near_miss_type": "possible-duplicate",
            "issue_numbers": [1, 2],
            "score": 0.6,
            "reason_not_signaled": (
                "title similarity below likely-duplicate threshold"
            ),
            "shared_evidence": ["shared issue kind: feature_enhancement"],
            "details": {"reason_category": "title_similarity_below_threshold"},
        }
    ]
    changed_omission = json.loads(json.dumps(report))
    changed_omission["omissions"] = []

    assert backlog_report_digest(changed_near_miss) != report[
        "backlog_synthesis_digest"
    ]
    assert backlog_report_digest(changed_omission) != report[
        "backlog_synthesis_digest"
    ]


def test_synthesis_review_packet_validation_accepts_minimal_packet() -> None:
    packet = synthesis_review_packet()

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert packet["comments_included"] is False
    assert packet["comment_evidence_status"] == "not_collected"


def test_build_synthesis_review_packet_from_valid_sources() -> None:
    snap = snapshot(issue(95), issue(96))
    results = audit(
        entry(
            95,
            semantic_disposition_hypothesis="keep",
            semantic_disposition_evidence=["contract accepted"],
        ),
        entry(96),
    )
    report = frontier.build_backlog_synthesis_report(snap, results)

    packet = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        issue_filter={95},
        max_age_hours=168,
    )

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert packet["schema_version"] == frontier.SYNTHESIS_REVIEW_PACKET_SCHEMA_VERSION
    assert packet["repository"] == "dckallos/dbt-diagnostics"
    assert packet["source_generated_at"] == snap["generated_at"]
    assert packet["source_artifacts"] == {
        "snapshot_digest": "a" * 64,
        "audit_digest": "b" * 64,
        "backlog_synthesis_digest": report["backlog_synthesis_digest"],
    }
    assert packet["packet_scope"]["issue_numbers"] == [95]
    assert packet["staleness"]["max_age_hours"] == 168
    assert packet["staleness"]["stale"] is False
    assert packet["staleness"]["llm_review_allowed"] is True
    assert packet["safety"]["github_api_calls"] is False
    assert packet["safety"]["github_mutations"] is False
    assert "operations" not in packet
    assert '"body":' not in json.dumps(packet, sort_keys=True)


def test_build_synthesis_review_packet_preserves_backlog_diagnostic_ids() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog review"),
    )
    results = audit(
        entry(1, issue_kind="feature_enhancement", parent_epics=[93]),
        entry(2, issue_kind="feature_enhancement", parent_epics=[93]),
    )
    report = frontier.build_backlog_synthesis_report(snap, results)

    packet = frontier.build_synthesis_review_packet(snap, results, report)

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert [
        item["near_miss_id"] for item in packet["near_misses"]
    ] == [
        "near-miss-possible-duplicate-001-002-"
        "title-similarity-below-threshold"
    ]
    assert "omission-no-issue-body-in-signals" in {
        item["omission_id"] for item in packet["omissions"]
    }
    assert "issue-comments-not-collected" in {
        item["omission_id"] for item in packet["omissions"]
    }


def test_build_synthesis_review_packet_scope_includes_disposition_only_issues() -> None:
    snap = snapshot(issue(95))
    results = audit(entry(95))
    report = frontier.build_backlog_synthesis_report(snap, results)

    assert report["signals"] == []

    packet = frontier.build_synthesis_review_packet(snap, results, report)

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert packet["packet_scope"]["issue_numbers"] == [95]
    assert packet["evidence_items"][0]["issue_numbers"] == [95]


def test_build_synthesis_review_packet_records_stricter_max_age() -> None:
    snap = snapshot(issue(95))
    results = audit(entry(95))
    report = frontier.build_backlog_synthesis_report(snap, results)

    packet = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        max_age_hours=24,
    )

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert packet["staleness"]["max_age_hours"] == 24


def test_build_synthesis_review_packet_records_project_plan_digest() -> None:
    snap = snapshot(issue(95))
    results = audit(entry(95))
    report = frontier.build_backlog_synthesis_report(snap, results)
    plan = frontier.build_project_plan(
        snap,
        results,
        policy={"project": {"enabled": False}},
    )

    packet = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        project_plan=plan,
    )

    assert frontier.validate_synthesis_review_packet(packet) == []
    assert (
        packet["source_artifacts"]["project_plan_digest"]
        == plan["project_plan_digest"]
    )


def test_synthesis_review_packet_source_validation_rejects_digest_mismatch() -> None:
    snap = snapshot(issue(95))
    results = audit(entry(95))
    report = frontier.build_backlog_synthesis_report(snap, results)
    report["audit_digest"] = "9" * 64
    report["backlog_synthesis_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in report.items()
            if key != "backlog_synthesis_digest"
        }
    )

    errors = frontier.validate_synthesis_review_packet_sources(snap, results, report)

    assert errors == ["backlog-synthesis audit digest does not match readiness audit"]


def test_build_synthesis_review_packet_is_deterministic() -> None:
    snap = snapshot(issue(95))
    results = audit(entry(95))
    report = frontier.build_backlog_synthesis_report(snap, results)

    left = frontier.build_synthesis_review_packet(snap, results, report)
    right = frontier.build_synthesis_review_packet(snap, results, report)

    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def test_synthesis_review_packet_machine_schema_documents_required_surface() -> None:
    schema = json.loads(
        Path("docs/synthesis-review-packet-schema-v1.json").read_text()
    )

    assert "synthesis_review_packet_digest" in schema["required"]
    assert schema["properties"]["comments_included"]["const"] is False
    assert (
        schema["properties"]["comment_evidence_status"]["const"] == "not_collected"
    )
    assert schema["properties"]["budget"]["properties"]["hard_bytes"]["const"] == 307200
    assert "serialized_bytes_exceeds_target_bytes" in schema["properties"]["budget"][
        "properties"
    ]["budget_warnings"]["items"]["enum"]
    staleness = schema["properties"]["staleness"]["properties"]
    assert staleness["warning_age_hours"]["const"] == 24
    assert staleness["max_age_hours"]["type"] == "integer"
    assert set(staleness["freshness_status"]["enum"]) == {
        "fresh",
        "warning",
        "stale",
    }
    assert (
        schema["properties"]["safety"]["properties"]["github_mutations"]["const"]
        is False
    )
    assert "forbiddenReadOnlyShape" in schema["$defs"]
    assert (
        schema["properties"]["evidence_items"]["items"]["allOf"][0]["$ref"]
        == "#/$defs/safeObject"
    )


def test_synthesis_review_packet_validation_rejects_required_and_type_errors() -> None:
    missing = synthesis_review_packet()
    missing.pop("repository")
    missing = sign_packet(missing)

    wrong_type = synthesis_review_packet()
    wrong_type["budget"]["serialized_bytes"] = "1024"
    wrong_type = sign_packet(wrong_type)

    missing_errors = frontier.validate_synthesis_review_packet(missing)
    wrong_type_errors = frontier.validate_synthesis_review_packet(wrong_type)

    assert "missing keys: repository" in missing_errors
    assert (
        "budget.serialized_bytes must be a non-negative integer"
        in wrong_type_errors
    )


def test_synthesis_review_packet_validation_recomputes_digest_canonically() -> None:
    packet = synthesis_review_packet()
    reordered = dict(reversed(list(packet.items())))

    assert frontier.validate_synthesis_review_packet(reordered) == []

    tampered = synthesis_review_packet()
    tampered["packet_scope"]["review_task"] = "tampered"

    assert (
        "synthesis_review_packet_digest mismatch"
        in frontier.validate_synthesis_review_packet(tampered)
    )


def test_synthesis_review_packet_validation_rejects_mutation_shape() -> None:
    packet = synthesis_review_packet(
        candidate_sets=[
            {
                "candidate_set_id": "set-1",
                "issues": [{"issue_number": 94, "state": "closed"}],
            }
        ],
        evidence_items=[
            {
                "evidence_id": "evidence-1",
                "issue": {
                    "issue_number": 94,
                    "body": "unbounded issue body must not be embedded",
                },
            }
        ],
        github_request={
            "method": "PATCH",
            "path": "/repos/dckallos/dbt-diagnostics/issues/94",
            "body": {"labels": ["documentation"]},
        },
        operations=[],
    )

    errors = frontier.validate_synthesis_review_packet(packet)

    assert "operations key is forbidden" in errors
    assert "github_request is forbidden" in errors
    assert "candidate_sets[0].issues[0].state is forbidden" in errors
    assert "evidence_items[0].issue.body is forbidden" in errors


def test_synthesis_review_packet_validation_allows_empty_collections() -> None:
    packet = synthesis_review_packet(
        candidate_sets=[],
        evidence_items=[],
        near_misses=[],
        omissions=[],
    )

    assert frontier.validate_synthesis_review_packet(packet) == []


def test_synthesis_review_packet_validation_enforces_byte_not_token_limit() -> None:
    advisory_tokens = synthesis_review_packet()
    advisory_tokens["budget"]["estimated_tokens"] = 1000000
    advisory_tokens["budget"]["budget_warnings"] = [
        "estimated_tokens_exceeds_target"
    ]
    advisory_tokens = sign_packet(advisory_tokens)

    too_large = synthesis_review_packet()
    too_large["budget"]["serialized_bytes"] = 307201
    too_large["budget"]["budget_warnings"] = [
        "serialized_bytes_exceeds_target_bytes",
        "estimated_tokens_exceeds_target",
    ]
    too_large = sign_packet(too_large)

    assert frontier.validate_synthesis_review_packet(advisory_tokens) == []
    assert (
        "budget.serialized_bytes must not exceed budget.hard_bytes"
        in frontier.validate_synthesis_review_packet(too_large)
    )


def test_synthesis_review_packet_budget_warnings_are_consistent() -> None:
    under_target = frontier.build_synthesis_review_packet(
        snapshot(issue(96)),
        audit(entry(96)),
        frontier.build_backlog_synthesis_report(
            snapshot(issue(96)),
            audit(entry(96)),
        ),
    )
    over_target = synthesis_review_packet()
    over_target["budget"]["serialized_bytes"] = 204801
    over_target["budget"]["estimated_tokens"] = 50001
    over_target["budget"]["budget_warnings"] = [
        "serialized_bytes_exceeds_target_bytes",
        "estimated_tokens_exceeds_target",
    ]
    over_target = sign_packet(over_target)
    missing_warning = synthesis_review_packet()
    missing_warning["budget"]["serialized_bytes"] = 204801
    missing_warning["budget"]["budget_warnings"] = [
        "estimated_tokens_exceeds_target"
    ]
    missing_warning = sign_packet(missing_warning)

    assert under_target["budget"]["budget_warnings"] == []
    assert frontier.validate_synthesis_review_packet(over_target) == []
    assert (
        "budget.budget_warnings must include "
        "serialized_bytes_exceeds_target_bytes when serialized_bytes exceeds "
        "target_bytes"
        in frontier.validate_synthesis_review_packet(missing_warning)
    )


def test_synthesis_review_packet_actual_size_requires_target_warning() -> None:
    packet = synthesis_review_packet()
    packet["budget"]["serialized_bytes"] = 1024
    packet["budget"]["estimated_tokens"] = 1
    packet["budget"]["budget_warnings"] = []
    packet["evidence_items"] = [
        {
            "evidence_id": "large-but-under-hard",
            "excerpt": "x" * 205000,
        }
    ]
    packet = sign_packet(packet)

    assert (
        "budget.budget_warnings must include "
        "serialized_bytes_exceeds_target_bytes when actual serialized bytes exceed "
        "target_bytes"
        in frontier.validate_synthesis_review_packet(packet)
    )


def test_synthesis_review_packet_validation_enforces_actual_serialized_bytes() -> None:
    packet = synthesis_review_packet()
    packet["budget"]["serialized_bytes"] = 1024
    packet["evidence_items"] = [
        {
            "evidence_id": "oversized",
            "excerpt": "x" * 308000,
        }
    ]
    packet = sign_packet(packet)

    assert (
        "synthesis_review_packet serialized bytes must not exceed budget.hard_bytes"
        in frontier.validate_synthesis_review_packet(packet)
    )


def test_synthesis_review_packet_validation_rejects_stale_packets() -> None:
    not_reviewable = synthesis_review_packet(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-07-02T00:00:01Z",
            "source_age_hours": 192.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "stale",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": True,
            "llm_review_allowed": False,
        }
    )
    packet = synthesis_review_packet(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-07-02T00:00:01Z",
            "source_age_hours": 192.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "stale",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": True,
            "llm_review_allowed": True,
        }
    )

    assert (
        "staleness.llm_review_allowed must be false when staleness.stale is true"
        in frontier.validate_synthesis_review_packet(packet)
    )
    assert (
        "staleness.stale packets are not valid for LLM review"
        in frontier.validate_synthesis_review_packet(not_reviewable)
    )
    assert frontier.validate_synthesis_review_packet(
        not_reviewable, allow_stale_offline=True
    ) == []


def test_synthesis_review_packet_builds_freshness_statuses_with_boundaries() -> None:
    snap = snapshot(issue(96))
    results = audit(entry(96))
    report = frontier.build_backlog_synthesis_report(snap, results)

    under_warning = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-06-24T23:59:59Z",
    )
    exact_warning = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-06-25T00:00:00Z",
    )
    warning = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-06-25T00:00:01Z",
    )
    exact_hard = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-07-01T00:00:00Z",
    )
    stale = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-07-01T00:00:01Z",
    )

    assert under_warning["staleness"]["freshness_status"] == "fresh"
    assert under_warning["staleness"]["freshness_warnings"] == []
    assert exact_warning["staleness"]["freshness_status"] == "fresh"
    assert warning["staleness"]["freshness_status"] == "warning"
    assert warning["staleness"]["stale"] is False
    assert warning["staleness"]["llm_review_allowed"] is True
    assert warning["staleness"]["freshness_warnings"] == [
        "source_age_exceeds_warning_age"
    ]
    assert frontier.validate_synthesis_review_packet(warning) == []
    assert exact_hard["staleness"]["freshness_status"] == "warning"
    assert exact_hard["staleness"]["stale"] is False
    assert exact_hard["staleness"]["llm_review_allowed"] is True
    assert stale["staleness"]["freshness_status"] == "stale"
    assert stale["staleness"]["stale"] is True
    assert stale["staleness"]["llm_review_allowed"] is False
    assert (
        "staleness.stale packets are not valid for LLM review"
        in frontier.validate_synthesis_review_packet(stale)
    )
    assert frontier.validate_synthesis_review_packet(
        stale, allow_stale_offline=True
    ) == []


def test_synthesis_review_packet_stricter_max_age_can_make_warning_stale() -> None:
    snap = snapshot(issue(96))
    results = audit(entry(96))
    report = frontier.build_backlog_synthesis_report(snap, results)

    packet = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        max_age_hours=48,
        evaluated_at="2026-06-27T00:00:01Z",
    )

    assert round(packet["staleness"]["source_age_hours"], 3) == 72.0
    assert packet["staleness"]["freshness_status"] == "stale"
    assert packet["staleness"]["stale"] is True
    assert packet["staleness"]["llm_review_allowed"] is False


def test_synthesis_review_packet_validation_rejects_staleness_contradictions() -> None:
    warning_stale = synthesis_review_packet(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-25T01:00:00Z",
            "source_age_hours": 25.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "warning",
            "freshness_warnings": [],
            "stale": True,
            "llm_review_allowed": False,
        }
    )
    bad_thresholds = synthesis_review_packet(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-25T01:00:00Z",
            "source_age_hours": 25.0,
            "warning_age_hours": 169,
            "max_age_hours": 168,
            "freshness_status": "warning",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": False,
            "llm_review_allowed": True,
        }
    )
    unknown_status = synthesis_review_packet(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-25T01:00:00Z",
            "source_age_hours": 25.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "invalid_lineage",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": False,
            "llm_review_allowed": True,
        }
    )
    missing_age = synthesis_review_packet()
    missing_age["staleness"].pop("source_age_hours")
    missing_age = sign_packet(missing_age)

    warning_errors = frontier.validate_synthesis_review_packet(warning_stale)
    threshold_errors = frontier.validate_synthesis_review_packet(bad_thresholds)
    status_errors = frontier.validate_synthesis_review_packet(unknown_status)
    missing_errors = frontier.validate_synthesis_review_packet(missing_age)

    assert "staleness.warning freshness must not be stale" in warning_errors
    assert (
        "staleness.warning_age_hours must not exceed staleness.max_age_hours"
        in threshold_errors
    )
    assert "staleness.freshness_status must be fresh, warning, or stale" in status_errors
    assert "missing keys: source_age_hours" in missing_errors


def test_synthesis_review_packet_digest_changes_with_freshness_metadata() -> None:
    snap = snapshot(issue(96))
    results = audit(entry(96))
    report = frontier.build_backlog_synthesis_report(snap, results)

    fresh = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-06-25T00:00:00Z",
    )
    warning = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        evaluated_at="2026-06-25T00:00:01Z",
    )

    assert fresh["synthesis_review_packet_digest"] != warning[
        "synthesis_review_packet_digest"
    ]


def test_synthesis_review_packet_rejects_nested_read_only_forbidden_shapes() -> None:
    packet = synthesis_review_packet(
        evidence_items=[
            {
                "evidence_id": "comments",
                "comments": ["issue comment text"],
            },
            {
                "evidence_id": "snapshot",
                "snapshot": {"issues": [], "pulls": []},
            },
            {
                "evidence_id": "metadata",
                "label_updates": [{"issue_number": 1, "add": ["bug"]}],
            },
        ]
    )

    errors = frontier.validate_synthesis_review_packet(packet)

    assert "evidence_items[0].comments is forbidden" in errors
    assert "evidence_items[1].snapshot is a forbidden full tracker snapshot" in errors
    assert "evidence_items[2].label_updates is forbidden" in errors


def test_read_only_artifact_validators_reject_operations_regression() -> None:
    plan = frontier.build_project_plan(
        snapshot(issue(10)),
        audit(entry(10)),
        policy={"project": {"enabled": False}},
    )
    report = frontier.build_backlog_synthesis_report(
        snapshot(issue(10)),
        audit(entry(10)),
    )
    packet = synthesis_review_packet()
    plan["operations"] = []
    report["operations"] = []
    packet["operations"] = []

    assert "operations key is forbidden" in frontier.validate_project_plan(plan)
    assert (
        "operations key is forbidden"
        in frontier.validate_backlog_synthesis_report(report)
    )
    assert (
        "operations key is forbidden"
        in frontier.validate_synthesis_review_packet(packet)
    )


def test_backlog_review_verdict_machine_schema_documents_required_surface() -> None:
    schema = json.loads(
        (ROOT / "docs" / "backlog-review-verdict-schema-v1.json").read_text()
    )

    required = set(schema["required"])
    assert "backlog_review_verdict_digest" in required
    assert "packet_reviewability" in required
    assert (
        schema["properties"]["safety"]["properties"]["github_mutations"]["const"]
        is False
    )
    assert (
        schema["properties"]["safety"]["properties"][
            "future_apply_recommendations_are_advisory"
        ]["const"]
        is True
    )
    forbidden = {
        tuple(item["required"])
        for item in schema["$defs"]["forbiddenReadOnlyShape"]["not"]["anyOf"]
    }
    expected_single_key_forbidden = (
        {"operations", "body", "state"}
        | frontier.READ_ONLY_GITHUB_REQUEST_KEYS
        | frontier.READ_ONLY_COMMENT_KEYS
        | frontier.READ_ONLY_METADATA_MUTATION_KEYS
        | frontier.VERDICT_APPLY_LIKE_KEYS
    )
    assert {
        required[0] for required in forbidden if len(required) == 1
    } == expected_single_key_forbidden
    assert {
        required for required in forbidden if len(required) > 1
    } == {
        ("method", "path"),
        ("method", "url"),
        ("method", "endpoint"),
        ("issues", "pulls"),
        ("issues", "pull_requests"),
    }
    assert schema["allOf"] == [{"$ref": "#/$defs/safeObject"}]


def test_backlog_review_verdict_valid_minimal_and_packet_refs_validate() -> None:
    packet = synthesis_review_packet_with_refs()
    verdict = backlog_review_verdict(packet=packet)

    assert frontier.validate_backlog_review_verdict(verdict) == []
    assert frontier.validate_backlog_review_verdict_against_packet(
        verdict, packet
    ) == []


def test_backlog_review_verdict_recomputes_digest_canonically() -> None:
    verdict = backlog_review_verdict()
    reordered = dict(reversed(list(verdict.items())))
    tampered = backlog_review_verdict()
    tampered["verdicts"][0]["recommendation"] = "Changed recommendation."

    assert frontier.validate_backlog_review_verdict(reordered) == []
    assert (
        "backlog_review_verdict_digest mismatch"
        in frontier.validate_backlog_review_verdict(tampered)
    )


def test_backlog_review_verdict_rejects_forbidden_mutation_shapes() -> None:
    verdict = backlog_review_verdict(
        operations=[],
        future_apply_recommendations=[
            {
                "recommendation_id": "future-apply-001",
                "summary": "unsafe executable recommendation",
                "rationale": "must not pass",
                "advisory_only": True,
                "operation_id": "issue.body.update:abc",
                "method": "PATCH",
                "path": "/repos/dckallos/dbt-diagnostics/issues/1",
            }
        ],
        verdicts=[
            {
                "verdict_id": "verdict-unsafe",
                "verdict_type": "likely-duplicate",
                "issue_numbers": [1, 2],
                "recommendation": "unsafe",
                "confidence": "medium",
                "evidence_refs": ["evidence-001"],
                "near_miss_refs": [],
                "omission_refs": [],
                "rationale": "unsafe",
                "risks": [],
                "required_maintainer_checks": [],
                "github_request": {
                    "method": "POST",
                    "path": "/repos/dckallos/dbt-diagnostics/issues/1/labels",
                    "body": {"labels": ["duplicate"]},
                },
            }
        ],
    )

    errors = frontier.validate_backlog_review_verdict(verdict)

    assert "operations key is forbidden" in errors
    assert "future_apply_recommendations[0].operation_id is forbidden" in errors
    assert (
        "future_apply_recommendations[0] is a forbidden request target"
        in errors
    )
    assert "verdicts[0].github_request is forbidden" in errors


def test_backlog_review_verdict_allows_advisory_future_apply_recommendation() -> None:
    verdict = backlog_review_verdict(
        future_apply_recommendations=[
            {
                "recommendation_id": "future-apply-001",
                "summary": "Maintainer may close #2 after manual review.",
                "rationale": "This is advisory text and carries no operation.",
                "advisory_only": True,
            }
        ]
    )

    assert frontier.validate_backlog_review_verdict(verdict) == []


def test_backlog_review_verdict_requires_evidence_unless_insufficient() -> None:
    missing_evidence = backlog_review_verdict()
    missing_evidence["verdicts"][0]["evidence_refs"] = []
    missing_evidence = sign_verdict(missing_evidence)
    insufficient = backlog_review_verdict(
        verdicts=[
            {
                "verdict_id": "verdict-insufficient-evidence",
                "verdict_type": "insufficient-evidence",
                "issue_numbers": [1, 2],
                "recommendation": "No advisory action.",
                "confidence": "low",
                "evidence_refs": [],
                "near_miss_refs": [],
                "omission_refs": ["omission-no-issue-body-in-signals"],
                "rationale": "The packet does not contain enough evidence.",
                "risks": [],
                "required_maintainer_checks": [
                    "Collect additional maintainer evidence before acting."
                ],
            }
        ],
        future_apply_recommendations=[],
    )

    assert (
        "verdicts[0].evidence_refs is required unless verdict_type is "
        "insufficient-evidence"
        in frontier.validate_backlog_review_verdict(missing_evidence)
    )
    assert frontier.validate_backlog_review_verdict(insufficient) == []


def test_backlog_review_verdict_empty_verdicts_require_no_actionable_rationale() -> None:
    missing_rationale = backlog_review_verdict(
        verdicts=[],
        future_apply_recommendations=[],
        uncertainty=[],
    )
    with_rationale = backlog_review_verdict(
        verdicts=[],
        future_apply_recommendations=[],
        uncertainty=[
            {
                "code": "no_actionable_candidates",
                "rationale": "The packet had no bounded actionable candidates.",
            }
        ],
    )

    assert (
        "empty verdicts require no_actionable_candidates uncertainty rationale"
        in frontier.validate_backlog_review_verdict(missing_rationale)
    )
    assert frontier.validate_backlog_review_verdict(with_rationale) == []


def test_backlog_review_verdict_packet_aware_unknown_refs_fail() -> None:
    packet = synthesis_review_packet_with_refs()
    unknown_evidence = backlog_review_verdict(packet=packet)
    unknown_evidence["verdicts"][0]["evidence_refs"] = ["unknown-evidence"]
    unknown_evidence = sign_verdict(unknown_evidence)
    unknown_near_miss = backlog_review_verdict(packet=packet)
    unknown_near_miss["verdicts"][0]["near_miss_refs"] = ["unknown-near-miss"]
    unknown_near_miss = sign_verdict(unknown_near_miss)
    unknown_omission = backlog_review_verdict(packet=packet)
    unknown_omission["verdicts"][0]["omission_refs"] = ["unknown-omission"]
    unknown_omission = sign_verdict(unknown_omission)

    assert (
        "verdicts[0].evidence_refs contains unknown packet evidence_id: "
        "unknown-evidence"
        in frontier.validate_backlog_review_verdict_against_packet(
            unknown_evidence, packet
        )
    )
    assert (
        "verdicts[0].near_miss_refs contains unknown packet near_miss_id: "
        "unknown-near-miss"
        in frontier.validate_backlog_review_verdict_against_packet(
            unknown_near_miss, packet
        )
    )
    assert (
        "verdicts[0].omission_refs contains unknown packet omission_id: "
        "unknown-omission"
        in frontier.validate_backlog_review_verdict_against_packet(
            unknown_omission, packet
        )
    )


def test_backlog_review_verdict_packet_digest_and_source_mismatches_fail() -> None:
    packet = synthesis_review_packet_with_refs()
    packet_mismatch = backlog_review_verdict(packet=packet)
    packet_mismatch["source_packet_digest"] = "9" * 64
    packet_mismatch = sign_verdict(packet_mismatch)
    source_mismatch = backlog_review_verdict(packet=packet)
    source_mismatch["source_snapshot_digest"] = "8" * 64
    source_mismatch = sign_verdict(source_mismatch)

    assert (
        "source_packet_digest does not match packet digest"
        in frontier.validate_backlog_review_verdict_against_packet(
            packet_mismatch, packet
        )
    )
    assert (
        "source_snapshot_digest does not match packet source_artifacts.snapshot_digest"
        in frontier.validate_backlog_review_verdict_against_packet(
            source_mismatch, packet
        )
    )


def test_backlog_review_verdict_rejects_hard_stale_or_non_reviewable_packet() -> None:
    stale_packet = synthesis_review_packet_with_refs(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-07-02T00:00:01Z",
            "source_age_hours": 192.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "stale",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": True,
            "llm_review_allowed": False,
        }
    )
    stale_verdict = backlog_review_verdict(packet=stale_packet)
    invalid_lineage = backlog_review_verdict(
        packet=synthesis_review_packet_with_refs(),
        packet_reviewability={
            "source_packet_digest": "d" * 64,
            "source_snapshot_digest": "a" * 64,
            "source_audit_digest": "b" * 64,
            "source_backlog_synthesis_digest": "c" * 64,
            "freshness_status": "fresh",
            "freshness_warnings": [],
            "packet_stale": False,
            "llm_review_allowed": True,
            "invalid_lineage": True,
        },
    )

    stale_errors = frontier.validate_backlog_review_verdict_against_packet(
        stale_verdict, stale_packet
    )
    invalid_lineage_errors = frontier.validate_backlog_review_verdict(
        invalid_lineage
    )

    assert "source packet invalid: staleness.stale packets are not valid for LLM review" in stale_errors
    assert "packet_reviewability.invalid_lineage must be false" in invalid_lineage_errors


def test_backlog_review_verdict_warning_packet_must_preserve_warning() -> None:
    warning_packet = synthesis_review_packet_with_refs(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-25T01:00:00Z",
            "source_age_hours": 25.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "warning",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": False,
            "llm_review_allowed": True,
        }
    )
    source_artifacts = warning_packet["source_artifacts"]
    warning_reviewability_without_warning = {
        "source_packet_digest": warning_packet["synthesis_review_packet_digest"],
        "source_snapshot_digest": source_artifacts["snapshot_digest"],
        "source_audit_digest": source_artifacts["audit_digest"],
        "source_backlog_synthesis_digest": source_artifacts[
            "backlog_synthesis_digest"
        ],
        "freshness_status": "warning",
        "freshness_warnings": [],
        "packet_stale": False,
        "llm_review_allowed": True,
        "invalid_lineage": False,
    }
    missing_warning = backlog_review_verdict(
        packet=warning_packet,
        packet_reviewability=warning_reviewability_without_warning,
        uncertainty=[],
        required_maintainer_checks=[],
    )
    preserved_in_packet_reviewability = backlog_review_verdict(
        packet=warning_packet,
    )
    preserved_in_uncertainty = backlog_review_verdict(
        packet=warning_packet,
        packet_reviewability=warning_reviewability_without_warning,
        uncertainty=[
            {
                "code": "packet_freshness_warning",
                "message": "source_age_exceeds_warning_age",
            }
        ],
    )
    preserved_in_maintainer_checks = backlog_review_verdict(
        packet=warning_packet,
        packet_reviewability=warning_reviewability_without_warning,
        required_maintainer_checks=[
            "Review packet freshness warning: source_age_exceeds_warning_age."
        ],
    )

    assert (
        "warning-only packet freshness warning is not preserved in verdict"
        in frontier.validate_backlog_review_verdict_against_packet(
            missing_warning, warning_packet
        )
    )
    assert frontier.validate_backlog_review_verdict_against_packet(
        preserved_in_packet_reviewability, warning_packet
    ) == []
    assert frontier.validate_backlog_review_verdict_against_packet(
        preserved_in_uncertainty, warning_packet
    ) == []
    assert frontier.validate_backlog_review_verdict_against_packet(
        preserved_in_maintainer_checks, warning_packet
    ) == []


def test_backlog_review_validation_result_accepts_fresh_pair() -> None:
    packet = synthesis_review_packet_with_refs()
    verdict = backlog_review_verdict(packet=packet)

    result = frontier.build_backlog_review_validation_result(packet, verdict)

    assert result == {
        "schema_version": 1,
        "valid": True,
        "packet_digest": packet["synthesis_review_packet_digest"],
        "verdict_digest": verdict["backlog_review_verdict_digest"],
        "errors": [],
        "warnings": [],
    }


def test_backlog_review_validation_result_allows_warning_packet_with_finding() -> None:
    warning_packet = synthesis_review_packet_with_refs(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-06-25T01:00:00Z",
            "source_age_hours": 25.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "warning",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": False,
            "llm_review_allowed": True,
        }
    )
    verdict = backlog_review_verdict(packet=warning_packet)

    result = frontier.build_backlog_review_validation_result(
        warning_packet, verdict
    )

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == [
        {
            "code": "packet_freshness_warning",
            "message": "source_age_exceeds_warning_age",
            "source": "packet.staleness.freshness_warnings",
        }
    ]


def test_backlog_review_validation_result_classifies_integrated_errors() -> None:
    packet = synthesis_review_packet_with_refs()
    verdict = backlog_review_verdict(packet=packet)
    verdict["source_packet_digest"] = "9" * 64
    verdict["source_snapshot_digest"] = "8" * 64
    verdict["verdicts"][0]["evidence_refs"] = ["unknown-evidence"]
    verdict["verdicts"][0]["near_miss_refs"] = ["unknown-near-miss"]
    verdict["verdicts"][0]["omission_refs"] = ["unknown-omission"]
    verdict = sign_verdict(verdict)

    result = frontier.build_backlog_review_validation_result(packet, verdict)
    errors = {item["code"]: item["message"] for item in result["errors"]}

    assert result["valid"] is False
    assert (
        errors["source_packet_digest_mismatch"]
        == "source_packet_digest does not match packet digest"
    )
    assert (
        errors["source_artifact_digest_mismatch"]
        == "source_snapshot_digest does not match "
        "packet source_artifacts.snapshot_digest"
    )
    assert (
        errors["unknown_packet_reference"]
        == "verdicts[0].omission_refs contains unknown packet omission_id: "
        "unknown-omission"
    )


def test_backlog_review_validation_result_rejects_hard_stale_packet() -> None:
    stale_packet = synthesis_review_packet_with_refs(
        staleness={
            "source_generated_at": "2026-06-24T00:00:00Z",
            "evaluated_at": "2026-07-02T00:00:01Z",
            "source_age_hours": 192.0,
            "warning_age_hours": 24,
            "max_age_hours": 168,
            "freshness_status": "stale",
            "freshness_warnings": ["source_age_exceeds_warning_age"],
            "stale": True,
            "llm_review_allowed": False,
        }
    )
    verdict = backlog_review_verdict(packet=stale_packet)

    result = frontier.build_backlog_review_validation_result(stale_packet, verdict)
    codes = {item["code"] for item in result["errors"]}

    assert result["valid"] is False
    assert "packet_hard_stale" in codes
    assert "packet_not_reviewable" in codes


def test_backlog_review_validation_result_rejects_executable_payloads() -> None:
    packet = synthesis_review_packet_with_refs()
    verdict = backlog_review_verdict(
        packet=packet,
        future_apply_recommendations=[
            {
                "recommendation_id": "future-apply-001",
                "summary": "unsafe executable recommendation",
                "rationale": "must not pass",
                "advisory_only": True,
                "operation_id": "issue.body.update:abc",
                "workflow_dispatch": {"workflow_id": "ci.yml"},
            }
        ],
    )

    result = frontier.build_backlog_review_validation_result(packet, verdict)
    codes = {item["code"] for item in result["errors"]}

    assert result["valid"] is False
    assert "forbidden_mutation_shape" in codes


def test_backlog_review_validation_result_reuses_recall_fixture_pair() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
    )
    _report, packet = review_artifacts(snap, results)
    verdict = review_verdict(
        packet,
        verdict_type="likely-duplicate",
        issue_numbers=(1, 2),
        evidence_refs=("evidence-001",),
    )

    result = frontier.build_backlog_review_validation_result(packet, verdict)

    assert result["valid"] is True
    assert result["errors"] == []


def test_bounded_review_recall_fixture_labels_cover_expected_matrix() -> None:
    assert RECALL_FIXTURE_LABELS == (
        "likely-duplicate-true-positive",
        "likely-duplicate-false-positive-control",
        "close-duplicate-near-miss",
        "backlog-omission-id-preservation",
        "split-candidate",
        "no-split-control",
        "dependency-order-inversion",
        "no-dependency-order-inversion-control",
        "semantic-disposition-evidence",
        "insufficient-evidence-verdict",
        "fresh-packet-under-warning",
        "warning-only-packet",
        "hard-stale-packet",
        "stricter-max-age-packet",
        "invalid-lineage-packet",
        "unknown-diagnostic-ref",
    )


def test_bounded_review_recall_positive_candidate_fixtures_validate() -> None:
    cases = [
        {
            "label": "likely-duplicate-true-positive",
            "snapshot": snapshot(
                issue(1, title="feat: deterministic backlog synthesis"),
                issue(2, title="feat: deterministic backlog synthesis"),
            ),
            "audit": audit(
                entry(
                    1,
                    issue_kind="feature_enhancement",
                    referenced_paths=["scripts/triage/frontier.py"],
                ),
                entry(
                    2,
                    issue_kind="feature_enhancement",
                    referenced_paths=["scripts/triage/frontier.py"],
                ),
            ),
            "signal_type": "likely-duplicate",
            "issue_numbers": (1, 2),
            "verdict_type": "likely-duplicate",
        },
        {
            "label": "split-candidate",
            "snapshot": snapshot(
                issue(
                    3,
                    title="feat: oversized governance workflow",
                    body=(
                        "This issue describes multiple coherent PRs and "
                        "separable workstreams."
                    ),
                ),
            ),
            "audit": audit(entry(3)),
            "signal_type": "split-candidate",
            "issue_numbers": (3,),
            "verdict_type": "split-candidate",
        },
        {
            "label": "dependency-order-inversion",
            "snapshot": snapshot(
                issue(10, title="feat: dependent"),
                issue(20, title="feat: blocker"),
            ),
            "audit": audit(entry(10, dependencies=[20]), entry(20)),
            "signal_type": "dependency-inversion",
            "issue_numbers": (10, 20),
            "verdict_type": "dependency-order",
        },
        {
            "label": "semantic-disposition-evidence",
            "snapshot": snapshot(
                issue(30, title="feat: duplicate"),
                issue(31, title="feat: owner"),
            ),
            "audit": audit(
                entry(
                    30,
                    recommended_disposition="implement",
                    semantic_disposition_hypothesis="likely-duplicate-of #31",
                    semantic_disposition_evidence=[
                        "semantic review points at #31 as the owner"
                    ],
                ),
                entry(31),
            ),
            "signal_type": "semantic-disposition",
            "issue_numbers": (30, 31),
            "verdict_type": "likely-duplicate",
        },
    ]

    for case in cases:
        report, packet = review_artifacts(case["snapshot"], case["audit"])
        signals = signals_by_type(report, str(case["signal_type"]))

        assert signals, case["label"]
        assert signals[0]["issue_numbers"] == list(case["issue_numbers"])
        assert frontier.validate_synthesis_review_packet(packet) == []
        assert packet["candidate_sets"][0]["signal_type"] == case["signal_type"]
        assert packet["evidence_items"][0]["evidence_id"] == "evidence-001"
        assert '"body":' not in json.dumps(packet, sort_keys=True)

        verdict = review_verdict(
            packet,
            verdict_type=str(case["verdict_type"]),
            issue_numbers=case["issue_numbers"],
            evidence_refs=("evidence-001",),
        )

        assert_verdict_validates_against_packet(verdict, packet)


def test_bounded_review_recall_precision_controls_validate_no_action_paths() -> None:
    controls = [
        {
            "label": "likely-duplicate-false-positive-control",
            "snapshot": snapshot(
                issue(1, title="feat: deterministic backlog synthesis"),
                issue(2, title="fix: pull request dependency resolution"),
            ),
            "audit": audit(
                entry(1, referenced_paths=["scripts/triage/frontier.py"]),
                entry(2, referenced_paths=["scripts/triage/readiness.py"]),
            ),
            "absent_signal": "likely-duplicate",
        },
        {
            "label": "no-split-control",
            "snapshot": snapshot(
                issue(3, title="feat: compact governance workflow", body="one task")
            ),
            "audit": audit(entry(3)),
            "absent_signal": "split-candidate",
        },
        {
            "label": "no-dependency-order-inversion-control",
            "snapshot": snapshot(
                issue(10, title="feat: blocker"),
                issue(20, title="feat: dependent"),
            ),
            "audit": audit(entry(10), entry(20, dependencies=[10])),
            "absent_signal": "dependency-inversion",
        },
    ]

    for case in controls:
        report, packet = review_artifacts(case["snapshot"], case["audit"])

        assert signals_by_type(report, str(case["absent_signal"])) == [], case[
            "label"
        ]
        assert frontier.validate_synthesis_review_packet(packet) == []

        no_action_verdict = backlog_review_verdict(
            packet=packet,
            verdicts=[],
            future_apply_recommendations=[],
            uncertainty=[
                {
                    "code": "no_actionable_candidates",
                    "rationale": (
                        "The hand-labeled control fixture has no bounded "
                        "actionable candidate."
                    ),
                }
            ],
        )

        assert_verdict_validates_against_packet(no_action_verdict, packet)


def test_bounded_review_recall_preserves_diagnostic_ids_and_rejects_unknown_refs() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog review"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
            parent_epics=[93],
        ),
    )

    report, packet = review_artifacts(snap, results)
    expected_near_miss = (
        "near-miss-possible-duplicate-001-002-"
        "title-similarity-below-threshold"
    )
    expected_omission = "omission-no-issue-body-in-signals"

    assert signals_by_type(report, "likely-duplicate") == []
    assert [item["near_miss_id"] for item in report["near_misses"]] == [
        expected_near_miss
    ]
    assert [item["omission_id"] for item in report["omissions"]] == [
        expected_omission
    ]
    assert expected_near_miss in {
        item["near_miss_id"] for item in packet["near_misses"]
    }
    assert expected_omission in {item["omission_id"] for item in packet["omissions"]}

    verdict = review_verdict(
        packet,
        verdict_type="insufficient-evidence",
        issue_numbers=(1, 2),
        near_miss_refs=(expected_near_miss,),
        omission_refs=(expected_omission,),
    )
    unknown_near_miss = json.loads(json.dumps(verdict))
    unknown_near_miss["verdicts"][0]["near_miss_refs"] = ["unknown-near-miss"]
    unknown_near_miss = sign_verdict(unknown_near_miss)
    unknown_omission = json.loads(json.dumps(verdict))
    unknown_omission["verdicts"][0]["omission_refs"] = ["unknown-omission"]
    unknown_omission = sign_verdict(unknown_omission)

    assert_verdict_validates_against_packet(verdict, packet)
    assert (
        "verdicts[0].near_miss_refs contains unknown packet near_miss_id: "
        "unknown-near-miss"
        in frontier.validate_backlog_review_verdict_against_packet(
            unknown_near_miss, packet
        )
    )
    assert (
        "verdicts[0].omission_refs contains unknown packet omission_id: "
        "unknown-omission"
        in frontier.validate_backlog_review_verdict_against_packet(
            unknown_omission, packet
        )
    )


def test_bounded_review_recall_freshness_degradation_fixtures() -> None:
    snap = snapshot(issue(96))
    results = audit(entry(96))
    report = frontier.build_backlog_synthesis_report(snap, results)

    fresh = frontier.build_synthesis_review_packet(
        snap, results, report, evaluated_at="2026-06-24T01:00:00Z"
    )
    exact_warning_boundary = frontier.build_synthesis_review_packet(
        snap, results, report, evaluated_at="2026-06-25T00:00:00Z"
    )
    warning = frontier.build_synthesis_review_packet(
        snap, results, report, evaluated_at="2026-06-25T01:00:00Z"
    )
    exact_hard_boundary = frontier.build_synthesis_review_packet(
        snap, results, report, evaluated_at="2026-07-01T00:00:00Z"
    )
    hard_stale = frontier.build_synthesis_review_packet(
        snap, results, report, evaluated_at="2026-07-01T00:00:01Z"
    )
    stricter_stale = frontier.build_synthesis_review_packet(
        snap,
        results,
        report,
        max_age_hours=48,
        evaluated_at="2026-06-27T00:00:01Z",
    )

    assert fresh["staleness"]["freshness_status"] == "fresh"
    assert fresh["staleness"]["freshness_warnings"] == []
    assert exact_warning_boundary["staleness"]["freshness_status"] == "fresh"
    assert warning["staleness"]["freshness_status"] == "warning"
    assert warning["staleness"]["stale"] is False
    assert warning["staleness"]["llm_review_allowed"] is True
    assert exact_hard_boundary["staleness"]["freshness_status"] == "warning"
    assert exact_hard_boundary["staleness"]["llm_review_allowed"] is True
    assert hard_stale["staleness"]["freshness_status"] == "stale"
    assert hard_stale["staleness"]["llm_review_allowed"] is False
    assert stricter_stale["staleness"]["freshness_status"] == "stale"
    assert frontier.validate_synthesis_review_packet(fresh) == []
    assert frontier.validate_synthesis_review_packet(warning) == []
    assert (
        "staleness.stale packets are not valid for LLM review"
        in frontier.validate_synthesis_review_packet(hard_stale)
    )

    source_artifacts = warning["source_artifacts"]
    warning_not_visible = {
        "source_packet_digest": warning["synthesis_review_packet_digest"],
        "source_snapshot_digest": source_artifacts["snapshot_digest"],
        "source_audit_digest": source_artifacts["audit_digest"],
        "source_backlog_synthesis_digest": source_artifacts[
            "backlog_synthesis_digest"
        ],
        "freshness_status": "warning",
        "freshness_warnings": [],
        "packet_stale": False,
        "llm_review_allowed": True,
        "invalid_lineage": False,
    }
    missing_warning_verdict = review_verdict(
        warning,
        verdict_type="insufficient-evidence",
        issue_numbers=(96,),
        omission_refs=("omission-no-issue-body-in-signals",),
        uncertainty=[],
        required_maintainer_checks=[],
        packet_reviewability=warning_not_visible,
    )
    preserved_warning_verdict = review_verdict(
        warning,
        verdict_type="insufficient-evidence",
        issue_numbers=(96,),
        omission_refs=("omission-no-issue-body-in-signals",),
        uncertainty=[
            {
                "code": "packet_freshness_warning",
                "message": "source_age_exceeds_warning_age",
            }
        ],
        packet_reviewability=warning_not_visible,
    )
    hard_stale_verdict = review_verdict(
        hard_stale,
        verdict_type="insufficient-evidence",
        issue_numbers=(96,),
        omission_refs=("omission-no-issue-body-in-signals",),
    )

    assert (
        "warning-only packet freshness warning is not preserved in verdict"
        in frontier.validate_backlog_review_verdict_against_packet(
            missing_warning_verdict, warning
        )
    )
    assert_verdict_validates_against_packet(preserved_warning_verdict, warning)
    assert (
        "source packet invalid: staleness.stale packets are not valid for LLM review"
        in frontier.validate_backlog_review_verdict_against_packet(
            hard_stale_verdict, hard_stale
        )
    )


def test_bounded_review_recall_invalid_lineage_fails_regardless_of_age() -> None:
    snap = snapshot(issue(99))
    results = audit(entry(99))
    report = frontier.build_backlog_synthesis_report(snap, results)
    tampered_report = json.loads(json.dumps(report))
    tampered_report["audit_digest"] = "9" * 64
    tampered_report["backlog_synthesis_digest"] = backlog_report_digest(
        tampered_report
    )
    invalid_lineage_verdict = backlog_review_verdict(
        packet=synthesis_review_packet_with_refs(),
        packet_reviewability={
            "source_packet_digest": "d" * 64,
            "source_snapshot_digest": "a" * 64,
            "source_audit_digest": "b" * 64,
            "source_backlog_synthesis_digest": "c" * 64,
            "freshness_status": "fresh",
            "freshness_warnings": [],
            "packet_stale": False,
            "llm_review_allowed": True,
            "invalid_lineage": True,
        },
    )

    assert frontier.validate_synthesis_review_packet_sources(
        snap, results, tampered_report
    ) == ["backlog-synthesis audit digest does not match readiness audit"]
    assert (
        "packet_reviewability.invalid_lineage must be false"
        in frontier.validate_backlog_review_verdict(invalid_lineage_verdict)
    )


def test_bounded_review_recall_artifact_digests_are_stable_and_tamper_visible() -> None:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
    )
    results = audit(
        entry(
            1,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
        entry(
            2,
            issue_kind="feature_enhancement",
            referenced_paths=["scripts/triage/frontier.py"],
        ),
    )

    left_report, left_packet = review_artifacts(snap, results)
    right_report, right_packet = review_artifacts(snap, results)
    left_verdict = review_verdict(
        left_packet,
        verdict_type="likely-duplicate",
        issue_numbers=(1, 2),
        evidence_refs=("evidence-001",),
    )
    right_verdict = review_verdict(
        right_packet,
        verdict_type="likely-duplicate",
        issue_numbers=(1, 2),
        evidence_refs=("evidence-001",),
    )
    tampered_verdict = json.loads(json.dumps(left_verdict))
    tampered_verdict["verdicts"][0]["recommendation"] = "Tampered."

    assert json.dumps(left_report, sort_keys=True) == json.dumps(
        right_report, sort_keys=True
    )
    assert left_report["backlog_synthesis_digest"] == right_report[
        "backlog_synthesis_digest"
    ]
    assert left_packet["synthesis_review_packet_digest"] == right_packet[
        "synthesis_review_packet_digest"
    ]
    assert left_verdict["backlog_review_verdict_digest"] == right_verdict[
        "backlog_review_verdict_digest"
    ]
    assert (
        "backlog_review_verdict_digest mismatch"
        in frontier.validate_backlog_review_verdict(tampered_verdict)
    )


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


def test_worker_packet_verification_commands_come_from_policy(tmp_path: Path) -> None:
    widgets_policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    snap = snapshot(issue(1))
    results = audit(entry(1))

    packet = frontier.build_worker_packet(
        1,
        snap,
        results,
        root=tmp_path,
        repo_policy=widgets_policy,
    )

    assert packet["required_verification_commands"] == [
        "python -m compileall -q scripts .codex/scripts .codex/hooks .codex/tests",
        "pytest -q scripts/triage",
    ]
    assert "dbt" not in repr(packet["required_verification_commands"])


def test_worker_packet_validation_rejects_mutating_verification_command(
    tmp_path: Path,
) -> None:
    packet = frontier.build_worker_packet(
        1,
        snapshot(issue(1)),
        audit(entry(1)),
        root=tmp_path,
    )
    packet["required_verification_commands"] = [
        "python -m pytest",
        "gh issue edit 119 --body-file body.md",
    ]
    packet["packet_digest"] = frontier.sha256_json(
        {key: value for key, value in packet.items() if key != "packet_digest"}
    )

    errors = frontier.validate_worker_packet(packet)

    assert any(
        "required_verification_commands[1]" in error
        and "GitHub mutation command" in error
        for error in errors
    )


def test_suggested_branch_strips_conventional_commit_scope() -> None:
    entry = {"issue_kind": "bug_fix", "issue_number": 7}
    branch = frontier.suggested_branch(entry, "fix(cli): resolve crash")
    assert branch.startswith("fix/7-")
    assert "cli" not in branch
    assert "resolve-crash" in branch
