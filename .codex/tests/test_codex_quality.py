from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]


def _load_codex_script(name: str):
    path = ROOT / ".codex" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_codex_quality_wrapper_is_exposed() -> None:
    action = (ROOT / ".codex" / "bin" / "action.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / ".codex" / "bin" / "codex-quality.sh").read_text(
        encoding="utf-8"
    )

    assert "codex-quality  Run repository-specific Codex semantic quality gates" in action
    assert "\n  codex-quality)" in action
    assert ".codex/scripts/codex_quality.py" in wrapper


def test_issue_work_skill_does_not_authorize_issue_body_mutation() -> None:
    skill = (ROOT / ".agents" / "skills" / "issue-work" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "only GitHub metadata mutation allowed" not in skill
    assert "live issue body is updated" not in skill
    assert "authorized writer flow" not in skill
    assert "maintainer updates the live issue" not in skill
    assert "changes outside issue-work" in skill
    assert "issue-work skill never" in skill


def test_agents_records_single_progress_log_entry_per_pr() -> None:
    agents = re.sub(
        r"\s+", " ", (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )

    assert "Maintain exactly one dated entry per PR" in agents
    assert "otherwise edit that PR entry in place" in agents
    assert "single cohesive entry" in agents


def test_agents_records_direct_operator_delegation_boundary() -> None:
    agents = re.sub(
        r"\s+", " ", (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )

    assert "one exact GitHub operator action" in agents
    assert "outside issue-governance/issue-work outputs" in agents
    assert "triage artifacts, plans, and allowlists" in agents


def test_issue_work_skill_requires_pr_auto_close_keyword() -> None:
    skill = (ROOT / ".agents" / "skills" / "issue-work" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Closes #<issue>" in skill
    assert "Refs #<issue>" in skill
    assert "closingIssuesReferences" in skill


def test_governance_boundary_checker_rejects_authorized_issue_body_write() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = (
        "The issue-body update is the only GitHub metadata mutation allowed "
        "by this prerequisite."
    )

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "issue-body-write",
        "allowed-github-metadata-mutation",
    }


def test_governance_boundary_checker_rejects_mixed_safe_and_unsafe_prose() -> None:
    checker = _load_codex_script("check_governance_boundary")
    mixed = (
        "Never close issues from the read-only governance workflow. "
        "The issue-body update is the only GitHub metadata mutation allowed "
        "by this prerequisite."
    )

    violations = checker.scan_text(mixed, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "issue-body-write",
        "allowed-github-metadata-mutation",
    }


def test_governance_boundary_checker_rejects_read_only_authorization() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "This read-only skill may close GitHub issues."

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "authorized-tracker-mutation",
    }


def test_governance_boundary_checker_allows_negated_read_only_sentence() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "This read-only skill must not close GitHub issues."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_allows_negated_project_mutation() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "The tool does not create a Project or mutate Project fields."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_allows_pr_auto_close_keyword() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = (
        "When creating a PR, make the PR body close this implemented issue with "
        "a GitHub auto-close keyword."
    )

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_rejects_forbidden_operation_allowlist() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "Allowed operations: issue.body.update"

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "forbidden-operation-id",
    }


def test_governance_boundary_checker_allows_forbidden_operation_id_docs() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "The forbidden operation issue.body.update remains unsupported."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_rejects_verb_first_tracker_mutation() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "Edit the GitHub issue body after approval."

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "verb-first-tracker-mutation",
    }


def test_governance_boundary_checker_allows_forbidden_operation_docs() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = (
        "Never create, edit, close, label, milestone, or move a GitHub item. "
        "Issue-body mutation remains forbidden."
    )

    assert checker.scan_text(safe, path="fixture.md") == []


def test_default_governance_boundary_scan_includes_issue_contract() -> None:
    checker = _load_codex_script("check_governance_boundary")

    paths = {path.relative_to(ROOT).as_posix() for path in checker.default_paths(ROOT)}

    assert "docs/ISSUE_CONTRACT_V1.md" in paths


def test_codex_quality_writes_receipt(tmp_path: Path) -> None:
    quality = _load_codex_script("codex_quality")
    (tmp_path / ".agents" / "skills" / "issue-work").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text(
        "Never create, edit, close, label, milestone, or move a GitHub item.\n",
        encoding="ascii",
    )
    (tmp_path / ".agents" / "skills" / "issue-work" / "SKILL.md").write_text(
        "Issue-body mutation remains forbidden.\n",
        encoding="ascii",
    )

    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    receipt = quality.run_quality(root=tmp_path, receipt_path=receipt_path)

    assert receipt["passed"] is True
    assert receipt_path.is_file()
    saved = json.loads(receipt_path.read_text(encoding="ascii"))
    assert saved["schema_version"] == 1
    assert saved["checks"][0]["name"] == "governance-boundary"
    assert saved["checks"][0]["status"] == "passed"
    assert saved["covered_protected_paths"] == [
        ".agents/skills/issue-work/SKILL.md",
        "AGENTS.md",
    ]
    assert saved["quality_receipt_digest"] == quality.receipt_digest(saved)


def test_codex_quality_records_deterministic_covered_protected_paths(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    (tmp_path / ".codex" / "hooks").mkdir(parents=True)
    (tmp_path / ".codex" / "hooks" / "stop.py").write_text(
        "# stop hook\n", encoding="ascii"
    )
    (tmp_path / "README.md").write_text("unprotected\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"

    receipt = quality.run_quality(
        root=tmp_path,
        receipt_path=receipt_path,
        paths=[
            Path("README.md"),
            Path(".codex/hooks/stop.py"),
            Path("./.codex/hooks/stop.py"),
        ],
    )

    assert receipt["covered_protected_paths"] == [".codex/hooks/stop.py"]
    saved = json.loads(receipt_path.read_text(encoding="ascii"))
    assert saved["covered_protected_paths"] == [".codex/hooks/stop.py"]
    assert saved["quality_receipt_digest"] == quality.receipt_digest(saved)
