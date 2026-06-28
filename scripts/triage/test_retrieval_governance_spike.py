from __future__ import annotations

import json
from pathlib import Path

from scripts.triage.experiments import retrieval_governance_spike as spike


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "RETRIEVAL_GOVERNANCE_SPIKE.md"
CHANGELOG = ROOT / "CHANGELOG.md"
TRIAGE = ROOT / "scripts" / "triage" / "triage.py"


def _experiment() -> dict:
    return spike.run_experiment()


def test_harness_covers_recall_labels_and_stronger_cases() -> None:
    output = _experiment()
    labels = {result["label"] for result in output["results"]}

    assert set(spike.RECALL_FIXTURE_LABELS).issubset(labels)
    assert {
        "multi-candidate-duplicate-split-dependency-semantic",
        "distractor-evidence-unrelated-issue-numbers",
        "valid-handle-wrong-issue-numbers",
        "omission-retrieved-as-positive-evidence",
        "freshness-retrieved-as-positive-evidence",
        "close-near-miss-not-upgraded",
        "hard-stale-retrieval-hit-nonreviewable",
        "invalid-lineage-retrieval-hit-invalid",
        "evidence-id-instability-demonstration",
    }.issubset(labels)


def test_scoring_is_deterministic_and_reports_misses_and_noise() -> None:
    left = _experiment()
    right = _experiment()

    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    assert left["baseline"]["scorer"] == "token-overlap-jaccard-v1"

    for result in left["results"]:
        assert isinstance(result["false_negative"], bool)
        assert isinstance(result["noisy_result"], bool)
        assert isinstance(result["safe_as_supplemental_packet_evidence"], bool)
        assert "retrieved_top_k" in result

    assert any(result["false_negative"] for result in left["results"])
    assert any(result["noisy_result"] for result in left["results"])


def test_guardrail_failures_remain_nonreviewable_despite_hits() -> None:
    output = _experiment()
    by_label = {result["label"]: result for result in output["results"]}

    for label in [
        "hard-stale-packet",
        "stricter-max-age-packet",
        "invalid-lineage-packet",
        "hard-stale-retrieval-hit-nonreviewable",
        "invalid-lineage-retrieval-hit-invalid",
    ]:
        result = by_label[label]
        assert result["true_positive_handles"], label
        assert result["safe_as_supplemental_packet_evidence"] is False

    assert by_label["hard-stale-packet"]["guardrail_status"] == (
        "hard_stale_non_reviewable"
    )
    assert by_label["invalid-lineage-packet"]["guardrail_status"] == (
        "invalid_lineage"
    )


def test_corpus_excludes_unbounded_tracker_and_mutation_shapes() -> None:
    output = _experiment()
    forbidden_fragments = [
        '"issues"',
        '"pulls"',
        '"operations"',
        '"apply_operations"',
        '"github_request"',
        "workflow.dispatch",
        "pull_request.merge",
        "approval batch",
        "issue.body.update",
        "issue.title.update",
        "full raw snapshot",
        "comment body",
    ]

    for result in output["results"]:
        corpus_text = json.dumps(result["corpus"], sort_keys=True)
        for fragment in forbidden_fragments:
            assert fragment not in corpus_text


def test_no_production_triage_retrieval_command_is_added() -> None:
    text = TRIAGE.read_text(encoding="utf-8")

    assert "retrieval-governance-spike" not in text
    assert "retrieval_governance_spike" not in text
    assert "search-index" not in text
    assert "vector" not in text


def test_spike_report_records_gap_audit_recommendation_and_guardrails() -> None:
    text = REPORT.read_text(encoding="utf-8")
    plain = " ".join(text.casefold().split())

    assert "## Summary and recommendation" in text
    assert "## Residual closed-issue gap audit" in text
    assert "#97 duplicate-centric near misses" in text
    assert "#99 fixtures are in-test, not reusable evaluation assets" in text
    assert "#100 ref-existence versus issue-alignment gap" in text
    assert "Recommendation: add more fixture/evaluation work first" in text
    assert plain.count("recommendation: add more fixture/evaluation work first") == 1
    assert "retrieval cannot replace backlog-synthesis" in plain
    assert "retrieval cannot fetch github live by default" in plain
    assert "retrieval cannot collect github comments unless separately authorized" in plain
    assert "retrieval cannot invoke an llm" in plain
    assert "retrieval cannot mutate github" in plain
    assert "retrieval cannot generate apply plans" in plain
    assert "retrieval cannot make hard-stale" in plain
    assert "stable ids and provenance" in plain


def test_changelog_describes_spike_as_research_only_if_updated() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    if "retrieval governance spike" not in text.casefold():
        return

    section = text.split("### Retrieval governance spike", maxsplit=1)[1]
    section = section.split("\n### ", maxsplit=1)[0]
    plain = " ".join(section.casefold().split())

    assert "research/evaluation" in plain
    assert "no production retrieval command" in plain
    assert "no stable schema" in plain
    assert "no validator" in plain
    assert "no skill behavior" in plain
    assert "no github mutation" in plain
    assert "no apply integration" in plain
