#!/usr/bin/env python3
"""Build and validate local bounded Codex review packets."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import codex_quality
import codex_surface
from scripts.triage import repo_config


SCHEMA_VERSION = 1
DIGEST_FIELD = "codex_review_packet_digest"
DEFAULT_TARGET_BYTES = 204800
DEFAULT_HARD_BYTES = 307200
DEFAULT_SNIPPET_BYTES = 12000
COMMAND_OUTPUT_BYTES = 12000
REDACTED_SECRET = "[REDACTED_SECRET]"
REQUIRED_QUALITY_CHECKS = (
    "governance-boundary",
    "artifact-contracts",
    "agent-regression",
)
TOP_LEVEL_FIELDS = (
    "schema_version",
    "repository",
    "generated_at",
    "issue",
    "source_refs",
    "evidence_sources",
    "changed_files",
    "protected_surfaces",
    "contract_surfaces",
    "quality_receipt",
    "risk_findings",
    "diff_snippets",
    "commands",
    "omissions",
    "budget",
    "safety",
    DIGEST_FIELD,
)
ARRAY_FIELDS = (
    "changed_files",
    "protected_surfaces",
    "contract_surfaces",
    "risk_findings",
    "diff_snippets",
    "commands",
    "omissions",
)
SAFETY_FLAGS = {
    "read_only": True,
    "github_api_calls": False,
    "github_mutations": False,
    "llm_calls": False,
    "contains_executable_operations": False,
    "contains_github_request_payloads": False,
    "contains_issue_write_payloads": False,
    "contains_full_repository_bundle": False,
    "contains_full_tracker_snapshot": False,
    "diff_snippets_are_untrusted": True,
    "command_output_is_untrusted": True,
    "maintainer_decides": True,
    "codex_review_is_advisory": True,
}
FORBIDDEN_KEYS = frozenset(
    {
        *repo_config.FORBIDDEN_MUTATION_KEYS,
        "apply_operation",
        "apply_operations",
        "approved_operation_ids",
        "approval_batch",
        "approval_batches",
        "body",
        "comment",
        "comments",
        "full_repository_bundle",
        "full_tracker_snapshot",
        "issue_comment",
        "issue_comments",
        "issue_write_payload",
        "issue_write_payloads",
        "labels",
        "milestone",
        "milestones",
        "operation",
        "project",
        "projects",
        "pull_request_merge_instruction",
        "pull_request_merge_instructions",
        "repository_bundle",
        "review_comment",
        "review_comments",
        "review_thread",
        "review_threads",
        "state",
        "workflow",
        "workflows",
    }
)
SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(password|token|secret|api_key)\s*=\s*([^\s\"']+|\"[^\"]*\"|'[^']*')"
    ),
)
SEMANTICALLY_RELEVANT_RISK_CLASSES = frozenset(
    {"skill", "schema_doc", "issue_governance_doc"}
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def codex_review_packet_without_digest(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in packet.items() if key != DIGEST_FIELD}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _normalize_path(path: str) -> str:
    return codex_surface.normalize_path(path)


def _relative_path(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _is_semantic_scan_path(
    path: str, *, repo_policy: repo_config.RepoPolicy
) -> bool:
    normalized = _normalize_path(path)
    return any(
        normalized == root or normalized.startswith(f"{root.rstrip('/')}/")
        for root in repo_policy.paths.semantic_scan_roots
    )


def _matched_patterns(
    path: str, *, repo_policy: repo_config.RepoPolicy
) -> tuple[str, ...]:
    normalized = _normalize_path(path)
    return tuple(
        pattern
        for pattern in codex_surface.protected_patterns(repo_policy)
        if fnmatch.fnmatchcase(normalized, pattern)
    )


def _risk_classes_for_path(path: str) -> tuple[str, ...]:
    normalized = _normalize_path(path)
    result: set[str] = set()
    if normalized.startswith(".agents/skills/"):
        result.add("skill")
    if normalized.startswith(".codex/scripts/"):
        result.add("codex_script")
    if normalized.startswith(".codex/hooks/") or normalized == ".codex/hooks.json":
        result.add("codex_hook")
    if normalized.startswith(".codex/bin/"):
        result.add("codex_bin")
    if normalized.startswith("scripts/triage/"):
        result.add("triage_governance")
    if normalized.startswith(".github/workflows/"):
        result.add("workflow")
    if normalized.endswith("SCHEMA_V1.md") or (
        normalized.startswith("docs/") and "SCHEMA" in Path(normalized).name
    ):
        result.add("schema_doc")
    if normalized.startswith("docs/") and normalized.endswith(".json") and "schema" in normalized:
        result.add("schema_json")
    if normalized == "docs/ISSUE_GOVERNANCE.md":
        result.add("issue_governance_doc")
    if normalized == ".codex/artifact-contracts-v1.json":
        result.add("artifact_contract_manifest")
    if normalized == ".codex/agent-regression-cases-v1.json" or normalized.startswith(
        ".codex/agent-regression/"
    ):
        result.add("agent_regression_fixture")
    if normalized.endswith(".json") and (
        "schema" in normalized or normalized.startswith(".codex/")
    ):
        result.add("stable_json")
    if normalized.endswith(".sh") or normalized.startswith(".codex/bin/"):
        result.add("public_cli_contract")
    return tuple(sorted(result))


def _is_contract_surface(path: str, risk_classes: Sequence[str]) -> bool:
    normalized = _normalize_path(path)
    classes = set(risk_classes)
    if classes & {
        "skill",
        "codex_script",
        "codex_hook",
        "codex_bin",
        "schema_doc",
        "schema_json",
        "issue_governance_doc",
        "artifact_contract_manifest",
        "agent_regression_fixture",
        "public_cli_contract",
        "stable_json",
    }:
        return True
    return normalized in {
        ".codex/artifact-contracts-v1.json",
        ".codex/README.md",
        "CHANGELOG.md",
    }


def _check_hints_for_path(path: str, risk_classes: Sequence[str]) -> tuple[str, ...]:
    hints = {"codex-quality receipt coverage"}
    classes = set(risk_classes)
    if classes & {"schema_doc", "schema_json", "artifact_contract_manifest", "stable_json"}:
        hints.add("artifact-contracts")
    if classes & {"skill", "codex_script", "codex_hook", "codex_bin", "triage_governance"}:
        hints.add("governance-boundary")
    if classes & {"agent_regression_fixture", "artifact_contract_manifest"}:
        hints.add("agent-regression")
    if "public_cli_contract" in classes:
        hints.add("wrapper or CLI behavior tests")
    return tuple(sorted(hints))


def _contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def _redact_secrets(text: str) -> tuple[str, bool]:
    redacted = text
    changed = False
    for pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(REDACTED_SECRET, redacted)
        changed = changed or count > 0
    return redacted, changed


def _bounded_text(text: str, *, byte_limit: int) -> tuple[str, bool]:
    data = text.encode("utf-8")
    if len(data) <= byte_limit:
        return text, False
    bounded = data[:byte_limit].decode("utf-8", errors="ignore")
    return bounded, True


def _finding(
    code: str,
    severity: str,
    message: str,
    repair_guidance: str,
    *,
    path: str | None = None,
    evidence_source: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "repair_guidance": repair_guidance,
    }
    if path is not None:
        result["path"] = path
    if evidence_source is not None:
        result["evidence_source"] = evidence_source
    return result


def _omission(
    code: str,
    reason: str,
    *,
    path: str | None = None,
    evidence_source: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "reason": reason}
    if path is not None:
        result["path"] = path
    if evidence_source is not None:
        result["evidence_source"] = evidence_source
    return result


@dataclass
class CommandRecorder:
    root: Path
    commands: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)

    def git(self, args: Sequence[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
        command = ["git", *args]
        command_text = " ".join(command)
        result = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        stdout, stdout_redacted = _redact_secrets(result.stdout)
        stderr, stderr_redacted = _redact_secrets(result.stderr)
        stdout, stdout_truncated = _bounded_text(stdout, byte_limit=COMMAND_OUTPUT_BYTES)
        stderr, stderr_truncated = _bounded_text(stderr, byte_limit=COMMAND_OUTPUT_BYTES)
        if stdout_redacted or stderr_redacted:
            self.findings.append(
                _finding(
                    "secret-redacted",
                    "warning",
                    "Secret-shaped text was redacted from command output.",
                    "Inspect the local source and rotate any real secret before sharing the packet.",
                    evidence_source="command",
                )
            )
        self.commands.append(
            {
                "command": command_text,
                "generated_by_packet_builder": True,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "untrusted": True,
            }
        )
        return result


def _parse_status_paths(stdout: str) -> tuple[dict[str, str], tuple[str, ...]]:
    statuses: dict[str, str] = {}
    paths: list[str] = []
    for line in stdout.splitlines():
        if not line:
            continue
        status = line[:2].strip() or "changed"
        raw_path = line[3:] if len(line) > 3 else ""
        if " -> " in raw_path:
            parts = [_normalize_path(part) for part in raw_path.split(" -> ") if part]
            for part in parts:
                statuses[part] = status
                paths.append(part)
        elif raw_path:
            path = _normalize_path(raw_path)
            statuses[path] = status
            paths.append(path)
    return statuses, tuple(sorted(set(paths)))


def _parse_name_status(stdout: str) -> tuple[dict[str, str], tuple[str, ...]]:
    statuses: dict[str, str] = {}
    paths: list[str] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path_values = parts[1:]
        for raw_path in path_values:
            path = _normalize_path(raw_path)
            statuses[path] = status
            paths.append(path)
    return statuses, tuple(sorted(set(paths)))


def _source_refs(
    recorder: CommandRecorder,
    *,
    base_ref: str,
    head_ref: str,
    omissions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    base_sha: str | None = None
    head_sha: str | None = None
    merge_base_sha: str | None = None
    base = recorder.git(["rev-parse", "--verify", base_ref])
    if base.returncode == 0:
        base_sha = base.stdout.strip()
    else:
        omissions.append(
            _omission(
                "base-ref-unresolved",
                f"Base ref {base_ref!r} could not be resolved locally.",
                evidence_source="branch_base_diff",
            )
        )
    head = recorder.git(["rev-parse", "--verify", head_ref])
    if head.returncode == 0:
        head_sha = head.stdout.strip()
    else:
        omissions.append(
            _omission(
                "head-ref-unresolved",
                f"Head ref {head_ref!r} could not be resolved locally.",
                evidence_source="branch_base_diff",
            )
        )
    if base_sha and head_sha:
        merge_base = recorder.git(["merge-base", base_ref, head_ref])
        if merge_base.returncode == 0:
            merge_base_sha = merge_base.stdout.strip()
        else:
            omissions.append(
                _omission(
                    "merge-base-unavailable",
                    "Local git could not compute a merge base for branch/base diff.",
                    evidence_source="branch_base_diff",
                )
            )
            findings.append(
                _finding(
                    "missing-branch-base-diff",
                    "warning",
                    "Branch/base diff evidence is unavailable because merge-base failed.",
                    "Fetch or provide a resolvable base ref, then rebuild the packet.",
                    evidence_source="branch_base_diff",
                )
            )
    return {
        "base_ref": base_ref,
        "head_ref": head_ref,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "merge_base_sha": merge_base_sha,
    }


def _collect_worktree_evidence(
    recorder: CommandRecorder,
    *,
    findings: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], tuple[str, ...]]:
    command = "git status --porcelain --untracked-files=all"
    result = recorder.git(["status", "--porcelain", "--untracked-files=all"])
    if result.returncode != 0:
        omissions.append(
            _omission(
                "worktree-status-unavailable",
                "Local git status failed.",
                evidence_source="worktree_status",
            )
        )
        findings.append(
            _finding(
                "missing-worktree-evidence",
                "warning",
                "Worktree status evidence is unavailable.",
                "Resolve local git status errors, then rebuild the packet.",
                evidence_source="worktree_status",
            )
        )
        return (
            {
                "available": False,
                "command": command,
                "changed_paths": [],
                "error": result.stderr.strip() or "git status failed",
            },
            {},
            (),
        )
    statuses, paths = _parse_status_paths(result.stdout)
    return (
        {
            "available": True,
            "command": command,
            "changed_paths": list(paths),
            "error": None,
        },
        statuses,
        paths,
    )


def _collect_branch_base_evidence(
    recorder: CommandRecorder,
    *,
    source_refs: Mapping[str, Any],
    findings: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], tuple[str, ...]]:
    base_ref = str(source_refs["base_ref"])
    head_ref = str(source_refs["head_ref"])
    command = f"git diff --name-status {base_ref}...{head_ref}"
    if not source_refs.get("merge_base_sha"):
        omissions.append(
            _omission(
                "branch-base-diff-unavailable",
                "Branch/base diff was not run because refs or merge base were unavailable.",
                evidence_source="branch_base_diff",
            )
        )
        return (
            {
                "available": False,
                "command": command,
                "base_ref": base_ref,
                "head_ref": head_ref,
                "changed_paths": [],
                "error": "refs or merge base unavailable",
            },
            {},
            (),
        )
    result = recorder.git(["diff", "--name-status", f"{base_ref}...{head_ref}"])
    if result.returncode != 0:
        omissions.append(
            _omission(
                "branch-base-diff-unavailable",
                "Local git diff failed.",
                evidence_source="branch_base_diff",
            )
        )
        findings.append(
            _finding(
                "missing-branch-base-diff",
                "warning",
                "Branch/base diff evidence is unavailable.",
                "Fetch or provide a resolvable base ref, then rebuild the packet.",
                evidence_source="branch_base_diff",
            )
        )
        return (
            {
                "available": False,
                "command": command,
                "base_ref": base_ref,
                "head_ref": head_ref,
                "changed_paths": [],
                "error": result.stderr.strip() or "git diff failed",
            },
            {},
            (),
        )
    statuses, paths = _parse_name_status(result.stdout)
    return (
        {
            "available": True,
            "command": command,
            "base_ref": base_ref,
            "head_ref": head_ref,
            "changed_paths": list(paths),
            "error": None,
        },
        statuses,
        paths,
    )


def _changed_files(
    *,
    worktree_statuses: Mapping[str, str],
    worktree_paths: Sequence[str],
    branch_statuses: Mapping[str, str],
    branch_paths: Sequence[str],
    explicit_paths: Sequence[str],
    repo_policy: repo_config.RepoPolicy,
) -> list[dict[str, Any]]:
    all_paths = sorted(
        {_normalize_path(path) for path in [*worktree_paths, *branch_paths, *explicit_paths] if path}
    )
    result: list[dict[str, Any]] = []
    for path in all_paths:
        sources = []
        if path in worktree_paths:
            sources.append("worktree_status")
        if path in branch_paths:
            sources.append("branch_base_diff")
        if path in explicit_paths:
            sources.append("explicit")
        risk_classes = _risk_classes_for_path(path)
        protected = codex_surface.is_protected_path(path, repo_policy=repo_policy)
        result.append(
            {
                "path": path,
                "change_sources": sorted(sources),
                "status": {
                    "worktree": worktree_statuses.get(path),
                    "branch_base_diff": branch_statuses.get(path),
                },
                "protected": protected,
                "matched_protected_patterns": list(
                    _matched_patterns(path, repo_policy=repo_policy)
                ),
                "risk_classes": list(risk_classes),
                "contract_surface": _is_contract_surface(path, risk_classes),
                "semantic_scan_applies": (
                    protected and _is_semantic_scan_path(path, repo_policy=repo_policy)
                ),
                "diff_snippet_included": False,
                "diff_snippet_omitted": False,
                "diff_snippet_truncated": False,
            }
        )
    return result


def _protected_surfaces(
    changed_files: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "path": str(item["path"]),
            "matched_protected_patterns": list(item["matched_protected_patterns"]),
            "risk_classes": list(item["risk_classes"]),
            "change_sources": list(item["change_sources"]),
        }
        for item in changed_files
        if item.get("protected") is True
    ]


def _contract_surfaces(
    changed_files: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in changed_files:
        if item.get("contract_surface") is not True:
            continue
        path = str(item["path"])
        risk_classes = list(item["risk_classes"])
        result.append(
            {
                "path": path,
                "risk_classes": risk_classes,
                "required_check_hints": list(_check_hints_for_path(path, risk_classes)),
            }
        )
    return result


def _snippet_needed(item: Mapping[str, Any]) -> bool:
    return item.get("protected") is True or item.get("contract_surface") is True


def _diff_for_path(
    recorder: CommandRecorder,
    *,
    path: str,
    source_refs: Mapping[str, Any],
    branch_available: bool,
    change_sources: Sequence[str],
) -> tuple[str, str]:
    parts: list[str] = []
    sources: list[str] = []
    if branch_available and "branch_base_diff" in change_sources:
        base_ref = str(source_refs["base_ref"])
        head_ref = str(source_refs["head_ref"])
        result = recorder.git(["diff", f"{base_ref}...{head_ref}", "--", path])
        if result.returncode == 0 and result.stdout:
            parts.append(result.stdout)
            sources.append(f"git diff {base_ref}...{head_ref} -- {path}")
    if "worktree_status" in change_sources:
        result = recorder.git(["diff", "--", path])
        if result.returncode == 0 and result.stdout:
            parts.append(result.stdout)
            sources.append(f"git diff -- {path}")
    if not parts and ("worktree_status" in change_sources or "explicit" in change_sources):
        path_obj = recorder.root / path
        if path_obj.is_file():
            try:
                text = path_obj.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return "", f"local file read failed: {path}"
            parts.append(text)
            sources.append(f"bounded local file excerpt: {path}")
    if parts:
        return "\n".join(parts), " + ".join(sources)
    return "", f"diff unavailable: {path}"


def _build_diff_snippets(
    *,
    recorder: CommandRecorder,
    source_refs: Mapping[str, Any],
    changed_files: list[dict[str, Any]],
    snippet_bytes: int,
    branch_available: bool,
    findings: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for item in changed_files:
        path = str(item["path"])
        if not _snippet_needed(item):
            item["diff_snippet_omitted"] = True
            continue
        text, source_command = _diff_for_path(
            recorder,
            path=path,
            source_refs=source_refs,
            branch_available=branch_available,
            change_sources=[str(source) for source in item["change_sources"]],
        )
        if not text:
            item["diff_snippet_omitted"] = True
            omissions.append(
                _omission(
                    "diff-snippet-unavailable",
                    "No local diff or bounded file excerpt was available.",
                    path=path,
                    evidence_source="diff_snippets",
                )
            )
            findings.append(
                _finding(
                    "diff-snippet-omitted",
                    "warning",
                    "A risky file has no diff snippet in the packet.",
                    "Inspect the file locally before relying on the packet.",
                    path=path,
                    evidence_source="diff_snippets",
                )
            )
            continue
        redacted, secret_redacted = _redact_secrets(text)
        bounded, truncated = _bounded_text(redacted, byte_limit=snippet_bytes)
        if secret_redacted:
            findings.append(
                _finding(
                    "secret-redacted",
                    "warning",
                    "Secret-shaped text was redacted from a diff snippet.",
                    "Inspect the local source and rotate any real secret before sharing the packet.",
                    path=path,
                    evidence_source="diff_snippets",
                )
            )
        if truncated:
            omissions.append(
                _omission(
                    "diff-snippet-truncated",
                    f"Snippet exceeded {snippet_bytes} bytes and was truncated.",
                    path=path,
                    evidence_source="diff_snippets",
                )
            )
            findings.append(
                _finding(
                    "diff-snippet-truncated",
                    "warning",
                    "A risky file diff snippet was truncated.",
                    "Inspect the full local diff before relying on the packet.",
                    path=path,
                    evidence_source="diff_snippets",
                )
            )
        item["diff_snippet_included"] = True
        item["diff_snippet_truncated"] = truncated
        snippets.append(
            {
                "path": path,
                "source": source_command,
                "untrusted": True,
                "byte_limit": snippet_bytes,
                "serialized_bytes": len(bounded.encode("utf-8")),
                "truncated": truncated,
                "secret_redacted": secret_redacted,
                "content": bounded,
            }
        )
    return snippets


def _load_quality_receipt(
    *,
    root: Path,
    receipt_path: Path,
    changed_files: Sequence[Mapping[str, Any]],
    repo_policy: repo_config.RepoPolicy,
    findings: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
) -> dict[str, Any]:
    path = receipt_path if receipt_path.is_absolute() else root / receipt_path
    relpath = _relative_path(path, root=root)
    summary: dict[str, Any] = {
        "path": relpath,
        "present": False,
        "readable": False,
        "digest_valid": False,
        "generated_at": None,
        "passed": False,
        "check_statuses": {},
        "findings_summary": [],
        "freshness_bound_protected_paths": [],
        "semantically_checked_protected_paths": [],
        "changed_protected_paths": [],
        "missing_freshness_bound_protected_paths": [],
        "missing_semantically_checked_protected_paths": [],
        "stale_protected_paths": [],
        "usable_as_evidence": False,
        "limitations": [
            "codex-quality is local evidence for named checks and covered paths only."
        ],
        "error": None,
    }
    protected_paths = sorted(
        str(item["path"]) for item in changed_files if item.get("protected") is True
    )
    semantic_paths = sorted(
        str(item["path"])
        for item in changed_files
        if item.get("protected") is True and item.get("semantic_scan_applies") is True
    )
    summary["changed_protected_paths"] = protected_paths
    if not path.is_file():
        summary["error"] = f"missing {relpath}"
        omissions.append(
            _omission(
                "quality-receipt-missing",
                "No local codex-quality receipt was found.",
                evidence_source="quality_receipt",
            )
        )
        findings.append(
            _finding(
                "missing-quality-receipt",
                "warning",
                "No local codex-quality receipt is available.",
                "Run codex-quality separately, then rebuild the packet.",
                evidence_source="quality_receipt",
            )
        )
        return summary
    summary["present"] = True
    try:
        raw = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        summary["error"] = f"cannot read receipt: {type(exc).__name__}"
        omissions.append(
            _omission(
                "quality-receipt-malformed",
                "The local codex-quality receipt could not be parsed.",
                evidence_source="quality_receipt",
            )
        )
        findings.append(
            _finding(
                "malformed-quality-receipt",
                "warning",
                "The local codex-quality receipt is malformed or unreadable.",
                "Run codex-quality separately, then rebuild the packet.",
                evidence_source="quality_receipt",
            )
        )
        return summary
    if not isinstance(raw, dict):
        summary["error"] = "receipt is not a JSON object"
        findings.append(
            _finding(
                "malformed-quality-receipt",
                "warning",
                "The local codex-quality receipt is not a JSON object.",
                "Run codex-quality separately, then rebuild the packet.",
                evidence_source="quality_receipt",
            )
        )
        return summary
    summary["readable"] = True
    expected = raw.get("quality_receipt_digest")
    summary["digest_valid"] = isinstance(expected, str) and expected == codex_quality.receipt_digest(raw)
    summary["generated_at"] = raw.get("generated_at") if isinstance(raw.get("generated_at"), str) else None
    summary["passed"] = raw.get("passed") is True
    checks = raw.get("checks")
    check_statuses: dict[str, str] = {}
    findings_summary: list[dict[str, Any]] = []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            name = check.get("name")
            status = check.get("status")
            if isinstance(name, str) and isinstance(status, str):
                check_statuses[name] = status
            raw_findings = check.get("findings")
            if isinstance(name, str) and isinstance(raw_findings, list):
                findings_summary.append(
                    {
                        "check": name,
                        "count": len(raw_findings),
                    }
                )
    summary["check_statuses"] = dict(sorted(check_statuses.items()))
    summary["findings_summary"] = findings_summary
    freshness = raw.get("freshness_bound_protected_paths")
    semantic = raw.get("semantically_checked_protected_paths")
    if isinstance(freshness, list) and all(isinstance(item, str) for item in freshness):
        summary["freshness_bound_protected_paths"] = list(
            codex_surface.protected_paths(freshness, repo_policy=repo_policy)
        )
    if isinstance(semantic, list) and all(isinstance(item, str) for item in semantic):
        summary["semantically_checked_protected_paths"] = list(
            codex_surface.protected_paths(semantic, repo_policy=repo_policy)
        )
    missing_freshness = sorted(
        set(protected_paths) - set(summary["freshness_bound_protected_paths"])
    )
    missing_semantic = sorted(
        set(semantic_paths) - set(summary["semantically_checked_protected_paths"])
    )
    stale_paths: list[str] = []
    try:
        receipt_mtime = path.stat().st_mtime_ns
    except OSError:
        receipt_mtime = None
    if receipt_mtime is not None:
        for protected_path in protected_paths:
            local_path = root / protected_path
            try:
                if local_path.exists() and local_path.stat().st_mtime_ns > receipt_mtime:
                    stale_paths.append(protected_path)
            except OSError:
                stale_paths.append(protected_path)
    summary["missing_freshness_bound_protected_paths"] = missing_freshness
    summary["missing_semantically_checked_protected_paths"] = missing_semantic
    summary["stale_protected_paths"] = stale_paths
    required_missing = sorted(set(REQUIRED_QUALITY_CHECKS) - set(check_statuses))
    usable = (
        summary["readable"] is True
        and summary["digest_valid"] is True
        and summary["passed"] is True
        and not required_missing
        and not missing_freshness
        and not missing_semantic
        and not stale_paths
    )
    summary["usable_as_evidence"] = usable
    if not summary["digest_valid"]:
        findings.append(
            _finding(
                "digest-invalid-quality-receipt",
                "warning",
                "The codex-quality receipt digest is invalid.",
                "Run codex-quality separately, then rebuild the packet.",
                evidence_source="quality_receipt",
            )
        )
    if summary["passed"] is not True:
        findings.append(
            _finding(
                "failed-quality-receipt",
                "warning",
                "The codex-quality receipt did not pass.",
                "Fix codex-quality findings, rerun codex-quality, then rebuild the packet.",
                evidence_source="quality_receipt",
            )
        )
    if required_missing:
        findings.append(
            _finding(
                "quality-receipt-required-check-missing",
                "warning",
                "The codex-quality receipt is missing required check statuses.",
                "Rerun current codex-quality before relying on the packet.",
                evidence_source="quality_receipt",
            )
        )
    for path_value in missing_freshness:
        findings.append(
            _finding(
                "receipt-not-freshness-covering-protected-path",
                "warning",
                "A changed protected path is absent from freshness_bound_protected_paths.",
                "Run codex-quality after the protected change, then rebuild the packet.",
                path=path_value,
                evidence_source="quality_receipt",
            )
        )
    for path_value in missing_semantic:
        findings.append(
            _finding(
                "semantic-coverage-caveat",
                "warning",
                "A semantically relevant protected path is absent from semantically_checked_protected_paths.",
                "Run codex-quality with semantic coverage for this path or inspect it manually.",
                path=path_value,
                evidence_source="quality_receipt",
            )
        )
    for path_value in stale_paths:
        findings.append(
            _finding(
                "stale-quality-receipt",
                "warning",
                "A changed protected path is newer than the codex-quality receipt.",
                "Run codex-quality after the protected change, then rebuild the packet.",
                path=path_value,
                evidence_source="quality_receipt",
            )
        )
    return summary


def _load_command_log(
    *,
    command_log: Path | None,
    root: Path,
    findings: list[dict[str, Any]],
    omissions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if command_log is None:
        omissions.append(
            _omission(
                "command-output-omitted",
                "No command log was supplied; commands array contains only builder-generated commands.",
                evidence_source="commands",
            )
        )
        findings.append(
            _finding(
                "command-output-omitted",
                "info",
                "No external command output log was supplied.",
                "Reviewers should not infer tests were run from this packet alone.",
                evidence_source="commands",
            )
        )
        return []
    path = command_log if command_log.is_absolute() else root / command_log
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        findings.append(
            _finding(
                "command-log-malformed",
                "warning",
                f"Command log could not be read: {type(exc).__name__}.",
                "Provide a JSON command log array or omit --command-log.",
                evidence_source="commands",
            )
        )
        return []
    if not isinstance(value, list):
        findings.append(
            _finding(
                "command-log-malformed",
                "warning",
                "Command log must be a JSON array.",
                "Provide a JSON command log array or omit --command-log.",
                evidence_source="commands",
            )
        )
        return []
    commands: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        command = item.get("command")
        if not isinstance(command, str):
            continue
        reason = repo_config.governance_mutation_command_reason(command)
        if reason is not None:
            findings.append(
                _finding(
                    "mutation-command-rejected",
                    "error",
                    "Command log contains a mutation-shaped command.",
                    "Remove write-shaped commands from read-only packet inputs.",
                    evidence_source="commands",
                )
            )
            continue
        entry = dict(item)
        entry["generated_by_packet_builder"] = False
        entry["untrusted"] = True
        for field_name in ("stdout", "stderr", "output"):
            raw_text = entry.get(field_name)
            if not isinstance(raw_text, str):
                continue
            redacted, changed = _redact_secrets(raw_text)
            bounded, truncated = _bounded_text(
                redacted, byte_limit=COMMAND_OUTPUT_BYTES
            )
            entry[field_name] = bounded
            entry[f"{field_name}_truncated"] = truncated
            if changed:
                findings.append(
                    _finding(
                        "secret-redacted",
                        "warning",
                        "Secret-shaped text was redacted from command output.",
                        "Inspect the local source and rotate any real secret before sharing the packet.",
                        evidence_source="commands",
                    )
                )
        entry["command_log_index"] = index
        commands.append(entry)
    return commands


def _finalize_packet(packet: dict[str, Any]) -> dict[str, Any]:
    packet[DIGEST_FIELD] = "0" * 64
    for _ in range(12):
        serialized = len(canonical_json(packet).encode("utf-8"))
        budget = dict(packet["budget"])
        budget["serialized_bytes"] = serialized
        warnings = []
        if serialized > int(budget["target_bytes"]):
            warnings.append("serialized_bytes_exceeds_target_bytes")
        if serialized > int(budget["hard_bytes"]):
            warnings.append("serialized_bytes_exceeds_hard_bytes")
        budget["budget_warnings"] = warnings
        packet["budget"] = budget
        digest = sha256_json(codex_review_packet_without_digest(packet))
        if (
            packet[DIGEST_FIELD] == digest
            and serialized == len(canonical_json(packet).encode("utf-8"))
        ):
            return packet
        packet[DIGEST_FIELD] = digest
    return packet


def _enforce_hard_budget(packet: dict[str, Any]) -> dict[str, Any]:
    hard_bytes = int(packet["budget"]["hard_bytes"])
    if len(canonical_json(packet).encode("utf-8")) <= hard_bytes:
        return packet
    snippets = list(packet.get("diff_snippets") or [])
    while snippets and len(canonical_json(packet).encode("utf-8")) > hard_bytes:
        removed = snippets.pop()
        path = removed.get("path") if isinstance(removed, Mapping) else None
        packet["omissions"].append(
            _omission(
                "diff-snippet-omitted-for-hard-budget",
                "A diff snippet was omitted to keep the packet under hard_bytes.",
                path=str(path) if path else None,
                evidence_source="budget",
            )
        )
        packet["risk_findings"].append(
            _finding(
                "diff-snippet-omitted",
                "warning",
                "A diff snippet was omitted to keep the packet under hard_bytes.",
                "Inspect the full local diff before relying on the packet.",
                path=str(path) if path else None,
                evidence_source="budget",
            )
        )
        packet["diff_snippets"] = snippets
        packet = _finalize_packet(packet)
    return packet


def build_codex_review_packet(
    *,
    issue: int,
    output: Path | None = None,
    receipt: Path | None = None,
    base_ref: str | None = None,
    head_ref: str = "HEAD",
    parent_epic: int | None = None,
    target_bytes: int = DEFAULT_TARGET_BYTES,
    hard_bytes: int = DEFAULT_HARD_BYTES,
    snippet_bytes: int = DEFAULT_SNIPPET_BYTES,
    command_log: Path | None = None,
    explicit_paths: Sequence[str] | None = None,
    root: Path | None = None,
    generated_at: str | None = None,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> dict[str, Any]:
    del output
    root = (root or Path.cwd()).resolve()
    active_policy = repo_policy or repo_config.load_repo_policy()
    active_base_ref = base_ref or active_policy.repository.default_branch
    active_receipt = receipt or Path(active_policy.codex.quality_receipt_path)
    explicit = tuple(sorted({_normalize_path(path) for path in explicit_paths or () if path}))
    findings: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    if parent_epic is None:
        omissions.append(
            _omission(
                "parent-epic-unknown",
                "No parent epic was supplied; the command does not fetch GitHub.",
                evidence_source="issue",
            )
        )
    recorder = CommandRecorder(root=root)
    source_refs = _source_refs(
        recorder,
        base_ref=active_base_ref,
        head_ref=head_ref,
        omissions=omissions,
        findings=findings,
    )
    worktree_source, worktree_statuses, worktree_paths = _collect_worktree_evidence(
        recorder, findings=findings, omissions=omissions
    )
    branch_source, branch_statuses, branch_paths = _collect_branch_base_evidence(
        recorder,
        source_refs=source_refs,
        findings=findings,
        omissions=omissions,
    )
    evidence_sources = {
        "worktree_status": worktree_source,
        "branch_base_diff": branch_source,
        "explicit_paths": {
            "available": bool(explicit),
            "changed_paths": list(explicit),
            "error": None,
        },
    }
    changed_files = _changed_files(
        worktree_statuses=worktree_statuses,
        worktree_paths=worktree_paths,
        branch_statuses=branch_statuses,
        branch_paths=branch_paths,
        explicit_paths=explicit,
        repo_policy=active_policy,
    )
    protected_surfaces = _protected_surfaces(changed_files)
    contract_surfaces = _contract_surfaces(changed_files)
    quality_receipt = _load_quality_receipt(
        root=root,
        receipt_path=active_receipt,
        changed_files=changed_files,
        repo_policy=active_policy,
        findings=findings,
        omissions=omissions,
    )
    external_commands = _load_command_log(
        command_log=command_log,
        root=root,
        findings=findings,
        omissions=omissions,
    )
    diff_snippets = _build_diff_snippets(
        recorder=recorder,
        source_refs=source_refs,
        changed_files=changed_files,
        snippet_bytes=snippet_bytes,
        branch_available=branch_source["available"] is True,
        findings=findings,
        omissions=omissions,
    )
    findings.extend(recorder.findings)
    packet: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository": active_policy.repository.full_name,
        "generated_at": generated_at or _utc_now(),
        "issue": {
            "issue_number": issue,
            "parent_epic": parent_epic,
        },
        "source_refs": source_refs,
        "evidence_sources": evidence_sources,
        "changed_files": changed_files,
        "protected_surfaces": protected_surfaces,
        "contract_surfaces": contract_surfaces,
        "quality_receipt": quality_receipt,
        "risk_findings": sorted(findings, key=lambda item: canonical_json(item)),
        "diff_snippets": sorted(diff_snippets, key=lambda item: str(item["path"])),
        "commands": [*recorder.commands, *external_commands],
        "omissions": sorted(omissions, key=lambda item: canonical_json(item)),
        "budget": {
            "serialized_bytes": 0,
            "target_bytes": target_bytes,
            "hard_bytes": hard_bytes,
            "per_file_snippet_bytes": snippet_bytes,
            "omitted_files_count": 0,
            "omitted_snippets_count": 0,
            "budget_warnings": [],
        },
        "safety": dict(SAFETY_FLAGS),
        DIGEST_FIELD: "0" * 64,
    }
    packet["budget"]["omitted_files_count"] = sum(
        1
        for item in packet["changed_files"]
        if item["diff_snippet_omitted"] and _snippet_needed(item)
    )
    packet["budget"]["omitted_snippets_count"] = sum(
        1 for item in packet["omissions"] if "snippet" in str(item.get("code", ""))
    )
    packet = _finalize_packet(packet)
    packet = _enforce_hard_budget(packet)
    packet = _finalize_packet(packet)
    return packet


@dataclass
class PacketValidationContext:
    packet: Mapping[str, Any]
    errors: list[str] = field(default_factory=list)

    def require_mapping(self, value: Any, name: str) -> Mapping[str, Any] | None:
        if not isinstance(value, Mapping):
            self.errors.append(f"{name} must be an object")
            return None
        return value

    def require_array(self, name: str) -> None:
        if not isinstance(self.packet.get(name), list):
            self.errors.append(f"{name} must be an array")


@dataclass(frozen=True)
class CodexReviewPacketValidator:
    packet: Mapping[str, Any]

    def validate(self) -> list[str]:
        context = PacketValidationContext(self.packet)
        self._validate_required(context)
        self._validate_shapes(context)
        self._validate_safety(context)
        self._validate_budget(context)
        self._validate_digest(context)
        self._validate_forbidden_shapes(context)
        self._validate_secret_redaction(context)
        self._validate_commands(context)
        self._validate_receipt(context)
        self._validate_changed_files(context)
        return context.errors

    def _validate_required(self, context: PacketValidationContext) -> None:
        for field_name in TOP_LEVEL_FIELDS:
            if field_name not in self.packet:
                context.errors.append(f"missing required field: {field_name}")
        if self.packet.get("schema_version") != SCHEMA_VERSION:
            context.errors.append("schema_version must be 1")

    def _validate_shapes(self, context: PacketValidationContext) -> None:
        for field_name in ARRAY_FIELDS:
            context.require_array(field_name)
        issue = context.require_mapping(self.packet.get("issue"), "issue")
        if issue is not None:
            number = issue.get("issue_number")
            if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                context.errors.append("issue.issue_number must be a positive integer")
            parent = issue.get("parent_epic")
            if parent is not None and (
                not isinstance(parent, int) or isinstance(parent, bool) or parent <= 0
            ):
                context.errors.append("issue.parent_epic must be null or a positive integer")
        for name in ("source_refs", "evidence_sources", "quality_receipt", "budget", "safety"):
            context.require_mapping(self.packet.get(name), name)

    def _validate_safety(self, context: PacketValidationContext) -> None:
        safety = self.packet.get("safety")
        if not isinstance(safety, Mapping):
            return
        for key, expected in SAFETY_FLAGS.items():
            if safety.get(key) is not expected:
                context.errors.append(f"safety.{key} must be {expected!r}")

    def _validate_budget(self, context: PacketValidationContext) -> None:
        budget = self.packet.get("budget")
        if not isinstance(budget, Mapping):
            return
        for field_name in (
            "serialized_bytes",
            "target_bytes",
            "hard_bytes",
            "per_file_snippet_bytes",
            "omitted_files_count",
            "omitted_snippets_count",
        ):
            value = budget.get(field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                context.errors.append(f"budget.{field_name} must be a non-negative integer")
        hard_bytes = budget.get("hard_bytes")
        target_bytes = budget.get("target_bytes")
        if isinstance(hard_bytes, int) and isinstance(target_bytes, int) and target_bytes > hard_bytes:
            context.errors.append("budget.target_bytes must not exceed budget.hard_bytes")
        actual = len(canonical_json(self.packet).encode("utf-8"))
        if budget.get("serialized_bytes") != actual:
            context.errors.append("budget.serialized_bytes does not match canonical packet size")
        if isinstance(hard_bytes, int) and actual > hard_bytes:
            context.errors.append("packet exceeds budget.hard_bytes")
        if not isinstance(budget.get("budget_warnings"), list):
            context.errors.append("budget.budget_warnings must be an array")

    def _validate_digest(self, context: PacketValidationContext) -> None:
        digest = self.packet.get(DIGEST_FIELD)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            context.errors.append(f"{DIGEST_FIELD} must be a lowercase sha256 digest")
            return
        expected = sha256_json(codex_review_packet_without_digest(self.packet))
        if digest != expected:
            context.errors.append(f"{DIGEST_FIELD} does not match canonical digest")

    def _validate_forbidden_shapes(self, context: PacketValidationContext) -> None:
        _reject_forbidden_shapes(self.packet, errors=context.errors, path="$")

    def _validate_secret_redaction(self, context: PacketValidationContext) -> None:
        for snippet in self.packet.get("diff_snippets", []):
            if not isinstance(snippet, Mapping):
                continue
            content = snippet.get("content")
            if isinstance(content, str) and _contains_secret(content):
                context.errors.append(
                    f"diff_snippets contains unredacted secret-shaped text: {snippet.get('path')}"
                )
            if snippet.get("untrusted") is not True:
                context.errors.append(
                    f"diff snippet must be marked untrusted: {snippet.get('path')}"
                )
        for command in self.packet.get("commands", []):
            if not isinstance(command, Mapping):
                continue
            if command.get("untrusted") is not True:
                context.errors.append("command output must be marked untrusted")
            for field_name in ("stdout", "stderr", "output"):
                value = command.get(field_name)
                if isinstance(value, str) and _contains_secret(value):
                    context.errors.append(
                        f"commands contains unredacted secret-shaped text: {field_name}"
                    )

    def _validate_commands(self, context: PacketValidationContext) -> None:
        for command in self.packet.get("commands", []):
            if not isinstance(command, Mapping):
                context.errors.append("commands entries must be objects")
                continue
            command_text = command.get("command")
            if not isinstance(command_text, str) or not command_text.strip():
                context.errors.append("commands entries must include command text")
                continue
            reason = repo_config.governance_mutation_command_reason(command_text)
            if reason is not None:
                context.errors.append(f"command string is mutation-shaped: {command_text}")

    def _validate_receipt(self, context: PacketValidationContext) -> None:
        receipt = self.packet.get("quality_receipt")
        if not isinstance(receipt, Mapping):
            return
        if receipt.get("usable_as_evidence") is True:
            for field_name in ("present", "readable", "digest_valid", "passed"):
                if receipt.get(field_name) is not True:
                    context.errors.append(
                        f"quality_receipt.usable_as_evidence requires {field_name}"
                    )
            for field_name in (
                "missing_freshness_bound_protected_paths",
                "missing_semantically_checked_protected_paths",
                "stale_protected_paths",
            ):
                if receipt.get(field_name) != []:
                    context.errors.append(
                        f"quality_receipt.usable_as_evidence requires empty {field_name}"
                    )
            statuses = receipt.get("check_statuses")
            if not isinstance(statuses, Mapping):
                context.errors.append("quality_receipt.check_statuses must be an object")
            else:
                missing = sorted(set(REQUIRED_QUALITY_CHECKS) - set(statuses))
                if missing:
                    context.errors.append(
                        "quality_receipt.usable_as_evidence missing check statuses: "
                        + ", ".join(missing)
                    )
        for field_name in (
            "freshness_bound_protected_paths",
            "semantically_checked_protected_paths",
            "changed_protected_paths",
            "missing_freshness_bound_protected_paths",
            "missing_semantically_checked_protected_paths",
            "stale_protected_paths",
        ):
            if not isinstance(receipt.get(field_name), list):
                context.errors.append(f"quality_receipt.{field_name} must be an array")

    def _validate_changed_files(self, context: PacketValidationContext) -> None:
        for item in self.packet.get("changed_files", []):
            if not isinstance(item, Mapping):
                context.errors.append("changed_files entries must be objects")
                continue
            if not isinstance(item.get("path"), str) or not item.get("path"):
                context.errors.append("changed_files entries require path")
            sources = item.get("change_sources")
            if not isinstance(sources, list) or not all(
                source in {"worktree_status", "branch_base_diff", "explicit"}
                for source in sources
            ):
                context.errors.append(
                    f"changed_files change_sources invalid for {item.get('path')}"
                )


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(".", "_")


def _reject_forbidden_shapes(value: Any, *, errors: list[str], path: str) -> None:
    if isinstance(value, Mapping):
        keys = {_normalize_key(str(key)) for key in value}
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            normalized = _normalize_key(key)
            item_path = f"{path}.{key}"
            if normalized in FORBIDDEN_KEYS:
                errors.append(f"{item_path} uses forbidden read-only packet key")
            if repo_config.FORBIDDEN_OPERATION_RE.search(key):
                errors.append(f"{item_path} names a forbidden operation id")
            _reject_forbidden_shapes(raw_item, errors=errors, path=item_path)
        if {"method", "path", "body"}.issubset(keys) or {"request_method", "request_path"}.issubset(keys):
            errors.append(f"{path} looks like a GitHub request payload")
        if {"issues", "pulls"}.issubset(keys) or {"issues", "pull_requests"}.issubset(keys):
            errors.append(f"{path} looks like a full tracker snapshot")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_shapes(item, errors=errors, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and repo_config.FORBIDDEN_OPERATION_RE.search(value):
        errors.append(f"{path} contains a forbidden operation id")


def validate_codex_review_packet(packet: Mapping[str, Any]) -> list[str]:
    if not isinstance(packet, Mapping):
        return ["packet must be an object"]
    return CodexReviewPacketValidator(packet).validate()


def _write_packet(path: Path, packet: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="emit packet JSON to stdout")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--parent-epic", type=int)
    parser.add_argument("--target-bytes", type=int, default=DEFAULT_TARGET_BYTES)
    parser.add_argument("--hard-bytes", type=int, default=DEFAULT_HARD_BYTES)
    parser.add_argument("--snippet-bytes", type=int, default=DEFAULT_SNIPPET_BYTES)
    parser.add_argument("--command-log", type=Path)
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args(argv)

    if args.target_bytes <= 0 or args.hard_bytes <= 0 or args.snippet_bytes <= 0:
        print("ERROR: byte budgets must be positive integers", file=sys.stderr)
        return 2
    if args.target_bytes > args.hard_bytes:
        print("ERROR: --target-bytes must not exceed --hard-bytes", file=sys.stderr)
        return 2
    try:
        packet = build_codex_review_packet(
            issue=args.issue,
            output=args.output,
            receipt=args.receipt,
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            parent_epic=args.parent_epic,
            target_bytes=args.target_bytes,
            hard_bytes=args.hard_bytes,
            snippet_bytes=args.snippet_bytes,
            command_log=args.command_log,
            explicit_paths=args.path,
            root=Path.cwd(),
        )
    except (OSError, subprocess.SubprocessError, repo_config.RepoConfigError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = validate_codex_review_packet(packet)
    if errors:
        print("ERROR: codex-review-packet validation failed.", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.output is not None:
        _write_packet(args.output, packet)
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=True))
    elif args.output is not None:
        print(f"OK: wrote codex-review-packet to {args.output.as_posix()}.")
    else:
        print("OK: codex-review-packet built and validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
