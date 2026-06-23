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
    policy = {"audit": {"check_missing_repo_paths": True, "check_dependency_cycles": False}}

    findings = triage.audit_snapshot(snapshot, policy, root=tmp_path)

    assert any(f["code"] == "missing-repo-path" for f in findings)
    assert findings[0]["data"] == ["docs/MISSING.md"]


def test_plan_digest_embedded_matches_normalized_plan() -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    assert plan["plan_sha256"] == triage.sha256_json(triage.normalized_plan_without_digest(plan))


def test_approval_rejects_wrong_digest() -> None:
    plan = triage.make_plan({"repository": "r", "issues": []}, {"audit": {}}, [])
    approval = {"plan_sha256": "bad", "approved_batches": ["bootstrap"], "approved_operation_ids": []}
    with pytest.raises(triage.TriageError, match="plan digest mismatch|approval file"):
        triage.validate_approval(plan, approval, "bad", "bootstrap")


def test_apply_dry_run_allows_empty_approved_batch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
