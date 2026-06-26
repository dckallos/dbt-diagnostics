"""Deterministic audit and implementation frontiers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping

from scripts.triage.common import (
    issue_map,
    pull_map,
    repository_name,
    sha256_json,
    slugify,
    snapshot_digest,
)
from scripts.triage.contract import parse_sections

COORDINATOR_SCHEMA_VERSION = 1
WORKER_PACKET_SCHEMA_VERSION = 1
PROJECT_PLAN_SCHEMA_VERSION = 1
MAX_WORKER_ISSUE_BODY_CHARS = 30000
MAX_PROGRESS_CONTEXT_CHARS = 4000

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

PROJECT_PLAN_COLUMNS = (
    ("ready", "Ready"),
    ("needs_semantic_review", "Needs semantic review"),
    ("needs_contract_revision", "Needs contract revision"),
    ("needs_decision", "Needs decision"),
    ("blocked", "Blocked"),
    ("stale", "Stale"),
    ("overlapping", "Overlapping"),
    ("unsafe", "Unsafe"),
    ("superseded", "Superseded"),
    ("unknown", "Unknown"),
)


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


def _positive_ints(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    return sorted(
        {
            item
            for item in values
            if isinstance(item, int) and not isinstance(item, bool) and item > 0
        }
    )


def _column_name(column_id: str) -> str:
    return " ".join(part for part in column_id.replace("_", " ").split()).capitalize()


def _project_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    project = policy.get("project", {}) if isinstance(policy, Mapping) else {}
    if not isinstance(project, Mapping):
        project = {}
    result: dict[str, Any] = {"enabled": bool(project.get("enabled", False))}
    for key in ("owner_type", "owner", "number"):
        value = project.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            result[key] = value
    return result


def _project_plan_without_digest(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "project_plan_digest"}


def build_project_plan(
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only desired GitHub Project layout from a readiness audit."""

    issues = issue_map(snapshot)
    entries = _issue_entries(audit)
    configured_columns = list(PROJECT_PLAN_COLUMNS)
    known_column_ids = {column_id for column_id, _name in configured_columns}
    extra_column_ids = sorted(
        {
            str(entry.get("implementation_state") or "unknown")
            for entry in entries.values()
            if str(entry.get("implementation_state") or "unknown")
            not in known_column_ids
        }
    )
    column_defs = configured_columns + [
        (column_id, _column_name(column_id)) for column_id in extra_column_ids
    ]
    column_rank = {
        column_id: index for index, (column_id, _name) in enumerate(column_defs)
    }
    columns = [
        {"id": column_id, "name": name, "position": index + 1}
        for index, (column_id, name) in enumerate(column_defs)
    ]

    pending_items: list[dict[str, Any]] = []
    for number in sorted(entries):
        issue = issues.get(number)
        if issue is None:
            continue
        entry = entries[number]
        column_id = str(entry.get("implementation_state") or "unknown")
        if column_id not in column_rank:
            column_id = "unknown"
        pending_items.append(
            {
                "issue_number": number,
                "title": entry.get("title") or issue.get("title"),
                "url": entry.get("url") or issue.get("html_url"),
                "column_id": column_id,
                "direct_dependencies": _positive_ints(
                    entry.get("direct_dependencies")
                ),
                "parent_epics": _positive_ints(entry.get("parent_epics")),
                "release_gate": bool(entry.get("release_gate")),
                "dependency_impact": int(entry.get("dependency_impact") or 0),
            }
        )
    pending_items.sort(
        key=lambda item: (
            column_rank.get(str(item["column_id"]), 999),
            item["issue_number"],
        )
    )

    column_positions: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for index, item in enumerate(pending_items, start=1):
        column_id = str(item["column_id"])
        column_positions[column_id] = column_positions.get(column_id, 0) + 1
        items.append(
            {
                **item,
                "position": index,
                "column_position": column_positions[column_id],
            }
        )

    position_by_issue = {
        int(item["issue_number"]): int(item["position"]) for item in items
    }
    conflicts: list[dict[str, Any]] = []
    for item in items:
        issue_number = int(item["issue_number"])
        issue_position = int(item["position"])
        for dependency in item["direct_dependencies"]:
            dependency_position = position_by_issue.get(dependency)
            if dependency_position is None or issue_position > dependency_position:
                continue
            conflicts.append(
                {
                    "code": "dependency-inversion",
                    "issue_number": issue_number,
                    "dependency_issue_number": dependency,
                    "issue_position": issue_position,
                    "dependency_position": dependency_position,
                    "message": (
                        f"#{issue_number} is ordered before its dependency "
                        f"#{dependency}"
                    ),
                }
            )

    plan: dict[str, Any] = {
        "schema_version": PROJECT_PLAN_SCHEMA_VERSION,
        "repository": repository_name(snapshot),
        "generated_at": snapshot.get("generated_at") or "unknown",
        "snapshot_digest": snapshot_digest(snapshot),
        "audit_digest": audit.get("audit_digest"),
        "project": _project_policy(policy),
        "columns": columns,
        "items": items,
        "ordering_conflicts": conflicts,
        "safety": {
            "read_only": True,
            "github_api_calls": False,
            "github_mutations": False,
            "project_writes_supported": False,
            "metadata_operations_supported": False,
            "contains_issue_content": False,
            "contains_state_changes": False,
        },
    }
    plan["project_plan_digest"] = sha256_json(_project_plan_without_digest(plan))
    return plan


def _dependency_is_closed(
    dependency: int,
    issues: Mapping[int, Mapping[str, Any]],
    pulls: Mapping[int, Mapping[str, Any]],
) -> bool:
    """A direct dependency is satisfied when it resolves to a closed issue or a
    closed pull request. Pull requests live in a separate snapshot map, so a
    merged-PR dependency must be looked up there rather than treated as missing
    (and therefore unclosed). The companion dependency_merge_evidence guard
    still requires recorded merge evidence, so a closed-unmerged PR is not let
    through here alone.
    """

    target = issues.get(dependency)
    if target is not None:
        return target.get("state") == "closed"
    pull = pulls.get(dependency)
    if pull is not None:
        return pull.get("state") == "closed"
    return False


def implementation_frontier_candidates(
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues = issue_map(snapshot)
    pulls = pull_map(snapshot)
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
            if not _dependency_is_closed(dependency, issues, pulls)
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
    cleaned = re.sub(r"^(?:\[[^]]+\]\s*)?(?:[a-z]+)(?:\([^)]*\))?:\s*", "", title, flags=re.I)
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
        "repository": repository_name(snapshot),
        "generated_at": generated_at,
        "snapshot_digest": snapshot_digest(snapshot),
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
        "issue_contract_digest",
        "governance_state",
        "implementation_state",
        "selection_reason",
        "parent_epics",
        "direct_dependencies",
        "blockers",
        "required_decisions",
        "required_external_evidence",
        "referenced_paths",
        "suggested_branch",
        "suggested_next_command",
        "candidate_count",
        "rejected_count",
        "coordinator_digest",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if value.get("schema_version") != COORDINATOR_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if value.get("mode") not in {"audit", "implement"}:
        errors.append("invalid mode")
    repository = value.get("repository")
    if not isinstance(repository, str) or not re.fullmatch(r"[^/]+/[^/]+", repository):
        errors.append("repository must be owner/name")
    if not isinstance(value.get("generated_at"), str):
        errors.append("generated_at must be a string")
    for key in ("snapshot_digest", "audit_digest", "coordinator_digest"):
        digest = value.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{key} must be a lowercase SHA-256 digest")
    selected = value.get("selected_issue")
    if selected is not None and (
        isinstance(selected, bool) or not isinstance(selected, int) or selected <= 0
    ):
        errors.append("selected_issue must be a positive integer or null")
    for key in ("issue_contract_digest", "governance_state", "implementation_state"):
        item = value.get(key)
        if item is not None and not isinstance(item, str):
            errors.append(f"{key} must be a string or null")
    if not isinstance(value.get("selection_reason"), str):
        errors.append("selection_reason must be a string")
    for key in ("parent_epics", "direct_dependencies"):
        items = value.get(key)
        if not isinstance(items, list) or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in (items if isinstance(items, list) else [])
        ):
            errors.append(f"{key} must be an array of positive integers")
    for key in (
        "blockers",
        "required_decisions",
        "required_external_evidence",
        "referenced_paths",
    ):
        items = value.get(key)
        if not isinstance(items, list) or any(
            not isinstance(item, str)
            for item in (items if isinstance(items, list) else [])
        ):
            errors.append(f"{key} must be an array of strings")
    for key in ("suggested_branch", "suggested_next_command"):
        item = value.get(key)
        if item is not None and not isinstance(item, str):
            errors.append(f"{key} must be a string or null")
    for key in ("candidate_count", "rejected_count"):
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            errors.append(f"{key} must be a non-negative integer")
    if selected is None:
        for key in (
            "issue_contract_digest",
            "governance_state",
            "implementation_state",
            "suggested_branch",
            "suggested_next_command",
        ):
            if value.get(key) is not None:
                errors.append(f"{key} must be null for an empty frontier")
    elif value.get("issue_contract_digest") is None:
        errors.append("issue_contract_digest is required for a selected issue")
    score = value.get("score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, int)):
        errors.append("score must be an integer when present")
    components = value.get("score_components")
    if components is not None and (
        not isinstance(components, Mapping)
        or any(
            not isinstance(key, str)
            or isinstance(item, bool)
            or not isinstance(item, int)
            for key, item in (
                components.items() if isinstance(components, Mapping) else []
            )
        )
    ):
        errors.append("score_components must map strings to integers")
    preview = value.get("rejected_preview")
    if preview is not None and (not isinstance(preview, list) or len(preview) > 20):
        errors.append("rejected_preview must be an array of at most 20 items")
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
    pulls = pull_map(snapshot)
    dependencies = []
    for dependency in sorted(entry.get("direct_dependencies") or []):
        target = issues.get(dependency) or pulls.get(dependency)
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
    full_body = issue.get("body") or ""
    bounded_body = full_body[:MAX_WORKER_ISSUE_BODY_CHARS]
    packet = {
        "schema_version": WORKER_PACKET_SCHEMA_VERSION,
        "repository": repository_name(snapshot),
        "generated_at": snapshot.get("generated_at") or "unknown",
        "snapshot_digest": snapshot_digest(snapshot),
        "audit_digest": audit.get("audit_digest"),
        "issue": {
            "number": issue_number,
            "title": issue.get("title"),
            "url": issue.get("html_url"),
            "labels": issue.get("labels") or [],
            "milestone": issue.get("milestone"),
            "body": bounded_body,
            "body_truncated": len(full_body) > len(bounded_body),
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
        "historical_progress_context": (progress_context or "")[
            :MAX_PROGRESS_CONTEXT_CHARS
        ]
        or None,
        "historical_progress_truncated": bool(
            progress_context and len(progress_context) > MAX_PROGRESS_CONTEXT_CHARS
        ),
        "historical_progress_is_authoritative": False,
    }
    packet["packet_digest"] = sha256_json(packet)
    return packet


def validate_worker_packet(value: Mapping[str, Any]) -> list[str]:
    """Validate the bounded worker-packet envelope and its digest."""

    errors: list[str] = []
    required = {
        "schema_version",
        "repository",
        "generated_at",
        "snapshot_digest",
        "audit_digest",
        "issue",
        "contract",
        "acceptance_criteria",
        "non_goals",
        "dependencies",
        "parent_epics",
        "referenced_paths",
        "likely_entry_points",
        "uncertainty",
        "required_verification_commands",
        "branch_worktree_state",
        "historical_progress_context",
        "historical_progress_truncated",
        "historical_progress_is_authoritative",
        "packet_digest",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if value.get("schema_version") != WORKER_PACKET_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    repository = value.get("repository")
    if not isinstance(repository, str) or not re.fullmatch(r"[^/]+/[^/]+", repository):
        errors.append("repository must be owner/name")
    if not isinstance(value.get("generated_at"), str):
        errors.append("generated_at must be a string")
    for key in ("snapshot_digest", "audit_digest", "packet_digest"):
        digest = value.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{key} must be a lowercase SHA-256 digest")
    issue = value.get("issue")
    if not isinstance(issue, Mapping):
        errors.append("issue must be an object")
    else:
        number = issue.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            errors.append("issue.number must be a positive integer")
        body = issue.get("body")
        if not isinstance(body, str) or len(body) > MAX_WORKER_ISSUE_BODY_CHARS:
            errors.append("issue.body exceeds the worker-packet bound")
        if not isinstance(issue.get("body_truncated"), bool):
            errors.append("issue.body_truncated must be boolean")
    if not isinstance(value.get("contract"), Mapping):
        errors.append("contract must be an object")
    for key in ("acceptance_criteria", "non_goals"):
        item = value.get(key)
        if item is not None and not isinstance(item, str):
            errors.append(f"{key} must be a string or null")
    for key in (
        "dependencies",
        "parent_epics",
        "referenced_paths",
        "likely_entry_points",
        "required_verification_commands",
    ):
        if not isinstance(value.get(key), list):
            errors.append(f"{key} must be an array")
    if not isinstance(value.get("uncertainty"), Mapping):
        errors.append("uncertainty must be an object")
    if not isinstance(value.get("branch_worktree_state"), Mapping):
        errors.append("branch_worktree_state must be an object")
    progress = value.get("historical_progress_context")
    if progress is not None and (
        not isinstance(progress, str) or len(progress) > MAX_PROGRESS_CONTEXT_CHARS
    ):
        errors.append("historical_progress_context exceeds the worker-packet bound")
    if not isinstance(value.get("historical_progress_truncated"), bool):
        errors.append("historical_progress_truncated must be boolean")
    if value.get("historical_progress_is_authoritative") is not False:
        errors.append("historical progress must be marked non-authoritative")
    actual_digest = sha256_json(
        {key: item for key, item in value.items() if key != "packet_digest"}
    )
    if value.get("packet_digest") != actual_digest:
        errors.append("packet_digest mismatch")
    return errors
