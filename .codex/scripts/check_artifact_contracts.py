#!/usr/bin/env python3
"""Check stable artifact contracts for schema/doc/validator drift."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.triage import frontier, repo_config


CHECK_NAME = "artifact-contracts"
MANIFEST_PATH = Path(".codex/artifact-contracts-v1.json")
SCHEMA_VERSION = 1
ACTIVE_STATUS = "active"
TERMINAL_STATUSES = frozenset({"active", "pending", "excluded"})
INVARIANT_OWNERS = frozenset(
    {
        "json_schema",
        "python_validator",
        "codex_quality_checker",
        "shared_classifier",
        "deliberate_python_only",
        "pending",
    }
)
KNOWN_SCHEMA_VERSION_ARTIFACTS = frozenset(
    {
        "approval",
        "backlog-review-validation",
        "backlog-review-verdict",
        "backlog-synthesis",
        "codex-quality-receipt",
        "coordinator-result",
        "operation",
        "project-plan",
        "readiness-audit",
        "retrieval-governance-spike-output",
        "snapshot",
        "synthesis-review-packet",
        "triage-plan",
        "worker-packet",
    }
)


@dataclass(frozen=True)
class ArtifactContractFinding:
    code: str
    message: str
    repair_guidance: str
    severity: str = "error"
    artifact: str | None = None
    path: str | None = None

    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.artifact or "",
            self.code,
            self.path or "",
            self.message,
        )

    def to_json(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "repair_guidance": self.repair_guidance,
        }
        if self.artifact is not None:
            result["artifact"] = self.artifact
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class ArtifactContractResult:
    checked_files: tuple[str, ...]
    findings: tuple[ArtifactContractFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    def to_json(self) -> dict[str, object]:
        return {
            "name": CHECK_NAME,
            "status": "passed" if self.passed else "failed",
            "checked_files": list(self.checked_files),
            "findings": [finding.to_json() for finding in self.findings],
        }


@dataclass(frozen=True)
class ArtifactContract:
    artifact: str
    status: str
    reason: str | None
    schema_version: int | None
    human_doc: str | None
    machine_schema: str | None
    validator: str | None
    paired_validator: str | None
    digest_field: str | None
    fixture: str | None
    required_fields: tuple[str, ...]
    forbidden_shapes: tuple[str, ...]
    authoritative_recomputed_fields: tuple[str, ...]
    invariant_enforcement: Mapping[str, str]

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], *, index: int
    ) -> tuple[ArtifactContract | None, tuple[ArtifactContractFinding, ...]]:
        findings: list[ArtifactContractFinding] = []
        artifact = value.get("artifact")
        status = value.get("status")
        if not isinstance(artifact, str) or not artifact:
            findings.append(
                _finding(
                    "manifest-artifact-name",
                    f"artifacts[{index}].artifact must be a non-empty string",
                    "Give every manifest entry a stable artifact name.",
                )
            )
            artifact = f"<invalid-{index}>"
        if status not in TERMINAL_STATUSES:
            findings.append(
                _finding(
                    "manifest-artifact-status",
                    f"{artifact} has unsupported status {status!r}",
                    "Use active, pending, or excluded.",
                    artifact=artifact,
                )
            )
            status = "pending"

        reason = value.get("reason")
        if status in {"pending", "excluded"} and not (
            isinstance(reason, str) and reason.strip()
        ):
            findings.append(
                _finding(
                    "manifest-status-reason",
                    f"{artifact} must record a reason for status {status}",
                    "Add a reason explaining why the artifact is not active.",
                    artifact=artifact,
                )
            )

        required_fields = _string_tuple(value.get("required_fields"))
        forbidden_shapes = _string_tuple(value.get("forbidden_shapes"))
        authoritative = _string_tuple(value.get("authoritative_recomputed_fields"))
        enforcement = value.get("invariant_enforcement")
        if enforcement is None:
            enforcement_map: dict[str, str] = {}
        elif isinstance(enforcement, Mapping):
            enforcement_map = {
                str(key): str(owner) for key, owner in enforcement.items()
            }
            for invariant, owner in enforcement_map.items():
                if owner not in INVARIANT_OWNERS:
                    findings.append(
                        _finding(
                            "manifest-invariant-owner",
                            f"{artifact}.{invariant} uses unsupported owner {owner!r}",
                            "Use one of the allowed invariant owner values.",
                            artifact=artifact,
                        )
                    )
        else:
            findings.append(
                _finding(
                    "manifest-invariant-map",
                    f"{artifact}.invariant_enforcement must be an object",
                    "Use an object mapping invariant names to owner strings.",
                    artifact=artifact,
                )
            )
            enforcement_map = {}

        entry = cls(
            artifact=str(artifact),
            status=str(status),
            reason=reason if isinstance(reason, str) else None,
            schema_version=value.get("schema_version")
            if isinstance(value.get("schema_version"), int)
            else None,
            human_doc=value.get("human_doc") if isinstance(value.get("human_doc"), str) else None,
            machine_schema=value.get("machine_schema")
            if isinstance(value.get("machine_schema"), str)
            else None,
            validator=value.get("validator") if isinstance(value.get("validator"), str) else None,
            paired_validator=value.get("paired_validator")
            if isinstance(value.get("paired_validator"), str)
            else None,
            digest_field=value.get("digest_field")
            if isinstance(value.get("digest_field"), str)
            else None,
            fixture=value.get("fixture") if isinstance(value.get("fixture"), str) else None,
            required_fields=required_fields,
            forbidden_shapes=forbidden_shapes,
            authoritative_recomputed_fields=authoritative,
            invariant_enforcement=enforcement_map,
        )
        findings.extend(entry._shape_findings())
        return entry, tuple(findings)

    def _shape_findings(self) -> list[ArtifactContractFinding]:
        findings: list[ArtifactContractFinding] = []
        if self.status != ACTIVE_STATUS:
            return findings
        required = {
            "schema_version": self.schema_version,
            "human_doc": self.human_doc,
            "machine_schema": self.machine_schema,
            "validator": self.validator,
            "digest_field": self.digest_field,
            "fixture": self.fixture,
        }
        for field, value in required.items():
            if value is None or value == () or value == "":
                findings.append(
                    _finding(
                        "manifest-active-field",
                        f"{self.artifact} active entry is missing {field}",
                        "Add the active artifact field to the manifest.",
                        artifact=self.artifact,
                    )
                )
        if not self.required_fields:
            findings.append(
                _finding(
                    "manifest-required-fields",
                    f"{self.artifact} has no required_fields list",
                    "Record the artifact's stable top-level required fields.",
                    artifact=self.artifact,
                )
            )
        if not self.invariant_enforcement:
            findings.append(
                _finding(
                    "manifest-invariants",
                    f"{self.artifact} has no invariant_enforcement map",
                    "Record each invariant and its enforcement owner.",
                    artifact=self.artifact,
                )
            )
        return findings


def _finding(
    code: str,
    message: str,
    repair_guidance: str,
    *,
    artifact: str | None = None,
    path: str | None = None,
    severity: str = "error",
) -> ArtifactContractFinding:
    return ArtifactContractFinding(
        code=code,
        message=message,
        repair_guidance=repair_guidance,
        severity=severity,
        artifact=artifact,
        path=path,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_manifest(
    root: Path, manifest_path: Path
) -> tuple[tuple[ArtifactContract, ...], list[ArtifactContractFinding]]:
    findings: list[ArtifactContractFinding] = []
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    if not path.exists():
        return (), [
            _finding(
                "manifest-missing",
                f"artifact contract manifest is missing: {_relpath(path, root)}",
                "Create the manifest or pass the correct --manifest path.",
                path=_relpath(path, root),
            )
        ]
    try:
        raw = json.loads(path.read_text(encoding="ascii"))
    except UnicodeDecodeError:
        return (), [
            _finding(
                "manifest-non-ascii",
                "artifact contract manifest must be ASCII",
                "Rewrite the manifest with ASCII-only JSON.",
                path=_relpath(path, root),
            )
        ]
    except json.JSONDecodeError as exc:
        return (), [
            _finding(
                "manifest-json",
                f"artifact contract manifest is invalid JSON: {exc}",
                "Repair the JSON manifest.",
                path=_relpath(path, root),
            )
        ]
    if not isinstance(raw, Mapping):
        return (), [
            _finding(
                "manifest-object",
                "artifact contract manifest must be a JSON object",
                "Use a top-level JSON object with schema_version and artifacts.",
                path=_relpath(path, root),
            )
        ]
    if raw.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            _finding(
                "manifest-schema-version",
                "artifact contract manifest schema_version must be 1",
                "Set schema_version to 1.",
                path=_relpath(path, root),
            )
        )
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, list):
        findings.append(
            _finding(
                "manifest-artifacts",
                "artifact contract manifest must include artifacts array",
                "Add an artifacts array to the manifest.",
                path=_relpath(path, root),
            )
        )
        return (), findings
    entries: list[ArtifactContract] = []
    seen: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            findings.append(
                _finding(
                    "manifest-artifact-object",
                    f"artifacts[{index}] must be an object",
                    "Make every artifact entry a JSON object.",
                )
            )
            continue
        entry, entry_findings = ArtifactContract.from_mapping(item, index=index)
        findings.extend(entry_findings)
        if entry is None:
            continue
        if entry.artifact in seen:
            findings.append(
                _finding(
                    "manifest-duplicate-artifact",
                    f"duplicate artifact entry: {entry.artifact}",
                    "Keep exactly one manifest entry per artifact.",
                    artifact=entry.artifact,
                )
            )
        seen.add(entry.artifact)
        entries.append(entry)
    return tuple(sorted(entries, key=lambda item: item.artifact)), findings


def _load_callable(import_path: str) -> Callable[..., Any]:
    module_name, _, function_name = import_path.partition(":")
    if not module_name or not function_name:
        raise ValueError("validator import path must be module:function")
    module = importlib.import_module(module_name)
    value = getattr(module, function_name)
    if not callable(value):
        raise TypeError(f"{import_path} is not callable")
    return value


def _callable_source_path(value: Callable[..., Any], root: Path) -> str | None:
    source = inspect.getsourcefile(value)
    if source is None:
        return None
    path = Path(source)
    return _relpath(path, root)


def _canonical_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold())


def _schema_validation_errors(schema: Mapping[str, Any], value: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    return sorted(error.message for error in validator.iter_errors(value))


def _sign_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    verdict["backlog_review_verdict_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in verdict.items()
            if key != "backlog_review_verdict_digest"
        }
    )
    return verdict


def _finalize_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet["synthesis_review_packet_digest"] = "0" * 64
    for _ in range(10):
        budget = dict(packet["budget"])
        serialized_bytes = len(frontier.canonical_json(packet).encode("utf-8"))
        budget["serialized_bytes"] = serialized_bytes
        budget["estimated_tokens"] = (serialized_bytes + 3) // 4
        warnings: list[str] = []
        if serialized_bytes > int(budget.get("target_bytes") or 0):
            warnings.append(frontier.SERIALIZED_BYTES_EXCEEDS_TARGET_BYTES)
        if int(budget["estimated_tokens"]) > int(
            budget.get("target_estimated_tokens") or 0
        ):
            warnings.append(frontier.ESTIMATED_TOKENS_EXCEEDS_TARGET)
        budget["budget_warnings"] = warnings
        packet["budget"] = budget
        digest = frontier.sha256_json(
            {
                key: value
                for key, value in packet.items()
                if key != "synthesis_review_packet_digest"
            }
        )
        if (
            packet.get("synthesis_review_packet_digest") == digest
            and serialized_bytes == len(frontier.canonical_json(packet).encode("utf-8"))
        ):
            return packet
        packet["synthesis_review_packet_digest"] = digest
    return packet


def _snapshot(*issues: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "snapshot_digest": "a" * 64,
        "repository": "dckallos/dbt-diagnostics",
        "issues": list(issues),
        "pulls": [],
    }


def _issue(number: int, *, title: str, body: str = "") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "labels": ["test"],
        "state": "open",
        "body": body,
        "html_url": f"https://github.com/dckallos/dbt-diagnostics/issues/{number}",
    }


def _audit(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_digest": "a" * 64,
        "audit_digest": "b" * 64,
        "issues": list(entries),
    }


def _entry(number: int, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "issue_number": number,
        "title": f"fix: issue {number}",
        "issue_kind": "feature_enhancement",
        "contract_id": "dbt-diagnostics.issue-contract.v1",
        "contract_version": "1.0",
        "body_digest": f"body-{number}",
        "governance_state": "conformant",
        "contract_accepted": True,
        "implementation_state": "ready",
        "release_gate": False,
        "dependency_impact": 0,
        "direct_dependencies": [],
        "dependency_merge_evidence": True,
        "dependency_cycles": [],
        "required_decisions": [],
        "required_external_evidence": [],
        "missing_repository_paths": [],
        "active_pr_conflicts": [],
        "overlap_conflicts": [],
        "blockers": [],
        "parent_epics": [93],
        "referenced_paths": ["scripts/triage/frontier.py"],
        "source_claims_checked": [],
        "semantic_review_notes": [],
        "recommended_disposition": "implement",
        "semantic_disposition_hypothesis": None,
        "semantic_disposition_evidence": [],
    }
    value.update(extra)
    return value


def _duplicate_sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    snap = _snapshot(
        _issue(1, title="feat: deterministic backlog synthesis"),
        _issue(2, title="feat: deterministic backlog synthesis"),
    )
    audit = _audit(_entry(1), _entry(2))
    report = frontier.build_backlog_synthesis_report(snap, audit)
    return snap, audit, report


def _fixture_project_plan() -> dict[str, Any]:
    return frontier.build_project_plan(
        _snapshot(_issue(1, title="feat: project plan")),
        _audit(_entry(1)),
        policy={"project": {"enabled": False}},
    )


def _fixture_backlog_synthesis() -> dict[str, Any]:
    _snap, _audit_value, report = _duplicate_sources()
    return report


def _fixture_synthesis_review_packet() -> dict[str, Any]:
    snap, audit, report = _duplicate_sources()
    return frontier.build_synthesis_review_packet(
        snap,
        audit,
        report,
        evaluated_at="2026-06-24T01:00:00Z",
    )


def _fixture_backlog_review_verdict() -> dict[str, Any]:
    packet = _fixture_synthesis_review_packet()
    source_artifacts = packet["source_artifacts"]
    verdict = {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "generated_at": "2026-06-24T01:30:00Z",
        "source_packet_digest": packet["synthesis_review_packet_digest"],
        "source_snapshot_digest": source_artifacts["snapshot_digest"],
        "source_audit_digest": source_artifacts["audit_digest"],
        "source_backlog_synthesis_digest": source_artifacts[
            "backlog_synthesis_digest"
        ],
        "packet_reviewability": {
            "source_packet_digest": packet["synthesis_review_packet_digest"],
            "source_snapshot_digest": source_artifacts["snapshot_digest"],
            "source_audit_digest": source_artifacts["audit_digest"],
            "source_backlog_synthesis_digest": source_artifacts[
                "backlog_synthesis_digest"
            ],
            "freshness_status": packet["staleness"]["freshness_status"],
            "freshness_warnings": packet["staleness"]["freshness_warnings"],
            "packet_stale": packet["staleness"]["stale"],
            "llm_review_allowed": packet["staleness"]["llm_review_allowed"],
            "invalid_lineage": False,
        },
        "verdicts": [
            {
                "verdict_id": "verdict-likely-duplicate-001-002",
                "verdict_type": "likely-duplicate",
                "issue_numbers": [1, 2],
                "recommendation": "Maintainer should review #1 and #2.",
                "confidence": "medium",
                "evidence_refs": ["evidence-001"],
                "near_miss_refs": [],
                "omission_refs": ["issue-comments-not-collected"],
                "rationale": "The bounded packet includes duplicate evidence.",
                "risks": ["The issues may still be separable."],
                "required_maintainer_checks": [
                    "Confirm the advisory verdict before tracker action."
                ],
            }
        ],
        "future_apply_recommendations": [],
        "uncertainty": [],
        "required_maintainer_checks": [],
        "safety": {
            "read_only": True,
            "github_api_calls": False,
            "github_mutations": False,
            "contains_executable_operations": False,
            "contains_github_request_payloads": False,
            "contains_issue_write_payloads": False,
            "future_apply_recommendations_are_advisory": True,
            "maintainer_decides": True,
            "llm_verdicts_are_advisory": True,
        },
    }
    return _sign_verdict(verdict)


FIXTURES: Mapping[str, Callable[[], dict[str, Any]]] = {
    "project-plan": _fixture_project_plan,
    "backlog-synthesis": _fixture_backlog_synthesis,
    "synthesis-review-packet": _fixture_synthesis_review_packet,
    "backlog-review-verdict": _fixture_backlog_review_verdict,
}


def _fixture_for(artifact: str) -> dict[str, Any]:
    return FIXTURES[artifact]()


def _validator_errors(entry: ArtifactContract, value: Mapping[str, Any]) -> list[str]:
    assert entry.validator is not None
    validator = _load_callable(entry.validator)
    return list(validator(value))


def _paired_validator_errors(
    entry: ArtifactContract, value: Mapping[str, Any], packet: Mapping[str, Any]
) -> list[str]:
    assert entry.paired_validator is not None
    validator = _load_callable(entry.paired_validator)
    return list(validator(value, packet))


def _tamper_digest(entry: ArtifactContract, value: dict[str, Any]) -> dict[str, Any]:
    assert entry.digest_field is not None
    tampered = deepcopy(value)
    tampered[entry.digest_field] = "0" * 64
    return tampered


def _unsafe_shape(entry: ArtifactContract, value: dict[str, Any]) -> dict[str, Any]:
    unsafe = deepcopy(value)
    if entry.artifact == "project-plan":
        if unsafe.get("items"):
            unsafe["items"][0]["body"] = "full issue body"
            unsafe["items"][0]["state"] = "closed"
        else:
            unsafe["operations"] = []
    elif entry.artifact == "backlog-review-verdict":
        unsafe["future_apply_recommendations"] = [
            {
                "recommendation_id": "future-apply-001",
                "summary": "unsafe",
                "rationale": "unsafe",
                "advisory_only": True,
                "request_method": "PATCH",
            }
        ]
    else:
        unsafe["safety"]["github_request"] = {"method": "PATCH", "path": "/issues"}
    return unsafe


def _with_packet_staleness(
    packet: Mapping[str, Any],
    *,
    evaluated_at: str,
    max_age_hours: int = frontier.DEFAULT_SYNTHESIS_REVIEW_MAX_AGE_HOURS,
) -> dict[str, Any]:
    result = deepcopy(packet)
    staleness = frontier.build_synthesis_review_packet_staleness(
        source_generated_at=result["source_generated_at"],
        evaluated_at=evaluated_at,
        max_age_hours=max_age_hours,
    )
    result["generated_at"] = staleness.evaluated_at
    result["staleness"] = staleness.to_json()
    return _finalize_packet(result)


def _verdict_for_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    verdict = _fixture_backlog_review_verdict()
    source_artifacts = packet["source_artifacts"]
    verdict["source_packet_digest"] = packet["synthesis_review_packet_digest"]
    verdict["source_snapshot_digest"] = source_artifacts["snapshot_digest"]
    verdict["source_audit_digest"] = source_artifacts["audit_digest"]
    verdict["source_backlog_synthesis_digest"] = source_artifacts[
        "backlog_synthesis_digest"
    ]
    verdict["packet_reviewability"] = {
        "source_packet_digest": packet["synthesis_review_packet_digest"],
        "source_snapshot_digest": source_artifacts["snapshot_digest"],
        "source_audit_digest": source_artifacts["audit_digest"],
        "source_backlog_synthesis_digest": source_artifacts[
            "backlog_synthesis_digest"
        ],
        "freshness_status": packet["staleness"]["freshness_status"],
        "freshness_warnings": packet["staleness"]["freshness_warnings"],
        "packet_stale": packet["staleness"]["stale"],
        "llm_review_allowed": packet["staleness"]["llm_review_allowed"],
        "invalid_lineage": False,
    }
    if packet["staleness"]["freshness_status"] == "warning":
        verdict["uncertainty"] = [
            {
                "code": frontier.SOURCE_AGE_EXCEEDS_WARNING_AGE,
                "rationale": "Packet freshness warning is visible.",
            }
        ]
    else:
        verdict["uncertainty"] = []
    return _sign_verdict(verdict)


def _check_active_entry(
    entry: ArtifactContract, *, root: Path, checked_files: set[str]
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    assert entry.human_doc is not None
    assert entry.machine_schema is not None
    assert entry.validator is not None
    doc_path = root / entry.human_doc
    schema_path = root / entry.machine_schema
    checked_files.update({entry.human_doc, entry.machine_schema})
    doc_text = ""
    schema: Mapping[str, Any] = {}
    validator: Callable[..., Any] | None = None

    if not doc_path.exists():
        findings.append(
            _finding(
                "human-doc-missing",
                f"{entry.artifact} human doc is missing",
                "Restore the manifest human_doc path or update the manifest.",
                artifact=entry.artifact,
                path=entry.human_doc,
            )
        )
    else:
        try:
            doc_text = doc_path.read_text(encoding="ascii")
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    "human-doc-non-ascii",
                    f"{entry.artifact} human doc must be ASCII",
                    "Rewrite the doc with ASCII-only text.",
                    artifact=entry.artifact,
                    path=entry.human_doc,
                )
            )

    if not schema_path.exists():
        findings.append(
            _finding(
                "machine-schema-missing",
                f"{entry.artifact} machine schema is missing",
                "Restore the manifest machine_schema path or update the manifest.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="ascii"))
            Draft202012Validator.check_schema(schema)
        except UnicodeDecodeError:
            findings.append(
                _finding(
                    "machine-schema-non-ascii",
                    f"{entry.artifact} machine schema must be ASCII",
                    "Rewrite the schema with ASCII-only JSON.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )
        except json.JSONDecodeError as exc:
            findings.append(
                _finding(
                    "machine-schema-json",
                    f"{entry.artifact} machine schema is invalid JSON: {exc}",
                    "Repair the machine schema JSON.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )
        except SchemaError as exc:
            findings.append(
                _finding(
                    "machine-schema-invalid",
                    f"{entry.artifact} machine schema is not valid JSON Schema: {exc.message}",
                    "Repair the Draft 2020-12 machine schema.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )

    try:
        validator = _load_callable(entry.validator)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        findings.append(
            _finding(
                "validator-import",
                f"{entry.artifact} validator import failed: {exc}",
                "Fix the manifest validator path or restore the validator.",
                artifact=entry.artifact,
            )
        )
    else:
        source = _callable_source_path(validator, root)
        if source:
            checked_files.add(source)

    if entry.paired_validator:
        try:
            paired = _load_callable(entry.paired_validator)
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            findings.append(
                _finding(
                    "paired-validator-import",
                    f"{entry.artifact} paired validator import failed: {exc}",
                    "Fix the manifest paired_validator path or restore the validator.",
                    artifact=entry.artifact,
                )
            )
        else:
            source = _callable_source_path(paired, root)
            if source:
                checked_files.add(source)

    if doc_text:
        findings.extend(_check_doc(entry, doc_text))
    if schema:
        findings.extend(_check_schema(entry, schema))
    if schema and validator is not None:
        findings.extend(_check_fixture(entry, schema))
    return findings


def _check_doc(entry: ArtifactContract, doc_text: str) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    text = _canonical_text(doc_text)
    expected = (
        entry.machine_schema,
        entry.digest_field,
        entry.validator.split(":", 1)[1] if entry.validator else None,
    )
    if entry.paired_validator:
        expected = expected + (entry.paired_validator.split(":", 1)[1],)
    for value in expected:
        if value and _canonical_text(value) not in text:
            findings.append(
                _finding(
                    "human-doc-drift",
                    f"{entry.artifact} doc does not mention {value}",
                    "Update the schema doc so it names the manifest contract surface.",
                    artifact=entry.artifact,
                    path=entry.human_doc,
                )
            )
    for word in ("advisory", "mutation"):
        if word not in text:
            findings.append(
                _finding(
                    "human-doc-boundary",
                    f"{entry.artifact} doc does not mention {word}",
                    "Document the advisory/read-only no-mutation boundary.",
                    artifact=entry.artifact,
                    path=entry.human_doc,
                )
            )
    if "read-only" not in text and "read only" not in text:
        findings.append(
            _finding(
                "human-doc-read-only",
                f"{entry.artifact} doc does not mention read-only behavior",
                "Document that the artifact is read-only.",
                artifact=entry.artifact,
                path=entry.human_doc,
            )
        )
    return findings


def _check_schema(
    entry: ArtifactContract, schema: Mapping[str, Any]
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    required = tuple(schema.get("required") or ())
    if tuple(entry.required_fields) != required:
        findings.append(
            _finding(
                "schema-required-fields",
                f"{entry.artifact} manifest required_fields do not match schema required",
                "Update the manifest and machine schema required fields together.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
    if entry.digest_field and entry.digest_field not in required:
        findings.append(
            _finding(
                "schema-digest-required",
                f"{entry.artifact} schema does not require {entry.digest_field}",
                "Require the digest field in the machine schema.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        findings.append(
            _finding(
                "schema-properties",
                f"{entry.artifact} schema must define properties",
                "Add a properties object to the machine schema.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
        return findings
    schema_version = properties.get("schema_version")
    if not (
        isinstance(schema_version, Mapping)
        and schema_version.get("const") == entry.schema_version
    ):
        findings.append(
            _finding(
                "schema-version-const",
                f"{entry.artifact} schema_version const is missing or wrong",
                "Set properties.schema_version.const to the manifest schema_version.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
    if entry.artifact == "synthesis-review-packet":
        staleness = properties.get("staleness")
        staleness_required = (
            tuple(staleness.get("required") or ())
            if isinstance(staleness, Mapping)
            else ()
        )
        expected = (
            "source_generated_at",
            "evaluated_at",
            "source_age_hours",
            "warning_age_hours",
            "max_age_hours",
            "freshness_status",
            "freshness_warnings",
            "stale",
            "llm_review_allowed",
        )
        if not set(expected).issubset(set(staleness_required)):
            findings.append(
                _finding(
                    "schema-freshness-fields",
                    "synthesis-review-packet schema is missing required freshness fields",
                    "Require all #96 staleness fields in the machine schema.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )
    return findings


def _check_fixture(
    entry: ArtifactContract, schema: Mapping[str, Any]
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    value = _fixture_for(entry.artifact)
    schema_errors = _schema_validation_errors(schema, value)
    if schema_errors:
        findings.append(
            _finding(
                "fixture-schema-invalid",
                f"{entry.artifact} minimal fixture fails machine schema: {schema_errors[0]}",
                "Align the fixture, schema, or manifest active entry.",
                artifact=entry.artifact,
                path=entry.machine_schema,
            )
        )
    validator_errors = _validator_errors(entry, value)
    if validator_errors:
        findings.append(
            _finding(
                "fixture-validator-invalid",
                f"{entry.artifact} minimal fixture fails Python validator: {validator_errors[0]}",
                "Align the fixture, validator, or manifest active entry.",
                artifact=entry.artifact,
            )
        )
        return findings
    findings.extend(_check_negative_schema_cases(entry, schema, value))
    findings.extend(_check_negative_validator_cases(entry, value))
    if entry.artifact == "synthesis-review-packet":
        findings.extend(_check_packet_semantics(entry))
    if entry.artifact == "backlog-synthesis":
        findings.extend(_check_diagnostic_semantics(entry))
    if entry.artifact == "backlog-review-verdict":
        findings.extend(_check_verdict_semantics(entry))
    return findings


def _check_negative_schema_cases(
    entry: ArtifactContract, schema: Mapping[str, Any], value: Mapping[str, Any]
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    if entry.invariant_enforcement.get("schema_required_fields") == "json_schema":
        missing = deepcopy(value)
        removed = entry.required_fields[0]
        missing.pop(removed, None)
        if not _schema_validation_errors(schema, missing):
            findings.append(
                _finding(
                    "schema-required-not-enforced",
                    f"{entry.artifact} schema accepts fixture missing {removed}",
                    "Ensure required fields are enforced by the machine schema.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )
    if entry.invariant_enforcement.get("top_level_operations") == "json_schema":
        unsafe = deepcopy(value)
        unsafe["operations"] = []
        if not _schema_validation_errors(schema, unsafe):
            findings.append(
                _finding(
                    "schema-operations-not-forbidden",
                    f"{entry.artifact} schema accepts top-level operations",
                    "Forbid top-level operations in the machine schema.",
                    artifact=entry.artifact,
                    path=entry.machine_schema,
                )
            )
    return findings


def _check_negative_validator_cases(
    entry: ArtifactContract, value: Mapping[str, Any]
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    tampered = _tamper_digest(entry, dict(value))
    if not _validator_errors(entry, tampered):
        findings.append(
            _finding(
                "validator-digest-not-enforced",
                f"{entry.artifact} validator accepts digest tampering",
                "Recompute and enforce the canonical digest in the Python validator.",
                artifact=entry.artifact,
            )
        )
    unsafe = deepcopy(value)
    unsafe["operations"] = []
    if not _validator_errors(entry, unsafe):
        findings.append(
            _finding(
                "validator-operations-not-forbidden",
                f"{entry.artifact} validator accepts top-level operations",
                "Reject operation-shaped payloads in the Python validator.",
                artifact=entry.artifact,
            )
        )
    nested = _unsafe_shape(entry, dict(value))
    if not _validator_errors(entry, nested):
        findings.append(
            _finding(
                "validator-forbidden-shape-not-enforced",
                f"{entry.artifact} validator accepts a forbidden nested shape",
                "Reject nested write-shaped payloads through existing validators.",
                artifact=entry.artifact,
            )
        )
    if entry.invariant_enforcement.get("mutation_command_string") == "shared_classifier":
        reason = repo_config.governance_mutation_command_reason(
            "python scripts/triage/triage.py apply --execute"
        )
        if reason is None:
            findings.append(
                _finding(
                    "shared-classifier-mutation-command",
                    f"{entry.artifact} shared classifier accepts apply --execute",
                    "Route mutation command strings through the shared classifier.",
                    artifact=entry.artifact,
                )
            )
    return findings


def _check_packet_semantics(entry: ArtifactContract) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    packet = _fixture_synthesis_review_packet()
    warning = _with_packet_staleness(packet, evaluated_at="2026-06-25T01:00:00Z")
    if _validator_errors(entry, warning):
        findings.append(
            _finding(
                "freshness-warning-rejected",
                "warning-only synthesis-review-packet must remain reviewable",
                "Keep warning-only freshness as a visible warning, not hard stale.",
                artifact=entry.artifact,
            )
        )
    stale = _with_packet_staleness(packet, evaluated_at="2026-07-02T01:00:01Z")
    if not _validator_errors(entry, stale):
        findings.append(
            _finding(
                "hard-stale-reviewable",
                "hard-stale synthesis-review-packet passes default validation",
                "Reject stale packets by default for LLM review.",
                artifact=entry.artifact,
            )
        )
    if frontier.validate_synthesis_review_packet(stale, allow_stale_offline=True):
        findings.append(
            _finding(
                "hard-stale-offline-invalid",
                "hard-stale synthesis-review-packet does not pass explicit offline stale validation",
                "Keep explicit offline stale validation available only when requested.",
                artifact=entry.artifact,
            )
        )
    strict = _with_packet_staleness(
        packet,
        evaluated_at="2026-06-25T13:00:00Z",
        max_age_hours=24,
    )
    if not _validator_errors(entry, strict):
        findings.append(
            _finding(
                "strict-max-age-not-stale",
                "stricter max_age_hours did not make an old packet stale",
                "Keep stricter max_age_hours capable of failing old packets.",
                artifact=entry.artifact,
            )
        )
    try:
        frontier.build_synthesis_review_packet_staleness(
            source_generated_at="2026-06-24T00:00:00Z",
            evaluated_at="2026-07-02T01:00:00Z",
            max_age_hours=240,
        )
    except frontier.TriageError:
        pass
    else:
        findings.append(
            _finding(
                "max-age-loosens-default",
                "max_age_hours can make packets older than the default threshold reviewable",
                "Reject max_age_hours values above the default hard threshold.",
                artifact=entry.artifact,
            )
        )
    lied = deepcopy(packet)
    lied["budget"]["serialized_bytes"] = 1
    lied = _sign_packet_digest_only(lied)
    if not _validator_errors(entry, lied):
        findings.append(
            _finding(
                "serialized-bytes-not-recomputed",
                "synthesis-review-packet validator accepts a serialized_bytes lie",
                "Recompute serialized bytes inside the Python validator.",
                artifact=entry.artifact,
            )
        )
    age_lie = deepcopy(packet)
    age_lie["staleness"]["source_age_hours"] = 2.0
    age_lie = _finalize_packet(age_lie)
    if not _validator_errors(entry, age_lie):
        findings.append(
            _finding(
                "source-age-not-recomputed",
                "synthesis-review-packet validator accepts a source_age_hours lie",
                "Recompute source_age_hours from source/evaluation timestamps.",
                artifact=entry.artifact,
            )
        )
    return findings


def _sign_packet_digest_only(packet: dict[str, Any]) -> dict[str, Any]:
    packet["synthesis_review_packet_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in packet.items()
            if key != "synthesis_review_packet_digest"
        }
    )
    return packet


def _check_diagnostic_semantics(entry: ArtifactContract) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    snap = _snapshot(
        _issue(1, title="feat: deterministic backlog synthesis"),
        _issue(2, title="feat: deterministic backlog review"),
    )
    audit = _audit(_entry(1), _entry(2))
    report = frontier.build_backlog_synthesis_report(snap, audit)
    near_misses = report["near_misses"]
    if not near_misses or not str(near_misses[0]["near_miss_id"]).startswith(
        "near-miss-possible-duplicate-001-002-"
    ):
        findings.append(
            _finding(
                "near-miss-id-format",
                "backlog-synthesis did not emit the deterministic near_miss_id format",
                "Keep #97 near_miss_id generation deterministic.",
                artifact=entry.artifact,
            )
        )
    duplicate = deepcopy(report)
    duplicate["near_misses"].append(deepcopy(duplicate["near_misses"][0]))
    duplicate["backlog_synthesis_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in duplicate.items()
            if key != "backlog_synthesis_digest"
        }
    )
    if "near_misses contains duplicate near_miss_id" not in _validator_errors(
        entry, duplicate
    ):
        findings.append(
            _finding(
                "duplicate-near-miss-id",
                "backlog-synthesis validator accepts duplicate near_miss_id values",
                "Reject duplicate #97 diagnostic IDs.",
                artifact=entry.artifact,
            )
        )
    changed = deepcopy(report)
    changed["near_misses"][0]["reason_not_signaled"] = "changed"
    changed_digest = frontier.sha256_json(
        {
            key: value
            for key, value in changed.items()
            if key != "backlog_synthesis_digest"
        }
    )
    if changed_digest == report["backlog_synthesis_digest"]:
        findings.append(
            _finding(
                "diagnostic-digest-change",
                "backlog_synthesis_digest does not change when diagnostics change",
                "Include diagnostic content in the canonical digest.",
                artifact=entry.artifact,
            )
        )
    packet = frontier.build_synthesis_review_packet(
        snap,
        audit,
        report,
        evaluated_at="2026-06-24T01:00:00Z",
    )
    if packet["near_misses"][0]["near_miss_id"] != report["near_misses"][0]["near_miss_id"]:
        findings.append(
            _finding(
                "packet-near-miss-preservation",
                "synthesis-review-packet does not preserve near_miss_id",
                "Copy #97 diagnostic IDs into the packet unchanged.",
                artifact=entry.artifact,
            )
        )
    if "omission-no-issue-body-in-signals" not in {
        item.get("omission_id")
        for item in packet["omissions"]
        if isinstance(item, Mapping)
    }:
        findings.append(
            _finding(
                "packet-omission-preservation",
                "synthesis-review-packet does not preserve backlog omission_id",
                "Copy backlog omission IDs into the packet unchanged.",
                artifact=entry.artifact,
            )
        )
    return findings


def _check_verdict_semantics(entry: ArtifactContract) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    packet = _fixture_synthesis_review_packet()
    verdict = _verdict_for_packet(packet)
    if _paired_validator_errors(entry, verdict, packet):
        findings.append(
            _finding(
                "paired-verdict-invalid",
                "minimal backlog-review-verdict does not validate against its packet",
                "Align the verdict fixture with paired validation.",
                artifact=entry.artifact,
            )
        )
    for field, unknown in (
        ("evidence_refs", "missing-evidence"),
        ("near_miss_refs", "missing-near-miss"),
        ("omission_refs", "missing-omission"),
    ):
        bad = deepcopy(verdict)
        bad["verdicts"][0][field] = [unknown]
        bad = _sign_verdict(bad)
        if not _paired_validator_errors(entry, bad, packet):
            findings.append(
                _finding(
                    f"paired-{field}-not-enforced",
                    f"paired verdict validation accepts unknown {field}",
                    "Require verdict refs to cite exact packet-provided IDs.",
                    artifact=entry.artifact,
                )
            )
    stale_packet = _with_packet_staleness(packet, evaluated_at="2026-07-02T01:00:01Z")
    stale_verdict = _verdict_for_packet(stale_packet)
    if not _paired_validator_errors(entry, stale_verdict, stale_packet):
        findings.append(
            _finding(
                "paired-stale-packet-reviewable",
                "paired verdict validation accepts a hard-stale packet",
                "Reject hard-stale/non-reviewable packets in integrated validation.",
                artifact=entry.artifact,
            )
        )
    unsafe = deepcopy(verdict)
    unsafe["future_apply_recommendations"] = [
        {
            "recommendation_id": "future-apply-001",
            "summary": "unsafe",
            "rationale": "unsafe",
            "advisory_only": True,
            "operation_id": "issue.body.update",
        }
    ]
    unsafe = _sign_verdict(unsafe)
    if not _validator_errors(entry, unsafe):
        findings.append(
            _finding(
                "future-apply-executable",
                "verdict validator accepts executable future_apply_recommendations",
                "Reject apply-like operation shapes in verdicts.",
                artifact=entry.artifact,
            )
        )
    return findings


def _check_inventory(
    entries: Sequence[ArtifactContract], *, root: Path
) -> list[ArtifactContractFinding]:
    findings: list[ArtifactContractFinding] = []
    by_artifact = {entry.artifact: entry for entry in entries}
    missing_known = sorted(KNOWN_SCHEMA_VERSION_ARTIFACTS - set(by_artifact))
    for artifact in missing_known:
        findings.append(
            _finding(
                "inventory-artifact-missing",
                f"schema-versioned artifact lacks manifest status: {artifact}",
                "Add the artifact as active, pending, or excluded with a reason.",
                artifact=artifact,
            )
        )
    manifest_docs = {
        entry.human_doc
        for entry in entries
        if entry.human_doc is not None and entry.status in TERMINAL_STATUSES
    }
    manifest_schemas = {
        entry.machine_schema
        for entry in entries
        if entry.machine_schema is not None and entry.status in TERMINAL_STATUSES
    }
    for path in sorted((root / "docs").glob("*SCHEMA*.md")):
        rel = _relpath(path, root)
        if rel not in manifest_docs:
            findings.append(
                _finding(
                    "inventory-human-doc-missing",
                    f"schema doc lacks manifest status: {rel}",
                    "Add an active, pending, or excluded manifest entry.",
                    path=rel,
                )
            )
    for path in sorted((root / "docs").glob("*schema*.json")):
        rel = _relpath(path, root)
        if rel not in manifest_schemas:
            findings.append(
                _finding(
                    "inventory-machine-schema-missing",
                    f"machine schema lacks manifest status: {rel}",
                    "Add an active, pending, or excluded manifest entry.",
                    path=rel,
                )
            )
    return findings


def run_check(
    *,
    root: Path | None = None,
    manifest_path: Path | None = None,
) -> ArtifactContractResult:
    root = (root or Path.cwd()).resolve()
    manifest_path = manifest_path or MANIFEST_PATH
    checked_files: set[str] = {
        _relpath(manifest_path if manifest_path.is_absolute() else root / manifest_path, root)
    }
    entries, findings = _load_manifest(root, manifest_path)
    findings.extend(_check_inventory(entries, root=root))
    for entry in entries:
        if entry.status == ACTIVE_STATUS:
            findings.extend(
                _check_active_entry(entry, root=root, checked_files=checked_files)
            )
    return ArtifactContractResult(
        checked_files=tuple(sorted(checked_files)),
        findings=tuple(sorted(findings, key=lambda item: item.sort_key())),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--json", action="store_true", help="emit check JSON")
    args = parser.parse_args(argv)

    result = run_check(root=Path.cwd(), manifest_path=args.manifest)
    payload = result.to_json()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
    elif result.passed:
        print("OK: artifact-contracts passed.")
    else:
        print("ERROR: artifact-contracts failed.", file=sys.stderr)
        for finding in result.findings:
            print(
                f"- {finding.code}: {finding.message}",
                file=sys.stderr,
            )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
