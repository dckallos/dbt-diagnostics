from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "backlog-review" / "SKILL.md"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_backlog_review_skill_exists_with_frontmatter() -> None:
    text = _skill_text()

    assert SKILL.is_file()
    assert text.startswith("---\n")
    assert "\nname: backlog-review\n" in text
    assert "description:" in text
    assert "validated synthesis-review-packet" in text
    assert "without mutating GitHub" in text


def test_backlog_review_skill_loads_only_bounded_inputs() -> None:
    text = _skill_text()
    compact = _compact(text)

    assert "validated `synthesis-review-packet`" in text
    assert "docs/SYNTHESIS_REVIEW_PACKET_SCHEMA_V1.md" in text
    assert "docs/BACKLOG_REVIEW_VERDICT_SCHEMA_V1.md" in text
    assert "backlog-review-validate" in text
    assert "Do not use full snapshot prompting" in text
    assert "full tracker snapshot" in text
    assert "all open issue bodies" in text
    assert "GitHub comments" in text
    assert "Do not collect GitHub comments in v1" in text
    assert "retrieval indexes or semantic search output" in compact


def test_backlog_review_skill_forbids_github_and_apply_mutation_shapes() -> None:
    text = _skill_text()
    compact = _compact(text)

    for phrase in [
        "must not mutate GitHub",
        "must not create, edit, close, reopen",
        "label",
        "milestone",
        "Projects",
        "workflow dispatches",
        "pull request merges",
        "branches",
        "worktrees",
        "Codex threads",
        "approval batches",
        "apply payloads",
        "GitHub request payloads",
        "operation lists",
        "directly consumable by `triage.py apply`",
    ]:
        assert phrase in text or phrase in compact

    assert "may mutate GitHub" not in text
    assert "executable apply plan" not in text


def test_backlog_review_skill_stop_conditions_are_explicit() -> None:
    text = _skill_text()

    for phrase in [
        "packet validation fails",
        "packet source lineage is invalid",
        "packet is hard-stale",
        "packet is non-reviewable",
        "`llm_review_allowed` is false",
        "packet exceeds the hard byte budget",
        "source digests are missing or inconsistent",
        "forbidden mutation shape is present",
        "decisive evidence is omitted",
        "user asks the skill to mutate GitHub",
    ]:
        assert phrase in text


def test_backlog_review_skill_preserves_freshness_semantics() -> None:
    text = _skill_text()
    compact = _compact(text)

    assert "Fresh packet: continue normally" in text
    assert "Warning-only freshness: continue only" in text
    assert "Hard-stale packet: stop" in text
    assert "Non-reviewable packet: stop" in text
    assert "Invalid-lineage packet: stop" in text
    assert "Do not collapse warning-only freshness into a 24-hour hard stale cliff" in text
    assert "GitHub remains the source of truth" in text
    assert "packet_reviewability" in compact
    assert "uncertainty" in compact
    assert "required_maintainer_checks" in compact


def test_backlog_review_skill_requires_packet_bound_refs() -> None:
    text = _skill_text()

    for phrase in [
        "evidence_items[].evidence_id",
        "evidence_refs",
        "near_misses[].near_miss_id",
        "near_miss_refs",
        "omissions[].omission_id",
        "omission_refs",
        "do not invent `near_miss_id`, `omission_id`, `near_miss_refs`, or",
        "do not recompute diagnostic IDs",
        "cite only `near_miss_id` and `omission_id` values present",
        "request packet regeneration rather than fabricating a ref",
        "`near_miss_refs` and `omission_refs` must pass",
    ]:
        assert phrase in text


def test_backlog_review_skill_requires_integrated_validation_for_json() -> None:
    text = _skill_text()

    assert "If producing verdict JSON" in text
    assert "python scripts/triage/triage.py backlog-review-validate" in text
    assert "--packet <packet.json>" in text
    assert "--verdict <verdict.json>" in text
    assert "If the validator returns warnings without errors" in text
    assert "If the validator returns errors" in text
    assert "do not claim the verdict is valid" in text
