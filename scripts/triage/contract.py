"""Versioned issue-contract parsing and deterministic conformance checks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

from scripts.triage.common import iter_markdown_lines, normalize_labels, slugify

CONTRACT_VERSION = "1.0"
CONTRACT_ID = "dbt-diagnostics.issue-contract.v1"

ISSUE_KINDS = (
    "bug_fix",
    "feature_enhancement",
    "refactor_architecture",
    "test_verification",
    "spike_decision",
    "epic",
    "docs_chore_release",
)

GOVERNANCE_STATES = (
    "conformant",
    "needs_contract_revision",
    "stale",
    "conflicting",
    "unsafe",
    "unknown",
)


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    title: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ParsedSection:
    key: str | None
    title: str
    level: int
    line: int
    content: str


@dataclass(frozen=True)
class Requirement:
    alternatives: tuple[frozenset[str], ...]
    rationale: str
    level: str = "required"

    @classmethod
    def one_of(
        cls, *keys: str, rationale: str, level: str = "required"
    ) -> "Requirement":
        return cls(tuple(frozenset((key,)) for key in keys), rationale, level)

    @classmethod
    def all_of(
        cls, *keys: str, rationale: str, level: str = "required"
    ) -> "Requirement":
        return cls((frozenset(keys),), rationale, level)


SECTION_DEFINITIONS = (
    SectionDefinition("summary", "Summary", ("summary", "problem summary", "overview")),
    SectionDefinition(
        "user_problem",
        "User-visible problem or current gap",
        (
            "user visible problem",
            "user-visible problem",
            "problem",
            "current gap",
            "motivation",
            "why",
            "background why",
        ),
    ),
    SectionDefinition(
        "evidence_confidence",
        "Evidence and confidence",
        ("evidence and confidence", "evidence", "evidence confidence"),
    ),
    SectionDefinition(
        "current_behavior",
        "Current wrong behavior or gap",
        (
            "current behavior",
            "current wrong behavior",
            "current wrong behavior or gap",
            "observed behavior",
            "current structure",
            "current state",
        ),
    ),
    SectionDefinition(
        "root_cause",
        "Root cause or architectural reason",
        (
            "root cause",
            "architectural reason",
            "root cause or architectural reason",
            "why this happens",
        ),
    ),
    SectionDefinition(
        "expected_behavior",
        "Expected behavior or target outcome",
        (
            "expected behavior",
            "target behavior",
            "target outcome",
            "behavior",
            "proposed behavior",
            "target structure",
            "target pipeline",
        ),
    ),
    SectionDefinition(
        "trigger",
        "Trigger or applicability",
        ("trigger", "triggers", "applicability", "when this applies"),
    ),
    SectionDefinition(
        "acceptance_criteria",
        "Acceptance criteria",
        (
            "acceptance criteria",
            "done when",
            "definition of done",
            "combined definition of done",
        ),
    ),
    SectionDefinition(
        "test_plan",
        "Focused test plan",
        (
            "test plan",
            "focused test plan",
            "verification",
            "verification plan",
            "required focused regression suite",
            "boundary regression suite defined here",
        ),
    ),
    SectionDefinition(
        "edge_cases",
        "Negative, degradation, and regression coverage",
        (
            "negative degradation and regression coverage",
            "negative, degradation, and regression coverage",
            "edge cases",
            "failure modes",
            "regression coverage",
        ),
    ),
    SectionDefinition(
        "scope_files",
        "Scope and likely files",
        (
            "scope",
            "scope and likely files",
            "scope and files touched",
            "exact source and test paths expected to change",
            "files touched",
            "files added modified deleted or reduced to re-exports",
            "files and ownership by child",
            "scope deliverables",
        ),
    ),
    SectionDefinition(
        "non_goals",
        "Explicit non-goals",
        (
            "non goals",
            "non-goals",
            "explicit non goals",
            "explicit non-goals",
            "out of scope",
        ),
    ),
    SectionDefinition(
        "dependencies_traceability",
        "Dependencies and traceability",
        (
            "dependencies and traceability",
            "traceability",
            "dependencies",
            "dependency",
            "relationships",
            "relationship to existing epics",
            "relationship to 4",
        ),
    ),
    SectionDefinition(
        "decisions_blockers",
        "Maintainer decisions and blockers",
        (
            "maintainer decisions and blockers",
            "open decisions",
            "decisions",
            "decision needed",
            "blocked by",
            "blockers",
            "open decision",
        ),
    ),
    SectionDefinition(
        "offline_behavior",
        "Offline behavior",
        ("offline behavior", "offline live behavior", "offline/live behavior"),
    ),
    SectionDefinition(
        "live_behavior_cost",
        "Live behavior and cost tier",
        (
            "live behavior",
            "live behavior and cost tier",
            "cost tier",
            "environment and cost",
            "offline live behavior",
            "offline/live behavior",
        ),
    ),
    SectionDefinition(
        "external_requirements",
        "External evidence, permissions, credentials, or fixtures",
        (
            "external requirements",
            "external evidence",
            "permissions credentials fixtures or external evidence",
            "credentials and permissions",
            "fixtures",
            "what requires a real snowflake account",
            "evidence needed before beginning safely",
        ),
    ),
    SectionDefinition(
        "compatibility_json",
        "Compatibility and canonical JSON implications",
        (
            "compatibility",
            "compatibility behavior",
            "compatibility and canonical json implications",
            "canonical json implications",
            "json implications",
            "compatibility migration",
        ),
    ),
    SectionDefinition(
        "migration_rollback",
        "Migration, coexistence, and rollback",
        (
            "migration rollback",
            "migration and rollback",
            "migration coexistence and rollback",
            "migration order",
            "migration order within the pr",
            "rollback",
            "rollback point",
            "coexistence with remaining legacy diagnostics",
            "compatibility shims",
        ),
    ),
    SectionDefinition(
        "release_priority",
        "Release relevance and priority",
        (
            "release relevance and priority",
            "priority and release relevance",
            "release target",
            "priority",
            "initial release gate",
            "release engineering owned elsewhere",
        ),
    ),
    SectionDefinition(
        "docs_changelog",
        "Documentation and CHANGELOG obligations",
        (
            "documentation and changelog obligations",
            "documentation",
            "changelog",
            "docs and changelog",
        ),
    ),
    SectionDefinition(
        "question",
        "Question to answer",
        ("question", "question to answer", "decision question"),
    ),
    SectionDefinition(
        "investigation_tasks",
        "Investigation tasks",
        ("investigation tasks", "scope tasks", "tasks", "investigation"),
    ),
    SectionDefinition(
        "deliverable",
        "Deliverable",
        ("deliverable", "deliverables", "scope deliverables"),
    ),
    SectionDefinition(
        "decision_criteria",
        "Decision criteria",
        ("decision criteria", "go no go criteria", "go/no-go criteria"),
    ),
    SectionDefinition(
        "thesis", "Thesis or decision", ("thesis", "decision", "architectural decision")
    ),
    SectionDefinition(
        "release_gate",
        "Initial-release gate or build order",
        (
            "initial release gate",
            "build order",
            "release definition of done",
            "combined definition of done",
            "critical path",
        ),
    ),
    SectionDefinition(
        "children_backlog",
        "Children and backlog",
        (
            "children",
            "completed children",
            "post release capabilities",
            "post-release capabilities",
            "post release hardening",
            "post-release hardening",
            "research backlog",
            "research and docs backlog",
        ),
    ),
    SectionDefinition(
        "workflow", "Workflow", ("workflow", "process", "constraints process note")
    ),
    SectionDefinition(
        "implementation_plan",
        "Implementation plan",
        ("implementation plan", "final implementation", "proposed implementation"),
    ),
    SectionDefinition(
        "single_pr_boundary",
        "Single-PR boundary",
        (
            "single pr boundary",
            "single-pr boundary",
            "one pr boundary",
            "one-pr boundary",
        ),
    ),
)


def normalize_heading(value: str) -> str:
    value = value.strip().strip("#").strip()
    value = value.replace("`", "")
    value = value.replace("&", " and ")
    value = value.replace("/", " ")
    value = value.replace("_", " ")
    value = value.replace("-", " ")
    value = re.sub(r"[^a-zA-Z0-9+.]+", " ", value.lower())
    value = re.sub(r"\s+", " ", value).strip(" .:-")
    return value


_ALIAS_TO_KEY: dict[str, str] = {}
_TITLE_BY_KEY: dict[str, str] = {}
for definition in SECTION_DEFINITIONS:
    _TITLE_BY_KEY[definition.key] = definition.title
    for alias in definition.aliases + (definition.title,):
        _ALIAS_TO_KEY[normalize_heading(alias)] = definition.key


def canonical_section_key(title: str) -> str | None:
    normalized = normalize_heading(title)
    if normalized in _ALIAS_TO_KEY:
        return _ALIAS_TO_KEY[normalized]
    # Accept explanatory suffixes after a known title, for example
    # "Acceptance criteria for the first release".
    for alias, key in sorted(
        _ALIAS_TO_KEY.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if normalized.startswith(alias + " "):
            return key
    return None


def parse_sections(body: str) -> tuple[list[ParsedSection], list[dict[str, Any]]]:
    headings: list[tuple[int, int, str, str | None]] = []
    findings: list[dict[str, Any]] = []
    lines = (body or "").splitlines()
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    malformed_re = re.compile(r"^#{2,6}[^#\s]")

    for line_number, line, in_fence in iter_markdown_lines(body):
        if in_fence:
            continue
        if malformed_re.match(line):
            findings.append(
                {
                    "level": "error",
                    "code": "malformed-heading",
                    "message": f"heading at line {line_number} requires a space after #",
                    "line": line_number,
                }
            )
            continue
        match = heading_re.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip().rstrip("#").strip()
        key = canonical_section_key(title)
        if key is not None and level != 2:
            findings.append(
                {
                    "level": "warning",
                    "code": "canonical-heading-level",
                    "message": f"canonical section '{title}' should use a level-2 heading",
                    "line": line_number,
                    "section": key,
                }
            )
        headings.append((line_number, level, title, key))

    sections: list[ParsedSection] = []
    for index, (line_number, level, title, key) in enumerate(headings):
        start = line_number
        end = len(lines)
        for next_line, next_level, _next_title, _next_key in headings[index + 1 :]:
            if next_level <= level:
                end = next_line - 1
                break
        content = "\n".join(lines[start:end]).strip()
        sections.append(ParsedSection(key, title, level, line_number, content))

    by_key: dict[str, list[ParsedSection]] = {}
    for section in sections:
        if section.key is not None:
            by_key.setdefault(section.key, []).append(section)
    for key, duplicates in sorted(by_key.items()):
        if len(duplicates) > 1:
            lines_text = ", ".join(str(section.line) for section in duplicates)
            findings.append(
                {
                    "level": "error",
                    "code": "duplicate-section",
                    "message": f"section '{_TITLE_BY_KEY[key]}' appears more than once at lines {lines_text}",
                    "section": key,
                    "lines": [section.line for section in duplicates],
                }
            )
    return sections, findings


def section_map(sections: Iterable[ParsedSection]) -> dict[str, ParsedSection]:
    result: dict[str, ParsedSection] = {}
    for section in sections:
        if section.key is not None and section.key not in result:
            result[section.key] = section
    return result


def infer_issue_kind(title: str, labels: Iterable[str] = ()) -> str:
    normalized_title = title.strip().lower()
    label_set = {label.lower() for label in labels}
    if (
        "epic" in label_set
        or normalized_title.startswith("[epic]")
        or normalized_title.startswith("epic:")
    ):
        return "epic"
    prefix = re.split(r"[(:\s]", normalized_title.lstrip("["), maxsplit=1)[0].rstrip("]")
    if prefix in {"fix", "bug", "hotfix"} or "bug" in label_set:
        return "bug_fix"
    if prefix in {"feat", "feature", "enhancement"} or "enhancement" in label_set:
        return "feature_enhancement"
    if prefix in {"refactor", "architecture", "arch"} or "architecture" in label_set:
        return "refactor_architecture"
    if prefix in {"test", "verify", "verification"} or "test" in label_set:
        return "test_verification"
    if prefix in {"spike", "decision", "research"} or "spike" in label_set:
        return "spike_decision"
    if prefix in {"docs", "documentation", "chore", "release", "build", "ci"}:
        return "docs_chore_release"
    if label_set & {"docs", "documentation", "chore", "release"}:
        return "docs_chore_release"
    return "feature_enhancement"


COMMON_REQUIREMENTS = (
    Requirement.one_of("summary", rationale="Every issue needs a bounded summary."),
    Requirement.one_of(
        "evidence_confidence",
        rationale="Claims must identify evidence and uncertainty.",
    ),
    Requirement.one_of(
        "acceptance_criteria",
        rationale="Completion must be observable and testable.",
    ),
    Requirement.one_of(
        "test_plan", rationale="Verification must be focused and reproducible."
    ),
    Requirement(
        (
            frozenset(("scope_files", "non_goals")),
            frozenset(("scope_files",)),
        ),
        "The issue must bound its scope and likely change surface.",
    ),
    Requirement.one_of(
        "dependencies_traceability",
        rationale="Dependencies, parent work, and related ownership must be explicit.",
    ),
)

KIND_REQUIREMENTS: dict[str, tuple[Requirement, ...]] = {
    "bug_fix": (
        Requirement.one_of(
            "current_behavior", rationale="A defect needs the current wrong behavior."
        ),
        Requirement.one_of(
            "root_cause",
            rationale="A known root cause or explicit hypothesis is required.",
        ),
        Requirement.one_of(
            "expected_behavior", rationale="The corrected behavior must be stated."
        ),
        Requirement.one_of(
            "non_goals", rationale="The repair boundary must be explicit."
        ),
    ),
    "feature_enhancement": (
        Requirement.one_of(
            "user_problem",
            "trigger",
            rationale="The user problem or trigger must be clear.",
        ),
        Requirement.one_of(
            "expected_behavior", rationale="The intended behavior must be specified."
        ),
        Requirement.one_of(
            "non_goals", rationale="The feature boundary must be explicit."
        ),
    ),
    "refactor_architecture": (
        Requirement.one_of(
            "current_behavior", rationale="The current architecture must be described."
        ),
        Requirement.one_of(
            "expected_behavior", rationale="The target architecture must be described."
        ),
        Requirement.one_of(
            "migration_rollback",
            rationale="Refactors require migration, coexistence, and rollback rules.",
        ),
        Requirement.one_of(
            "compatibility_json",
            rationale="Compatibility implications must be explicit.",
        ),
        Requirement.one_of(
            "non_goals", rationale="The refactor boundary must be explicit."
        ),
    ),
    "test_verification": (
        Requirement.one_of(
            "user_problem",
            "current_behavior",
            rationale="The verification gap must be stated.",
        ),
        Requirement.one_of(
            "external_requirements",
            "scope_files",
            rationale="Fixtures and environments must be named.",
        ),
        Requirement.one_of(
            "non_goals",
            rationale="The test issue must not silently expand product behavior.",
        ),
    ),
    "spike_decision": (
        Requirement.one_of(
            "question", rationale="A spike must ask a decision question."
        ),
        Requirement.one_of(
            "investigation_tasks", rationale="The bounded investigation must be listed."
        ),
        Requirement.one_of(
            "deliverable", rationale="A spike must produce a decision artifact."
        ),
        Requirement.one_of(
            "decision_criteria",
            "acceptance_criteria",
            rationale="Go/no-go criteria must be observable.",
        ),
        Requirement.one_of(
            "non_goals", rationale="A spike must forbid premature implementation."
        ),
    ),
    "epic": (
        Requirement.one_of("thesis", rationale="An epic needs a decision or thesis."),
        Requirement.one_of(
            "release_gate", rationale="An epic needs a build order or completion gate."
        ),
        Requirement.one_of(
            "children_backlog",
            rationale="Children and deferred work must be separated.",
        ),
        Requirement.one_of(
            "decisions_blockers", rationale="Unresolved decisions must remain explicit."
        ),
        Requirement.one_of(
            "workflow", rationale="Execution and ownership rules must be stated."
        ),
    ),
    "docs_chore_release": (
        Requirement.one_of(
            "user_problem",
            "deliverable",
            "scope_files",
            rationale="The maintenance outcome must be concrete.",
        ),
        Requirement.one_of(
            "release_priority",
            "dependencies_traceability",
            rationale="Release relevance or dependency context is required.",
        ),
        Requirement.one_of(
            "non_goals",
            rationale="Maintenance work must have a bounded exclusion list.",
        ),
    ),
}

RECOMMENDED: dict[str, tuple[Requirement, ...]] = {
    "bug_fix": (
        Requirement.one_of(
            "edge_cases",
            rationale="Negative, degradation, and regression cases should be explicit.",
            level="recommended",
        ),
        Requirement.one_of(
            "compatibility_json",
            rationale="Compatibility effects should be recorded.",
            level="recommended",
        ),
    ),
    "feature_enhancement": (
        Requirement.one_of(
            "edge_cases",
            rationale="Failure and regression behavior should be explicit.",
            level="recommended",
        ),
        Requirement.one_of(
            "offline_behavior",
            rationale="Offline behavior should be described where applicable.",
            level="recommended",
        ),
    ),
    "refactor_architecture": (
        Requirement.one_of(
            "edge_cases",
            rationale="Migration failure and regression cases should be explicit.",
            level="recommended",
        ),
        Requirement.one_of(
            "single_pr_boundary",
            rationale="A coherent PR boundary should be stated.",
            level="recommended",
        ),
    ),
    "test_verification": (
        Requirement.one_of(
            "edge_cases",
            rationale="Negative and degradation cases should be represented.",
            level="recommended",
        ),
    ),
    "spike_decision": (
        Requirement.one_of(
            "external_requirements",
            rationale="Required evidence sources should be named.",
            level="recommended",
        ),
    ),
    "epic": (),
    "docs_chore_release": (
        Requirement.one_of(
            "docs_changelog",
            rationale="Documentation and CHANGELOG effects should be stated.",
            level="recommended",
        ),
    ),
}

FORBIDDEN_BY_KIND: dict[str, frozenset[str]] = {
    "spike_decision": frozenset(("implementation_plan",)),
    "epic": frozenset(("single_pr_boundary",)),
}


def _has_terms(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


# A term documents required work only when it is not immediately negated, so
# "No open decisions" or "No external evidence required" do not trigger a
# conditional section. The negation must directly precede the term.
_NEG_PREFIX_RE = re.compile(r"\b(?:no|not|none|without|never|n/?a)\b[\s:,;.\-]*$")


def _requires_terms(text: str, terms: Iterable[str]) -> bool:
    lower = text.lower()
    for term in terms:
        start = 0
        while True:
            idx = lower.find(term, start)
            if idx == -1:
                break
            if not _NEG_PREFIX_RE.search(lower[max(0, idx - 24):idx]):
                return True
            start = idx + len(term)
    return False


def conditional_requirements(
    kind: str, labels: Iterable[str], body: str, milestone: Any
) -> list[Requirement]:
    label_set = {label.lower() for label in labels}
    result: list[Requirement] = []
    if label_set & {"tier-a", "tier-b", "live", "snowflake"} or _has_terms(
        body,
        (
            "snowflake",
            "live probe",
            "warehouse",
            "credential",
            "query history",
            "tier b",
            "tier-b",
        ),
    ):
        result.append(
            Requirement.one_of(
                "live_behavior_cost",
                rationale="Live behavior and cost tier are conditional on warehouse access.",
            )
        )
        result.append(
            Requirement.one_of(
                "offline_behavior",
                rationale="A live-capable issue must state offline degradation behavior.",
            )
        )
    if label_set & {"decision-needed", "blocked"} or _requires_terms(
        body,
        (
            "maintainer decision",
            "decision needed",
            "**open",
            "open decision",
            "blocked by",
        ),
    ):
        result.append(
            Requirement.one_of(
                "decisions_blockers",
                rationale="Decision-needed and blocked work must name the unresolved item.",
            )
        )
    if _requires_terms(
        body,
        (
            "credential",
            "permission",
            "real fixture",
            "external evidence",
            "real snowflake",
            "protected environment",
        ),
    ):
        result.append(
            Requirement.one_of(
                "external_requirements",
                rationale="External evidence, credentials, permissions, or fixtures must be explicit.",
            )
        )
    if _has_terms(
        body,
        (
            "canonical json",
            "json contract",
            "schema version",
            "migration",
            "deprecated",
            "compatibility implications",
        ),
    ):
        result.append(
            Requirement.one_of(
                "compatibility_json",
                rationale="Compatibility and canonical JSON implications are conditional on contract changes.",
            )
        )
    if kind == "refactor_architecture" or _has_terms(
        body, ("rollback", "coexist", "cutover", "migration")
    ):
        result.append(
            Requirement.one_of(
                "migration_rollback",
                rationale="Cutover and refactor work must state rollback and coexistence rules.",
            )
        )
    if (
        milestone is not None
        or any(label.startswith("priority:") for label in label_set)
        or _has_terms(body, ("initial release", "release gate", "release target"))
    ):
        result.append(
            Requirement.one_of(
                "release_priority",
                rationale="Release-relevant work must state priority and gate impact.",
                level="recommended",
            )
        )
    return result


def requirement_satisfied(requirement: Requirement, present: set[str]) -> bool:
    return any(alternative <= present for alternative in requirement.alternatives)


def requirement_label(requirement: Requirement) -> str:
    alternatives = []
    for group in requirement.alternatives:
        alternatives.append(
            " + ".join(_TITLE_BY_KEY.get(key, key) for key in sorted(group))
        )
    return " or ".join(alternatives)


def title_label_findings(
    title: str, labels: Iterable[str], kind: str
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    label_set = {label.lower() for label in labels}
    expected = {
        "bug_fix": {"bug"},
        "feature_enhancement": {"enhancement"},
        "refactor_architecture": {"architecture"},
        "test_verification": {"test"},
        "spike_decision": {"spike"},
        "epic": {"epic"},
        "docs_chore_release": {"documentation", "chore"},
    }[kind]
    if not label_set & expected:
        findings.append(
            {
                "level": "warning",
                "code": "missing-type-label",
                "message": f"inferred kind '{kind}' has none of the expected labels: {sorted(expected)}",
            }
        )
    if title.startswith("[") and not title.lower().startswith("[epic]"):
        findings.append(
            {
                "level": "warning",
                "code": "legacy-title-prefix",
                "message": "use a conventional lowercase type prefix instead of a bracketed title prefix",
            }
        )
    return findings


def acceptance_coverage(text: str) -> dict[str, bool]:
    lower = text.lower()
    return {
        "positive": _has_terms(
            lower,
            (
                "success",
                "positive",
                "returns",
                "emits",
                "produces",
                "works",
                "valid ",
                "confirmed",
            ),
        ),
        "negative": _has_terms(
            lower,
            (
                "negative",
                "invalid",
                "malformed",
                "missing",
                "reject",
                "does not",
                "never ",
                "no ",
                "wrong",
            ),
        ),
        "degradation": _has_terms(
            lower,
            (
                "degrad",
                "unverified",
                "unsupported",
                "unknown",
                "offline",
                "failed probe",
                "no credentials",
                "fallback",
            ),
        ),
        "regression": _has_terms(
            lower,
            (
                "regression",
                "existing",
                "backward",
                "compatib",
                "unchanged",
                "remain",
                "retains",
            ),
        ),
    }


def audit_contract(issue: Mapping[str, Any]) -> dict[str, Any]:
    title = issue.get("title") if isinstance(issue.get("title"), str) else ""
    body = issue.get("body") if isinstance(issue.get("body"), str) else ""
    labels = normalize_labels(issue.get("labels"))
    milestone = issue.get("milestone")
    kind = infer_issue_kind(title, labels)
    sections, findings = parse_sections(body)
    present = {section.key for section in sections if section.key is not None}

    requirements = list(COMMON_REQUIREMENTS)
    if kind == "epic":
        # Epics use their own small contract instead of the implementation core.
        requirements = [COMMON_REQUIREMENTS[0], COMMON_REQUIREMENTS[1]]
    requirements.extend(KIND_REQUIREMENTS[kind])
    requirements.extend(conditional_requirements(kind, labels, body, milestone))
    recommendations = list(RECOMMENDED[kind])

    missing_required: list[str] = []
    missing_recommended: list[str] = []
    for requirement in requirements:
        if requirement_satisfied(requirement, present):
            continue
        target = (
            missing_recommended
            if requirement.level == "recommended"
            else missing_required
        )
        target.append(requirement_label(requirement))
        findings.append(
            {
                "level": "warning" if requirement.level == "recommended" else "error",
                "code": "missing-recommended-section"
                if requirement.level == "recommended"
                else "missing-required-section",
                "message": f"missing {requirement.level} section: {requirement_label(requirement)}",
                "rationale": requirement.rationale,
            }
        )
    for requirement in recommendations:
        if not requirement_satisfied(requirement, present):
            missing_recommended.append(requirement_label(requirement))
            findings.append(
                {
                    "level": "warning",
                    "code": "missing-recommended-section",
                    "message": f"missing recommended section: {requirement_label(requirement)}",
                    "rationale": requirement.rationale,
                }
            )

    forbidden = FORBIDDEN_BY_KIND.get(kind, frozenset())
    for key in sorted(forbidden & present):
        findings.append(
            {
                "level": "error",
                "code": "forbidden-section",
                "message": f"section '{_TITLE_BY_KEY[key]}' is forbidden for issue kind '{kind}'",
                "section": key,
            }
        )

    findings.extend(title_label_findings(title, labels, kind))
    coverage_text = "\n".join(
        section.content
        for section in sections
        if section.key in {"acceptance_criteria", "test_plan", "edge_cases"}
    )
    coverage = acceptance_coverage(coverage_text)
    expected_coverage = {
        "bug_fix": ("positive", "negative", "degradation", "regression"),
        "feature_enhancement": ("positive", "negative", "regression"),
        "refactor_architecture": ("positive", "negative", "degradation", "regression"),
        "test_verification": ("positive", "negative", "degradation", "regression"),
        "spike_decision": ("positive", "negative"),
        "epic": (),
        "docs_chore_release": ("positive", "regression"),
    }[kind]
    missing_coverage = [name for name in expected_coverage if not coverage[name]]
    for name in missing_coverage:
        findings.append(
            {
                "level": "warning",
                "code": f"missing-{name}-coverage",
                "message": f"acceptance/test text does not explicitly represent {name} coverage",
            }
        )

    error_codes = {
        finding["code"] for finding in findings if finding["level"] == "error"
    }
    if "forbidden-section" in error_codes:
        state = "unsafe"
    elif error_codes:
        state = "needs_contract_revision"
    else:
        state = "conformant"

    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "issue_kind": kind,
        "governance_state": state,
        "contract_accepted": state == "conformant",
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "level": section.level,
                "line": section.line,
                "content_digest": slugify(section.content, max_length=24)
                if section.content
                else None,
            }
            for section in sections
        ],
        "present_sections": sorted(present),
        "missing_required_sections": sorted(set(missing_required)),
        "missing_recommended_sections": sorted(set(missing_recommended)),
        "acceptance_coverage": coverage,
        "missing_acceptance_coverage": missing_coverage,
        "findings": sorted(
            findings,
            key=lambda item: (
                {"error": 0, "warning": 1, "info": 2}.get(item.get("level"), 3),
                item.get("code", ""),
                item.get("line", 0),
            ),
        ),
    }


def preferred_section_order(kind: str) -> list[str]:
    common = [
        "summary",
        "user_problem",
        "evidence_confidence",
        "current_behavior",
        "root_cause",
        "expected_behavior",
        "trigger",
        "acceptance_criteria",
        "test_plan",
        "edge_cases",
        "scope_files",
        "non_goals",
        "dependencies_traceability",
        "decisions_blockers",
        "offline_behavior",
        "live_behavior_cost",
        "external_requirements",
        "compatibility_json",
        "migration_rollback",
        "release_priority",
        "docs_changelog",
    ]
    if kind == "spike_decision":
        return [
            "question",
            "summary",
            "evidence_confidence",
            "investigation_tasks",
            "external_requirements",
            "deliverable",
            "decision_criteria",
            "acceptance_criteria",
            "test_plan",
            "scope_files",
            "non_goals",
            "dependencies_traceability",
        ]
    if kind == "epic":
        return [
            "summary",
            "thesis",
            "evidence_confidence",
            "release_gate",
            "children_backlog",
            "decisions_blockers",
            "dependencies_traceability",
            "workflow",
        ]
    return common


def propose_normalized_body(issue: Mapping[str, Any]) -> str:
    body = issue.get("body") if isinstance(issue.get("body"), str) else ""
    title = issue.get("title") if isinstance(issue.get("title"), str) else ""
    labels = normalize_labels(issue.get("labels"))
    kind = infer_issue_kind(title, labels)
    sections, _findings = parse_sections(body)
    mapped = section_map(sections)
    contract = audit_contract(issue)

    required_keys: set[str] = set()
    requirements = list(
        COMMON_REQUIREMENTS if kind != "epic" else COMMON_REQUIREMENTS[:2]
    )
    requirements.extend(KIND_REQUIREMENTS[kind])
    requirements.extend(
        conditional_requirements(kind, labels, body, issue.get("milestone"))
    )
    for requirement in requirements:
        # Select the smallest deterministic alternative for a proposed skeleton.
        alternative = min(
            requirement.alternatives, key=lambda group: (len(group), sorted(group))
        )
        required_keys.update(alternative)

    ordered = preferred_section_order(kind)
    keys = [key for key in ordered if key in mapped or key in required_keys]
    lines: list[str] = []
    for key in keys:
        title_text = _TITLE_BY_KEY[key]
        lines.extend([f"## {title_text}", ""])
        existing = mapped.get(key)
        if existing and existing.content.strip():
            lines.append(existing.content.strip())
        else:
            lines.append(
                "Unknown. I could not establish this contract item from the current issue body; maintainer review is required."
            )
        lines.append("")

    unmapped = [
        section for section in sections if section.key is None and section.level == 2
    ]
    if unmapped:
        lines.extend(["## Additional context retained from the current issue", ""])
        for section in unmapped:
            lines.extend(
                [f"### {section.title}", "", section.content.strip() or "[empty]", ""]
            )

    if contract["missing_acceptance_coverage"] and "acceptance_criteria" in keys:
        lines.extend(
            [
                "## Contract audit notes",
                "",
                "The following coverage categories remain explicit review items:",
            ]
        )
        for item in contract["missing_acceptance_coverage"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
