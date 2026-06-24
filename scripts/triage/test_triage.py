from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.triage import triage


def test_sha_is_stable_for_unordered_dicts() -> None:
    assert triage.sha256_json({"b": 2, "a": 1}) == triage.sha256_json({"a": 1, "b": 2})


def test_refs_in_text_extracts_issue_numbers() -> None:
    assert triage.refs_in_text("Depends on #54 and #68, not abc#12") == {54, 68}


def test_dependency_cycle_detection() -> None:
    cycles = triage.find_cycles({1: {2}, 2: {3}, 3: {1}, 4: set()})
    assert cycles == [[1, 2, 3, 1]]


def test_missing_repo_paths_are_reported(tmp_path: Path) -> None:
    snapshot = {
        "issues": [
            {
                "number": 1,
                "state": "open",
                "labels": [],
                "body": "See docs/MISSING.md and docs/EXISTS.md.",
                "updated_at": "2026-06-23T00:00:00Z",
            }
        ],
        "labels": [],
    }
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "EXISTS.md").write_text("ok", encoding="ascii")
    policy = {
        "audit": {"check_missing_repo_paths": True, "check_dependency_cycles": False}
    }

    findings = triage.audit_snapshot(snapshot, policy, root=tmp_path)

    assert any(f["code"] == "missing-repo-path" for f in findings)
    assert findings[0]["data"] == ["docs/MISSING.md"]


def test_plan_digest_embedded_matches_normalized_plan() -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    assert plan["plan_sha256"] == triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )


def test_approval_rejects_wrong_digest() -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    approval = {
        "plan_sha256": "bad",
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": [],
    }
    with pytest.raises(triage.TriageError, match="plan digest mismatch|approval file"):
        triage.validate_approval(plan, approval, "bad", "bootstrap")


def test_apply_dry_run_allows_empty_approved_batch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    plan_path.write_text(json.dumps(plan), encoding="ascii")
    approval_path.write_text(
        json.dumps(
            {
                "plan_sha256": plan["plan_sha256"],
                "approved_batches": ["bootstrap"],
                "approved_operation_ids": [],
                "allow_destructive": False,
            }
        ),
        encoding="ascii",
    )

    code = triage.main(
        [
            "apply",
            "--plan",
            str(plan_path),
            "--approval",
            str(approval_path),
            "--plan-sha",
            plan["plan_sha256"],
            "--batch",
            "bootstrap",
            "--dry-run",
        ]
    )

    assert code == 0
    assert "No operations selected" in capsys.readouterr().out


def _valid_bug_body() -> str:
    return """## Summary

Fix one issue.

## Evidence and confidence

Source proves the defect.

## Current wrong behavior

Unknown becomes false.

## Root cause

State collapse.

## Expected behavior

Preserve unknown.

## Acceptance criteria

- Positive succeeds.
- Invalid negative is rejected.
- Failure degrades to unverified offline behavior.
- Existing compatibility remains unchanged in regression tests.

## Focused test plan

Run positive, negative, degradation, and regression tests.

## Scope and likely files

- scripts/triage/triage.py

## Explicit non-goals

- No writes.

## Dependencies and traceability

- Parent epic: #4
"""


def _snapshot_file(tmp_path: Path) -> Path:
    (tmp_path / "scripts/triage").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts/triage/triage.py").write_text("", encoding="ascii")
    snapshot = {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": "dckallos/dbt-diagnostics",
        "source": {"transport": "offline-test", "github_writes_attempted": False},
        "issues": [
            {
                "number": 1,
                "state": "open",
                "title": "fix: one issue",
                "labels": ["bug"],
                "milestone": None,
                "body": _valid_bug_body(),
                "html_url": "https://github.com/dckallos/dbt-diagnostics/issues/1",
            }
        ],
        "pulls": [],
        "labels": [{"name": "bug", "description": "", "color": "d73a4a"}],
        "milestones": [],
        "projects": {"status": "disabled", "items": []},
    }
    snapshot["snapshot_digest"] = triage.content_digest(snapshot)
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="ascii")
    return path


def test_gh_api_paginated_is_get_only_and_flattens_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_gh_json(runner, args, timeout=60.0):
        captured.append(args)
        return [[{"number": 1}], [{"number": 2}]]

    monkeypatch.setattr(triage, "gh_json", fake_gh_json)
    result = triage.gh_api_paginated(
        triage.Runner(), "/repos/x/y/issues", {"state": "open"}
    )
    assert result == [{"number": 1}, {"number": 2}]
    command = captured[0]
    assert command[:5] == ["api", "--method", "GET", "--paginate", "--slurp"]
    assert not any(value in {"POST", "PATCH", "PUT", "DELETE"} for value in command)


def test_snapshot_validation_rejects_digest_drift(tmp_path: Path) -> None:
    path = _snapshot_file(tmp_path)
    value = json.loads(path.read_text())
    value["issues"][0]["title"] = "changed"
    with pytest.raises(triage.TriageError, match="snapshot_digest"):
        triage.validate_snapshot(value)


def test_contract_command_runs_fully_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot_path = _snapshot_file(tmp_path)
    code = triage.main(
        ["contract", "--issue", "1", "--snapshot", str(snapshot_path), "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "1.0"


def test_audit_command_writes_machine_and_readable_results(tmp_path: Path) -> None:
    snapshot_path = _snapshot_file(tmp_path)
    semantic = tmp_path / "semantic.json"
    semantic.write_text(
        json.dumps(
            {
                "1": {
                    "status": "accepted",
                    "source_claims_checked": ["scripts/triage/triage.py"],
                    "tests_checked": ["scripts/triage/test_triage.py"],
                    "one_pr_coherent": True,
                    "dependency_merge_evidence": True,
                }
            }
        ),
        encoding="ascii",
    )
    output = tmp_path / "audit-output"
    code = triage.main(
        [
            "audit",
            "--snapshot",
            str(snapshot_path),
            "--semantic-evidence",
            str(semantic),
            "--output-dir",
            str(output),
        ]
    )
    assert code == 0
    payload = json.loads((output / "audit.json").read_text())
    assert payload["issue_count"] == 1
    assert (output / "audit.md").is_file()


def test_review_packet_is_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_path = _snapshot_file(tmp_path)
    output = tmp_path / "review"
    calls: list[object] = []

    def fail(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("subprocess attempted")

    monkeypatch.setattr("subprocess.run", fail)
    code = triage.main(
        [
            "review-packet",
            "--issue",
            "1",
            "--snapshot",
            str(snapshot_path),
            "--output-dir",
            str(output),
        ]
    )
    assert code == 0
    assert calls == []
    assert (output / "review.json").is_file()
    assert (output / "proposed-body.md").is_file()
    assert (
        json.loads((output / "review.json").read_text())["github_mutation_permitted"]
        is False
    )


def test_standardize_reaudits_proposed_body_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_path = _snapshot_file(tmp_path)
    proposed = tmp_path / "proposed.md"
    proposed.write_text(_valid_bug_body(), encoding="ascii")
    output = tmp_path / "standardized"
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess attempted")
        ),
    )
    code = triage.main(
        [
            "standardize",
            "--issue",
            "1",
            "--snapshot",
            str(snapshot_path),
            "--proposed-body",
            str(proposed),
            "--output-dir",
            str(output),
        ]
    )
    assert code == 0
    audit = json.loads((output / "contract-audit.json").read_text())
    assert audit["governance_state"] == "conformant"


def test_apply_forbids_issue_body_operation(tmp_path: Path) -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    operation = {
        "operation_id": "body-1",
        "kind": "issue.body.update",
        "batch": "bootstrap",
        "destructive": False,
    }
    plan["operations"] = [operation]
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": ["body-1"],
        "allow_destructive": False,
    }
    with pytest.raises(triage.TriageError, match="body mutation"):
        triage.validate_approval(plan, approval, plan["plan_sha256"], "bootstrap")


def test_execute_mode_remains_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    plan["operations"] = [
        {
            "operation_id": "label-1",
            "kind": "issue.label.add",
            "batch": "bootstrap",
            "destructive": False,
        }
    ]
    plan["plan_sha256"] = triage.sha256_json(
        triage.normalized_plan_without_digest(plan)
    )
    approval = {
        "plan_sha256": plan["plan_sha256"],
        "approved_batches": ["bootstrap"],
        "approved_operation_ids": ["label-1"],
        "allow_destructive": False,
    }
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "approval.json"
    plan_path.write_text(json.dumps(plan), encoding="ascii")
    approval_path.write_text(json.dumps(approval), encoding="ascii")
    code = triage.main(
        [
            "apply",
            "--plan",
            str(plan_path),
            "--approval",
            str(approval_path),
            "--plan-sha",
            plan["plan_sha256"],
            "--batch",
            "bootstrap",
            "--execute",
        ]
    )
    assert code == 2
    assert "intentionally unavailable" in capsys.readouterr().err


def test_generated_repository_files_are_ascii(tmp_path: Path) -> None:
    snapshot_path = _snapshot_file(tmp_path)
    output = tmp_path / "review"
    assert (
        triage.main(
            [
                "review-packet",
                "--issue",
                "1",
                "--snapshot",
                str(snapshot_path),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    for path in output.iterdir():
        path.read_bytes().decode("ascii")
