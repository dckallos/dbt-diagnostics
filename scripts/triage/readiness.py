"""Deterministic governance and implementation-readiness auditing."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from scripts.triage.common import (
    issue_map,
    normalize_issue,
    parse_iso_date,
    pull_map,
    referenced_paths,
    refs_in_text,
    repository_name,
    sha256_json,
    snapshot_digest,
)
from scripts.triage.contract import audit_contract, normalize_heading, parse_sections

IMPLEMENTATION_STATES = (
    "ready",
    "needs_contract_revision",
    "needs_semantic_review",
    "needs_decision",
    "blocked",
    "stale",
    "overlapping",
    "superseded",
    "unsafe",
    "unknown",
)

DEPENDENCY_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?P<label>depends on(?: [^:*]+)?|blocked by(?: [^:*]+)?|requires(?: [^:*]+)?|must land after|sequence after|prerequisites?)"
    r"\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
PARENT_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:parent epic|parent|epic)\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
RELATED_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:related|coordinates with|coordinate with|supports|consumed by)"
    r"\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
BLOCKS_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:blocks)"
    r"\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
SUPERSEDES_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:supersedes|absorbs|merged into)\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
OWNERSHIP_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:owns|scope owner|ownership)\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*(?P<value>.+)$"
)
CHECKLIST_REF_RE = re.compile(r"(?m)^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<text>.*)$")
DECISION_TERMS = (
    "decision-needed",
    "maintainer decision",
    "open decision",
    "decision required",
    "decision needed",
)
EXTERNAL_TERMS = (
    "real snowflake account",
    "credentials required",
    "requires credentials",
    "external evidence required",
    "protected environment",
    "real fixture",
    "license selection",
    "security contact",
)
FALSE_ASSUMPTION_TERMS = (
    "known false assumption",
    "factually wrong",
    "unsafe confirmed",
)


@dataclass(frozen=True)
class RelationshipSet:
    dependencies: tuple[int, ...]
    parent_epics: tuple[int, ...]
    related: tuple[int, ...]
    blocks: tuple[int, ...]
    supersedes: tuple[int, ...]
    ownership: tuple[str, ...]


def _line_refs(pattern: re.Pattern[str], body: str) -> set[int]:
    result: set[int] = set()
    for match in pattern.finditer(body or ""):
        result.update(refs_in_text(match.group("value")))
    return result


def parse_relationships(body: str) -> RelationshipSet:
    return RelationshipSet(
        dependencies=tuple(sorted(_line_refs(DEPENDENCY_LINE_RE, body))),
        parent_epics=tuple(sorted(_line_refs(PARENT_LINE_RE, body))),
        related=tuple(sorted(_line_refs(RELATED_LINE_RE, body))),
        blocks=tuple(sorted(_line_refs(BLOCKS_LINE_RE, body))),
        supersedes=tuple(sorted(_line_refs(SUPERSEDES_LINE_RE, body))),
        ownership=tuple(
            sorted(
                {
                    re.sub(r"\s+", " ", match.group("value").strip().lower())
                    for match in OWNERSHIP_LINE_RE.finditer(body or "")
                    if match.group("value").strip()
                }
            )
        ),
    )


def dependency_graph(snapshot: Mapping[str, Any]) -> dict[int, set[int]]:
    graph: dict[int, set[int]] = {}
    for number, issue in issue_map(snapshot, include_closed=False).items():
        graph[number] = set(parse_relationships(issue.get("body") or "").dependencies)
    return graph


def blocked_by_graph(snapshot: Mapping[str, Any]) -> dict[int, set[int]]:
    """Map each issue to the issues that declare ``Blocks: #<it>``.

    A ``Blocks`` edge on issue A is the inverse of a dependency: the named
    target is blocked by A. The tracker often records the relationship only on
    the blocker side, so readiness resolves it here and enforces it as an
    inbound block, rather than treating ``Blocks`` as an informational
    ``related`` reference. Closed issues are retained so the consumer can decide
    that a closed blocker no longer blocks.
    """
    blocked_by: dict[int, set[int]] = defaultdict(set)
    for number, issue in issue_map(snapshot).items():
        for target in parse_relationships(issue.get("body") or "").blocks:
            blocked_by[target].add(number)
    return blocked_by


def find_cycles(edges: Mapping[int, set[int]]) -> list[list[int]]:
    cycles: list[list[int]] = []
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def visit(node: int) -> None:
        if node in visiting:
            index = stack.index(node)
            cycle = stack[index:] + [node]
            # Rotate to the smallest issue number for stable representation.
            core = cycle[:-1]
            smallest = min(range(len(core)), key=lambda i: core[i])
            rotated = core[smallest:] + core[:smallest]
            rotated.append(rotated[0])
            if rotated not in cycles:
                cycles.append(rotated)
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for dependency in sorted(edges.get(node, set())):
            if dependency in edges:
                visit(dependency)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(edges):
        visit(node)
    return sorted(cycles)


def dependency_impact(graph: Mapping[int, set[int]]) -> dict[int, int]:
    reverse: dict[int, set[int]] = defaultdict(set)
    for issue, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(issue)
    impact: dict[int, int] = {}
    for start in graph:
        seen: set[int] = set()
        queue: deque[int] = deque(sorted(reverse.get(start, set())))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            queue.extend(sorted(reverse.get(current, set())))
        impact[start] = len(seen)
    return impact


def _section_text(issue: Mapping[str, Any], keys: set[str]) -> str:
    sections, _ = parse_sections(issue.get("body") or "")
    return "\n".join(section.content for section in sections if section.key in keys)


def derive_release_gate(
    snapshot: Mapping[str, Any], policy: Mapping[str, Any]
) -> list[int]:
    issues = issue_map(snapshot)
    release = (
        policy.get("release") if isinstance(policy.get("release"), Mapping) else {}
    )
    epic_numbers = (
        release.get("epic_numbers", release.get("epics"))
        if isinstance(release, Mapping)
        else None
    )
    if not isinstance(epic_numbers, list):
        epic_numbers = [4, 48, 68]
    section_names = (
        release.get("section_headings", release.get("gate_headings"))
        if isinstance(release, Mapping)
        else None
    )
    if not isinstance(section_names, list):
        section_names = [
            "initial release gate",
            "release engineering owned elsewhere",
            "build order and rollback points",
            "build order",
            "release definition of done",
        ]
    normalized_names = {normalize_heading(name) for name in section_names}
    gate: set[int] = set()
    include_epics = bool(release.get("include_epics", True))
    for raw_number in epic_numbers:
        if not isinstance(raw_number, int):
            continue
        issue = issues.get(raw_number)
        if not issue:
            continue
        if include_epics:
            gate.add(raw_number)
        sections, _ = parse_sections(issue.get("body") or "")
        for section in sections:
            normalized = normalize_heading(section.title)
            if section.key in {"release_gate", "release_priority"} or any(
                normalized.startswith(name) for name in normalized_names
            ):
                gate.update(refs_in_text(section.content))
    configured = (
        release.get("additional_issue_numbers", release.get("additional_issues"))
        if isinstance(release, Mapping)
        else None
    )
    if isinstance(configured, list):
        gate.update(item for item in configured if isinstance(item, int))

    if bool(release.get("include_dependency_closure", True)):
        queue = list(gate)
        while queue:
            number = queue.pop()
            issue = issues.get(number)
            if issue is None:
                continue
            for dependency in parse_relationships(issue.get("body") or "").dependencies:
                if dependency not in gate:
                    gate.add(dependency)
                    queue.append(dependency)

    return sorted(
        number
        for number in gate
        if number in issues and issues[number].get("state") == "open"
    )


# Sections whose paths name intended deliverables (files the issue will create
# or change), not references that must already exist on disk.
DELIVERABLE_SECTION_KEYS = {"scope_files", "deliverable"}


def missing_paths(issue: Mapping[str, Any], root: Path) -> list[str]:
    body = issue.get("body") or ""
    sections, _ = parse_sections(body)
    deliverable_paths: set[str] = set()
    for section in sections:
        if section.key in DELIVERABLE_SECTION_KEYS:
            deliverable_paths.update(referenced_paths(section.content))
    missing: list[str] = []
    for path in referenced_paths(body):
        # Paths listed only as intended deliverables are not stale references.
        if path in deliverable_paths:
            continue
        if not (root / path).exists():
            missing.append(path)
    return missing


def stale_checklist_refs(
    issue: Mapping[str, Any],
    issues: Mapping[int, Mapping[str, Any]],
    pulls: Mapping[int, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    pulls = pulls or {}
    for match in CHECKLIST_REF_RE.finditer(issue.get("body") or ""):
        if match.group("done").lower() == "x":
            continue
        for reference in sorted(refs_in_text(match.group("text"))):
            # A checklist item may reference an issue or a pull request; both are
            # tracker items, so resolve against either map before judging it open.
            target = issues.get(reference)
            is_pull_request = False
            if target is None:
                target = pulls.get(reference)
                is_pull_request = target is not None
            if target and target.get("state") != "open":
                stale.append(
                    {
                        "reference": reference,
                        "state": target.get("state"),
                        "state_reason": target.get("state_reason"),
                        "is_pull_request": is_pull_request,
                        "text": match.group("text").strip(),
                    }
                )
    return stale


def referenced_closed_items(
    issue: Mapping[str, Any], issues: Mapping[int, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    relationships = parse_relationships(issue.get("body") or "")
    result: list[dict[str, Any]] = []
    for reference in relationships.dependencies:
        target = issues.get(reference)
        if target and target.get("state") != "open":
            result.append(
                {
                    "reference": reference,
                    "relationship": "dependency",
                    "state": target.get("state"),
                    "state_reason": target.get("state_reason"),
                }
            )
    return result


def referenced_closed_pulls(
    dependencies: Iterable[int], pulls: Mapping[int, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Closed/merged pull requests a dependency references.

    Dependencies may name a PR rather than an issue. The snapshot tracks PRs in
    a separate map, so resolve them here before a reference is judged absent.
    """
    result: list[dict[str, Any]] = []
    for reference in dependencies:
        pull = pulls.get(reference)
        if pull and pull.get("state") != "open":
            merge_commit = pull.get("merge_commit_sha")
            result.append(
                {
                    "reference": reference,
                    "relationship": "dependency",
                    "state": pull.get("state"),
                    "state_reason": pull.get("state_reason"),
                    "pull_request": True,
                    "merged": bool(pull.get("merged_at") or merge_commit),
                    "merge_commit_sha": merge_commit,
                }
            )
    return result


def active_pr_conflicts(issue_number: int, snapshot: Mapping[str, Any]) -> list[int]:
    conflicts: list[int] = []
    for number, pull in pull_map(snapshot).items():
        if pull.get("state") != "open":
            continue
        head_ref = pull.get("head_ref") or ""
        text = "\n".join(
            (
                pull.get("title") or "",
                pull.get("body") or "",
                head_ref,
            )
        )
        if issue_number in refs_in_text(text) or re.search(
            rf"(?:^|/)(?:issue[-_/]?)?{issue_number}(?:[-_/]|$)", head_ref
        ):
            conflicts.append(number)
    return sorted(conflicts)


def detect_explicit_overlaps(
    snapshot: Mapping[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    issues = issue_map(snapshot, include_closed=False)
    claims: dict[str, list[int]] = defaultdict(list)
    overlaps: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for number, issue in issues.items():
        relationships = parse_relationships(issue.get("body") or "")
        issue_claims = set(relationships.ownership)
        sections, _ = parse_sections(issue.get("body") or "")
        for section in sections:
            if (
                normalize_heading(section.title) in {"ownership", "scope owner"}
                and section.content.strip()
            ):
                issue_claims.add(re.sub(r"\s+", " ", section.content.strip().lower()))
        for claim in sorted(issue_claims):
            claims[claim].append(number)
    for claim, owners in claims.items():
        unique = sorted(set(owners))
        if len(unique) < 2:
            continue
        for number in unique:
            overlaps[number].append(
                {
                    "claim": claim,
                    "conflicting_issues": [item for item in unique if item != number],
                }
            )

    # Reciprocal supersession between open items is inherently contradictory.
    for number, issue in issues.items():
        supersedes = set(parse_relationships(issue.get("body") or "").supersedes)
        for target in supersedes:
            if target not in issues:
                continue
            target_supersedes = set(
                parse_relationships(issues[target].get("body") or "").supersedes
            )
            if number in target_supersedes:
                overlaps[number].append(
                    {
                        "claim": "reciprocal supersession",
                        "conflicting_issues": [target],
                    }
                )
    return {number: value for number, value in overlaps.items()}


def scope_warning(issue: Mapping[str, Any]) -> dict[str, Any] | None:
    body = issue.get("body") or ""
    paths = referenced_paths(body)
    subsystems = {
        path.split("/", 2)[1] if "/" in path else path for path in paths if path
    }
    responsibility_terms = (
        "parser",
        "cli",
        "renderer",
        "serializer",
        "connector",
        "profile",
        "lineage",
        "grouping",
        "resolver",
        "workflow",
        "package",
        "documentation",
    )
    matched_terms = sorted(
        term for term in responsibility_terms if term in body.lower()
    )
    if len(paths) >= 14 or len(subsystems) >= 8 or len(matched_terms) >= 8:
        return {
            "code": "one-pr-scope-warning",
            "message": "the issue spans enough files or responsibilities to require an explicit one-PR boundary review",
            "path_count": len(paths),
            "subsystem_count": len(subsystems),
            "responsibility_terms": matched_terms,
        }
    return None


def _semantic_review(
    issue: Mapping[str, Any], semantic_evidence: Mapping[int, Mapping[str, Any]] | None
) -> dict[str, Any]:
    number = issue.get("number")
    if isinstance(number, int) and semantic_evidence and number in semantic_evidence:
        return dict(semantic_evidence[number])
    embedded = issue.get("semantic_review")
    return dict(embedded) if isinstance(embedded, Mapping) else {}


def _body_has_any(body: str, terms: Iterable[str]) -> bool:
    lower = body.lower()
    return any(term in lower for term in terms)


# A term documents required work only when it is not immediately negated. The
# negation must directly precede the term (allowing simple separators) so that a
# distant "no" elsewhere in the line does not suppress a real signal.
_NEG_PREFIX_RE = re.compile(r"\b(?:no|not|none|without|never|n/?a)\b[\s:,;.\-]*$")


def _body_requires(body: str, terms: Iterable[str]) -> bool:
    """True if any term appears in the body without an immediate negation.

    Phrases such as "No open decisions" or "No external evidence required"
    document the absence of blockers and must not be treated as required work.
    """
    lower = (body or "").lower()
    for term in terms:
        start = 0
        while True:
            idx = lower.find(term, start)
            if idx == -1:
                break
            preceding = lower[max(0, idx - 24):idx]
            if not _NEG_PREFIX_RE.search(preceding):
                return True
            start = idx + len(term)
    return False


def audit_issue(
    issue: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    root: Path,
    cycles: list[list[int]],
    release_gate: set[int],
    impact: Mapping[int, int],
    overlaps: Mapping[int, list[dict[str, Any]]],
    blocked_by: Mapping[int, set[int]] | None = None,
    semantic_evidence: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_issue(issue)
    number = normalized["number"]
    if not isinstance(number, int):
        raise ValueError("issue number is required")
    issues = issue_map(snapshot)
    pulls = pull_map(snapshot)
    contract = audit_contract(normalized)
    body = normalized.get("body") or ""
    relationships = parse_relationships(body)
    missing = missing_paths(normalized, root)
    stale_checklists = stale_checklist_refs(normalized, issues, pulls)
    # A dependency may reference an issue or a pull request, tracked in separate
    # snapshot maps. Resolve both so a PR dependency is not reported as absent.
    closed_dependencies = referenced_closed_items(normalized, issues)
    closed_dependencies += referenced_closed_pulls(relationships.dependencies, pulls)
    open_dependencies = [
        dependency
        for dependency in relationships.dependencies
        if (dependency in issues and issues[dependency].get("state") == "open")
        or (dependency in pulls and pulls[dependency].get("state") == "open")
    ]
    missing_dependencies = [
        dependency
        for dependency in relationships.dependencies
        if dependency not in issues and dependency not in pulls
    ]
    # Inbound blockers: other open issues that declare `Blocks: #<this>`. The
    # relationship may be recorded only on the blocker side, so enforce it here
    # rather than relying on this issue to also declare a forward dependency.
    # Fall back to deriving the map from the snapshot so a caller that does not
    # precompute it still gets correct blocking.
    if blocked_by is None:
        blocked_by = blocked_by_graph(snapshot)
    inbound_blockers = sorted(blocked_by.get(number, set()))
    open_inbound_blockers = [
        blocker
        for blocker in inbound_blockers
        if blocker in issues and issues[blocker].get("state") == "open"
    ]
    issue_cycles = [cycle for cycle in cycles if number in cycle[:-1]]
    issue_overlaps = overlaps.get(number, [])
    pr_conflicts = active_pr_conflicts(number, snapshot)
    semantic = _semantic_review(normalized, semantic_evidence)
    scope = scope_warning(normalized)

    merge_evidence_default = bool(semantic.get("dependency_merge_evidence", False))
    raw_merge_details = semantic.get("dependency_merge_evidence_details")
    merge_evidence_details = (
        dict(raw_merge_details) if isinstance(raw_merge_details, Mapping) else {}
    )

    def has_merge_evidence(item: Mapping[str, Any]) -> bool:
        if item.get("merged") or item.get("merge_commit_sha"):
            return True
        if item.get("state_reason") in {"duplicate", "not_planned"}:
            return False
        reference = item.get("reference")
        detail = merge_evidence_details.get(str(reference))
        if detail is None:
            detail = merge_evidence_details.get(reference)
        if isinstance(detail, Mapping):
            return bool(
                detail.get("merged")
                or detail.get("merge_commit_sha")
                or detail.get("pull_request")
                or detail.get("evidence")
            )
        if detail is not None:
            return bool(detail)
        return merge_evidence_default

    stale_closed_dependencies = [
        item for item in closed_dependencies if not has_merge_evidence(item)
    ]
    dependency_merge_evidence = bool(relationships.dependencies) and not (
        open_dependencies or missing_dependencies or stale_closed_dependencies
    )
    if not relationships.dependencies:
        dependency_merge_evidence = True

    labels = set(normalized.get("labels") or [])
    decision_required = (
        "decision-needed" in labels
        or _body_requires(body, DECISION_TERMS)
        or bool(semantic.get("required_decisions"))
    )
    external_required = _body_requires(body, EXTERNAL_TERMS) or bool(
        semantic.get("required_external_evidence")
    )
    explicitly_blocked = "blocked" in labels or bool(semantic.get("blockers"))

    expected_milestone = None
    release_policy = (
        policy.get("release") if isinstance(policy.get("release"), Mapping) else {}
    )
    if isinstance(release_policy, Mapping):
        candidate = release_policy.get("milestone_number")
        if isinstance(candidate, int):
            expected_milestone = candidate
    actual_milestone = normalized.get("milestone")
    actual_milestone_number = (
        actual_milestone.get("number")
        if isinstance(actual_milestone, Mapping)
        else None
    )
    milestone_drift = (
        number in release_gate
        and expected_milestone is not None
        and actual_milestone_number != expected_milestone
    )

    tracker_findings: list[dict[str, Any]] = []
    for item in stale_checklists:
        tracker_findings.append(
            {
                "level": "error",
                "code": "stale-checklist-reference",
                "message": f"unchecked checklist references closed item #{item['reference']}",
                "data": item,
            }
        )
    for item in stale_closed_dependencies:
        tracker_findings.append(
            {
                "level": "error",
                "code": "closed-dependency",
                "message": (
                    f"direct dependency #{item['reference']} is closed without "
                    "accepted merge evidence"
                ),
                "data": item,
            }
        )
    for dependency in missing_dependencies:
        tracker_findings.append(
            {
                "level": "error",
                "code": "missing-dependency",
                "message": f"direct dependency #{dependency} is absent from the snapshot",
            }
        )
    for blocker in open_inbound_blockers:
        tracker_findings.append(
            {
                "level": "error",
                "code": "blocked-by-open-issue",
                "message": f"open issue #{blocker} declares it blocks this issue",
            }
        )
    if issue_cycles:
        tracker_findings.append(
            {
                "level": "error",
                "code": "dependency-cycle",
                "message": "issue participates in a dependency cycle",
                "data": issue_cycles,
            }
        )
    if missing:
        tracker_findings.append(
            {
                "level": "error",
                "code": "missing-repo-path",
                "message": "one or more referenced repository paths do not exist",
                "data": missing,
            }
        )
    if milestone_drift:
        tracker_findings.append(
            {
                "level": "warning",
                "code": "release-milestone-drift",
                "message": f"release-gate issue is not assigned to milestone {expected_milestone}",
                "data": {
                    "actual": actual_milestone_number,
                    "expected": expected_milestone,
                },
            }
        )
    if issue_overlaps:
        tracker_findings.append(
            {
                "level": "error",
                "code": "explicit-overlap",
                "message": "explicit ownership claims conflict with another open issue",
                "data": issue_overlaps,
            }
        )
    if pr_conflicts:
        tracker_findings.append(
            {
                "level": "warning",
                "code": "active-pr-conflict",
                "message": "one or more open pull requests reference this issue",
                "data": pr_conflicts,
            }
        )
    if scope:
        tracker_findings.append({"level": "warning", **scope})

    governance_state = contract["governance_state"]
    audit_policy = (
        policy.get("audit") if isinstance(policy.get("audit"), Mapping) else {}
    )
    require_type_label = bool(
        isinstance(audit_policy, Mapping)
        and audit_policy.get("require_open_issue_type_label")
    )
    if require_type_label and any(
        finding.get("code") == "missing-type-label"
        for finding in contract.get("findings", [])
    ):
        governance_state = "needs_contract_revision"
    if governance_state == "conformant":
        if issue_overlaps:
            governance_state = "conflicting"
        elif stale_checklists or stale_closed_dependencies or milestone_drift:
            governance_state = "stale"
        elif missing_dependencies:
            governance_state = "unknown"

    semantic_status = semantic.get("status")
    semantic_accepted = semantic_status == "accepted"
    semantic_rejected = semantic_status in {"rejected", "unsafe"}
    false_assumption = bool(semantic.get("known_false_assumption")) or _body_has_any(
        body, FALSE_ASSUMPTION_TERMS
    )
    coherent_pr = semantic.get("one_pr_coherent")

    if normalized.get("state") != "open":
        implementation_state = (
            "superseded"
            if normalized.get("state_reason") in {"duplicate", "not_planned"}
            else "stale"
        )
    elif governance_state == "unsafe" or semantic_status == "unsafe":
        implementation_state = "unsafe"
    elif governance_state in {"needs_contract_revision", "conflicting", "unknown"}:
        implementation_state = "needs_contract_revision"
    elif stale_checklists or stale_closed_dependencies or milestone_drift:
        implementation_state = "stale"
    elif issue_overlaps:
        implementation_state = "overlapping"
    elif issue_cycles or missing_dependencies or missing or pr_conflicts:
        implementation_state = "blocked"
    elif open_dependencies or explicitly_blocked or open_inbound_blockers:
        implementation_state = "blocked"
    elif decision_required:
        implementation_state = "needs_decision"
    elif external_required and not semantic.get("external_evidence_available", False):
        implementation_state = "blocked"
    elif false_assumption or semantic_rejected:
        implementation_state = "needs_contract_revision"
    elif coherent_pr is False:
        implementation_state = "needs_contract_revision"
    elif not semantic_accepted:
        implementation_state = "needs_semantic_review"
    elif contract["missing_acceptance_coverage"]:
        implementation_state = "needs_contract_revision"
    else:
        implementation_state = "ready"

    checked_claims = semantic.get("source_claims_checked") or []
    tests_checked = semantic.get("tests_checked") or []
    blockers = list(semantic.get("blockers") or [])
    if open_dependencies:
        blockers.append(
            "open direct dependencies: "
            + ", ".join(f"#{item}" for item in open_dependencies)
        )
    if open_inbound_blockers:
        blockers.append(
            "blocked by open issues: "
            + ", ".join(f"#{item}" for item in open_inbound_blockers)
        )
    if missing:
        blockers.append("missing repository paths: " + ", ".join(missing))
    if pr_conflicts:
        blockers.append(
            "active pull request conflicts: "
            + ", ".join(f"#{item}" for item in pr_conflicts)
        )
    required_decisions = list(semantic.get("required_decisions") or [])
    if decision_required and not required_decisions:
        required_decisions.append(
            "Resolve the decision-needed state recorded in labels or issue text."
        )
    required_external = list(semantic.get("required_external_evidence") or [])
    if external_required and not required_external:
        required_external.append(
            "Provide the external evidence, credential, permission, or fixture named by the issue."
        )

    recommended_disposition = {
        "ready": "implement",
        "needs_contract_revision": "revise_issue_contract",
        "needs_semantic_review": "run_bounded_semantic_review",
        "needs_decision": "obtain_maintainer_decision",
        "blocked": "keep_blocked_and_refresh_after_dependencies",
        "stale": "reconcile_live_tracker_state",
        "overlapping": "resolve_scope_ownership",
        "superseded": "keep_closed_or_close_as_superseded",
        "unsafe": "stop_and_redesign",
        "unknown": "collect_missing_evidence",
    }[implementation_state]

    return {
        "issue_number": number,
        "title": normalized.get("title"),
        "url": normalized.get("html_url"),
        "issue_kind": contract["issue_kind"],
        "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"],
        "governance_state": governance_state,
        "contract_accepted": governance_state == "conformant",
        "implementation_state": implementation_state,
        "direct_dependencies": list(relationships.dependencies),
        "dependency_merge_evidence": dependency_merge_evidence,
        "dependency_merge_evidence_details": merge_evidence_details,
        "open_dependencies": sorted(open_dependencies),
        "closed_or_stale_dependencies": closed_dependencies,
        "parent_epics": list(relationships.parent_epics),
        "related_items": list(relationships.related),
        "blocks": list(relationships.blocks),
        "inbound_blockers": inbound_blockers,
        "open_inbound_blockers": open_inbound_blockers,
        "supersedes": list(relationships.supersedes),
        "dependency_cycles": issue_cycles,
        "dependency_impact": int(impact.get(number, 0)),
        "release_gate": number in release_gate,
        "milestone_number": actual_milestone_number,
        "milestone_drift": milestone_drift,
        "stale_checklist_references": stale_checklists,
        "missing_repository_paths": missing,
        "referenced_paths": referenced_paths(body),
        "active_pr_conflicts": pr_conflicts,
        "overlap_conflicts": issue_overlaps,
        "acceptance_coverage": contract["acceptance_coverage"],
        "missing_acceptance_coverage": contract["missing_acceptance_coverage"],
        "source_claims_checked": checked_claims,
        "tests_checked": tests_checked,
        "semantic_review_status": semantic_status or "required",
        "semantic_review_notes": semantic.get("notes") or [],
        "one_pr_coherent": coherent_pr,
        "known_false_assumption": false_assumption,
        "blockers": sorted(set(blockers)),
        "required_decisions": sorted(set(required_decisions)),
        "required_external_evidence": sorted(set(required_external)),
        "recommended_disposition": recommended_disposition,
        "confidence": semantic.get("confidence")
        or ("high" if semantic_accepted else "medium"),
        "contract_findings": contract["findings"],
        "tracker_findings": sorted(
            tracker_findings,
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}.get(item.get("level"), 3),
                item.get("code", ""),
            ),
        ),
        "body_digest": sha256_json(body),
    }


def audit_all_issues(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    root: Path,
    semantic_evidence: Mapping[int, Mapping[str, Any]] | None = None,
    issue_filter: set[int] | None = None,
) -> dict[str, Any]:
    issues = issue_map(snapshot)
    graph = dependency_graph(snapshot)
    cycles = find_cycles(graph)
    impact = dependency_impact(graph)
    release_gate = set(derive_release_gate(snapshot, policy))
    overlaps = detect_explicit_overlaps(snapshot)
    blocked_by = blocked_by_graph(snapshot)
    results = []
    for number in sorted(issues):
        if issue_filter is not None and number not in issue_filter:
            continue
        results.append(
            audit_issue(
                issues[number],
                snapshot=snapshot,
                policy=policy,
                root=root,
                cycles=cycles,
                release_gate=release_gate,
                impact=impact,
                overlaps=overlaps,
                blocked_by=blocked_by,
                semantic_evidence=semantic_evidence,
            )
        )
    state_counts = Counter(item["implementation_state"] for item in results)
    governance_counts = Counter(item["governance_state"] for item in results)
    global_findings: list[dict[str, Any]] = []
    drift = progress_log_drift(snapshot, root / "docs" / "PROGRESS_LOG.md")
    if drift:
        global_findings.append({"level": "warning", **drift})
    projects = snapshot.get("projects", snapshot.get("project"))
    if not isinstance(projects, Mapping) or projects.get("status") not in {
        "available",
        "configured",
    }:
        global_findings.append(
            {
                "level": "warning",
                "code": "project-metadata-unknown",
                "message": "GitHub Project metadata is unavailable or intentionally disabled",
                "data": dict(projects) if isinstance(projects, Mapping) else None,
            }
        )
    expected_base = None
    repository_policy = policy.get("repository")
    if isinstance(repository_policy, Mapping):
        expected_base = repository_policy.get(
            "required_base_branch"
        ) or repository_policy.get("default_branch")
    for number, pull in pull_map(snapshot).items():
        if (
            pull.get("state") == "open"
            and expected_base
            and pull.get("base_ref") != expected_base
        ):
            global_findings.append(
                {
                    "level": "error",
                    "code": "pull-request-base-drift",
                    "message": f"open pull request #{number} targets {pull.get('base_ref')!r}, expected {expected_base!r}",
                }
            )
    payload = {
        "schema_version": 1,
        "repository": repository_name(snapshot),
        "snapshot_digest": snapshot_digest(snapshot),
        "policy_digest": sha256_json(policy),
        "release_gate_issues": sorted(release_gate),
        "dependency_cycles": cycles,
        "issue_count": len(results),
        "governance_state_counts": dict(sorted(governance_counts.items())),
        "implementation_state_counts": dict(sorted(state_counts.items())),
        "global_findings": sorted(
            global_findings,
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}.get(item.get("level"), 3),
                item.get("code", ""),
            ),
        ),
        "issues": results,
    }
    payload["audit_digest"] = sha256_json(payload)
    return payload


def progress_log_drift(
    snapshot: Mapping[str, Any], progress_log: Path
) -> dict[str, Any] | None:
    if not progress_log.is_file():
        return {
            "code": "missing-progress-log",
            "message": "docs/PROGRESS_LOG.md is missing",
        }
    text = progress_log.read_text(encoding="utf-8", errors="replace")
    dates = re.findall(r"(?m)^##\s+(20\d\d-\d\d-\d\d)", text)
    if not dates:
        return {
            "code": "unparseable-progress-log",
            "message": "no dated progress entry was found",
        }
    latest_progress = parse_iso_date(dates[-1] + "T23:59:59Z")
    issue_updates = [
        parse_iso_date(issue.get("updated_at"))
        for issue in issue_map(snapshot, include_closed=False).values()
    ]
    issue_updates = [value for value in issue_updates if value is not None]
    if not latest_progress or not issue_updates:
        return None
    latest_tracker = max(issue_updates)
    if latest_tracker <= latest_progress:
        return None
    return {
        "code": "stale-progress-log",
        "message": "live tracker updates are newer than the latest progress-log entry",
        "latest_progress_date": dates[-1],
        "latest_tracker_update": latest_tracker.isoformat().replace("+00:00", "Z"),
    }
