#!/usr/bin/env python3
"""Evaluate retrieval as supplemental governance evidence.

This is an offline spike harness for issue #103. It builds synthetic bounded
governance artifacts through the existing frontier builders, indexes only the
bounded report/packet fields, and scores deterministic lexical retrieval
queries. It deliberately does not add a production triage command.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.triage import frontier  # noqa: E402


SCHEMA_VERSION = 1
GENERATED_AT = "2026-06-28T00:00:00Z"
TOP_K = 3
RECOMMENDATION = "add more fixture/evaluation work first"
SCORER_NAME = "token-overlap-jaccard-v1"
SNAPSHOT_DIGEST = "a" * 64
AUDIT_DIGEST = "b" * 64

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

EXTRA_FIXTURE_LABELS = (
    "multi-candidate-duplicate-split-dependency-semantic",
    "distractor-evidence-unrelated-issue-numbers",
    "valid-handle-wrong-issue-numbers",
    "omission-retrieved-as-positive-evidence",
    "freshness-retrieved-as-positive-evidence",
    "close-near-miss-not-upgraded",
    "hard-stale-retrieval-hit-nonreviewable",
    "invalid-lineage-retrieval-hit-invalid",
    "evidence-id-instability-demonstration",
)

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "not",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

FORBIDDEN_CORPUS_KEYS = frozenset(
    {
        "operations",
        "apply_operations",
        "github_request",
        "github_requests",
        "request_body",
        "request_payload",
        "issue_comments",
        "review_comments",
        "comments",
        "issues",
        "pulls",
        "pull_requests",
        "body",
        "state",
        "workflow_dispatch",
        "approval_batches",
    }
)


@dataclass(frozen=True)
class CorpusDocument:
    handle: str
    artifact_kind: str
    source_path: str
    source_artifact_digest: str
    issue_numbers: tuple[int, ...]
    text: str
    guardrail_only: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "artifact_kind": self.artifact_kind,
            "source_path": self.source_path,
            "source_artifact_digest": self.source_artifact_digest,
            "issue_numbers": list(self.issue_numbers),
            "text": self.text,
            "guardrail_only": self.guardrail_only,
        }


@dataclass(frozen=True)
class RetrievalHit:
    handle: str
    rank: int
    score: float
    artifact_kind: str
    source_artifact_digest: str
    issue_numbers: tuple[int, ...]
    source_path: str
    excerpt: str
    guardrail_only: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "handle": self.handle,
            "rank": self.rank,
            "score": self.score,
            "artifact_kind": self.artifact_kind,
            "source_artifact_digest": self.source_artifact_digest,
            "issue_numbers": list(self.issue_numbers),
            "source_path": self.source_path,
            "excerpt": self.excerpt,
            "guardrail_only": self.guardrail_only,
        }


@dataclass(frozen=True)
class Artifacts:
    snapshot: Mapping[str, Any]
    audit: Mapping[str, Any]
    report: Mapping[str, Any]
    packet: Mapping[str, Any]
    lineage_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class FixtureCase:
    label: str
    query_id: str
    query: str
    build: Callable[[], Artifacts]
    expected_handles: tuple[str, ...]
    guardrail_status: str = "reviewable"
    expected_issue_numbers: tuple[int, ...] = ()
    points_to_deterministic_layer_gap: bool = False
    notes: str = ""


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _ascii(value: str) -> str:
    return value.encode("ascii", "ignore").decode("ascii")


def _tokens(text: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in STOPWORDS and len(token) > 1
    ]
    return tuple(tokens)


def _bounded_text(value: object) -> str:
    parts: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key in sorted(item):
                if str(key) in FORBIDDEN_CORPUS_KEYS:
                    continue
                parts.append(str(key))
                visit(item[key])
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            parts.append(str(item))

    visit(value)
    text = _ascii(" ".join(parts))
    return " ".join(text.split())[:800]


def snapshot(*issues: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "snapshot_digest": SNAPSHOT_DIGEST,
        "repository": "dckallos/dbt-diagnostics",
        "issues": list(issues),
        "pulls": [],
    }


def issue(
    number: int,
    *,
    title: str | None = None,
    labels: Sequence[str] | None = None,
    state: str = "open",
    body: str = "",
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title or f"fix: issue {number}",
        "labels": list(labels or ["bug"]),
        "state": state,
        "body": body,
        "html_url": f"https://github.com/dckallos/dbt-diagnostics/issues/{number}",
    }


def audit(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_digest": SNAPSHOT_DIGEST,
        "audit_digest": AUDIT_DIGEST,
        "issues": list(entries),
    }


def entry(
    number: int,
    *,
    governance: str = "conformant",
    implementation: str = "ready",
    dependencies: Sequence[int] | None = None,
    issue_kind: str = "feature_enhancement",
    referenced_paths: Sequence[str] | None = None,
    parent_epics: Sequence[int] | None = None,
    **extra: object,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "issue_number": number,
        "title": f"fix: issue {number}",
        "issue_kind": issue_kind,
        "contract_id": "dbt-diagnostics.issue-contract.v1",
        "contract_version": "1.0",
        "body_digest": f"body-{number}",
        "governance_state": governance,
        "contract_accepted": governance == "conformant",
        "implementation_state": implementation,
        "release_gate": False,
        "dependency_impact": 0,
        "direct_dependencies": list(dependencies or []),
        "dependency_merge_evidence": not bool(dependencies),
        "dependency_cycles": [],
        "required_decisions": [],
        "required_external_evidence": [],
        "missing_repository_paths": [],
        "active_pr_conflicts": [],
        "overlap_conflicts": [],
        "blockers": [],
        "parent_epics": list(parent_epics or [93]),
        "referenced_paths": list(referenced_paths or ["scripts/triage/frontier.py"]),
        "source_claims_checked": [],
        "semantic_review_notes": [],
        "recommended_disposition": "implement",
        "semantic_disposition_hypothesis": None,
        "semantic_disposition_evidence": [],
    }
    value.update(extra)
    return value


def _build_artifacts(
    snap: Mapping[str, Any],
    readiness: Mapping[str, Any],
    *,
    evaluated_at: str | None = "2026-06-24T01:00:00Z",
    max_age_hours: int = frontier.DEFAULT_SYNTHESIS_REVIEW_MAX_AGE_HOURS,
    invalid_lineage: bool = False,
) -> Artifacts:
    report = frontier.build_backlog_synthesis_report(snap, readiness)
    report_errors = frontier.validate_backlog_synthesis_report(report)
    if report_errors:
        raise AssertionError(report_errors)
    packet = frontier.build_synthesis_review_packet(
        snap,
        readiness,
        report,
        evaluated_at=evaluated_at,
        max_age_hours=max_age_hours,
    )
    lineage_errors: tuple[str, ...] = ()
    if invalid_lineage:
        tampered = json.loads(json.dumps(report))
        tampered["audit_digest"] = "9" * 64
        tampered["backlog_synthesis_digest"] = frontier.sha256_json(
            {
                key: value
                for key, value in tampered.items()
                if key != "backlog_synthesis_digest"
            }
        )
        lineage_errors = tuple(
            frontier.validate_synthesis_review_packet_sources(
                snap,
                readiness,
                tampered,
            )
        )
    else:
        lineage_errors = tuple(
            frontier.validate_synthesis_review_packet_sources(
                snap,
                readiness,
                report,
            )
        )
    return Artifacts(
        snapshot=snap,
        audit=readiness,
        report=report,
        packet=packet,
        lineage_errors=lineage_errors,
    )


def duplicate_artifacts(
    *,
    evaluated_at: str = "2026-06-24T01:00:00Z",
    max_age_hours: int = frontier.DEFAULT_SYNTHESIS_REVIEW_MAX_AGE_HOURS,
    invalid_lineage: bool = False,
) -> Artifacts:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
    )
    readiness = audit(
        entry(1, issue_kind="feature_enhancement"),
        entry(2, issue_kind="feature_enhancement"),
    )
    return _build_artifacts(
        snap,
        readiness,
        evaluated_at=evaluated_at,
        max_age_hours=max_age_hours,
        invalid_lineage=invalid_lineage,
    )


def near_miss_artifacts() -> Artifacts:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog review"),
    )
    readiness = audit(
        entry(1, issue_kind="feature_enhancement"),
        entry(2, issue_kind="feature_enhancement"),
    )
    return _build_artifacts(snap, readiness)


def split_artifacts() -> Artifacts:
    snap = snapshot(
        issue(
            3,
            title="feat: oversized governance workflow",
            body="This issue describes multiple coherent PRs and separable workstreams.",
        )
    )
    return _build_artifacts(snap, audit(entry(3)))


def dependency_artifacts(*, inverted: bool = True) -> Artifacts:
    if inverted:
        snap = snapshot(
            issue(10, title="feat: dependent"),
            issue(20, title="feat: blocker"),
        )
        readiness = audit(entry(10, dependencies=[20]), entry(20))
    else:
        snap = snapshot(
            issue(10, title="feat: blocker"),
            issue(20, title="feat: dependent"),
        )
        readiness = audit(entry(10), entry(20, dependencies=[10]))
    return _build_artifacts(snap, readiness)


def semantic_artifacts() -> Artifacts:
    snap = snapshot(
        issue(30, title="feat: duplicate"),
        issue(31, title="feat: owner"),
    )
    readiness = audit(
        entry(
            30,
            semantic_disposition_hypothesis="likely-duplicate-of #31",
            semantic_disposition_evidence=[
                "semantic review points at #31 as the owner"
            ],
        ),
        entry(31),
    )
    return _build_artifacts(snap, readiness)


def control_duplicate_artifacts() -> Artifacts:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="fix: pull request dependency resolution"),
    )
    readiness = audit(
        entry(1, referenced_paths=["scripts/triage/frontier.py"]),
        entry(2, referenced_paths=["scripts/triage/readiness.py"]),
    )
    return _build_artifacts(snap, readiness)


def no_split_artifacts() -> Artifacts:
    snap = snapshot(issue(3, title="feat: compact governance workflow", body="one task"))
    return _build_artifacts(snap, audit(entry(3)))


def multi_candidate_artifacts() -> Artifacts:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
        issue(
            3,
            title="feat: oversized governance workflow",
            body="This issue describes multiple coherent PRs and separable workstreams.",
        ),
        issue(10, title="feat: dependent"),
        issue(20, title="feat: blocker"),
        issue(30, title="feat: duplicate"),
        issue(31, title="feat: owner"),
    )
    readiness = audit(
        entry(1, issue_kind="feature_enhancement"),
        entry(2, issue_kind="feature_enhancement"),
        entry(3),
        entry(10, dependencies=[20]),
        entry(20),
        entry(
            30,
            semantic_disposition_hypothesis="likely-duplicate-of #31",
            semantic_disposition_evidence=[
                "semantic review points at #31 as the owner"
            ],
        ),
        entry(31),
    )
    return _build_artifacts(snap, readiness)


def distractor_artifacts() -> Artifacts:
    snap = snapshot(
        issue(1, title="feat: deterministic backlog synthesis"),
        issue(2, title="feat: deterministic backlog synthesis"),
        issue(90, title="feat: billing incident retrieval duplicate"),
        issue(91, title="feat: billing incident retrieval duplicate"),
    )
    readiness = audit(
        entry(1, issue_kind="feature_enhancement"),
        entry(2, issue_kind="feature_enhancement"),
        entry(90, issue_kind="feature_enhancement"),
        entry(91, issue_kind="feature_enhancement"),
    )
    return _build_artifacts(snap, readiness)


def fixture_cases() -> tuple[FixtureCase, ...]:
    near_miss_id = (
        "near-miss-possible-duplicate-001-002-"
        "title-similarity-below-threshold"
    )
    backlog_omission_id = "omission-no-issue-body-in-signals"
    comments_omission_id = "issue-comments-not-collected"
    return (
        FixtureCase(
            label="likely-duplicate-true-positive",
            query_id="q-duplicate-true-positive",
            query="deterministic backlog synthesis duplicate shared frontier path",
            build=duplicate_artifacts,
            expected_handles=("candidate-set-001", "evidence-001"),
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="likely-duplicate-false-positive-control",
            query_id="q-duplicate-control",
            query="warehouse grants unrelated root cause",
            build=control_duplicate_artifacts,
            expected_handles=(),
            guardrail_status="no_action_control",
        ),
        FixtureCase(
            label="close-duplicate-near-miss",
            query_id="q-close-near-miss",
            query="deterministic backlog review title similarity below threshold shared epic",
            build=near_miss_artifacts,
            expected_handles=(near_miss_id,),
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="backlog-omission-id-preservation",
            query_id="q-omission-id",
            query="read only signal report excludes full issue body",
            build=near_miss_artifacts,
            expected_handles=(backlog_omission_id,),
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="split-candidate",
            query_id="q-split-candidate",
            query="split marker multiple coherent PRs separable workstreams",
            build=split_artifacts,
            expected_handles=("candidate-set-001", "evidence-001"),
            expected_issue_numbers=(3,),
        ),
        FixtureCase(
            label="no-split-control",
            query_id="q-no-split-control",
            query="warehouse grants unrelated root cause",
            build=no_split_artifacts,
            expected_handles=(),
            guardrail_status="no_action_control",
        ),
        FixtureCase(
            label="dependency-order-inversion",
            query_id="q-dependency-inversion",
            query="issue ordered before dependency direct dependency",
            build=dependency_artifacts,
            expected_handles=("candidate-set-001", "evidence-001"),
            expected_issue_numbers=(10, 20),
        ),
        FixtureCase(
            label="no-dependency-order-inversion-control",
            query_id="q-no-dependency-control",
            query="warehouse grants unrelated root cause",
            build=lambda: dependency_artifacts(inverted=False),
            expected_handles=(),
            guardrail_status="no_action_control",
        ),
        FixtureCase(
            label="semantic-disposition-evidence",
            query_id="q-semantic-disposition",
            query="semantic review points owner duplicate",
            build=semantic_artifacts,
            expected_handles=("candidate-set-001", "evidence-001", "evidence-002"),
            expected_issue_numbers=(30, 31),
        ),
        FixtureCase(
            label="insufficient-evidence-verdict",
            query_id="q-insufficient-evidence",
            query="insufficient evidence title similarity below threshold no issue body signals",
            build=near_miss_artifacts,
            expected_handles=(near_miss_id, backlog_omission_id),
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="fresh-packet-under-warning",
            query_id="q-fresh-packet",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(evaluated_at="2026-06-24T01:00:00Z"),
            expected_handles=("candidate-set-001", "evidence-001"),
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="warning-only-packet",
            query_id="q-warning-packet",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(evaluated_at="2026-06-25T01:00:00Z"),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="warning_only",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="hard-stale-packet",
            query_id="q-hard-stale-packet",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(evaluated_at="2026-07-01T00:00:01Z"),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="hard_stale_non_reviewable",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="stricter-max-age-packet",
            query_id="q-stricter-max-age",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(
                evaluated_at="2026-06-27T00:00:01Z",
                max_age_hours=48,
            ),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="hard_stale_non_reviewable",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="invalid-lineage-packet",
            query_id="q-invalid-lineage",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(invalid_lineage=True),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="invalid_lineage",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="unknown-diagnostic-ref",
            query_id="q-unknown-diagnostic-ref",
            query="unknown diagnostic ref fabricated by model",
            build=near_miss_artifacts,
            expected_handles=(),
            guardrail_status="no_action_control",
        ),
        FixtureCase(
            label="multi-candidate-duplicate-split-dependency-semantic",
            query_id="q-multi-candidate",
            query="semantic duplicate split dependency backlog evidence",
            build=multi_candidate_artifacts,
            expected_handles=(
                "candidate-set-001",
                "candidate-set-002",
                "candidate-set-003",
                "candidate-set-004",
            ),
            expected_issue_numbers=(1, 2, 3, 10, 20, 30, 31),
            points_to_deterministic_layer_gap=True,
            notes="Top-K pressure misses at least one valid candidate handle.",
        ),
        FixtureCase(
            label="distractor-evidence-unrelated-issue-numbers",
            query_id="q-distractor",
            query="billing incident retrieval duplicate",
            build=distractor_artifacts,
            expected_handles=("candidate-set-001", "evidence-001"),
            expected_issue_numbers=(1, 2),
            points_to_deterministic_layer_gap=True,
            notes="Lexical retrieval can prefer unrelated issue-number evidence.",
        ),
        FixtureCase(
            label="valid-handle-wrong-issue-numbers",
            query_id="q-valid-handle-wrong-issues",
            query="billing incident retrieval duplicate",
            build=distractor_artifacts,
            expected_handles=("candidate-set-001",),
            expected_issue_numbers=(1, 2),
            points_to_deterministic_layer_gap=True,
        ),
        FixtureCase(
            label="omission-retrieved-as-positive-evidence",
            query_id="q-omission-as-positive",
            query="issue discussion text not collected proves duplicate",
            build=duplicate_artifacts,
            expected_handles=(),
            guardrail_status="no_action_control",
            points_to_deterministic_layer_gap=True,
            notes="Omission handles are diagnostics, not positive verdict evidence.",
        ),
        FixtureCase(
            label="freshness-retrieved-as-positive-evidence",
            query_id="q-freshness-as-positive",
            query="source age warning proves duplicate action",
            build=lambda: duplicate_artifacts(evaluated_at="2026-06-25T01:00:00Z"),
            expected_handles=(),
            guardrail_status="warning_only",
            points_to_deterministic_layer_gap=True,
        ),
        FixtureCase(
            label="close-near-miss-not-upgraded",
            query_id="q-near-miss-no-upgrade",
            query="title similarity below likely duplicate threshold",
            build=near_miss_artifacts,
            expected_handles=(near_miss_id,),
            expected_issue_numbers=(1, 2),
            notes="Finding the near-miss ID must not upgrade it to likely-duplicate.",
        ),
        FixtureCase(
            label="hard-stale-retrieval-hit-nonreviewable",
            query_id="q-hard-stale-hit",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(evaluated_at="2026-07-01T00:00:01Z"),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="hard_stale_non_reviewable",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="invalid-lineage-retrieval-hit-invalid",
            query_id="q-invalid-lineage-hit",
            query="deterministic backlog synthesis duplicate",
            build=lambda: duplicate_artifacts(invalid_lineage=True),
            expected_handles=("candidate-set-001", "evidence-001"),
            guardrail_status="invalid_lineage",
            expected_issue_numbers=(1, 2),
        ),
        FixtureCase(
            label="evidence-id-instability-demonstration",
            query_id="q-evidence-id-instability",
            query="deterministic backlog synthesis duplicate",
            build=duplicate_artifacts,
            expected_handles=("evidence-001",),
            expected_issue_numbers=(1, 2),
            points_to_deterministic_layer_gap=True,
            notes="Sequential packet evidence IDs are local-order dependent.",
        ),
    )


def _candidate_handle_by_source_index(packet: Mapping[str, Any]) -> dict[int, str]:
    handles: dict[int, str] = {}
    for candidate in packet.get("candidate_sets") or []:
        if not isinstance(candidate, Mapping):
            continue
        source_index = candidate.get("source_signal_index")
        candidate_id = candidate.get("candidate_set_id")
        if isinstance(source_index, int) and isinstance(candidate_id, str):
            handles[source_index] = candidate_id
    return handles


def build_corpus(artifacts: Artifacts) -> tuple[CorpusDocument, ...]:
    report = artifacts.report
    packet = artifacts.packet
    documents: list[CorpusDocument] = []
    report_digest = str(report.get("backlog_synthesis_digest") or "")
    packet_digest = str(packet.get("synthesis_review_packet_digest") or "")
    candidate_by_index = _candidate_handle_by_source_index(packet)

    for index, signal in enumerate(report.get("signals") or [], start=1):
        if not isinstance(signal, Mapping):
            continue
        handle = candidate_by_index.get(index)
        if handle is None:
            continue
        documents.append(
            CorpusDocument(
                handle=handle,
                artifact_kind="backlog_synthesis_signal",
                source_path=f"backlog-synthesis.signals[{index - 1}]",
                source_artifact_digest=report_digest,
                issue_numbers=_issue_numbers(signal.get("issue_numbers")),
                text=_bounded_text(
                    {
                        "signal_type": signal.get("signal_type"),
                        "summary": signal.get("summary"),
                        "evidence": signal.get("evidence"),
                        "details": signal.get("details"),
                    }
                ),
            )
        )

    for index, near_miss in enumerate(report.get("near_misses") or []):
        if not isinstance(near_miss, Mapping):
            continue
        near_miss_id = near_miss.get("near_miss_id")
        if not isinstance(near_miss_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=near_miss_id,
                artifact_kind="backlog_synthesis_near_miss",
                source_path=f"backlog-synthesis.near_misses[{index}]",
                source_artifact_digest=report_digest,
                issue_numbers=_issue_numbers(near_miss.get("issue_numbers")),
                text=_bounded_text(
                    {
                        "near_miss_id": near_miss_id,
                        "reason_not_signaled": near_miss.get(
                            "reason_not_signaled"
                        ),
                        "shared_evidence": near_miss.get("shared_evidence"),
                        "details": near_miss.get("details"),
                    }
                ),
            )
        )

    for index, omission in enumerate(report.get("omissions") or []):
        if not isinstance(omission, Mapping):
            continue
        omission_id = omission.get("omission_id")
        if not isinstance(omission_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=omission_id,
                artifact_kind="backlog_synthesis_omission",
                source_path=f"backlog-synthesis.omissions[{index}]",
                source_artifact_digest=report_digest,
                issue_numbers=(),
                text=_bounded_text(
                    {
                        "omission_id": omission_id,
                        "reason": omission.get("reason"),
                        "details": omission.get("details"),
                    }
                ),
            )
        )

    for index, candidate in enumerate(packet.get("candidate_sets") or []):
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = candidate.get("candidate_set_id")
        if not isinstance(candidate_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=candidate_id,
                artifact_kind="packet_candidate_set",
                source_path=f"synthesis-review-packet.candidate_sets[{index}]",
                source_artifact_digest=packet_digest,
                issue_numbers=_issue_numbers(candidate.get("issue_numbers")),
                text=_bounded_text(
                    {
                        "candidate_set_id": candidate_id,
                        "signal_type": candidate.get("signal_type"),
                        "summary": candidate.get("summary"),
                        "evidence_ids": candidate.get("evidence_ids"),
                    }
                ),
            )
        )

    for index, evidence in enumerate(packet.get("evidence_items") or []):
        if not isinstance(evidence, Mapping):
            continue
        evidence_id = evidence.get("evidence_id")
        if not isinstance(evidence_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=evidence_id,
                artifact_kind="packet_evidence_item",
                source_path=f"synthesis-review-packet.evidence_items[{index}]",
                source_artifact_digest=packet_digest,
                issue_numbers=_issue_numbers(evidence.get("issue_numbers")),
                text=_bounded_text(
                    {
                        "evidence_id": evidence_id,
                        "source": evidence.get("source"),
                        "excerpt": evidence.get("excerpt"),
                    }
                ),
            )
        )

    for index, near_miss in enumerate(packet.get("near_misses") or []):
        if not isinstance(near_miss, Mapping):
            continue
        near_miss_id = near_miss.get("near_miss_id")
        if not isinstance(near_miss_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=near_miss_id,
                artifact_kind="packet_near_miss",
                source_path=f"synthesis-review-packet.near_misses[{index}]",
                source_artifact_digest=packet_digest,
                issue_numbers=_issue_numbers(near_miss.get("issue_numbers")),
                text=_bounded_text(near_miss),
            )
        )

    for index, omission in enumerate(packet.get("omissions") or []):
        if not isinstance(omission, Mapping):
            continue
        omission_id = omission.get("omission_id")
        if not isinstance(omission_id, str):
            continue
        documents.append(
            CorpusDocument(
                handle=omission_id,
                artifact_kind="packet_omission",
                source_path=f"synthesis-review-packet.omissions[{index}]",
                source_artifact_digest=packet_digest,
                issue_numbers=(),
                text=_bounded_text(omission),
            )
        )

    staleness = packet.get("staleness")
    if isinstance(staleness, Mapping):
        status = str(staleness.get("freshness_status") or "unknown")
        documents.append(
            CorpusDocument(
                handle=f"staleness:{status}",
                artifact_kind="packet_staleness_guardrail",
                source_path="synthesis-review-packet.staleness",
                source_artifact_digest=packet_digest,
                issue_numbers=(),
                text=_bounded_text(staleness),
                guardrail_only=True,
            )
        )

    return tuple(documents)


def _issue_numbers(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    numbers = sorted(
        {
            int(item)
            for item in value
            if isinstance(item, int) and item > 0
        }
    )
    return tuple(numbers)


def _jaccard(query_tokens: Sequence[str], document_tokens: Sequence[str]) -> float:
    query = set(query_tokens)
    document = set(document_tokens)
    if not query or not document:
        return 0.0
    overlap = query & document
    if not overlap:
        return 0.0
    return round(len(overlap) / len(query | document), 6)


def retrieve(
    corpus: Sequence[CorpusDocument],
    *,
    query: str,
    top_k: int = TOP_K,
) -> tuple[RetrievalHit, ...]:
    query_tokens = _tokens(query)
    best_by_handle: dict[str, tuple[float, CorpusDocument]] = {}
    for document in corpus:
        score = _jaccard(query_tokens, _tokens(document.text))
        if score <= 0:
            continue
        current = best_by_handle.get(document.handle)
        if current is None or (score, document.artifact_kind, document.source_path) > (
            current[0],
            current[1].artifact_kind,
            current[1].source_path,
        ):
            best_by_handle[document.handle] = (score, document)

    ranked = sorted(
        best_by_handle.values(),
        key=lambda item: (-item[0], item[1].handle, item[1].artifact_kind),
    )[:top_k]
    hits: list[RetrievalHit] = []
    for rank, (score, document) in enumerate(ranked, start=1):
        hits.append(
            RetrievalHit(
                handle=document.handle,
                rank=rank,
                score=score,
                artifact_kind=document.artifact_kind,
                source_artifact_digest=document.source_artifact_digest,
                issue_numbers=document.issue_numbers,
                source_path=document.source_path,
                excerpt=document.text[:240],
                guardrail_only=document.guardrail_only,
            )
        )
    return tuple(hits)


def _wrong_issue_hit(
    hit: RetrievalHit,
    expected_issue_numbers: Sequence[int],
) -> bool:
    expected = set(expected_issue_numbers)
    if not expected or not hit.issue_numbers:
        return False
    return expected.isdisjoint(hit.issue_numbers)


def evaluate_case(case: FixtureCase) -> dict[str, Any]:
    artifacts = case.build()
    corpus = build_corpus(artifacts)
    hits = retrieve(corpus, query=case.query)
    retrieved_handles = tuple(hit.handle for hit in hits)
    expected_handles = tuple(case.expected_handles)
    true_positive_handles = tuple(
        handle for handle in retrieved_handles if handle in expected_handles
    )
    missed_handles = tuple(
        handle for handle in expected_handles if handle not in retrieved_handles
    )
    noisy_handles = tuple(
        hit.handle
        for hit in hits
        if hit.handle not in expected_handles
        or hit.guardrail_only
        or _wrong_issue_hit(hit, case.expected_issue_numbers)
    )
    false_negative = bool(missed_handles)
    noisy_result = bool(noisy_handles)
    reviewable = case.guardrail_status in {"reviewable", "warning_only", "no_action_control"}
    safe = reviewable and not false_negative and not noisy_result
    if case.expected_handles and not true_positive_handles:
        safe = False
    if case.guardrail_status in {"hard_stale_non_reviewable", "invalid_lineage"}:
        safe = False

    packet_errors = tuple(frontier.validate_synthesis_review_packet(artifacts.packet))
    result: dict[str, Any] = {
        "label": case.label,
        "query_id": case.query_id,
        "query": case.query,
        "tokens": list(_tokens(case.query)),
        "top_k": TOP_K,
        "expected_handles": list(expected_handles),
        "retrieved_top_k": [hit.to_json() for hit in hits],
        "true_positive_handles": list(true_positive_handles),
        "missed_handles": list(missed_handles),
        "false_negative": false_negative,
        "noisy_handles": list(dict.fromkeys(noisy_handles)),
        "noisy_result": noisy_result,
        "guardrail_status": case.guardrail_status,
        "safe_as_supplemental_packet_evidence": safe,
        "points_to_deterministic_layer_gap": case.points_to_deterministic_layer_gap,
        "packet_reviewability": {
            "freshness_status": artifacts.packet["staleness"]["freshness_status"],
            "stale": artifacts.packet["staleness"]["stale"],
            "llm_review_allowed": artifacts.packet["staleness"][
                "llm_review_allowed"
            ],
            "lineage_errors": list(artifacts.lineage_errors),
            "packet_validation_errors": list(packet_errors),
        },
        "corpus": [document.to_json() for document in corpus],
    }
    if case.notes:
        result["notes"] = case.notes
    return result


def evidence_id_instability_demo() -> dict[str, Any]:
    baseline = duplicate_artifacts()
    shifted = multi_candidate_artifacts()

    def evidence_map(artifacts: Artifacts) -> dict[str, list[int]]:
        return {
            item["evidence_id"]: list(item.get("issue_numbers") or [])
            for item in artifacts.packet.get("evidence_items") or []
            if isinstance(item, Mapping)
        }

    baseline_map = evidence_map(baseline)
    shifted_map = evidence_map(shifted)
    return {
        "baseline_evidence_id_issue_numbers": baseline_map,
        "shifted_evidence_id_issue_numbers": shifted_map,
        "finding": (
            "The same sequential evidence ID can refer to different issue-number "
            "sets when earlier signals are added; future retrieved evidence needs "
            "a separate stable namespace."
        ),
    }


def run_experiment() -> dict[str, Any]:
    results = [evaluate_case(case) for case in fixture_cases()]
    false_negative_count = sum(1 for result in results if result["false_negative"])
    noisy_count = sum(1 for result in results if result["noisy_result"])
    safe_count = sum(
        1 for result in results if result["safe_as_supplemental_packet_evidence"]
    )
    guardrail_counts = Counter(result["guardrail_status"] for result in results)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "recommendation": RECOMMENDATION,
        "baseline": {
            "scorer": SCORER_NAME,
            "top_k": TOP_K,
            "tokenizer": "lowercase ASCII alphanumeric tokens with stable stopword filtering",
            "tie_break": "score desc, handle asc, artifact_kind asc",
            "external_dependencies": [],
            "network_calls": False,
            "github_calls": False,
            "llm_calls": False,
        },
        "fixture_labels": {
            "recall": list(RECALL_FIXTURE_LABELS),
            "issue_103_specific": list(EXTRA_FIXTURE_LABELS),
        },
        "summary": {
            "fixture_count": len(results),
            "false_negative_count": false_negative_count,
            "noisy_result_count": noisy_count,
            "safe_as_supplemental_packet_evidence_count": safe_count,
            "guardrail_counts": dict(sorted(guardrail_counts.items())),
        },
        "results": results,
        "evidence_id_instability": evidence_id_instability_demo(),
        "guardrails": {
            "retrieval_replaces_backlog_synthesis": False,
            "retrieval_replaces_candidate_generation": False,
            "retrieval_is_authoritative_selector": False,
            "github_live_fetch_default": False,
            "comments_collected": False,
            "llm_invoked": False,
            "github_mutations": False,
            "apply_plans_generated": False,
            "full_issue_bodies_embedded": False,
            "packet_verdict_validation_weakened": False,
        },
    }


def _print_human(output: Mapping[str, Any]) -> None:
    summary = output["summary"]
    print("retrieval governance spike")
    print(f"recommendation: {output['recommendation']}")
    print(f"fixtures: {summary['fixture_count']}")
    print(f"false negatives: {summary['false_negative_count']}")
    print(f"noisy results: {summary['noisy_result_count']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline retrieval governance spike harness."
    )
    parser.add_argument("--json", action="store_true", help="print JSON results")
    args = parser.parse_args(argv)

    output = run_experiment()
    if args.json:
        print(canonical_json(output))
    else:
        _print_human(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by command tests.
    raise SystemExit(main())
