from __future__ import annotations

from pathlib import Path

from scripts.triage import readiness


def bug_body(extra: str = "") -> str:
    return f"""## Summary

I will fix one bounded defect.

## Evidence and confidence

Source and tests establish the problem with high confidence.

## Current wrong behavior

Unknown state becomes a false fact.

## Root cause

A boolean collapses multiple outcomes.

## Expected behavior

Preserve every state.

## Acceptance criteria

- A positive case succeeds.
- An invalid negative case is rejected.
- A failed probe degrades to unverified offline behavior.
- Existing compatibility remains unchanged in regression tests.

## Focused test plan

Run positive, negative, degradation, and regression tests.

## Scope and likely files

- scripts/triage/triage.py

## Explicit non-goals

- No GitHub write.

## Dependencies and traceability

{extra or "- Parent epic: #4"}
"""


def snapshot(*issues: dict, pulls: list[dict] | None = None) -> dict:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "issues": list(issues),
        "pulls": pulls or [],
        "labels": [],
        "milestones": [{"number": 1, "title": "Initial release", "state": "open"}],
        "projects": {"status": "disabled", "items": []},
    }


def policy() -> dict:
    return {
        "repository": {
            "default_branch": "donkey-kong-sandbox",
            "required_base_branch": "donkey-kong-sandbox",
        },
        "release": {"milestone_number": 1, "epics": [4], "additional_issues": []},
        "audit": {"require_open_issue_type_label": True},
    }


def accepted_semantic(**overrides: object) -> dict:
    result: dict[str, object] = {
        "status": "accepted",
        "source_claims_checked": ["scripts/triage/triage.py"],
        "tests_checked": ["scripts/triage/test_triage.py"],
        "one_pr_coherent": True,
        "confidence": "high",
        "dependency_merge_evidence": True,
    }
    result.update(overrides)
    return result


def test_dependency_relationships_parse_only_direct_fields() -> None:
    body = """## Traceability

- Parent epic: #4
- Depends on corrected probes: #55, #54
- Coordinates with: #63
- Supersedes: #64
"""
    parsed = readiness.parse_relationships(body)
    assert parsed.dependencies == (54, 55)
    assert parsed.parent_epics == (4,)
    assert parsed.related == (63,)
    assert parsed.supersedes == (64,)


def test_dependency_cycle_is_detected() -> None:
    snap = snapshot(
        {
            "number": 1,
            "state": "open",
            "title": "fix: one",
            "labels": ["bug"],
            "body": bug_body("- Depends on: #2"),
        },
        {
            "number": 2,
            "state": "open",
            "title": "fix: two",
            "labels": ["bug"],
            "body": bug_body("- Depends on: #1"),
        },
    )
    assert readiness.find_cycles(readiness.dependency_graph(snap)) == [[1, 2, 1]]


def test_closed_duplicate_dependency_marks_issue_stale(tmp_path: Path) -> None:
    snap = snapshot(
        {
            "number": 1,
            "state": "open",
            "title": "fix: one",
            "labels": ["bug"],
            "body": bug_body("- Depends on: #2"),
        },
        {
            "number": 2,
            "state": "closed",
            "state_reason": "duplicate",
            "title": "fix: old",
            "labels": ["bug"],
            "body": bug_body(),
        },
    )
    result = readiness.audit_all_issues(
        snap,
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    issue = next(item for item in result["issues"] if item["issue_number"] == 1)
    assert issue["implementation_state"] == "stale"
    assert issue["closed_or_stale_dependencies"][0]["state_reason"] == "duplicate"


def test_closed_duplicate_issue_is_superseded(tmp_path: Path) -> None:
    snap = snapshot(
        {
            "number": 2,
            "state": "closed",
            "state_reason": "duplicate",
            "title": "fix: old",
            "labels": ["bug"],
            "body": bug_body(),
        },
    )
    result = readiness.audit_all_issues(snap, policy(), root=tmp_path)
    assert result["issues"][0]["implementation_state"] == "superseded"


def test_release_gate_milestone_drift(tmp_path: Path) -> None:
    epic_body = """## Summary

Track release work.

## Evidence and confidence

Live tracker evidence.

## Thesis

Use explicit gates.

## Initial-release gate

- [ ] #2

## Children and backlog

- #2

## Open decisions

- None.

## Workflow

One issue per PR.
"""
    snap = snapshot(
        {
            "number": 4,
            "state": "open",
            "title": "[Epic] Release",
            "labels": ["epic"],
            "milestone": {"number": 1},
            "body": epic_body,
        },
        {
            "number": 2,
            "state": "open",
            "title": "fix: gate",
            "labels": ["bug"],
            "milestone": None,
            "body": bug_body(),
        },
    )
    result = readiness.audit_all_issues(snap, policy(), root=tmp_path)
    item = next(value for value in result["issues"] if value["issue_number"] == 2)
    assert item["release_gate"] is True
    assert item["milestone_drift"] is True
    assert item["governance_state"] == "stale"


def test_missing_source_path_blocks_readiness(tmp_path: Path) -> None:
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: path",
        "labels": ["bug"],
        "body": bug_body().replace("scripts/triage/triage.py", "docs/MISSING.md"),
    }
    result = readiness.audit_all_issues(
        snapshot(issue),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    item = result["issues"][0]
    assert item["implementation_state"] == "blocked"
    assert item["missing_repository_paths"] == ["docs/MISSING.md"]


def test_one_pr_scope_warning_is_reported(tmp_path: Path) -> None:
    paths = "\n".join(f"- docs/path_{index}.md" for index in range(15))
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: broad",
        "labels": ["bug"],
        "body": bug_body().replace("- scripts/triage/triage.py", paths),
    }
    for index in range(15):
        (tmp_path / "docs").mkdir(exist_ok=True)
        (tmp_path / "docs" / f"path_{index}.md").write_text("x", encoding="ascii")
    result = readiness.audit_all_issues(snapshot(issue), policy(), root=tmp_path)
    assert any(
        finding["code"] == "one-pr-scope-warning"
        for finding in result["issues"][0]["tracker_findings"]
    )


def test_decision_needed_state_is_not_ready(tmp_path: Path) -> None:
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: decision",
        "labels": ["bug", "decision-needed"],
        "body": bug_body()
        + "\n## Maintainer decisions and blockers\n\nChoose the default.\n",
    }
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    result = readiness.audit_all_issues(
        snapshot(issue),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    item = result["issues"][0]
    assert item["implementation_state"] == "needs_decision"
    assert item["required_decisions"]


def test_external_evidence_blocks_until_available(tmp_path: Path) -> None:
    body = (
        bug_body()
        + """
## External evidence, permissions, credentials, or fixtures

A real Snowflake account is required.

## Offline behavior

No credentials are used offline.

## Live behavior and cost tier

Tier A metadata only.
"""
    )
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: live",
        "labels": ["bug", "live"],
        "body": body,
    }
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    result = readiness.audit_all_issues(
        snapshot(issue),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    assert result["issues"][0]["implementation_state"] == "blocked"

    semantic = accepted_semantic(external_evidence_available=True)
    result = readiness.audit_all_issues(
        snapshot(issue), policy(), root=tmp_path, semantic_evidence={1: semantic}
    )
    assert result["issues"][0]["implementation_state"] == "ready"


def test_semantic_review_is_required_before_ready(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: review",
        "labels": ["bug"],
        "body": bug_body(),
    }
    result = readiness.audit_all_issues(snapshot(issue), policy(), root=tmp_path)
    assert result["issues"][0]["implementation_state"] == "needs_semantic_review"


def test_semantic_acceptance_can_make_issue_ready(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body(),
    }
    result = readiness.audit_all_issues(
        snapshot(issue),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    assert result["issues"][0]["implementation_state"] == "ready"


def test_known_false_assumption_prevents_ready(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: false",
        "labels": ["bug"],
        "body": bug_body(),
    }
    semantic = accepted_semantic(known_false_assumption=True)
    result = readiness.audit_all_issues(
        snapshot(issue), policy(), root=tmp_path, semantic_evidence={1: semantic}
    )
    assert result["issues"][0]["implementation_state"] == "needs_contract_revision"


def test_explicit_ownership_overlap_is_detected(tmp_path: Path) -> None:
    first = bug_body() + "\n## Ownership\n\ncanonical report assembly\n"
    second = bug_body() + "\n## Scope owner\n\ncanonical report assembly\n"
    snap = snapshot(
        {
            "number": 1,
            "state": "open",
            "title": "fix: one",
            "labels": ["bug"],
            "body": first,
        },
        {
            "number": 2,
            "state": "open",
            "title": "fix: two",
            "labels": ["bug"],
            "body": second,
        },
    )
    result = readiness.audit_all_issues(snap, policy(), root=tmp_path)
    states = {
        item["issue_number"]: item["implementation_state"] for item in result["issues"]
    }
    assert states == {
        1: "needs_contract_revision",
        2: "needs_contract_revision",
    }
    assert all(item["overlap_conflicts"] for item in result["issues"])


def test_active_pr_conflict_blocks_implementation(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body(),
    }
    pulls = [
        {
            "number": 10,
            "state": "open",
            "title": "Fixes #1",
            "body": "",
            "head_ref": "fix/1-ready",
            "base_ref": "donkey-kong-sandbox",
        }
    ]
    result = readiness.audit_all_issues(
        snapshot(issue, pulls=pulls),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    assert result["issues"][0]["implementation_state"] == "blocked"
    assert result["issues"][0]["active_pr_conflicts"] == [10]


def test_progress_log_staleness(tmp_path: Path) -> None:
    progress = tmp_path / "PROGRESS_LOG.md"
    progress.write_text("## 2026-06-16\n\nOld.\n", encoding="ascii")
    snap = snapshot(
        {
            "number": 1,
            "state": "open",
            "title": "fix: update",
            "labels": ["bug"],
            "body": bug_body(),
            "updated_at": "2026-06-23T00:00:00Z",
        }
    )
    drift = readiness.progress_log_drift(snap, progress)
    assert drift and drift["code"] == "stale-progress-log"


def test_audit_digest_and_order_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issues = [
        {
            "number": 2,
            "state": "open",
            "title": "fix: two",
            "labels": ["bug"],
            "body": bug_body(),
        },
        {
            "number": 1,
            "state": "open",
            "title": "fix: one",
            "labels": ["bug"],
            "body": bug_body(),
        },
    ]
    first = readiness.audit_all_issues(snapshot(*issues), policy(), root=tmp_path)
    second = readiness.audit_all_issues(
        snapshot(*reversed(issues)), policy(), root=tmp_path
    )
    assert [item["issue_number"] for item in first["issues"]] == [1, 2]
    assert first["audit_digest"] == second["audit_digest"]


def test_bold_relationship_labels_with_colon_inside_bold_are_parsed() -> None:
    body = """## Traceability

- **Depends on:** #2
- **Parent epic:** #4
- **Related:** #6
- **Supersedes:** #7
- **Ownership:** coordinator validation
"""
    parsed = readiness.parse_relationships(body)
    assert parsed.dependencies == (2,)
    assert parsed.parent_epics == (4,)
    assert parsed.related == (6,)
    assert parsed.supersedes == (7,)
    assert parsed.ownership == ("coordinator validation",)


def test_release_gate_honors_current_policy_keys_and_dependency_closure() -> None:
    snap = snapshot(
        {
            "number": 9,
            "state": "open",
            "title": "[Epic] Release",
            "labels": ["epic"],
            "body": "## Ship gate\n\n- [ ] #8\n",
        },
        {
            "number": 8,
            "state": "open",
            "title": "fix: gate",
            "labels": ["bug"],
            "body": "- **Depends on:** #6\n",
        },
        {
            "number": 7,
            "state": "open",
            "title": "fix: configured",
            "labels": ["bug"],
            "body": "",
        },
        {
            "number": 6,
            "state": "open",
            "title": "fix: dependency",
            "labels": ["bug"],
            "body": "",
        },
    )
    value = policy()
    value["release"] = {
        "milestone_number": 1,
        "epic_numbers": [9],
        "section_headings": ["Ship gate"],
        "additional_issue_numbers": [7],
        "include_epics": False,
        "include_dependency_closure": True,
    }
    assert readiness.derive_release_gate(snap, value) == [6, 7, 8]


def test_closed_dependency_with_merge_evidence_remains_ready(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    snap = snapshot(
        {
            "number": 1,
            "state": "open",
            "title": "fix: ready",
            "labels": ["bug"],
            "body": bug_body("- **Depends on:** #2"),
        },
        {
            "number": 2,
            "state": "closed",
            "state_reason": "completed",
            "title": "fix: merged dependency",
            "labels": ["bug"],
            "body": bug_body(),
        },
    )
    result = readiness.audit_all_issues(
        snap,
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic(dependency_merge_evidence=True)},
    )
    item = next(value for value in result["issues"] if value["issue_number"] == 1)
    assert item["governance_state"] == "conformant"
    assert item["implementation_state"] == "ready"
    assert item["dependency_merge_evidence"] is True
    assert not any(
        finding["code"] == "closed-dependency" for finding in item["tracker_findings"]
    )


def test_live_snapshot_pull_request_keys_are_consumed(tmp_path: Path) -> None:
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body(),
    }
    open_pull = {
        "number": 10,
        "state": "open",
        "title": "Fixes #1",
        "body": "",
        "head_ref": "fix/1-ready",
        "base_ref": "wrong-base",
    }
    for key in ("pull_requests", "open_pull_requests"):
        snap = snapshot(issue)
        snap.pop("pulls")
        snap[key] = [open_pull]
        assert readiness.active_pr_conflicts(1, snap) == [10]
        result = readiness.audit_all_issues(snap, policy(), root=tmp_path)
        assert any(
            finding["code"] == "pull-request-base-drift"
            for finding in result["global_findings"]
        )


def test_blocks_line_parses_into_blocks_not_related() -> None:
    parsed = readiness.parse_relationships(
        bug_body("- Parent epic: #4\n- Blocks: #70, #54\n- Related: #63")
    )
    assert parsed.blocks == (54, 70)
    assert parsed.related == (63,)
    assert 70 not in parsed.related and 54 not in parsed.related


def test_open_inbound_blocker_blocks_otherwise_ready_issue(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    blocker = {
        "number": 1,
        "state": "open",
        "title": "fix: blocker",
        "labels": ["bug"],
        "body": bug_body("- Parent epic: #4\n- Blocks: #2"),
    }
    blocked = {
        "number": 2,
        "state": "open",
        "title": "fix: blocked",
        "labels": ["bug"],
        "body": bug_body("- Parent epic: #4"),
    }
    result = readiness.audit_all_issues(
        snapshot(blocker, blocked),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic(), 2: accepted_semantic()},
    )
    item = next(v for v in result["issues"] if v["issue_number"] == 2)
    assert item["implementation_state"] == "blocked"
    assert item["open_inbound_blockers"] == [1]
    assert any(
        finding["code"] == "blocked-by-open-issue"
        for finding in item["tracker_findings"]
    )


def test_closed_inbound_blocker_does_not_block(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    blocker = {
        "number": 1,
        "state": "closed",
        "state_reason": "completed",
        "title": "fix: blocker",
        "labels": ["bug"],
        "body": bug_body("- Parent epic: #4\n- Blocks: #2"),
    }
    blocked = {
        "number": 2,
        "state": "open",
        "title": "fix: blocked",
        "labels": ["bug"],
        "body": bug_body("- Parent epic: #4"),
    }
    result = readiness.audit_all_issues(
        snapshot(blocker, blocked),
        policy(),
        root=tmp_path,
        semantic_evidence={2: accepted_semantic()},
    )
    item = next(v for v in result["issues"] if v["issue_number"] == 2)
    assert item["open_inbound_blockers"] == []
    assert item["implementation_state"] == "ready"


def test_body_requires_ignores_immediately_negated_terms() -> None:
    assert readiness._body_requires("No open decisions.", readiness.DECISION_TERMS) is False
    assert (
        readiness._body_requires(
            "No external evidence required.", readiness.EXTERNAL_TERMS
        )
        is False
    )
    # A genuine signal (not negated) is still detected.
    assert (
        readiness._body_requires("Open decision: pick a default.", readiness.DECISION_TERMS)
        is True
    )
    # A distant negation elsewhere on the line does not suppress a real signal.
    assert (
        readiness._body_requires(
            "This requires a maintainer decision; no shortcuts.",
            readiness.DECISION_TERMS,
        )
        is True
    )


def test_documented_absence_of_blockers_stays_ready(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    body = bug_body("- Parent epic: #4").replace(
        "I will fix one bounded defect.",
        "I will fix one bounded defect. No open decisions. "
        "No external evidence required.",
    )
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": body,
    }
    result = readiness.audit_all_issues(
        snapshot(issue), policy(), root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    item = next(v for v in result["issues"] if v["issue_number"] == 1)
    assert item["implementation_state"] == "ready"


def test_genuine_open_decision_text_needs_decision(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    body = bug_body("- Parent epic: #4").replace(
        "I will fix one bounded defect.",
        "I will fix one bounded defect. Open decision: choose the default mode.",
    )
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": body,
    }
    result = readiness.audit_all_issues(
        snapshot(issue), policy(), root=tmp_path,
        semantic_evidence={1: accepted_semantic()},
    )
    item = next(v for v in result["issues"] if v["issue_number"] == 1)
    assert item["implementation_state"] == "needs_decision"


def test_dependency_on_merged_pull_request_is_satisfied(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body("- **Depends on:** #2"),
    }
    merged_pull = {
        "number": 2,
        "state": "closed",
        "title": "feat: merged dependency",
        "body": "",
        "head_ref": "feat/2-dependency",
        "base_ref": "donkey-kong-sandbox",
        "merged_at": "2026-06-24T00:00:00Z",
        "merge_commit_sha": "abc1234",
    }
    result = readiness.audit_all_issues(
        snapshot(issue, pulls=[merged_pull]),
        policy(),
        root=tmp_path,
        # The PR's own merge state must satisfy the dependency, so deny the
        # semantic merge-evidence default to prove the PR map is consulted.
        semantic_evidence={1: accepted_semantic(dependency_merge_evidence=False)},
    )
    item = next(value for value in result["issues"] if value["issue_number"] == 1)
    assert item["implementation_state"] == "ready"
    assert item["dependency_merge_evidence"] is True
    assert not any(
        finding["code"] in {"missing-dependency", "closed-dependency"}
        for finding in item["tracker_findings"]
    )


def test_dependency_on_open_pull_request_blocks_but_is_not_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body("- **Depends on:** #2"),
    }
    open_pull = {
        "number": 2,
        "state": "open",
        "title": "feat: dependency in flight",
        "body": "",
        "head_ref": "feat/2-dependency",
        "base_ref": "donkey-kong-sandbox",
    }
    result = readiness.audit_all_issues(
        snapshot(issue, pulls=[open_pull]),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic(dependency_merge_evidence=False)},
    )
    item = next(value for value in result["issues"] if value["issue_number"] == 1)
    assert item["implementation_state"] == "blocked"
    assert not any(
        finding["code"] == "missing-dependency"
        for finding in item["tracker_findings"]
    )


def test_dependency_on_closed_unmerged_pull_request_is_stale(tmp_path: Path) -> None:
    (tmp_path / "scripts/triage").mkdir(parents=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    issue = {
        "number": 1,
        "state": "open",
        "title": "fix: ready",
        "labels": ["bug"],
        "body": bug_body("- **Depends on:** #2"),
    }
    closed_pull = {
        "number": 2,
        "state": "closed",
        "title": "feat: abandoned dependency",
        "body": "",
        "head_ref": "feat/2-dependency",
        "base_ref": "donkey-kong-sandbox",
    }
    result = readiness.audit_all_issues(
        snapshot(issue, pulls=[closed_pull]),
        policy(),
        root=tmp_path,
        semantic_evidence={1: accepted_semantic(dependency_merge_evidence=False)},
    )
    item = next(value for value in result["issues"] if value["issue_number"] == 1)
    assert item["implementation_state"] == "stale"
    assert any(
        finding["code"] == "closed-dependency"
        for finding in item["tracker_findings"]
    )
