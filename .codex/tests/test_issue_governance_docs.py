from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
ISSUE_GOVERNANCE = ROOT / "docs" / "ISSUE_GOVERNANCE.md"
CODEX_README = ROOT / ".codex" / "README.md"
CODEX_GETTING_STARTED = ROOT / "docs" / "CODEX_GETTING_STARTED.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _plain_compact(text: str) -> str:
    return _compact(text.replace("`", "")).casefold()


def test_issue_governance_documents_bounded_backlog_review_workflow() -> None:
    text = _text(ISSUE_GOVERNANCE)
    plain = _plain_compact(text)

    assert "## Bounded LLM backlog review workflow" in text
    assert "snapshot.json" in text
    assert "audit.json" in text
    assert "project-plan.json" in text
    assert "backlog-synthesis.json" in text
    assert "synthesis-review-packet.json" in text
    assert "backlog-review-verdict.json" in text
    assert "python scripts/triage/triage.py synthesis-review-packet" in text
    assert "python scripts/triage/triage.py backlog-review-validate" in text
    assert "$backlog-review" in text
    assert "project-plan is optional for packet generation" in plain


def test_issue_governance_preserves_review_safety_boundary() -> None:
    text = _text(ISSUE_GOVERNANCE)
    plain = _plain_compact(text)

    for phrase in [
        "GitHub remains the source of truth",
        "LLM verdicts are advisory",
        "maintainer decides",
        "do not prompt with the full raw snapshot by default",
        "retrieval is not authoritative",
        "future_apply_recommendations are not executable operations",
        "do not feed verdict JSON into `triage.py apply`",
        "packets or verdicts must not create tracker writes",
    ]:
        assert phrase.replace("`", "").casefold() in plain


def test_issue_governance_documents_freshness_and_reviewability() -> None:
    text = _text(ISSUE_GOVERNANCE)
    plain = _plain_compact(text)

    assert "24 hours is the default freshness-warning threshold" in text
    assert "not the default stale cliff" in plain
    assert "168 hours / 7 days is the default hard LLM-review threshold" in text
    assert "Warning-only packets have `stale: false`" in text
    assert "have llm_review_allowed: true" in plain
    assert "Hard-stale packets have `stale: true`" in text
    assert "packets with llm_review_allowed: false are not valid llm inputs" in plain
    assert "invalid source lineage or digest mismatch is a hard failure" in plain
    assert "regenerate the local source artifacts" in plain


def test_issue_governance_documents_diagnostic_id_flow() -> None:
    text = _text(ISSUE_GOVERNANCE)
    plain = _plain_compact(text)

    assert "backlog-synthesis.near_misses[].near_miss_id" in text
    assert "synthesis-review-packet.near_misses[].near_miss_id" in text
    assert "backlog-review-verdict.verdicts[].near_miss_refs[]" in text
    assert "backlog-synthesis.omissions[].omission_id" in text
    assert "synthesis-review-packet.omissions[].omission_id" in text
    assert "backlog-review-verdict.verdicts[].omission_refs[]" in text
    assert "refs are exact packet-provided strings" in plain
    assert "model must not invent or recompute diagnostic ids" in plain
    assert "diagnostic refs do not authorize writes" in plain


def test_codex_onboarding_points_to_bounded_review_docs() -> None:
    readme = _text(CODEX_README)
    getting_started = _text(CODEX_GETTING_STARTED)
    getting_started_plain = _plain_compact(getting_started)

    assert "synthesis-review-packet" in readme
    assert "backlog-review-validate" in readme
    assert "$backlog-review" in readme
    assert "docs/ISSUE_GOVERNANCE.md" in readme

    assert "full snapshots" in getting_started_plain
    assert "retrieval" in getting_started_plain
    assert "mutate github" in getting_started_plain
    assert "docs/issue_governance.md" in getting_started_plain
