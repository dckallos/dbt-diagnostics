from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = ROOT / ".agents" / "skills" / "issue-work" / "SKILL.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _normalized_skill() -> str:
    return re.sub(r"\s+", " ", _skill_text())


def test_issue_work_skill_frontmatter_preserves_scope() -> None:
    skill = _skill_text()

    assert SKILL_PATH.is_file()
    assert skill.startswith("---\n")
    assert "\nname: issue-work\n" in skill
    assert "Implement exactly one configured-repository GitHub issue" in skill
    assert "Do not use for backlog-wide planning or GitHub metadata changes." in skill


def test_issue_work_skill_requires_full_risk_contract() -> None:
    skill = _skill_text()
    required_fields = (
        "issue",
        "parent/dependencies",
        "blocker/dependency state",
        "change class",
        "protected surfaces expected",
        "stable artifacts/contracts touched",
        "read-only/write-boundary risk",
        "existing owners to modify",
        "likely obsolete paths to remove or simplify",
        "required focused tests",
        "required gates",
        "stop conditions",
        "remaining uncertainty",
    )

    assert "Risk contract:" in skill
    for field in required_fields:
        assert f"- {field}:" in skill


def test_issue_work_skill_requires_risk_contract_refresh() -> None:
    skill = _normalized_skill()

    assert "refresh the risk contract" in skill
    for trigger in (
        "new protected surface",
        "stable artifact",
        "schema/doc/validator contract",
        "public CLI or JSON contract",
        "new dependency",
        "broader issue scope",
        "writer/mutation risk",
        "unresolved blocker",
        "maintainer decision",
        "contradiction between live issue text and current source",
    ):
        assert trigger in skill


def test_issue_work_skill_uses_policy_for_protected_surfaces() -> None:
    skill = _skill_text()

    assert "scripts/triage/policy.toml" in skill
    assert "governance.paths.protected_surfaces" in skill
    assert "not in a hard-coded skill list" in skill
    for example in (
        ".agents/skills/**",
        ".codex/agent-regression-cases-v1.json",
        ".codex/agent-regression/**",
        ".codex/artifact-contracts-v1.json",
        ".codex/bin/**",
        ".codex/scripts/**",
        ".codex/hooks/**",
        ".codex/hooks.json",
        "scripts/triage/**",
        "docs/*SCHEMA*.md",
        "docs/*schema*.json",
        "docs/ISSUE_GOVERNANCE.md",
        "AGENTS.md",
        ".github/workflows/**",
    ):
        assert example in skill


def test_issue_work_skill_requires_codex_quality_for_protected_changes() -> None:
    skill = _normalized_skill()

    assert "bash .codex/bin/action.sh codex-quality --json" in skill
    assert "intended or actual changes touch configured protected surfaces" in skill
    assert "--path" in skill
    assert "scoped" in skill
    assert "targeted" in skill
    assert "full-repo semantic coverage" in skill


def test_issue_work_skill_requires_quality_receipt_reporting() -> None:
    skill = _normalized_skill()

    for expected in (
        "output/codex/quality-receipt.json",
        "receipt JSON was readable",
        "quality_receipt_digest",
        "generated_at",
        "passed",
        "governance-boundary",
        "artifact-contracts",
        "agent-regression",
        "findings",
        "freshness_bound_protected_paths",
        "semantically_checked_protected_paths",
        "limitations",
        "omissions",
        "generated after the protected changes",
    ):
        assert expected in skill


def test_issue_work_skill_reports_worktree_vs_branch_base_diff_limits() -> None:
    skill = _normalized_skill()

    assert "clean worktree is not proof" in skill
    assert "committed protected changes" in skill
    assert "local Stop hook path is based on local changed paths/worktree status" in skill
    assert "protected-change evidence source" in skill
    assert "worktree status" in skill
    assert "branch/base diff" in skill
    assert "both" in skill
    assert "not available" in skill
    assert "worktree status only" in skill


def test_issue_work_skill_preserves_write_boundary() -> None:
    skill = _normalized_skill()

    assert "issue-work never edits issue bodies" in skill
    assert "no GitHub metadata mutation" in skill
    assert "no executable issue-body writer flow" in skill
    assert "no labels/milestones/Project moves/workflow dispatches/PR merges" in skill
    assert "write payloads for issue body/title/state remain forbidden" in skill
    assert "no apply operation generation" in skill
    assert "No GitHub mutation" in skill
    assert "No issue-body writer" in skill
    assert "No new hook behavior" in skill
    assert "No new `codex-quality` check" in skill
    assert "No #110 `codex-review-packet`" in skill
    assert "No #111 `$codex-review`" in skill
    assert "No #133 wiring `$codex-review` into `$issue-work`" in skill
    assert "No #118/#120/#121 extraction/distribution" in skill

    assert "live issue body is updated" not in skill
    assert "authorized writer flow" not in skill
    assert "only GitHub metadata mutation allowed" not in skill
    assert "maintainer updates the live issue" not in skill
    assert "recommended command: triage.py apply --execute" not in skill.lower()


def test_issue_work_skill_preserves_cleanup_ledger() -> None:
    skill = _normalized_skill()

    assert "cleanup/deletion ledger" in skill
    assert "obsolete paths removed or simplified" in skill
    assert "parallel paths intentionally retained" in skill
    assert "compatibility reason" in skill
    assert "likely obsolete paths identified in the risk contract" in skill


def test_issue_work_skill_preserves_existing_gates_and_pr_rules() -> None:
    skill = _normalized_skill()

    assert "bash .codex/bin/action.sh doctor" in skill
    assert "bash .codex/bin/action.sh context <issue> --comments" in skill
    assert "python scripts/triage/triage.py contract --issue <issue>" in skill
    assert "STOP issue-work and run the `issue-governance` skill" in skill
    assert "Closes #<issue>" in skill
    assert "Refs #<issue>" in skill
    assert "closingIssuesReferences" in skill
    assert "Do not push, merge, or mutate GitHub metadata" in skill
    assert "a package that is not already installed" in skill
