"""Deterministic audit and implementation frontiers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from scripts.triage.common import issue_map, sha256_json, slugify
from scripts.triage.contract import parse_sections

COORDINATOR_SCHEMA_VERSION = 1
WORKER_PACKET_SCHEMA_VERSION = 1

AUDIT_STATE_PRIORITY = {
    "unsafe": 1200,
    "stale": 800,
    "overlapping": 700,
    "needs_contract_revision": 600,
    "needs_decision": 500,
    "blocked": 400,
    "needs_semantic_review": 300,
    "unknown": 200,
    "ready": 0,
    "superseded": -100,
}


def _priority_label_score(labels: list[str]) -> int:
    values = set(labels)
    if "priority: now" in values:
        return 90
    if "priority: next" in values:
        return 60
    if "priority: deferred" in values:
        return 10
    return 0


def _issue_entries(audit: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in audit.get("issues") or []:
        if not isinstance(item, Mapping):
            continue
        number = item.get("issue_number")
        if isinstance(number, int):
            result[number] = dict(item)
    return result


def audit_frontier_candidates(
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
) -> list[dict[str, Any]]:
    issues = issue_map(snapshot, include_closed=False)
    entries = _issue_entries(audit)
    candidates: list[dict[str, Any]] = []
    for number in sorted(entries):
        if issue_filter is not None and number not in issue_filter:
            continue
        entry = entries[number]
        issue = issues.get(number)
        if issue is None:
            continue
        state = entry.get("implementation_state") or "unknown"
        if state in {"ready", "superseded"}:
            continue
        score = AUDIT_STATE_PRIORITY.get(state, 100)
        components = {"state": score}
        if entry.get("release_gate"):
            score += 250
            components["release_gate"] = 250
        impact_score = min(int(entry.get("dependency_impact") or 0) * 12, 180)
        if impact_score:
            score += impact_score
            components["dependency_impact"] = impact_score
        label_score = _priority_label_score(issue.get("labels") or [])
        if label_score:
            score += label_score
            components["priority"] = label_score
        if entry.get("governance_state") == "stale":
            score += 80
            components["governance_stale"] = 80
        candidates.append(
            {
                "issue_number": number,
                "score": score,
                "score_components": components,
                "state": state,
                "title": issue.get("title"),
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["issue_number"]))


def implementation_frontier_candidates(
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues = issue_map(snapshot)
    entries = _issue_entries(audit)
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for number in sorted(entries):
        if issue_filter is not None and number not in issue_filter:
            continue
        entry = entries[number]
        issue = issues.get(number)
        if issue is None or issue.get("state") != "open":
            continue
        reasons: list[str] = []
        if not entry.get("contract_accepted"):
            reasons.append("governance contract is not accepted")
        if entry.get("implementation_state") != "ready":
            reasons.append(
                f"implementation state is {entry.get('implementation_state') or 'unknown'}"
            )
        if entry.get("dependency_cycles"):
            reasons.append("dependency cycle exists")
        if entry.get("required_decisions"):
            reasons.append("unresolved maintainer decisions")
        if entry.get("required_external_evidence"):
            reasons.append("required external evidence is unavailable")
        if entry.get("missing_repository_paths"):
            reasons.append("referenced repository path is missing")
        if entry.get("active_pr_conflicts"):
            reasons.append("active pull request conflict")
        if entry.get("overlap_conflicts"):
            reasons.append("overlapping issue ownership")
        if entry.get("blockers"):
            reasons.append("readiness blockers remain")

        dependencies = entry.get("direct_dependencies") or []
        unclosed = [
            dependency
            for dependency in dependencies
            if dependency not in issues or issues[dependency].get("state") != "closed"
        ]
        if unclosed:
            reasons.append(
                "direct dependencies are not closed: "
                + ", ".join(f"#{item}" for item in sorted(unclosed))
            )
        if dependencies and not entry.get("dependency_merge_evidence", False):
            reasons.append("closed dependency merge evidence is not recorded")

        if reasons:
            rejected.append(
                {
                    "issue_number": number,
                    "title": issue.get("title"),
                    "reasons": sorted(set(reasons)),
                }
            )
            continue

        score = 0
        components: dict[str, int] = {}
        if entry.get("release_gate"):
            score += 300
            components["release_gate"] = 300
        label_score = _priority_label_score(issue.get("labels") or [])
        if label_score:
            score += label_score
            components["priority"] = label_score
        impact_score = min(int(entry.get("dependency_impact") or 0) * 12, 180)
        if impact_score:
            score += impact_score
            components["dependency_impact"] = impact_score
        if not dependencies:
            score += 25
            components["no_direct_dependencies"] = 25
        candidates.append(
            {
                "issue_number": number,
                "title": issue.get("title"),
                "score": score,
                "score_components": components,
            }
        )
    return (
        sorted(candidates, key=lambda item: (-item["score"], item["issue_number"])),
        sorted(rejected, key=lambda item: item["issue_number"]),
    )


def suggested_branch(entry: Mapping[str, Any], title: str) -> str:
    kind = entry.get("issue_kind")
    prefix = {
        "bug_fix": "fix",
        "feature_enhancement": "feat",
        "refactor_architecture": "refactor",
        "test_verification": "test",
        "spike_decision": "spike",
        "epic": "chore",
        "docs_chore_release": "chore",
    }.get(kind, "chore")
    number = int(entry["issue_number"])
    cleaned = re.sub(r"^(?:\[[^]]+\]\s*)?(?:[a-z]+):\s*", "", title, flags=re.I)
    return f"{prefix}/{number}-{slugify(cleaned, max_length=48)}"


def _selection_reason(mode: str, candidate: Mapping[str, Any]) -> str:
    components = candidate.get("score_components") or {}
    details = ", ".join(f"{key}={value}" for key, value in sorted(components.items()))
    if mode == "audit":
        return f"highest deterministic audit score {candidate['score']}" + (
            f" ({details})" if details else ""
        )
    return f"highest deterministic implementation score {candidate['score']}" + (
        f" ({details})" if details else ""
    )


def build_coordinator_result(
    mode: str,
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
) -> dict[str, Any]:
    if mode not in {"audit", "implement"}:
        raise ValueError(f"unsupported frontier mode: {mode}")
    issues = issue_map(snapshot)
    entries = _issue_entries(audit)
    rejected: list[dict[str, Any]] = []
    if mode == "audit":
        candidates = audit_frontier_candidates(
            snapshot, audit, issue_filter=issue_filter
        )
    else:
        candidates, rejected = implementation_frontier_candidates(
            snapshot, audit, issue_filter=issue_filter
        )

    candidate = candidates[0] if candidates else None
    generated_at = snapshot.get("generated_at") or "unknown"
    base = {
        "schema_version": COORDINATOR_SCHEMA_VERSION,
        "mode": mode,
        "repository": snapshot.get("repository"),
        "generated_at": generated_at,
        "snapshot_digest": snapshot.get("snapshot_digest"),
        "audit_digest": audit.get("audit_digest"),
        "selected_issue": None,
        "issue_contract_digest": None,
        "governance_state": None,
        "implementation_state": None,
        "selection_reason": "frontier is empty",
        "parent_epics": [],
        "direct_dependencies": [],
        "blockers": [],
        "required_decisions": [],
        "required_external_evidence": [],
        "referenced_paths": [],
        "suggested_branch": None,
        "suggested_next_command": None,
        "candidate_count": len(candidates),
        "rejected_count": len(rejected),
    }
    if candidate is not None:
        number = int(candidate["issue_number"])
        entry = entries[number]
        issue = issues[number]
        base.update(
            {
                "selected_issue": number,
                "issue_contract_digest": entry.get("body_digest"),
                "governance_state": entry.get("governance_state"),
                "implementation_state": entry.get("implementation_state"),
                "selection_reason": _selection_reason(mode, candidate),
                "parent_epics": sorted(entry.get("parent_epics") or []),
                "direct_dependencies": sorted(entry.get("direct_dependencies") or []),
                "blockers": sorted(entry.get("blockers") or []),
                "required_decisions": sorted(entry.get("required_decisions") or []),
                "required_external_evidence": sorted(
                    entry.get("required_external_evidence") or []
                ),
                "referenced_paths": sorted(entry.get("referenced_paths") or []),
                "suggested_branch": suggested_branch(
                    entry, issue.get("title") or "issue"
                ),
                "suggested_next_command": f"bash .codex/bin/action.sh context {number} --comments",
                "score": candidate.get("score"),
                "score_components": candidate.get("score_components") or {},
            }
        )
    if rejected:
        base["rejected_preview"] = rejected[:20]
    base["coordinator_digest"] = sha256_json(base)
    return base


def validate_coordinator_result(value: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "mode",
        "repository",
        "generated_at",
        "snapshot_digest",
        "audit_digest",
        "selected_issue",
        "selection_reason",
        "coordinator_digest",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if value.get("schema_version") != COORDINATOR_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if value.get("mode") not in {"audit", "implement"}:
        errors.append("invalid mode")
    selected = value.get("selected_issue")
    if selected is not None and (
        isinstance(selected, bool) or not isinstance(selected, int)
    ):
        errors.append("selected_issue must be an integer or null")
    actual_digest = sha256_json(
        {key: item for key, item in value.items() if key != "coordinator_digest"}
    )
    if value.get("coordinator_digest") != actual_digest:
        errors.append("coordinator_digest mismatch")
    return errors


def _extract_section(issue: Mapping[str, Any], keys: set[str]) -> str | None:
    sections, _ = parse_sections(issue.get("body") or "")
    values = [
        section.content
        for section in sections
        if section.key in keys and section.content
    ]
    return "\n\n".join(values) if values else None


def _parent_excerpt(
    parent: Mapping[str, Any], issue_number: int, *, limit: int = 1800
) -> str:
    lines = (parent.get("body") or "").splitlines()
    selected: list[str] = []
    for index, line in enumerate(lines):
        if f"#{issue_number}" not in line:
            continue
        start = max(0, index - 2)
        end = min(len(lines), index + 3)
        selected.extend(lines[start:end])
    text = "\n".join(dict.fromkeys(selected)).strip()
    if not text:
        text = "No issue-specific excerpt was found in the parent epic."
    return text[:limit]


def build_worker_packet(
    issue_number: int,
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    root: Path,
    branch_state: Mapping[str, Any] | None = None,
    progress_context: str | None = None,
) -> dict[str, Any]:
    issues = issue_map(snapshot)
    entries = _issue_entries(audit)
    if issue_number not in issues or issue_number not in entries:
        raise ValueError(f"issue #{issue_number} is not present in snapshot and audit")
    issue = issues[issue_number]
    entry = entries[issue_number]
    dependencies = []
    for dependency in sorted(entry.get("direct_dependencies") or []):
        target = issues.get(dependency)
        dependencies.append(
            {
                "issue_number": dependency,
                "state": target.get("state") if target else "unknown",
                "state_reason": target.get("state_reason") if target else None,
                "title": target.get("title") if target else None,
                "merge_evidence": entry.get(
                    "dependency_merge_evidence_details", {}
                ).get(str(dependency)),
            }
        )
    parents = []
    for parent_number in sorted(entry.get("parent_epics") or []):
        parent = issues.get(parent_number)
        if parent:
            parents.append(
                {
                    "issue_number": parent_number,
                    "title": parent.get("title"),
                    "excerpt": _parent_excerpt(parent, issue_number),
                }
            )
    paths = [
        {"path": path, "exists": (root / path).exists()}
        for path in sorted(entry.get("referenced_paths") or [])
    ]
    packet = {
        "schema_version": WORKER_PACKET_SCHEMA_VERSION,
        "repository": snapshot.get("repository"),
        "generated_at": snapshot.get("generated_at") or "unknown",
        "snapshot_digest": snapshot.get("snapshot_digest"),
        "audit_digest": audit.get("audit_digest"),
        "issue": {
            "number": issue_number,
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "labels": issue.get("labels") or [],
            "milestone": issue.get("milestone"),
            "body": issue.get("body") or "",
        },
        "contract": {
            "id": entry.get("contract_id"),
            "version": entry.get("contract_version"),
            "digest": entry.get("body_digest"),
            "governance_state": entry.get("governance_state"),
            "implementation_state": entry.get("implementation_state"),
        },
        "acceptance_criteria": _extract_section(issue, {"acceptance_criteria"}),
        "non_goals": _extract_section(issue, {"non_goals"}),
        "dependencies": dependencies,
        "parent_epics": parents,
        "referenced_paths": paths,
        "likely_entry_points": sorted(
            set(
                (entry.get("source_claims_checked") or [])
                + [item["path"] for item in paths]
            )
        ),
        "uncertainty": {
            "blockers": entry.get("blockers") or [],
            "required_decisions": entry.get("required_decisions") or [],
            "required_external_evidence": entry.get("required_external_evidence") or [],
            "semantic_review_notes": entry.get("semantic_review_notes") or [],
        },
        "required_verification_commands": [
            "python -m compileall -q dbt_diagnostics scripts/triage",
            "pytest -q",
        ],
        "branch_worktree_state": dict(branch_state or {}),
        "historical_progress_context": progress_context,
        "historical_progress_is_authoritative": False,
    }
    packet["packet_digest"] = sha256_json(packet)
    return packet
