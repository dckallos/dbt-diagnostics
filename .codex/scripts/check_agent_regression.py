#!/usr/bin/env python3
"""Run local Codex agent-regression fixtures against existing safety gates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Callable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
HOOK_DIR = ROOT_DIR / ".codex" / "hooks"
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

import check_artifact_contracts
import check_governance_boundary
import hook_policy
from scripts.triage import frontier, repo_config


CHECK_NAME = "agent-regression"
CASES_PATH = Path(".codex/agent-regression-cases-v1.json")
FIXTURE_ROOT = Path(".codex/agent-regression/fixtures")
SCHEMA_VERSION = 1
NO_FINDINGS_CODE = "no_findings"

ALLOWED_CHECKERS = frozenset(
    {
        "governance-boundary",
        "shared-command-classifier",
        "artifact-contracts",
        "synthesis-review-packet-validator",
        "backlog-review-validate",
        "hook-policy",
        "codex-quality-receipt",
        "limitation-record",
    }
)
ALLOWED_STATUSES = frozenset({"failed", "passed", "warning", "omission"})
IN_MEMORY_CHECKERS = frozenset({"shared-command-classifier"})
CASE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RISK_CLASS_RE = re.compile(r"^[a-z][a-z0-9_]*$")

OWNER_FILES = {
    "governance-boundary": (".codex/scripts/check_governance_boundary.py",),
    "shared-command-classifier": ("scripts/triage/repo_config.py",),
    "artifact-contracts": (".codex/scripts/check_artifact_contracts.py",),
    "synthesis-review-packet-validator": ("scripts/triage/frontier.py",),
    "backlog-review-validate": ("scripts/triage/frontier.py",),
    "hook-policy": (".codex/hooks/hook_policy.py", "scripts/triage/repo_config.py"),
    "codex-quality-receipt": (
        ".codex/scripts/codex_quality.py",
        ".codex/scripts/check_governance_boundary.py",
    ),
    "limitation-record": (),
}


@dataclass(frozen=True)
class AgentRegressionFinding:
    code: str
    message: str
    repair_guidance: str
    severity: str = "error"
    case_id: str | None = None
    risk_class: str | None = None
    path: str | None = None

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.case_id or "", self.code, self.path or "", self.message)

    def to_json(self) -> dict[str, str]:
        result = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "repair_guidance": self.repair_guidance,
        }
        if self.case_id is not None:
            result["case_id"] = self.case_id
        if self.risk_class is not None:
            result["risk_class"] = self.risk_class
        if self.path is not None:
            result["path"] = self.path
        return result


@dataclass(frozen=True)
class AgentRegressionCase:
    case_id: str
    risk_class: str
    fixture_files: tuple[str, ...]
    expected_checker: str
    expected_status: str
    expected_code: str
    expected_code_field: str
    repair_guidance: str | None
    expectation_rationale: str | None
    data: Mapping[str, Any]


@dataclass(frozen=True)
class ObservedCaseResult:
    status: str
    codes: tuple[str, ...]
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentRegressionCaseResult:
    case_id: str
    risk_class: str
    expected_checker: str
    expected_status: str
    expected_code: str
    observed_status: str
    observed_codes: tuple[str, ...]
    matched: bool

    def to_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "risk_class": self.risk_class,
            "expected_checker": self.expected_checker,
            "expected_status": self.expected_status,
            "expected_code": self.expected_code,
            "observed_status": self.observed_status,
            "observed_codes": list(self.observed_codes),
            "matched": self.matched,
        }


@dataclass(frozen=True)
class AgentRegressionResult:
    checked_files: tuple[str, ...]
    case_results: tuple[AgentRegressionCaseResult, ...]
    findings: tuple[AgentRegressionFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    def to_json(self) -> dict[str, object]:
        return {
            "name": CHECK_NAME,
            "status": "passed" if self.passed else "failed",
            "checked_files": list(self.checked_files),
            "case_results": [case.to_json() for case in self.case_results],
            "findings": [finding.to_json() for finding in self.findings],
        }


def _finding(
    code: str,
    message: str,
    repair_guidance: str,
    *,
    case_id: str | None = None,
    risk_class: str | None = None,
    path: str | None = None,
    severity: str = "error",
) -> AgentRegressionFinding:
    return AgentRegressionFinding(
        code=code,
        message=message,
        repair_guidance=repair_guidance,
        severity=severity,
        case_id=case_id,
        risk_class=risk_class,
        path=path,
    )


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _fixture_root(root: Path) -> Path:
    return root / FIXTURE_ROOT


def _read_ascii(path: Path) -> str:
    return path.read_text(encoding="ascii")


def _expected_code_field(expected_status: str) -> str:
    if expected_status == "warning":
        return "expected_warning_code"
    if expected_status == "omission":
        return "expected_omission_code"
    return "expected_finding_code"


def _string_list(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _validate_fixture_path(
    raw_path: str, *, root: Path, case_id: str, risk_class: str
) -> tuple[str | None, tuple[AgentRegressionFinding, ...]]:
    findings: list[AgentRegressionFinding] = []
    if "\\" in raw_path:
        findings.append(
            _finding(
                "fixture-path-invalid",
                f"{case_id} fixture path must use forward slashes: {raw_path}",
                "Use repository-relative POSIX paths under the regression fixture root.",
                case_id=case_id,
                risk_class=risk_class,
                path=raw_path,
            )
        )
        return None, tuple(findings)
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or ".." in pure.parts:
        findings.append(
            _finding(
                "fixture-path-outside-root",
                f"{case_id} fixture path escapes the repository: {raw_path}",
                "Keep fixture files under .codex/agent-regression/fixtures/.",
                case_id=case_id,
                risk_class=risk_class,
                path=raw_path,
            )
        )
        return None, tuple(findings)
    path = root / raw_path
    try:
        path.resolve().relative_to(_fixture_root(root).resolve())
    except ValueError:
        findings.append(
            _finding(
                "fixture-path-outside-root",
                f"{case_id} fixture path is outside {FIXTURE_ROOT.as_posix()}: {raw_path}",
                "Keep fixture files under .codex/agent-regression/fixtures/.",
                case_id=case_id,
                risk_class=risk_class,
                path=raw_path,
            )
        )
        return None, tuple(findings)
    if not path.is_file():
        findings.append(
            _finding(
                "fixture-missing",
                f"{case_id} fixture file is missing: {raw_path}",
                "Restore the fixture or update the case manifest.",
                case_id=case_id,
                risk_class=risk_class,
                path=raw_path,
            )
        )
        return raw_path, tuple(findings)
    try:
        _read_ascii(path)
    except UnicodeDecodeError:
        findings.append(
            _finding(
                "fixture-non-ascii",
                f"{case_id} fixture file must be ASCII: {raw_path}",
                "Rewrite regression fixtures with ASCII-only text.",
                case_id=case_id,
                risk_class=risk_class,
                path=raw_path,
            )
        )
    return raw_path, tuple(findings)


def _case_from_mapping(
    value: Mapping[str, Any], *, index: int, root: Path
) -> tuple[AgentRegressionCase | None, tuple[AgentRegressionFinding, ...]]:
    findings: list[AgentRegressionFinding] = []
    raw_case_id = value.get("case_id")
    case_id = raw_case_id if isinstance(raw_case_id, str) else f"<invalid-{index}>"
    raw_risk_class = value.get("risk_class")
    risk_class = raw_risk_class if isinstance(raw_risk_class, str) else "invalid"

    if not isinstance(raw_case_id, str) or not CASE_ID_RE.fullmatch(raw_case_id):
        findings.append(
            _finding(
                "manifest-case-id",
                f"cases[{index}].case_id must be stable kebab-case",
                "Use lowercase kebab-case for every case_id.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
    if not isinstance(raw_risk_class, str) or not RISK_CLASS_RE.fullmatch(
        raw_risk_class
    ):
        findings.append(
            _finding(
                "manifest-risk-class",
                f"{case_id}.risk_class must be a stable enum-like string",
                "Use a lowercase snake_case risk class.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )

    expected_checker = value.get("expected_checker")
    if expected_checker not in ALLOWED_CHECKERS:
        findings.append(
            _finding(
                "manifest-expected-checker",
                f"{case_id} has unsupported expected_checker {expected_checker!r}",
                "Use one of the supported regression checker groups.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
        expected_checker = "governance-boundary"
    expected_status = value.get("expected_status")
    if expected_status not in ALLOWED_STATUSES:
        findings.append(
            _finding(
                "manifest-expected-status",
                f"{case_id} has unsupported expected_status {expected_status!r}",
                "Use failed, passed, warning, or omission.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
        expected_status = "failed"

    code_field = _expected_code_field(str(expected_status))
    expected_code = value.get(code_field)
    if not isinstance(expected_code, str) or not expected_code:
        findings.append(
            _finding(
                "manifest-expected-code",
                f"{case_id} must define {code_field}",
                "Record the deterministic finding, warning, or omission code.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
        expected_code = "<missing>"

    fixture_files = _string_list(value.get("fixture_files"))
    if fixture_files is None:
        findings.append(
            _finding(
                "manifest-fixture-files",
                f"{case_id}.fixture_files must be an array of strings",
                "List repository-relative fixture files for the case.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
        fixture_files = ()
    elif not fixture_files and expected_checker not in IN_MEMORY_CHECKERS:
        findings.append(
            _finding(
                "manifest-fixture-files-empty",
                f"{case_id} must include at least one fixture file",
                "Use empty fixture_files only for explicitly in-memory cases.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )

    valid_fixture_files: list[str] = []
    for raw_path in fixture_files:
        fixture_path, fixture_findings = _validate_fixture_path(
            raw_path, root=root, case_id=case_id, risk_class=risk_class
        )
        findings.extend(fixture_findings)
        if fixture_path is not None:
            valid_fixture_files.append(fixture_path)

    repair_guidance = value.get("repair_guidance")
    expectation_rationale = value.get("expectation_rationale")
    if not (
        isinstance(repair_guidance, str)
        and repair_guidance.strip()
        or isinstance(expectation_rationale, str)
        and expectation_rationale.strip()
    ):
        findings.append(
            _finding(
                "manifest-rationale",
                f"{case_id} must include repair_guidance or expectation_rationale",
                "Explain why the case exists and how to repair a mismatch.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
    data = value.get("case_data")
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        findings.append(
            _finding(
                "manifest-case-data",
                f"{case_id}.case_data must be an object when present",
                "Use an object for checker-specific case data.",
                case_id=case_id,
                risk_class=risk_class,
            )
        )
        data = {}

    case = AgentRegressionCase(
        case_id=case_id,
        risk_class=risk_class,
        fixture_files=tuple(valid_fixture_files),
        expected_checker=str(expected_checker),
        expected_status=str(expected_status),
        expected_code=str(expected_code),
        expected_code_field=code_field,
        repair_guidance=repair_guidance if isinstance(repair_guidance, str) else None,
        expectation_rationale=(
            expectation_rationale if isinstance(expectation_rationale, str) else None
        ),
        data=data,
    )
    return case, tuple(findings)


def _load_cases(
    root: Path, cases_path: Path
) -> tuple[tuple[AgentRegressionCase, ...], list[AgentRegressionFinding]]:
    path = cases_path if cases_path.is_absolute() else root / cases_path
    if not path.exists():
        return (), [
            _finding(
                "manifest-missing",
                f"agent regression manifest is missing: {_relpath(path, root)}",
                "Create the manifest or pass the correct --cases path.",
                path=_relpath(path, root),
            )
        ]
    try:
        raw = json.loads(path.read_text(encoding="ascii"))
    except UnicodeDecodeError:
        return (), [
            _finding(
                "manifest-non-ascii",
                "agent regression manifest must be ASCII",
                "Rewrite the manifest with ASCII-only JSON.",
                path=_relpath(path, root),
            )
        ]
    except json.JSONDecodeError as exc:
        return (), [
            _finding(
                "manifest-json",
                f"agent regression manifest is invalid JSON: {exc}",
                "Repair the JSON manifest.",
                path=_relpath(path, root),
            )
        ]
    if not isinstance(raw, Mapping):
        return (), [
            _finding(
                "manifest-object",
                "agent regression manifest must be a JSON object",
                "Use a top-level JSON object with schema_version and cases.",
                path=_relpath(path, root),
            )
        ]
    findings: list[AgentRegressionFinding] = []
    if raw.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            _finding(
                "manifest-schema-version",
                "agent regression manifest schema_version must be 1",
                "Set schema_version to 1.",
                path=_relpath(path, root),
            )
        )
    cases_raw = raw.get("cases")
    if not isinstance(cases_raw, list):
        findings.append(
            _finding(
                "manifest-cases",
                "agent regression manifest must include cases array",
                "Add a cases array to the manifest.",
                path=_relpath(path, root),
            )
        )
        return (), findings
    cases: list[AgentRegressionCase] = []
    seen: set[str] = set()
    for index, item in enumerate(cases_raw):
        if not isinstance(item, Mapping):
            findings.append(
                _finding(
                    "manifest-case-object",
                    f"cases[{index}] must be an object",
                    "Make every regression case a JSON object.",
                    path=_relpath(path, root),
                )
            )
            continue
        case, case_findings = _case_from_mapping(item, index=index, root=root)
        findings.extend(case_findings)
        if case is None:
            continue
        if case.case_id in seen:
            findings.append(
                _finding(
                    "manifest-duplicate-case",
                    f"duplicate agent regression case: {case.case_id}",
                    "Keep exactly one manifest entry per case_id.",
                    case_id=case.case_id,
                    risk_class=case.risk_class,
                )
            )
        seen.add(case.case_id)
        cases.append(case)
    return tuple(sorted(cases, key=lambda item: item.case_id)), findings


def _read_case_text(case: AgentRegressionCase, root: Path) -> str:
    return "\n".join(_read_ascii(root / path).rstrip("\n") for path in case.fixture_files)


def _normalize_status_from_codes(codes: Sequence[str]) -> str:
    return "failed" if codes else "passed"


def _evaluate_governance_boundary(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    result = check_governance_boundary.run_check(
        [Path(path) for path in case.fixture_files],
        root=root,
    )
    codes = tuple(sorted({violation.code for violation in result.violations}))
    messages = tuple(sorted({violation.message for violation in result.violations}))
    return ObservedCaseResult(
        status=_normalize_status_from_codes(codes),
        codes=codes,
        messages=messages,
    )


def _evaluate_shared_command_classifier(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    command = _read_case_text(case, root)
    reason = repo_config.governance_mutation_command_reason(command)
    if reason is None:
        return ObservedCaseResult(status="passed", codes=())
    return ObservedCaseResult(
        status="failed",
        codes=("governance-mutation-command",),
        messages=(reason,),
    )


def _case_root(case: AgentRegressionCase, root: Path) -> Path:
    explicit = case.data.get("fixture_root")
    if isinstance(explicit, str) and explicit:
        return root / explicit
    return root / FIXTURE_ROOT / case.case_id


def _evaluate_artifact_contracts(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    manifest_path = case.data.get("manifest_path")
    if not isinstance(manifest_path, str) or not manifest_path:
        return ObservedCaseResult(
            status="failed",
            codes=("case-data-invalid",),
            messages=("artifact-contract case requires case_data.manifest_path",),
        )
    case_root = _case_root(case, root).resolve()
    import_roots = [
        case_root / path
        for path in case.data.get("import_roots", [])
        if isinstance(path, str)
    ]
    sys_paths = [case_root, *import_roots]
    module_names = [
        name for name in case.data.get("import_modules", []) if isinstance(name, str)
    ]
    old_modules = {name: sys.modules.get(name) for name in module_names}
    old_dont_write_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        for path in reversed(sys_paths):
            sys.path.insert(0, str(path))
        for name in module_names:
            sys.modules.pop(name, None)
        result = check_artifact_contracts.run_check(
            root=case_root,
            manifest_path=Path(manifest_path),
        )
    finally:
        for path in sys_paths:
            text = str(path)
            while text in sys.path:
                sys.path.remove(text)
        for name, module in old_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        sys.dont_write_bytecode = old_dont_write_bytecode
    codes = tuple(sorted({finding.code for finding in result.findings}))
    messages = tuple(sorted({finding.message for finding in result.findings}))
    return ObservedCaseResult(
        status=_normalize_status_from_codes(codes),
        codes=codes,
        messages=messages,
    )


def _issue(number: int, *, title: str, body: str = "") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "labels": ["test"],
        "state": "open",
        "body": body,
        "html_url": f"https://github.com/dckallos/dbt-diagnostics/issues/{number}",
    }


def _snapshot(*issues: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generated_at": "2026-06-24T00:00:00Z",
        "snapshot_digest": "a" * 64,
        "repository": "dckallos/dbt-diagnostics",
        "issues": list(issues),
        "pulls": [],
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
        "parent_epics": [134],
        "referenced_paths": ["scripts/triage/frontier.py"],
        "source_claims_checked": [],
        "semantic_review_notes": [],
        "recommended_disposition": "implement",
        "semantic_disposition_hypothesis": None,
        "semantic_disposition_evidence": [],
    }
    value.update(extra)
    return value


def _audit(*entries: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": "dckallos/dbt-diagnostics",
        "snapshot_digest": "a" * 64,
        "audit_digest": "b" * 64,
        "issues": list(entries),
    }


def _base_packet(*, evaluated_at: str = "2026-06-24T01:00:00Z") -> dict[str, Any]:
    snapshot = _snapshot(
        _issue(1, title="feat: deterministic backlog synthesis"),
        _issue(2, title="feat: deterministic backlog synthesis"),
    )
    audit = _audit(_entry(1), _entry(2))
    report = frontier.build_backlog_synthesis_report(snapshot, audit)
    return frontier.build_synthesis_review_packet(
        snapshot,
        audit,
        report,
        evaluated_at=evaluated_at,
    )


def _sign_packet_digest_only(packet: dict[str, Any]) -> dict[str, Any]:
    packet["synthesis_review_packet_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in packet.items()
            if key != "synthesis_review_packet_digest"
        }
    )
    return packet


def _sign_verdict(verdict: dict[str, Any]) -> dict[str, Any]:
    verdict["backlog_review_verdict_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in verdict.items()
            if key != "backlog_review_verdict_digest"
        }
    )
    return verdict


def _verdict_for_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    source_artifacts = packet["source_artifacts"]
    staleness = packet["staleness"]
    evidence_items = packet.get("evidence_items")
    evidence_id = "evidence-001"
    if isinstance(evidence_items, list) and evidence_items:
        item = evidence_items[0]
        if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str):
            evidence_id = str(item["evidence_id"])
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
            "freshness_status": staleness["freshness_status"],
            "freshness_warnings": staleness["freshness_warnings"],
            "packet_stale": staleness["stale"],
            "llm_review_allowed": staleness["llm_review_allowed"],
            "invalid_lineage": False,
        },
        "verdicts": [
            {
                "verdict_id": "verdict-likely-duplicate-001-002",
                "verdict_type": "likely-duplicate",
                "issue_numbers": [1, 2],
                "recommendation": "Maintainer should review #1 and #2.",
                "confidence": "medium",
                "evidence_refs": [evidence_id],
                "near_miss_refs": [],
                "omission_refs": [],
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
    if staleness["freshness_status"] == "warning":
        verdict["uncertainty"] = [
            {
                "code": frontier.SOURCE_AGE_EXCEEDS_WARNING_AGE,
                "rationale": "Packet freshness warning is visible.",
            }
        ]
    return _sign_verdict(verdict)


def _packet_error_code(message: str) -> str:
    if "serialized_bytes" in message:
        return "packet_serialized_bytes_mismatch"
    if "hard-stale" in message or "stale packets are not valid" in message:
        return "packet_hard_stale"
    if "llm_review_allowed" in message or "not LLM-reviewable" in message:
        return "packet_not_reviewable"
    if "comments_" in message or "comment_" in message or ".comments" in message:
        return "packet_comments_included"
    if "full tracker snapshot" in message or "forbidden" in message:
        return "forbidden_mutation_shape"
    return "packet_schema_invalid"


def _evaluate_packet_validator(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    variant = case.data.get("variant")
    if variant == "serialized-bytes-lie":
        packet = _base_packet()
        packet["budget"]["serialized_bytes"] = 1
        packet = _sign_packet_digest_only(packet)
        errors = frontier.validate_synthesis_review_packet(packet)
        codes = tuple(sorted({_packet_error_code(error) for error in errors}))
        return ObservedCaseResult(_normalize_status_from_codes(codes), codes, tuple(errors))
    if variant == "stale-reviewable-lie":
        packet = _base_packet(evaluated_at="2026-07-02T01:00:01Z")
        errors = frontier.validate_synthesis_review_packet(packet)
        codes = tuple(sorted({_packet_error_code(error) for error in errors}))
        return ObservedCaseResult(_normalize_status_from_codes(codes), codes, tuple(errors))
    if variant == "warning-only-reviewable":
        packet = _base_packet(evaluated_at="2026-06-25T01:00:00Z")
        verdict = _verdict_for_packet(packet)
        result = frontier.build_backlog_review_validation_result(packet, verdict)
        warnings = [
            item["code"]
            for item in result.get("warnings", [])
            if isinstance(item, Mapping) and isinstance(item.get("code"), str)
        ]
        errors = [
            item["code"]
            for item in result.get("errors", [])
            if isinstance(item, Mapping) and isinstance(item.get("code"), str)
        ]
        if errors:
            return ObservedCaseResult("failed", tuple(sorted(set(errors))))
        return ObservedCaseResult(
            "warning" if warnings else "passed",
            tuple(sorted(set(warnings))),
        )
    if variant == "comments-included":
        packet = _base_packet()
        packet["comments_included"] = False
        packet["comment_evidence_status"] = "not_collected"
        packet["evidence_items"][0]["comments"] = ["full comment text"]
        packet = _sign_packet_digest_only(packet)
        errors = frontier.validate_synthesis_review_packet(packet)
        codes = tuple(sorted({_packet_error_code(error) for error in errors}))
        return ObservedCaseResult(_normalize_status_from_codes(codes), codes, tuple(errors))
    if variant == "full-snapshot-nested":
        packet = _base_packet()
        packet["evidence_items"][0]["snapshot"] = {"issues": [], "pulls": []}
        packet = _sign_packet_digest_only(packet)
        errors = frontier.validate_synthesis_review_packet(packet)
        codes = tuple(sorted({_packet_error_code(error) for error in errors}))
        return ObservedCaseResult(_normalize_status_from_codes(codes), codes, tuple(errors))
    return ObservedCaseResult(
        "failed",
        ("case-data-invalid",),
        (f"unsupported packet validator variant: {variant!r}",),
    )


def _evaluate_backlog_review_validate(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    variant = case.data.get("variant")
    if variant == "hard-stale-packet-verdict":
        packet = _base_packet(evaluated_at="2026-07-02T01:00:01Z")
        verdict = _verdict_for_packet(packet)
    else:
        packet = _base_packet()
        verdict = _verdict_for_packet(packet)
        if variant == "fabricated-near-miss-ref":
            verdict["verdicts"][0]["near_miss_refs"] = ["missing-near-miss"]
        elif variant == "fabricated-omission-ref":
            verdict["verdicts"][0]["omission_refs"] = ["missing-omission"]
        elif variant == "fabricated-evidence-ref":
            verdict["verdicts"][0]["evidence_refs"] = ["missing-evidence"]
        else:
            return ObservedCaseResult(
                "failed",
                ("case-data-invalid",),
                (f"unsupported backlog review variant: {variant!r}",),
            )
        verdict = _sign_verdict(verdict)
    result = frontier.build_backlog_review_validation_result(packet, verdict)
    codes = tuple(
        sorted(
            {
                item["code"]
                for item in result.get("errors", [])
                if isinstance(item, Mapping) and isinstance(item.get("code"), str)
            }
        )
    )
    warnings = tuple(
        sorted(
            {
                item["code"]
                for item in result.get("warnings", [])
                if isinstance(item, Mapping) and isinstance(item.get("code"), str)
            }
        )
    )
    if codes:
        return ObservedCaseResult("failed", codes)
    if warnings:
        return ObservedCaseResult("warning", warnings)
    return ObservedCaseResult("passed", ())


def _evaluate_hook_policy(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    command = _read_case_text(case, root)
    result = hook_policy.evaluate_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"cmd": command}}
    )
    hook_output = result.get("hookSpecificOutput")
    if isinstance(hook_output, Mapping) and hook_output.get("permissionDecision") == "deny":
        return ObservedCaseResult("failed", ("hook_denied_github_mutation",))
    return ObservedCaseResult("passed", ())


def _evaluate_codex_quality_receipt(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    raw_path = case.data.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return ObservedCaseResult(
            "failed",
            ("case-data-invalid",),
            ("codex-quality-receipt case requires case_data.path",),
        )
    # Use the lower-level governance-boundary path gate to avoid recursive
    # codex-quality execution while codex-quality is running this check.
    result = check_governance_boundary.run_check([Path(raw_path)], root=root)
    codes = tuple(sorted({violation.code for violation in result.violations}))
    return ObservedCaseResult(_normalize_status_from_codes(codes), codes)


def _evaluate_limitation_record(
    case: AgentRegressionCase, root: Path
) -> ObservedCaseResult:
    code = case.data.get("omission_code") or case.expected_code
    if not isinstance(code, str) or not code:
        return ObservedCaseResult("failed", ("case-data-invalid",))
    return ObservedCaseResult("omission", (code,))


EVALUATORS: Mapping[str, Callable[[AgentRegressionCase, Path], ObservedCaseResult]] = {
    "governance-boundary": _evaluate_governance_boundary,
    "shared-command-classifier": _evaluate_shared_command_classifier,
    "artifact-contracts": _evaluate_artifact_contracts,
    "synthesis-review-packet-validator": _evaluate_packet_validator,
    "backlog-review-validate": _evaluate_backlog_review_validate,
    "hook-policy": _evaluate_hook_policy,
    "codex-quality-receipt": _evaluate_codex_quality_receipt,
    "limitation-record": _evaluate_limitation_record,
}


def _case_matches(case: AgentRegressionCase, observed: ObservedCaseResult) -> bool:
    if observed.status != case.expected_status:
        return False
    if case.expected_code == NO_FINDINGS_CODE:
        return not observed.codes
    return case.expected_code in observed.codes


def _evaluate_case(
    case: AgentRegressionCase, root: Path
) -> tuple[AgentRegressionCaseResult, AgentRegressionFinding | None]:
    evaluator = EVALUATORS.get(case.expected_checker)
    if evaluator is None:
        observed = ObservedCaseResult("failed", ("unsupported-checker",))
    else:
        try:
            observed = evaluator(case, root)
        except Exception as exc:  # pragma: no cover - defensive fail-closed guard.
            observed = ObservedCaseResult(
                "failed",
                ("checker-error",),
                (f"{type(exc).__name__}: {exc}",),
            )
    matched = _case_matches(case, observed)
    result = AgentRegressionCaseResult(
        case_id=case.case_id,
        risk_class=case.risk_class,
        expected_checker=case.expected_checker,
        expected_status=case.expected_status,
        expected_code=case.expected_code,
        observed_status=observed.status,
        observed_codes=observed.codes,
        matched=matched,
    )
    if matched:
        return result, None
    return result, _finding(
        "case-mismatch",
        (
            f"{case.case_id} expected {case.expected_status}/"
            f"{case.expected_code} from {case.expected_checker}, observed "
            f"{observed.status}/{list(observed.codes)}"
        ),
        case.repair_guidance
        or case.expectation_rationale
        or "Restore the expected checker behavior or update the manifest deliberately.",
        case_id=case.case_id,
        risk_class=case.risk_class,
    )


def run_check(
    root: Path | None = None,
    cases_path: Path | None = None,
) -> AgentRegressionResult:
    root = (root or Path.cwd()).resolve()
    cases_path = cases_path or CASES_PATH
    manifest = cases_path if cases_path.is_absolute() else root / cases_path
    checked_files: set[str] = {_relpath(manifest, root)}
    cases, findings = _load_cases(root, cases_path)
    case_results: list[AgentRegressionCaseResult] = []

    for case in cases:
        checked_files.update(case.fixture_files)
        checked_files.update(
            path for path in OWNER_FILES.get(case.expected_checker, ()) if (root / path).exists()
        )
        if any(finding.case_id == case.case_id for finding in findings):
            continue
        result, mismatch = _evaluate_case(case, root)
        case_results.append(result)
        if mismatch is not None:
            findings.append(mismatch)

    return AgentRegressionResult(
        checked_files=tuple(sorted(checked_files)),
        case_results=tuple(sorted(case_results, key=lambda item: item.case_id)),
        findings=tuple(sorted(findings, key=lambda item: item.sort_key())),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--json", action="store_true", help="emit check JSON")
    args = parser.parse_args(argv)

    result = run_check(root=Path.cwd(), cases_path=args.cases)
    payload = result.to_json()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
    elif result.passed:
        print("OK: agent-regression passed.")
    else:
        print("ERROR: agent-regression failed.", file=sys.stderr)
        for finding in result.findings:
            print(f"- {finding.code}: {finding.message}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
