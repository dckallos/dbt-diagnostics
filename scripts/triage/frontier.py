"""Deterministic audit and implementation frontiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, ClassVar, Mapping

from scripts.triage.common import (
    canonical_json,
    issue_map,
    pull_map,
    repository_name,
    sha256_json,
    slugify,
    snapshot_digest,
)
from scripts.triage import repo_config
from scripts.triage.contract import parse_sections

COORDINATOR_SCHEMA_VERSION = 1
WORKER_PACKET_SCHEMA_VERSION = 1
PROJECT_PLAN_SCHEMA_VERSION = 1
BACKLOG_SYNTHESIS_SCHEMA_VERSION = 1
SYNTHESIS_REVIEW_PACKET_SCHEMA_VERSION = 1
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

TITLE_STOPWORDS = {
    "a",
    "and",
    "as",
    "for",
    "in",
    "issue",
    "of",
    "or",
    "the",
    "to",
    "with",
}

SPLIT_MARKERS = (
    "split candidate",
    "separate pr",
    "separate prs",
    "multiple coherent pr",
    "multiple coherent prs",
    "more than one coherent pr",
    "separable deliverable",
    "separable deliverables",
    "separable workstream",
    "separable workstreams",
)

SIGNAL_SORT_ORDER = {
    "semantic-disposition": 10,
    "explicit-overlap": 20,
    "likely-duplicate": 30,
    "split-candidate": 40,
    "dependency-inversion": 50,
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


def _project_plan_without_digest(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "project_plan_digest"}


def _backlog_synthesis_without_digest(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key != "backlog_synthesis_digest"
    }


def _synthesis_review_packet_without_digest(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in packet.items()
        if key != "synthesis_review_packet_digest"
    }


@dataclass(frozen=True)
class ProjectPolicy:
    enabled: bool
    owner_type: str | int | None = None
    owner: str | int | None = None
    number: str | int | None = None

    @classmethod
    def from_policy(cls, policy: Mapping[str, Any] | None) -> ProjectPolicy:
        project = policy.get("project", {}) if isinstance(policy, Mapping) else {}
        if not isinstance(project, Mapping):
            project = {}
        values: dict[str, Any] = {"enabled": bool(project.get("enabled", False))}
        for key in ("owner_type", "owner", "number"):
            value = project.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                values[key] = value
        return cls(**values)

    def to_json(self) -> dict[str, Any]:
        result: dict[str, Any] = {"enabled": self.enabled}
        for key in ("owner_type", "owner", "number"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class ProjectPlanColumn:
    id: str
    name: str
    position: int

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "position": self.position}


@dataclass(frozen=True)
class ProjectPlanItem:
    issue_number: int
    title: str | None
    url: str | None
    column_id: str
    direct_dependencies: tuple[int, ...]
    parent_epics: tuple[int, ...]
    release_gate: bool
    dependency_impact: int
    position: int = 0
    column_position: int = 0

    def with_positions(self, *, position: int, column_position: int) -> ProjectPlanItem:
        return ProjectPlanItem(
            issue_number=self.issue_number,
            title=self.title,
            url=self.url,
            column_id=self.column_id,
            direct_dependencies=self.direct_dependencies,
            parent_epics=self.parent_epics,
            release_gate=self.release_gate,
            dependency_impact=self.dependency_impact,
            position=position,
            column_position=column_position,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "issue_number": self.issue_number,
            "title": self.title,
            "url": self.url,
            "column_id": self.column_id,
            "direct_dependencies": list(self.direct_dependencies),
            "parent_epics": list(self.parent_epics),
            "release_gate": self.release_gate,
            "dependency_impact": self.dependency_impact,
            "position": self.position,
            "column_position": self.column_position,
        }


@dataclass(frozen=True)
class ProjectPlanOrderingConflict:
    code: str
    issue_number: int
    dependency_issue_number: int
    issue_position: int
    dependency_position: int
    message: str

    @classmethod
    def dependency_inversion(
        cls,
        *,
        issue_number: int,
        dependency_issue_number: int,
        issue_position: int,
        dependency_position: int,
    ) -> ProjectPlanOrderingConflict:
        return cls(
            code="dependency-inversion",
            issue_number=issue_number,
            dependency_issue_number=dependency_issue_number,
            issue_position=issue_position,
            dependency_position=dependency_position,
            message=(
                f"#{issue_number} is ordered before its dependency "
                f"#{dependency_issue_number}"
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "issue_number": self.issue_number,
            "dependency_issue_number": self.dependency_issue_number,
            "issue_position": self.issue_position,
            "dependency_position": self.dependency_position,
            "message": self.message,
        }


@dataclass(frozen=True)
class ProjectPlanSafety:
    read_only: bool
    github_api_calls: bool
    github_mutations: bool
    project_writes_supported: bool
    metadata_operations_supported: bool
    contains_issue_content: bool
    contains_state_changes: bool

    @classmethod
    def read_only_contract(cls) -> ProjectPlanSafety:
        return cls(
            read_only=True,
            github_api_calls=False,
            github_mutations=False,
            project_writes_supported=False,
            metadata_operations_supported=False,
            contains_issue_content=False,
            contains_state_changes=False,
        )

    def to_json(self) -> dict[str, bool]:
        return {
            "read_only": self.read_only,
            "github_api_calls": self.github_api_calls,
            "github_mutations": self.github_mutations,
            "project_writes_supported": self.project_writes_supported,
            "metadata_operations_supported": self.metadata_operations_supported,
            "contains_issue_content": self.contains_issue_content,
            "contains_state_changes": self.contains_state_changes,
        }


@dataclass(frozen=True)
class ProjectPlan:
    repository: str
    generated_at: str
    snapshot_digest: str
    audit_digest: str | None
    project: ProjectPolicy
    columns: tuple[ProjectPlanColumn, ...]
    items: tuple[ProjectPlanItem, ...]
    ordering_conflicts: tuple[ProjectPlanOrderingConflict, ...]
    safety: ProjectPlanSafety = ProjectPlanSafety.read_only_contract()
    schema_version: int = PROJECT_PLAN_SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        plan: dict[str, Any] = {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "generated_at": self.generated_at,
            "snapshot_digest": self.snapshot_digest,
            "audit_digest": self.audit_digest,
            "project": self.project.to_json(),
            "columns": [column.to_json() for column in self.columns],
            "items": [item.to_json() for item in self.items],
            "ordering_conflicts": [
                conflict.to_json() for conflict in self.ordering_conflicts
            ],
            "safety": self.safety.to_json(),
        }
        plan["project_plan_digest"] = sha256_json(_project_plan_without_digest(plan))
        return plan


@dataclass(frozen=True)
class BacklogSynthesisSafety:
    read_only: bool
    github_api_calls: bool
    github_mutations: bool
    contains_issue_content: bool
    contains_state_changes: bool
    verdicts_are_advisory: bool

    @classmethod
    def read_only_contract(cls) -> BacklogSynthesisSafety:
        return cls(
            read_only=True,
            github_api_calls=False,
            github_mutations=False,
            contains_issue_content=False,
            contains_state_changes=False,
            verdicts_are_advisory=True,
        )

    def to_json(self) -> dict[str, bool]:
        return {
            "read_only": self.read_only,
            "github_api_calls": self.github_api_calls,
            "github_mutations": self.github_mutations,
            "contains_issue_content": self.contains_issue_content,
            "contains_state_changes": self.contains_state_changes,
            "verdicts_are_advisory": self.verdicts_are_advisory,
        }


@dataclass(frozen=True)
class BacklogIssueDisposition:
    issue_number: int
    mechanical_disposition: str
    semantic_hypothesis: str | None
    recommended_disposition: str
    semantic_evidence_status: str
    evidence: tuple[str, ...]

    @classmethod
    def from_entry(cls, entry: Mapping[str, Any]) -> BacklogIssueDisposition:
        issue_number = int(entry["issue_number"])
        mechanical = str(entry.get("recommended_disposition") or "unknown")
        raw_hypothesis = entry.get("semantic_disposition_hypothesis")
        hypothesis = raw_hypothesis if isinstance(raw_hypothesis, str) else None
        evidence = tuple(
            item
            for item in entry.get("semantic_disposition_evidence") or []
            if isinstance(item, str)
        )
        return cls(
            issue_number=issue_number,
            mechanical_disposition=mechanical,
            semantic_hypothesis=hypothesis,
            recommended_disposition=hypothesis or mechanical,
            semantic_evidence_status="provided" if hypothesis else "unknown",
            evidence=evidence,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "issue_number": self.issue_number,
            "mechanical_disposition": self.mechanical_disposition,
            "semantic_hypothesis": self.semantic_hypothesis,
            "recommended_disposition": self.recommended_disposition,
            "semantic_evidence_status": self.semantic_evidence_status,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class BacklogSynthesisSignal:
    signal_type: str
    issue_numbers: tuple[int, ...]
    confidence: str
    summary: str
    evidence: tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "issue_numbers": list(self.issue_numbers),
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class BacklogSynthesisReport:
    repository: str
    generated_at: str
    snapshot_digest: str
    audit_digest: str
    issue_dispositions: tuple[BacklogIssueDisposition, ...]
    signals: tuple[BacklogSynthesisSignal, ...]
    safety: BacklogSynthesisSafety = BacklogSynthesisSafety.read_only_contract()
    schema_version: int = BACKLOG_SYNTHESIS_SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "generated_at": self.generated_at,
            "snapshot_digest": self.snapshot_digest,
            "audit_digest": self.audit_digest,
            "issue_dispositions": [
                item.to_json() for item in self.issue_dispositions
            ],
            "signals": [signal.to_json() for signal in self.signals],
            "safety": self.safety.to_json(),
        }
        report["backlog_synthesis_digest"] = sha256_json(
            _backlog_synthesis_without_digest(report)
        )
        return report


def _is_positive_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _is_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


@dataclass
class ValidationContext:
    errors: list[str] = field(default_factory=list)

    def require_keys(self, value: Mapping[str, Any], required: set[str]) -> None:
        missing = sorted(required - set(value))
        if missing:
            self.errors.append("missing keys: " + ", ".join(missing))

    def require_repository(self, value: Any, *, name: str = "repository") -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[^/]+/[^/]+", value):
            self.errors.append(f"{name} must be owner/name")

    def require_string(self, value: Any, *, name: str) -> None:
        if not isinstance(value, str):
            self.errors.append(f"{name} must be a string")

    def require_non_empty_string(self, value: Any, *, name: str) -> None:
        if not isinstance(value, str) or not value:
            self.errors.append(f"{name} must be a non-empty string")

    def require_string_or_null(self, value: Any, *, name: str) -> None:
        if value is not None and not isinstance(value, str):
            self.errors.append(f"{name} must be a string or null")

    def require_string_list(self, value: Any, *, name: str) -> None:
        values = value if isinstance(value, list) else []
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in values
        ):
            self.errors.append(f"{name} must be an array of strings")

    def require_digest(self, value: Any, *, name: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            self.errors.append(f"{name} must be a lowercase SHA-256 digest")

    def require_bool(self, value: Any, *, name: str) -> None:
        if not isinstance(value, bool):
            self.errors.append(f"{name} must be boolean")

    def require_positive_int(self, value: Any, *, name: str) -> None:
        if not _is_positive_int(value):
            self.errors.append(f"{name} must be a positive integer")

    def require_positive_int_or_null(self, value: Any, *, name: str) -> None:
        if value is not None and not _is_positive_int(value):
            self.errors.append(f"{name} must be a positive integer or null")

    def require_non_negative_int(self, value: Any, *, name: str) -> None:
        if not _is_non_negative_int(value):
            self.errors.append(f"{name} must be a non-negative integer")

    def require_int_or_null(self, value: Any, *, name: str) -> None:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            self.errors.append(f"{name} must be an integer when present")

    def require_positive_int_list(self, value: Any, *, name: str) -> None:
        values = value if isinstance(value, list) else []
        if not isinstance(value, list) or any(
            not _is_positive_int(item) for item in values
        ):
            self.errors.append(f"{name} must be an array of positive integers")


@dataclass(frozen=True)
class ProjectPolicyShape:
    value: Mapping[str, Any]

    def validate(self, context: ValidationContext) -> None:
        context.require_bool(self.value.get("enabled"), name="project.enabled")
        for key in ("owner_type", "owner", "number"):
            item = self.value.get(key)
            if item is not None and (
                isinstance(item, bool) or not isinstance(item, (str, int))
            ):
                context.errors.append(f"project.{key} must be a string or integer")


@dataclass(frozen=True)
class ProjectPlanColumnShape:
    index: int
    value: Mapping[str, Any]

    @property
    def path(self) -> str:
        return f"columns[{self.index}]"

    def validate(self, context: ValidationContext) -> None:
        context.require_non_empty_string(self.value.get("id"), name=f"{self.path}.id")
        context.require_non_empty_string(
            self.value.get("name"), name=f"{self.path}.name"
        )
        context.require_positive_int(
            self.value.get("position"), name=f"{self.path}.position"
        )


@dataclass(frozen=True)
class ProjectPlanItemShape:
    index: int
    value: Mapping[str, Any]

    @property
    def path(self) -> str:
        return f"items[{self.index}]"

    def validate(self, context: ValidationContext) -> None:
        if "body" in self.value:
            context.errors.append(f"{self.path}.body is forbidden")
        if "state" in self.value:
            context.errors.append(f"{self.path}.state is forbidden")
        context.require_positive_int(
            self.value.get("issue_number"), name=f"{self.path}.issue_number"
        )
        context.require_string_or_null(
            self.value.get("title"), name=f"{self.path}.title"
        )
        context.require_string_or_null(self.value.get("url"), name=f"{self.path}.url")
        context.require_non_empty_string(
            self.value.get("column_id"), name=f"{self.path}.column_id"
        )
        context.require_positive_int_list(
            self.value.get("direct_dependencies"),
            name=f"{self.path}.direct_dependencies",
        )
        context.require_positive_int_list(
            self.value.get("parent_epics"), name=f"{self.path}.parent_epics"
        )
        context.require_bool(
            self.value.get("release_gate"), name=f"{self.path}.release_gate"
        )
        context.require_non_negative_int(
            self.value.get("dependency_impact"),
            name=f"{self.path}.dependency_impact",
        )
        for key in ("position", "column_position"):
            context.require_positive_int(self.value.get(key), name=f"{self.path}.{key}")


@dataclass(frozen=True)
class ProjectPlanOrderingConflictShape:
    index: int
    value: Mapping[str, Any]

    @property
    def path(self) -> str:
        return f"ordering_conflicts[{self.index}]"

    def validate(self, context: ValidationContext) -> None:
        context.require_non_empty_string(
            self.value.get("code"), name=f"{self.path}.code"
        )
        for key in (
            "issue_number",
            "dependency_issue_number",
            "issue_position",
            "dependency_position",
        ):
            context.require_positive_int(self.value.get(key), name=f"{self.path}.{key}")
        context.require_non_empty_string(
            self.value.get("message"), name=f"{self.path}.message"
        )


@dataclass(frozen=True)
class ProjectPlanSafetyShape:
    value: Mapping[str, Any]

    EXPECTED: ClassVar[dict[str, bool]] = {
        "read_only": True,
        "github_api_calls": False,
        "github_mutations": False,
        "project_writes_supported": False,
        "metadata_operations_supported": False,
        "contains_issue_content": False,
        "contains_state_changes": False,
    }

    def validate(self, context: ValidationContext) -> None:
        for key, expected in self.EXPECTED.items():
            if self.value.get(key) is not expected:
                context.errors.append(f"safety.{key} must be {str(expected).lower()}")


@dataclass(frozen=True)
class ProjectPlanValidator:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "schema_version",
        "repository",
        "generated_at",
        "snapshot_digest",
        "audit_digest",
        "project",
        "columns",
        "items",
        "ordering_conflicts",
        "safety",
        "project_plan_digest",
    }

    def validate(self) -> list[str]:
        context = ValidationContext()
        context.require_keys(self.value, self.REQUIRED_KEYS)
        if "operations" in self.value:
            context.errors.append("operations key is forbidden")
        if self.value.get("schema_version") != PROJECT_PLAN_SCHEMA_VERSION:
            context.errors.append("unsupported schema_version")
        context.require_repository(self.value.get("repository"))
        context.require_string(self.value.get("generated_at"), name="generated_at")
        for key in ("snapshot_digest", "audit_digest", "project_plan_digest"):
            context.require_digest(self.value.get(key), name=key)
        self._validate_project(context)
        self._validate_columns(context)
        self._validate_items(context)
        self._validate_ordering_conflicts(context)
        self._validate_safety(context)
        actual_digest = sha256_json(_project_plan_without_digest(self.value))
        if self.value.get("project_plan_digest") != actual_digest:
            context.errors.append("project_plan_digest mismatch")
        return context.errors

    def _validate_project(self, context: ValidationContext) -> None:
        project = self.value.get("project")
        if not isinstance(project, Mapping):
            context.errors.append("project must be an object")
            return
        ProjectPolicyShape(project).validate(context)

    def _validate_columns(self, context: ValidationContext) -> None:
        columns = self.value.get("columns")
        if not isinstance(columns, list):
            context.errors.append("columns must be an array")
            return
        for index, column in enumerate(columns):
            if not isinstance(column, Mapping):
                context.errors.append(f"columns[{index}] must be an object")
                continue
            ProjectPlanColumnShape(index, column).validate(context)

    def _validate_items(self, context: ValidationContext) -> None:
        items = self.value.get("items")
        if not isinstance(items, list):
            context.errors.append("items must be an array")
            return
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                context.errors.append(f"items[{index}] must be an object")
                continue
            ProjectPlanItemShape(index, item).validate(context)

    def _validate_ordering_conflicts(self, context: ValidationContext) -> None:
        ordering_conflicts = self.value.get("ordering_conflicts")
        if not isinstance(ordering_conflicts, list):
            context.errors.append("ordering_conflicts must be an array")
            return
        for index, conflict in enumerate(ordering_conflicts):
            if not isinstance(conflict, Mapping):
                context.errors.append(f"ordering_conflicts[{index}] must be an object")
                continue
            ProjectPlanOrderingConflictShape(index, conflict).validate(context)

    def _validate_safety(self, context: ValidationContext) -> None:
        safety = self.value.get("safety")
        if not isinstance(safety, Mapping):
            context.errors.append("safety must be an object")
            return
        ProjectPlanSafetyShape(safety).validate(context)


@dataclass(frozen=True)
class BacklogSynthesisSafetyShape:
    value: Mapping[str, Any]

    EXPECTED: ClassVar[dict[str, bool]] = {
        "read_only": True,
        "github_api_calls": False,
        "github_mutations": False,
        "contains_issue_content": False,
        "contains_state_changes": False,
        "verdicts_are_advisory": True,
    }

    def validate(self, context: ValidationContext) -> None:
        for key, expected in self.EXPECTED.items():
            if self.value.get(key) is not expected:
                context.errors.append(f"safety.{key} must be {str(expected).lower()}")


@dataclass(frozen=True)
class BacklogIssueDispositionShape:
    index: int
    value: Mapping[str, Any]

    @property
    def path(self) -> str:
        return f"issue_dispositions[{self.index}]"

    def validate(self, context: ValidationContext) -> None:
        if "body" in self.value:
            context.errors.append(f"{self.path}.body is forbidden")
        if "state" in self.value:
            context.errors.append(f"{self.path}.state is forbidden")
        context.require_positive_int(
            self.value.get("issue_number"), name=f"{self.path}.issue_number"
        )
        for key in ("mechanical_disposition", "recommended_disposition"):
            context.require_non_empty_string(
                self.value.get(key), name=f"{self.path}.{key}"
            )
        context.require_string_or_null(
            self.value.get("semantic_hypothesis"),
            name=f"{self.path}.semantic_hypothesis",
        )
        if self.value.get("semantic_evidence_status") not in {"provided", "unknown"}:
            context.errors.append(
                f"{self.path}.semantic_evidence_status must be provided or unknown"
            )
        context.require_string_list(
            self.value.get("evidence"), name=f"{self.path}.evidence"
        )


@dataclass(frozen=True)
class BacklogSynthesisSignalShape:
    index: int
    value: Mapping[str, Any]

    @property
    def path(self) -> str:
        return f"signals[{self.index}]"

    def validate(self, context: ValidationContext) -> None:
        if "body" in self.value:
            context.errors.append(f"{self.path}.body is forbidden")
        if "state" in self.value:
            context.errors.append(f"{self.path}.state is forbidden")
        context.require_non_empty_string(
            self.value.get("signal_type"), name=f"{self.path}.signal_type"
        )
        context.require_positive_int_list(
            self.value.get("issue_numbers"), name=f"{self.path}.issue_numbers"
        )
        issue_numbers = self.value.get("issue_numbers")
        if (
            isinstance(issue_numbers, list)
            and all(_is_positive_int(item) for item in issue_numbers)
            and issue_numbers != sorted(set(issue_numbers))
        ):
            context.errors.append(f"{self.path}.issue_numbers must be sorted and unique")
        if self.value.get("confidence") not in {"low", "medium", "high"}:
            context.errors.append(f"{self.path}.confidence must be low, medium, or high")
        context.require_non_empty_string(
            self.value.get("summary"), name=f"{self.path}.summary"
        )
        context.require_string_list(
            self.value.get("evidence"), name=f"{self.path}.evidence"
        )
        details = self.value.get("details")
        if not isinstance(details, Mapping):
            context.errors.append(f"{self.path}.details must be an object")
            return
        for forbidden in ("body", "state"):
            if forbidden in details:
                context.errors.append(f"{self.path}.details.{forbidden} is forbidden")


@dataclass(frozen=True)
class BacklogSynthesisReportValidator:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "schema_version",
        "repository",
        "generated_at",
        "snapshot_digest",
        "audit_digest",
        "issue_dispositions",
        "signals",
        "safety",
        "backlog_synthesis_digest",
    }

    def validate(self) -> list[str]:
        context = ValidationContext()
        context.require_keys(self.value, self.REQUIRED_KEYS)
        if "operations" in self.value:
            context.errors.append("operations key is forbidden")
        if self.value.get("schema_version") != BACKLOG_SYNTHESIS_SCHEMA_VERSION:
            context.errors.append("unsupported schema_version")
        context.require_repository(self.value.get("repository"))
        context.require_string(self.value.get("generated_at"), name="generated_at")
        for key in ("snapshot_digest", "audit_digest", "backlog_synthesis_digest"):
            context.require_digest(self.value.get(key), name=key)
        self._validate_issue_dispositions(context)
        self._validate_signals(context)
        self._validate_safety(context)
        actual_digest = sha256_json(_backlog_synthesis_without_digest(self.value))
        if self.value.get("backlog_synthesis_digest") != actual_digest:
            context.errors.append("backlog_synthesis_digest mismatch")
        return context.errors

    def _validate_issue_dispositions(self, context: ValidationContext) -> None:
        dispositions = self.value.get("issue_dispositions")
        if not isinstance(dispositions, list):
            context.errors.append("issue_dispositions must be an array")
            return
        for index, disposition in enumerate(dispositions):
            if not isinstance(disposition, Mapping):
                context.errors.append(f"issue_dispositions[{index}] must be an object")
                continue
            BacklogIssueDispositionShape(index, disposition).validate(context)

    def _validate_signals(self, context: ValidationContext) -> None:
        signals = self.value.get("signals")
        if not isinstance(signals, list):
            context.errors.append("signals must be an array")
            return
        for index, signal in enumerate(signals):
            if not isinstance(signal, Mapping):
                context.errors.append(f"signals[{index}] must be an object")
                continue
            BacklogSynthesisSignalShape(index, signal).validate(context)

    def _validate_safety(self, context: ValidationContext) -> None:
        safety = self.value.get("safety")
        if not isinstance(safety, Mapping):
            context.errors.append("safety must be an object")
            return
        BacklogSynthesisSafetyShape(safety).validate(context)


@dataclass(frozen=True)
class SynthesisReviewPacketSourceArtifactsShape:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "snapshot_digest",
        "audit_digest",
        "backlog_synthesis_digest",
    }

    def validate(self, context: ValidationContext) -> None:
        context.require_keys(self.value, self.REQUIRED_KEYS)
        for key in self.REQUIRED_KEYS | {"project_plan_digest"}:
            if key in self.value:
                context.require_digest(
                    self.value.get(key), name=f"source_artifacts.{key}"
                )


@dataclass(frozen=True)
class SynthesisReviewPacketBudgetShape:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "serialized_bytes",
        "target_bytes",
        "hard_bytes",
        "estimated_tokens",
        "target_estimated_tokens",
        "hard_estimated_tokens",
        "token_estimate_method",
    }
    EXPECTED_CONSTANTS: ClassVar[dict[str, int]] = {
        "target_bytes": 204800,
        "hard_bytes": 307200,
        "target_estimated_tokens": 50000,
        "hard_estimated_tokens": 75000,
    }

    def validate(self, context: ValidationContext) -> None:
        context.require_keys(self.value, self.REQUIRED_KEYS)
        for key in (
            "serialized_bytes",
            "target_bytes",
            "hard_bytes",
            "estimated_tokens",
            "target_estimated_tokens",
            "hard_estimated_tokens",
        ):
            context.require_non_negative_int(self.value.get(key), name=f"budget.{key}")
        for key, expected in self.EXPECTED_CONSTANTS.items():
            if self.value.get(key) != expected:
                context.errors.append(f"budget.{key} must be {expected}")
        context.require_non_empty_string(
            self.value.get("token_estimate_method"),
            name="budget.token_estimate_method",
        )
        serialized = self.value.get("serialized_bytes")
        hard = self.value.get("hard_bytes")
        if _is_non_negative_int(serialized) and _is_non_negative_int(hard):
            if int(serialized) > int(hard):
                context.errors.append(
                    "budget.serialized_bytes must not exceed budget.hard_bytes"
                )


@dataclass(frozen=True)
class SynthesisReviewPacketStalenessShape:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "max_age_hours",
        "stale",
        "llm_review_allowed",
    }

    def validate(self, context: ValidationContext) -> None:
        context.require_keys(self.value, self.REQUIRED_KEYS)
        context.require_positive_int(
            self.value.get("max_age_hours"), name="staleness.max_age_hours"
        )
        context.require_bool(self.value.get("stale"), name="staleness.stale")
        context.require_bool(
            self.value.get("llm_review_allowed"),
            name="staleness.llm_review_allowed",
        )
        if (
            self.value.get("stale") is True
            and self.value.get("llm_review_allowed") is not False
        ):
            context.errors.append(
                "staleness.llm_review_allowed must be false when "
                "staleness.stale is true"
            )
        if self.value.get("stale") is True:
            context.errors.append(
                "staleness.stale packets are not valid for LLM review"
            )


@dataclass(frozen=True)
class SynthesisReviewPacketSafetyShape:
    value: Mapping[str, Any]

    EXPECTED: ClassVar[dict[str, bool]] = {
        "read_only": True,
        "github_api_calls": False,
        "github_mutations": False,
        "contains_executable_operations": False,
        "contains_full_tracker_snapshot": False,
        "contains_issue_comments": False,
        "comments_included": False,
        "llm_verdicts_are_advisory": True,
    }

    def validate(self, context: ValidationContext) -> None:
        for key, expected in self.EXPECTED.items():
            if self.value.get(key) is not expected:
                context.errors.append(f"safety.{key} must be {str(expected).lower()}")


@dataclass(frozen=True)
class SynthesisReviewPacketValidator:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
        "schema_version",
        "repository",
        "generated_at",
        "source_generated_at",
        "source_artifacts",
        "packet_scope",
        "candidate_sets",
        "evidence_items",
        "near_misses",
        "omissions",
        "comments_included",
        "comment_evidence_status",
        "budget",
        "staleness",
        "safety",
        "synthesis_review_packet_digest",
    }
    GITHUB_REQUEST_KEYS: ClassVar[set[str]] = {
        "github_request",
        "github_requests",
        "github_request_payload",
        "github_request_payloads",
        "request_payload",
        "request_payloads",
        "rest_request",
        "rest_requests",
        "graphql_request",
        "graphql_requests",
        "mutation_request",
        "mutation_requests",
    }
    COMMENT_KEYS: ClassVar[set[str]] = {
        "comment",
        "comments",
        "issue_comment",
        "issue_comments",
        "review_comment",
        "review_comments",
        "review_thread",
        "review_threads",
    }
    METADATA_MUTATION_KEYS: ClassVar[set[str]] = {
        "body_update",
        "body_updates",
        "close_request",
        "close_requests",
        "label_update",
        "label_updates",
        "milestone_update",
        "milestone_updates",
        "project_update",
        "project_updates",
        "reopen_request",
        "reopen_requests",
        "state_update",
        "state_updates",
        "title_update",
        "title_updates",
    }

    def validate(self) -> list[str]:
        context = ValidationContext()
        context.require_keys(self.value, self.REQUIRED_KEYS)
        self._validate_forbidden_shape(context, self.value, "")
        if self.value.get("schema_version") != SYNTHESIS_REVIEW_PACKET_SCHEMA_VERSION:
            context.errors.append("unsupported schema_version")
        context.require_repository(self.value.get("repository"))
        context.require_string(self.value.get("generated_at"), name="generated_at")
        context.require_string(
            self.value.get("source_generated_at"), name="source_generated_at"
        )
        context.require_digest(
            self.value.get("synthesis_review_packet_digest"),
            name="synthesis_review_packet_digest",
        )
        self._validate_source_artifacts(context)
        self._validate_packet_scope(context)
        for key in ("candidate_sets", "evidence_items"):
            self._validate_array(context, key, allow_string=False)
        for key in ("near_misses", "omissions"):
            self._validate_array(context, key, allow_string=True)
        self._validate_evidence_items(context)
        self._validate_comments(context)
        self._validate_budget(context)
        self._validate_actual_serialized_size(context)
        self._validate_staleness(context)
        self._validate_safety(context)
        actual_digest = sha256_json(_synthesis_review_packet_without_digest(self.value))
        if self.value.get("synthesis_review_packet_digest") != actual_digest:
            context.errors.append("synthesis_review_packet_digest mismatch")
        return context.errors

    def _validate_source_artifacts(self, context: ValidationContext) -> None:
        source_artifacts = self.value.get("source_artifacts")
        if not isinstance(source_artifacts, Mapping):
            context.errors.append("source_artifacts must be an object")
            return
        SynthesisReviewPacketSourceArtifactsShape(source_artifacts).validate(context)

    def _validate_packet_scope(self, context: ValidationContext) -> None:
        packet_scope = self.value.get("packet_scope")
        if not isinstance(packet_scope, Mapping):
            context.errors.append("packet_scope must be an object")

    def _validate_array(
        self, context: ValidationContext, key: str, *, allow_string: bool
    ) -> None:
        values = self.value.get(key)
        if not isinstance(values, list):
            context.errors.append(f"{key} must be an array")
            return
        for index, item in enumerate(values):
            if isinstance(item, Mapping):
                continue
            if allow_string and isinstance(item, str):
                continue
            expected = "object or string" if allow_string else "object"
            context.errors.append(f"{key}[{index}] must be an {expected}")

    def _validate_evidence_items(self, context: ValidationContext) -> None:
        evidence_items = self.value.get("evidence_items")
        if not isinstance(evidence_items, list):
            return
        for index, item in enumerate(evidence_items):
            if not isinstance(item, Mapping):
                continue
            context.require_non_empty_string(
                item.get("evidence_id"), name=f"evidence_items[{index}].evidence_id"
            )
            if "excerpt" in item:
                context.require_non_empty_string(
                    item.get("excerpt"), name=f"evidence_items[{index}].excerpt"
                )

    def _validate_comments(self, context: ValidationContext) -> None:
        if self.value.get("comments_included") is not False:
            context.errors.append("comments_included must be false")
        if self.value.get("comment_evidence_status") != "not_collected":
            context.errors.append(
                "comment_evidence_status must be not_collected"
            )

    def _validate_budget(self, context: ValidationContext) -> None:
        budget = self.value.get("budget")
        if not isinstance(budget, Mapping):
            context.errors.append("budget must be an object")
            return
        SynthesisReviewPacketBudgetShape(budget).validate(context)

    def _validate_actual_serialized_size(self, context: ValidationContext) -> None:
        budget = self.value.get("budget")
        if not isinstance(budget, Mapping):
            return
        hard = budget.get("hard_bytes")
        if not _is_non_negative_int(hard):
            return
        serialized_bytes = len(canonical_json(self.value).encode("utf-8"))
        if serialized_bytes > int(hard):
            context.errors.append(
                "synthesis_review_packet serialized bytes must not exceed "
                "budget.hard_bytes"
            )

    def _validate_staleness(self, context: ValidationContext) -> None:
        staleness = self.value.get("staleness")
        if not isinstance(staleness, Mapping):
            context.errors.append("staleness must be an object")
            return
        SynthesisReviewPacketStalenessShape(staleness).validate(context)

    def _validate_safety(self, context: ValidationContext) -> None:
        safety = self.value.get("safety")
        if not isinstance(safety, Mapping):
            context.errors.append("safety must be an object")
            return
        SynthesisReviewPacketSafetyShape(safety).validate(context)
        if self.value.get("comments_included") is not safety.get("comments_included"):
            context.errors.append(
                "safety.comments_included must match comments_included"
            )

    def _validate_forbidden_shape(
        self, context: ValidationContext, value: Any, path: str
    ) -> None:
        if isinstance(value, Mapping):
            if self._looks_like_github_request(value):
                context.errors.append(
                    f"{path} is a forbidden GitHub request payload"
                    if path
                    else "GitHub request payload is forbidden"
                )
            if "issues" in value and (
                "pulls" in value or "pull_requests" in value
            ):
                context.errors.append(
                    f"{path} is a forbidden full tracker snapshot"
                    if path
                    else "full tracker snapshot shape is forbidden"
                )
            for key, item in value.items():
                item_path = f"{path}.{key}" if path else str(key)
                if key == "operations":
                    context.errors.append(
                        "operations key is forbidden"
                        if not path
                        else f"{item_path} is forbidden"
                    )
                if key in self.GITHUB_REQUEST_KEYS:
                    context.errors.append(f"{item_path} is forbidden")
                if key in self.COMMENT_KEYS:
                    context.errors.append(f"{item_path} is forbidden")
                if key in self.METADATA_MUTATION_KEYS:
                    context.errors.append(f"{item_path} is forbidden")
                if key in {"body", "state"}:
                    context.errors.append(f"{item_path} is forbidden")
                self._validate_forbidden_shape(context, item, item_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._validate_forbidden_shape(context, item, f"{path}[{index}]")

    def _looks_like_github_request(self, value: Mapping[str, Any]) -> bool:
        keys = set(value)
        return (
            "method" in keys
            and bool(keys & {"path", "url", "endpoint"})
            and bool(keys & {"body", "payload", "json", "data"})
        )


def build_project_plan(
    snapshot: Mapping[str, Any],
    audit: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
    repo_policy: repo_config.RepoPolicy | None = None,
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
    columns = tuple(
        ProjectPlanColumn(id=column_id, name=name, position=index + 1)
        for index, (column_id, name) in enumerate(column_defs)
    )

    pending_items: list[ProjectPlanItem] = []
    for number in sorted(entries):
        issue = issues.get(number)
        if issue is None:
            continue
        entry = entries[number]
        column_id = str(entry.get("implementation_state") or "unknown")
        if column_id not in column_rank:
            column_id = "unknown"
        pending_items.append(
            ProjectPlanItem(
                issue_number=number,
                title=entry.get("title") or issue.get("title"),
                url=entry.get("url") or issue.get("html_url"),
                column_id=column_id,
                direct_dependencies=tuple(
                    _positive_ints(entry.get("direct_dependencies"))
                ),
                parent_epics=tuple(_positive_ints(entry.get("parent_epics"))),
                release_gate=bool(entry.get("release_gate")),
                dependency_impact=int(entry.get("dependency_impact") or 0),
            )
        )
    pending_items.sort(
        key=lambda item: (
            column_rank.get(item.column_id, 999),
            item.issue_number,
        )
    )

    column_positions: dict[str, int] = {}
    items: list[ProjectPlanItem] = []
    for index, item in enumerate(pending_items, start=1):
        column_id = item.column_id
        column_positions[column_id] = column_positions.get(column_id, 0) + 1
        items.append(
            item.with_positions(
                position=index,
                column_position=column_positions[column_id],
            )
        )

    position_by_issue = {item.issue_number: item.position for item in items}
    conflicts: list[ProjectPlanOrderingConflict] = []
    for item in items:
        for dependency in item.direct_dependencies:
            dependency_position = position_by_issue.get(dependency)
            if dependency_position is None or item.position > dependency_position:
                continue
            conflicts.append(
                ProjectPlanOrderingConflict.dependency_inversion(
                    issue_number=item.issue_number,
                    dependency_issue_number=dependency,
                    issue_position=item.position,
                    dependency_position=dependency_position,
                )
            )

    return ProjectPlan(
        repository=repository_name(snapshot),
        generated_at=snapshot.get("generated_at") or "unknown",
        snapshot_digest=snapshot_digest(snapshot),
        audit_digest=audit.get("audit_digest"),
        project=ProjectPolicy.from_policy(policy),
        columns=columns,
        items=tuple(items),
        ordering_conflicts=tuple(conflicts),
    ).to_json()


def validate_project_plan(value: Mapping[str, Any]) -> list[str]:
    """Validate the read-only project-plan envelope and its digest."""

    return ProjectPlanValidator(value).validate()


def _title_tokens(title: Any) -> tuple[str, ...]:
    if not isinstance(title, str):
        return ()
    cleaned = re.sub(
        r"^(?:\[[^]]+\]\s*)?(?:[a-z]+)(?:\([^)]*\))?:\s*",
        "",
        title,
        flags=re.I,
    )
    return tuple(
        sorted(
            {
                token
                for token in re.findall(r"[a-z0-9]+", cleaned.lower())
                if token not in TITLE_STOPWORDS and not token.isdigit()
            }
        )
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _claim_path(value: str) -> str | None:
    candidate = value.split(" ", 1)[0].split(":", 1)[0]
    if "/" not in candidate and "." not in candidate:
        return None
    return candidate


def _entry_paths(entry: Mapping[str, Any]) -> set[str]:
    paths = {
        item
        for item in entry.get("referenced_paths") or []
        if isinstance(item, str)
    }
    for claim in entry.get("source_claims_checked") or []:
        if not isinstance(claim, str):
            continue
        path = _claim_path(claim)
        if path:
            paths.add(path)
    return paths


def _shared_duplicate_evidence(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    evidence: list[str] = []
    details: dict[str, Any] = {}
    left_tokens = set(_title_tokens(left.get("title")))
    right_tokens = set(_title_tokens(right.get("title")))
    shared_tokens = sorted(left_tokens & right_tokens)
    score = _jaccard(left_tokens, right_tokens)
    details["title_similarity"] = round(score, 3)
    if shared_tokens:
        evidence.append("shared title tokens: " + ", ".join(shared_tokens))
        details["shared_title_tokens"] = shared_tokens
    shared_paths = sorted(_entry_paths(left) & _entry_paths(right))
    if shared_paths:
        evidence.append("shared referenced paths: " + ", ".join(shared_paths))
        details["shared_paths"] = shared_paths
    shared_parents = sorted(
        set(_positive_ints(left.get("parent_epics")))
        & set(_positive_ints(right.get("parent_epics")))
    )
    if shared_parents:
        evidence.append(
            "shared parent epics: " + ", ".join(f"#{item}" for item in shared_parents)
        )
        details["shared_parent_epics"] = shared_parents
    if left.get("issue_kind") == right.get("issue_kind") and left.get("issue_kind"):
        evidence.append(f"shared issue kind: {left.get('issue_kind')}")
        details["shared_issue_kind"] = left.get("issue_kind")
    return evidence, details


def _duplicate_signals(
    entries: Mapping[int, Mapping[str, Any]],
    issues: Mapping[int, Mapping[str, Any]],
    open_issue_numbers: set[int],
) -> list[BacklogSynthesisSignal]:
    signals: list[BacklogSynthesisSignal] = []
    numbers = sorted(number for number in entries if number in open_issue_numbers)
    for left_index, left_number in enumerate(numbers):
        for right_number in numbers[left_index + 1 :]:
            left = {
                **entries[left_number],
                "title": issues[left_number].get("title")
                or entries[left_number].get("title"),
            }
            right = {
                **entries[right_number],
                "title": issues[right_number].get("title")
                or entries[right_number].get("title"),
            }
            left_tokens = set(_title_tokens(left.get("title")))
            right_tokens = set(_title_tokens(right.get("title")))
            score = _jaccard(left_tokens, right_tokens)
            evidence, details = _shared_duplicate_evidence(left, right)
            has_context = any(
                key in details
                for key in ("shared_paths", "shared_parent_epics", "shared_issue_kind")
            )
            if score < 0.8 or not has_context:
                continue
            confidence = "high" if score == 1.0 else "medium"
            signals.append(
                BacklogSynthesisSignal(
                    signal_type="likely-duplicate",
                    issue_numbers=(left_number, right_number),
                    confidence=confidence,
                    summary=(
                        f"#{left_number} and #{right_number} have highly similar "
                        "titles and shared audit context"
                    ),
                    evidence=tuple(evidence),
                    details=details,
                )
            )
    return signals


def _explicit_overlap_signals(
    entries: Mapping[int, Mapping[str, Any]],
    open_issue_numbers: set[int],
) -> list[BacklogSynthesisSignal]:
    signals: list[BacklogSynthesisSignal] = []
    seen: set[tuple[int, ...]] = set()
    for number in sorted(entries):
        if number not in open_issue_numbers:
            continue
        conflicts = entries[number].get("overlap_conflicts") or []
        for conflict in conflicts:
            other_numbers: list[int] = []
            if isinstance(conflict, Mapping):
                raw = conflict.get("issue_number") or conflict.get("number")
                if _is_positive_int(raw):
                    other_numbers.append(int(raw))
                conflicting = conflict.get("conflicting_issues")
                if isinstance(conflicting, list):
                    other_numbers.extend(
                        int(item) for item in conflicting if _is_positive_int(item)
                    )
            for other in sorted(set(other_numbers)):
                if other not in open_issue_numbers:
                    continue
                issue_numbers = tuple(sorted({number, other}))
                if issue_numbers in seen:
                    continue
                seen.add(issue_numbers)
                signals.append(
                    BacklogSynthesisSignal(
                        signal_type="explicit-overlap",
                        issue_numbers=issue_numbers,
                        confidence="high",
                        summary=(
                            f"#{issue_numbers[0]} and #{issue_numbers[1]} declare "
                            "overlapping ownership"
                        ),
                        evidence=("readiness audit reported explicit overlap",),
                        details={"source_issue_number": number},
                    )
                )
    return signals


def _split_candidate_signals(
    snapshot: Mapping[str, Any],
    entries: Mapping[int, Mapping[str, Any]],
    open_issue_numbers: set[int],
) -> list[BacklogSynthesisSignal]:
    issues = issue_map(snapshot, include_closed=False)
    signals: list[BacklogSynthesisSignal] = []
    for number in sorted(entries):
        if number not in open_issue_numbers:
            continue
        body = str(issues.get(number, {}).get("body") or "").lower()
        if not any(marker in body for marker in SPLIT_MARKERS):
            continue
        signals.append(
            BacklogSynthesisSignal(
                signal_type="split-candidate",
                issue_numbers=(number,),
                confidence="medium",
                summary=f"#{number} contains language that suggests separable work",
                evidence=("issue body contains a split marker",),
                details={"matched_marker_count": 1},
            )
        )
    return signals


def _dependency_inversion_signals(
    snapshot: Mapping[str, Any], audit: Mapping[str, Any]
) -> list[BacklogSynthesisSignal]:
    plan = build_project_plan(snapshot, audit, policy={"project": {"enabled": False}})
    signals: list[BacklogSynthesisSignal] = []
    for conflict in plan.get("ordering_conflicts") or []:
        if not isinstance(conflict, Mapping):
            continue
        issue_number = conflict.get("issue_number")
        dependency = conflict.get("dependency_issue_number")
        issue_position = conflict.get("issue_position")
        dependency_position = conflict.get("dependency_position")
        if not (_is_positive_int(issue_number) and _is_positive_int(dependency)):
            continue
        signals.append(
            BacklogSynthesisSignal(
                signal_type="dependency-inversion",
                issue_numbers=tuple(sorted({int(issue_number), int(dependency)})),
                confidence="high",
                summary=str(conflict.get("message") or ""),
                evidence=(
                    f"issue position {issue_position} is before dependency position "
                    f"{dependency_position}",
                    f"direct dependency: #{issue_number} depends on #{dependency}",
                ),
                details={
                    "issue_number": int(issue_number),
                    "dependency_issue_number": int(dependency),
                    "issue_position": int(issue_position),
                    "dependency_position": int(dependency_position),
                },
            )
        )
    return signals


def _refs_in_text(value: str) -> list[int]:
    return sorted(
        {
            int(match.group("number"))
            for match in re.finditer(
                r"(?:#|/issues/)(?P<number>[1-9][0-9]*)", value
            )
        }
    )


def _semantic_disposition_signals(
    dispositions: tuple[BacklogIssueDisposition, ...]
) -> list[BacklogSynthesisSignal]:
    signals: list[BacklogSynthesisSignal] = []
    for disposition in dispositions:
        hypothesis = disposition.semantic_hypothesis
        if not hypothesis:
            continue
        issue_numbers = tuple(
            sorted({disposition.issue_number, *_refs_in_text(hypothesis)})
        )
        signals.append(
            BacklogSynthesisSignal(
                signal_type="semantic-disposition",
                issue_numbers=issue_numbers,
                confidence="high" if disposition.evidence else "medium",
                summary=(
                    f"#{disposition.issue_number} semantic disposition hypothesis: "
                    f"{hypothesis}"
                ),
                evidence=disposition.evidence
                or ("semantic disposition hypothesis supplied",),
                details={
                    "issue_number": disposition.issue_number,
                    "mechanical_disposition": disposition.mechanical_disposition,
                    "semantic_hypothesis": hypothesis,
                    "recommended_disposition": disposition.recommended_disposition,
                },
            )
        )
    return signals


def _sort_signals(
    signals: list[BacklogSynthesisSignal],
) -> tuple[BacklogSynthesisSignal, ...]:
    return tuple(
        sorted(
            signals,
            key=lambda item: (
                SIGNAL_SORT_ORDER.get(item.signal_type, 999),
                item.issue_numbers,
                item.summary,
            ),
        )
    )


def build_backlog_synthesis_report(
    snapshot: Mapping[str, Any], audit: Mapping[str, Any]
) -> dict[str, Any]:
    """Build read-only candidate signals for backlog-level synthesis."""

    entries = _issue_entries(audit)
    issues = issue_map(snapshot, include_closed=False)
    open_issue_numbers = set(issues)
    dispositions = tuple(
        BacklogIssueDisposition.from_entry(entries[number])
        for number in sorted(entries)
        if number in issues
    )
    signals: list[BacklogSynthesisSignal] = []
    signals.extend(_semantic_disposition_signals(dispositions))
    signals.extend(_explicit_overlap_signals(entries, open_issue_numbers))
    signals.extend(_duplicate_signals(entries, issues, open_issue_numbers))
    signals.extend(_split_candidate_signals(snapshot, entries, open_issue_numbers))
    signals.extend(_dependency_inversion_signals(snapshot, audit))
    return BacklogSynthesisReport(
        repository=repository_name(snapshot),
        generated_at=snapshot.get("generated_at") or "unknown",
        snapshot_digest=snapshot_digest(snapshot),
        audit_digest=str(audit.get("audit_digest") or ""),
        issue_dispositions=dispositions,
        signals=_sort_signals(signals),
    ).to_json()


def validate_backlog_synthesis_report(value: Mapping[str, Any]) -> list[str]:
    """Validate the read-only backlog-synthesis signal envelope and digest."""

    return BacklogSynthesisReportValidator(value).validate()


def validate_synthesis_review_packet(value: Mapping[str, Any]) -> list[str]:
    """Validate the read-only synthesis-review-packet envelope and digest."""

    return SynthesisReviewPacketValidator(value).validate()


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


@dataclass(frozen=True)
class CoordinatorResultValidator:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
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

    def validate(self) -> list[str]:
        context = ValidationContext()
        context.require_keys(self.value, self.REQUIRED_KEYS)
        if self.value.get("schema_version") != COORDINATOR_SCHEMA_VERSION:
            context.errors.append("unsupported schema_version")
        if self.value.get("mode") not in {"audit", "implement"}:
            context.errors.append("invalid mode")
        context.require_repository(self.value.get("repository"))
        context.require_string(self.value.get("generated_at"), name="generated_at")
        for key in ("snapshot_digest", "audit_digest", "coordinator_digest"):
            context.require_digest(self.value.get(key), name=key)
        context.require_positive_int_or_null(
            self.value.get("selected_issue"), name="selected_issue"
        )
        self._validate_selected_issue_fields(context)
        self._validate_collections(context)
        self._validate_candidate_metadata(context)
        actual_digest = sha256_json(
            {
                key: item
                for key, item in self.value.items()
                if key != "coordinator_digest"
            }
        )
        if self.value.get("coordinator_digest") != actual_digest:
            context.errors.append("coordinator_digest mismatch")
        return context.errors

    def _validate_selected_issue_fields(self, context: ValidationContext) -> None:
        for key in ("issue_contract_digest", "governance_state", "implementation_state"):
            context.require_string_or_null(self.value.get(key), name=key)
        context.require_string(
            self.value.get("selection_reason"), name="selection_reason"
        )
        for key in ("suggested_branch", "suggested_next_command"):
            context.require_string_or_null(self.value.get(key), name=key)
        selected = self.value.get("selected_issue")
        if selected is None:
            for key in (
                "issue_contract_digest",
                "governance_state",
                "implementation_state",
                "suggested_branch",
                "suggested_next_command",
            ):
                if self.value.get(key) is not None:
                    context.errors.append(f"{key} must be null for an empty frontier")
        elif self.value.get("issue_contract_digest") is None:
            context.errors.append(
                "issue_contract_digest is required for a selected issue"
            )

    def _validate_collections(self, context: ValidationContext) -> None:
        for key in ("parent_epics", "direct_dependencies"):
            context.require_positive_int_list(self.value.get(key), name=key)
        for key in (
            "blockers",
            "required_decisions",
            "required_external_evidence",
            "referenced_paths",
        ):
            context.require_string_list(self.value.get(key), name=key)

    def _validate_candidate_metadata(self, context: ValidationContext) -> None:
        for key in ("candidate_count", "rejected_count"):
            context.require_non_negative_int(self.value.get(key), name=key)
        context.require_int_or_null(self.value.get("score"), name="score")
        components = self.value.get("score_components")
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
            context.errors.append("score_components must map strings to integers")
        preview = self.value.get("rejected_preview")
        if preview is not None and (
            not isinstance(preview, list) or len(preview) > 20
        ):
            context.errors.append("rejected_preview must be an array of at most 20 items")


def validate_coordinator_result(value: Mapping[str, Any]) -> list[str]:
    return CoordinatorResultValidator(value).validate()


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
    repo_policy: repo_config.RepoPolicy | None = None,
    branch_state: Mapping[str, Any] | None = None,
    progress_context: str | None = None,
) -> dict[str, Any]:
    active_policy = repo_policy or repo_config.load_repo_policy()
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
        "required_verification_commands": list(
            active_policy.worker_packet.required_verification_commands
        ),
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


@dataclass(frozen=True)
class WorkerPacketValidator:
    value: Mapping[str, Any]

    REQUIRED_KEYS: ClassVar[set[str]] = {
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

    def validate(self) -> list[str]:
        context = ValidationContext()
        context.require_keys(self.value, self.REQUIRED_KEYS)
        if self.value.get("schema_version") != WORKER_PACKET_SCHEMA_VERSION:
            context.errors.append("unsupported schema_version")
        context.require_repository(self.value.get("repository"))
        context.require_string(self.value.get("generated_at"), name="generated_at")
        for key in ("snapshot_digest", "audit_digest", "packet_digest"):
            context.require_digest(self.value.get(key), name=key)
        self._validate_issue(context)
        self._validate_contract_and_sections(context)
        self._validate_arrays(context)
        self._validate_context_objects(context)
        self._validate_progress_context(context)
        actual_digest = sha256_json(
            {key: item for key, item in self.value.items() if key != "packet_digest"}
        )
        if self.value.get("packet_digest") != actual_digest:
            context.errors.append("packet_digest mismatch")
        return context.errors

    def _validate_issue(self, context: ValidationContext) -> None:
        issue = self.value.get("issue")
        if not isinstance(issue, Mapping):
            context.errors.append("issue must be an object")
            return
        context.require_positive_int(issue.get("number"), name="issue.number")
        body = issue.get("body")
        if not isinstance(body, str) or len(body) > MAX_WORKER_ISSUE_BODY_CHARS:
            context.errors.append("issue.body exceeds the worker-packet bound")
        context.require_bool(
            issue.get("body_truncated"), name="issue.body_truncated"
        )

    def _validate_contract_and_sections(self, context: ValidationContext) -> None:
        if not isinstance(self.value.get("contract"), Mapping):
            context.errors.append("contract must be an object")
        for key in ("acceptance_criteria", "non_goals"):
            context.require_string_or_null(self.value.get(key), name=key)

    def _validate_arrays(self, context: ValidationContext) -> None:
        for key in (
            "dependencies",
            "parent_epics",
            "referenced_paths",
            "likely_entry_points",
            "required_verification_commands",
        ):
            if not isinstance(self.value.get(key), list):
                context.errors.append(f"{key} must be an array")

    def _validate_context_objects(self, context: ValidationContext) -> None:
        if not isinstance(self.value.get("uncertainty"), Mapping):
            context.errors.append("uncertainty must be an object")
        if not isinstance(self.value.get("branch_worktree_state"), Mapping):
            context.errors.append("branch_worktree_state must be an object")

    def _validate_progress_context(self, context: ValidationContext) -> None:
        progress = self.value.get("historical_progress_context")
        if progress is not None and (
            not isinstance(progress, str) or len(progress) > MAX_PROGRESS_CONTEXT_CHARS
        ):
            context.errors.append(
                "historical_progress_context exceeds the worker-packet bound"
            )
        context.require_bool(
            self.value.get("historical_progress_truncated"),
            name="historical_progress_truncated",
        )
        if self.value.get("historical_progress_is_authoritative") is not False:
            context.errors.append("historical progress must be marked non-authoritative")


def validate_worker_packet(value: Mapping[str, Any]) -> list[str]:
    """Validate the bounded worker-packet envelope and its digest."""

    return WorkerPacketValidator(value).validate()
