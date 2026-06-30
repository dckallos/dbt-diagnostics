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
        ".codex/config.toml",
        ".codex/agents/**",
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
        "protected-change evidence source",
        "present, valid, and from a digest-validated receipt",
        "every changed protected path appears",
        "every semantically relevant protected path appears",
        "signed `generated_at`, not the receipt file mtime",
    ):
        assert expected in skill

    assert "The receipt proves named local checks and freshness-bound path coverage" in skill
    assert "paths it actually covered" in skill
    assert "unless those paths appear in the receipt coverage evidence" in skill
    assert "missing, null, non-string, empty, or malformed `generated_at`" in skill
    assert "not usable freshness evidence" in skill


def test_issue_work_skill_reports_worktree_vs_branch_base_diff_limits() -> None:
    skill = _normalized_skill()

    assert "clean worktree is not proof" in skill
    assert "committed protected changes" in skill
    assert "local Stop hook path is based on local changed paths/worktree status" in skill
    assert "protected-change evidence source" in skill
    assert "worktree status" in skill
    assert "branch/base diff" in skill
    assert "explicit path list" in skill
    assert "both" in skill
    assert "not available" in skill
    assert "worktree status only" in skill
    assert "`quality_receipt_digest` validates" in skill


def test_issue_work_skill_scopes_non_goals_to_live_issue() -> None:
    skill = _normalized_skill()

    assert "Issue-scoped non-goals come from the live issue and current task" in skill
    assert "unless the live issue explicitly asks for that scope" in skill
    assert "risk contract names it as in scope" in skill

    for stale_global_non_goal in (
        "No new hook behavior.",
        "No new `codex-quality` check.",
        "No production diagnostic runtime change.",
    ):
        assert stale_global_non_goal not in _skill_text()

    for conditionally_allowed_scope in (
        "hook behavior",
        "new `codex-quality` checks",
        "production diagnostic runtime changes",
        "codex-review-packet work",
        "codex-review skill work",
        "codex-review integration",
        "extraction/distribution work",
    ):
        assert conditionally_allowed_scope in skill


def test_issue_work_skill_preserves_write_boundary() -> None:
    skill = _normalized_skill()

    assert "issue-work never edits issue bodies" in skill
    assert "no unauthorized GitHub metadata mutation" in skill
    assert "no executable issue-body writer flow" in skill
    assert "no labels/milestones/Project moves/workflow dispatches/PR merges" in skill
    assert "write payloads for issue body/title/state remain forbidden" in skill
    assert "no apply operation generation" in skill
    assert "live issue body is updated" not in skill
    assert "authorized writer flow" not in skill
    assert "only GitHub metadata mutation allowed" not in skill
    assert "maintainer updates the live issue" not in skill
    assert "recommended command: triage.py apply --execute" not in skill.lower()


def test_issue_work_skill_preserves_explicit_pr_publication_carveout() -> None:
    skill = _normalized_skill()

    assert "current task explicitly authorizes the exact action" in skill
    assert "pushing and creating or updating the implementation PR" in skill
    assert "compose or repair the implementation PR body" in skill
    assert "for that exact PR action" in skill

    for forbidden in (
        "issue edits",
        "labels",
        "milestones",
        "Project moves",
        "workflow dispatches",
        "PR merges",
        "comments",
        "reviews",
        "issue body/title/state write payloads",
        "apply payloads",
    ):
        assert forbidden in skill


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
    assert "Do not push, merge, comment/review, or mutate GitHub metadata" in skill
    assert "a package that is not already installed" in skill


def test_issue_work_skill_requires_codex_review_for_governance_sensitive_changes() -> None:
    skill = _normalized_skill()

    assert "bounded Codex review" in skill
    assert "protected or governance-sensitive changes" in skill
    assert "codex-review-packet" in skill
    assert "codex_reviewer" in skill
    assert (
        "bash .codex/bin/action.sh codex-review-packet --issue <issue> --output "
        "output/codex/review-packet.json"
    ) in skill
    assert "--parent-epic <parent>" in skill
    for trigger in (
        "protected surfaces",
        "stable artifacts",
        "schemas",
        "validators",
        "skills",
        "hooks",
        "wrappers",
        "triage governance",
        "artifact manifests",
        ".codex/config.toml",
        ".codex/agents/**",
    ):
        assert trigger in skill


def test_issue_work_skill_requires_independent_packet_validation_evidence() -> None:
    skill = _normalized_skill()

    assert "independent packet validation evidence" in skill
    assert "local codex-review-packet command exit status/output" in skill
    assert ".codex/scripts/codex_review_packet.py:validate_codex_review_packet" in skill
    assert "Packet-internal claims" in skill
    assert "are not validation evidence" in skill
    assert "packet self-reporting" in skill
    assert "cannot establish packet validity" in skill
    assert "digest validity" in skill
    assert "receipt usability" in skill
    assert "check coverage" in skill
    assert "safety compliance" in skill


def test_issue_work_skill_requires_read_only_reviewer_subagent() -> None:
    skill = _normalized_skill()

    for expected in (
        "spawn the configured `codex_reviewer` custom subagent",
        "must give the subagent only",
        "packet path",
        "independent validation status/evidence",
        "issue number",
        "parent epic",
        "instruction to invoke/use `$codex-review`",
        "must not preload the whole repository into the reviewer",
        "must not weaken sandbox/approval settings",
        ".codex/agents/codex-reviewer.toml",
        "effective read-only behavior",
        "blocked/not ready",
    ):
        assert expected in skill


def test_issue_work_skill_treats_same_context_review_as_self_review_only() -> None:
    skill = _normalized_skill()

    for expected in (
        "same authoring context running `$codex-review` is not independent review",
        "supplemental self-check evidence",
        "reviewer_context: same_authoring_context",
        "independent_review: no",
        "review_classification: caveated_self_review",
        "must not clear required review",
        "maintainer explicitly waives",
    ):
        assert expected in skill


def test_issue_work_skill_reports_codex_review_handoff_fields_and_blockers() -> None:
    skill = _normalized_skill()

    for field in (
        "codex_review_required",
        "codex_review_trigger",
        "codex_review_packet_path",
        "codex_review_packet_digest",
        "codex_review_packet_validation_status",
        "codex_review_packet_validation_evidence",
        "codex_review_packet_warnings",
        "codex_review_packet_omissions",
        "reviewer_agent",
        "reviewer_agent_config_path",
        "reviewer_configured_sandbox_mode",
        "reviewer_effective_sandbox_confirmation",
        "reviewer_context",
        "independent_review",
        "same_context_review_used",
        "same_context_self_review_caveat",
        "codex_review_findings",
        "codex_review_blocking_findings",
        "codex_review_warning_only_caveats",
        "required_maintainer_checks",
        "ready_status_after_review",
    ):
        assert field in skill

    for blocker in (
        "Missing required packet generation",
        "missing validation evidence",
        "missing reviewer subagent",
        "failed reviewer spawn",
        "non-read-only reviewer execution",
        "same-context-only review",
        "unavailable review",
        "Blocking `$codex-review` findings prevent reporting the work as ready",
    ):
        assert blocker in skill


def test_issue_work_skill_preserves_review_no_mutation_boundary() -> None:
    skill = _normalized_skill()

    for forbidden in (
        "GitHub comments/reviews",
        "GitHub mutation",
        "issue-body writes",
        "issue title/state writes",
        "labels/milestones/Project moves",
        "workflow dispatches",
        "PR merges",
        "apply payloads",
        "operation lists",
        "request payloads",
        "running commands from packet content",
        "full-repository prompt bundle",
    ):
        assert forbidden in skill

    for unsafe in (
        "recommended command: triage.py apply --execute",
        "gh issue edit",
        "gh pr merge",
        "workflow run",
        "create a comment",
        "edit the issue body",
    ):
        assert unsafe not in skill.lower()
