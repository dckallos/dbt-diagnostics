#!/usr/bin/env python3
"""Plan and audit GitHub issue governance with explicit approval gates.

Snapshot, audit, plan, project-plan, backlog-synthesis, contract,
review-packet, standardize, and frontier do not mutate GitHub. Apply performs a
live preflight before any selected operation. A real metadata write additionally
requires --execute, an exact repository confirmation, and
TRIAGE_ENABLE_GITHUB_WRITES=1.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlencode

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required.
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.triage import contract as issue_contract  # noqa: E402
from scripts.triage import frontier as issue_frontier  # noqa: E402
from scripts.triage import readiness as issue_readiness  # noqa: E402
from scripts.triage import common as governance_common  # noqa: E402
from scripts.triage import repo_config  # noqa: E402

DEFAULT_POLICY = ROOT / "scripts" / "triage" / "policy.toml"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "triage"
LOCK_PATH = DEFAULT_OUTPUT_DIR / ".metadata-writer.lock"

SNAPSHOT_SCHEMA_VERSION = 2
PLAN_SCHEMA_VERSION = 2
APPROVAL_SCHEMA_VERSION = 1
OPERATION_SCHEMA_VERSION = 1
GITHUB_API_VERSION = "2022-11-28"

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_REF_RE = re.compile(r"(?<![A-Za-z0-9_])#(?P<number>[1-9][0-9]*)")
MARKDOWN_HEADING_RE = re.compile(r"(?m)^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
PROGRESS_DATE_RE = re.compile(r"(?m)^##\s+(?P<date>20\d\d-\d\d-\d\d)\b")
UNCHECKED_LINE_RE = re.compile(r"(?im)^\s*[-*]\s+\[\s\]\s+(?P<body>[^\n]*)$")
RELATION_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?P<kind>depends\s+on|blocked\s+by|requires|must\s+land\s+after|"
    r"blocks|must\s+land\s+before|parent\s+epic|related|coordinates\s+with|"
    r"supersedes)\b(?:\*\*)?[^:\n]*:\s*(?:\*\*)?\s*(?P<refs>[^\n]*)$"
)
DECLARED_OPEN_RE = re.compile(
    r"(?im)^\s*[-*]?\s*Open\s+(?P<kind>issues?|PRs?)\s*:\s*(?P<refs>[^\n]*)$"
)

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+"),
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(
        r"(?i)\b(token|password|passphrase|secret|authorization)\s*([:=])\s*[^\s,;]+"
    ),
)
TYPE_LABEL_PREFIX_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("[epic]", "epic"),
    ("[feature]", "enhancement"),
    ("fix:", "bug"),
    ("feat:", "enhancement"),
    ("test:", "test"),
    ("docs:", "documentation"),
    ("chore:", "chore"),
    ("spike:", "spike"),
    ("refactor:", "architecture"),
)
SUPPORTED_OPERATION_KINDS = {
    "issue.labels.add",
    "issue.labels.remove",
    "issue.milestone.set",
    "issue.milestone.clear",
}
FORBIDDEN_OPERATION_KINDS = {
    "issue.create",
    "issue.close",
    "issue.reopen",
    "issue.body.update",
    "issue.title.update",
    "label.create",
    "label.delete",
    "label.rename",
    "milestone.create",
    "milestone.close",
    "project.create",
}


class TriageError(RuntimeError):
    """Raised for controlled user-facing failures."""


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class Runner:
    """Subprocess runner whose argument list is observable in tests."""

    cwd: Path = ROOT
    timeout: float = 60.0
    executable: str = "gh"
    require_executable: bool = True
    calls: list[tuple[str, ...]] = field(default_factory=list)
    inputs: list[str | None] = field(default_factory=list)

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: float | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        normalized = tuple(str(item) for item in args)
        self.calls.append(normalized)
        self.inputs.append(input_text)
        process = subprocess.run(
            list(normalized),
            cwd=self.cwd,
            text=True,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout or self.timeout,
            check=False,
        )
        return CommandResult(
            args=normalized,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def ensure_executable(self) -> None:
        if self.require_executable and shutil.which(self.executable) is None:
            raise TriageError("GitHub CLI `gh` is required")


@dataclass(frozen=True)
class GitHubClient:
    runner: Runner
    repo: str

    def api(
        self,
        path: str,
        *,
        method: str = "GET",
        query: Mapping[str, str | int | bool] | None = None,
        body: Mapping[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> Any:
        self.runner.ensure_executable()
        endpoint = path
        if query:
            encoded = urlencode(
                {
                    key: str(value).lower() if isinstance(value, bool) else value
                    for key, value in query.items()
                }
            )
            endpoint = f"{path}?{encoded}"
        args = [
            self.runner.executable,
            "api",
            "--method",
            method.upper(),
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            f"X-GitHub-Api-Version: {GITHUB_API_VERSION}",
            endpoint,
        ]
        input_text = None
        if body is not None:
            args.extend(["--input", "-"])
            input_text = canonical_json(body)
        result = self.runner.run(args, timeout=timeout, input_text=input_text)
        return parse_gh_result(result)

    def api_paginated(
        self,
        path: str,
        *,
        query: Mapping[str, str | int | bool] | None = None,
        timeout: float = 120.0,
    ) -> list[Any]:
        self.runner.ensure_executable()
        endpoint = path
        if query:
            encoded = urlencode(
                {
                    key: str(value).lower() if isinstance(value, bool) else value
                    for key, value in query.items()
                }
            )
            endpoint = f"{path}?{encoded}"
        args = [
            self.runner.executable,
            "api",
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            f"X-GitHub-Api-Version: {GITHUB_API_VERSION}",
            "--paginate",
            "--slurp",
            endpoint,
        ]
        result = self.runner.run(args, timeout=timeout)
        data = parse_gh_result(result)
        if data is None:
            return []
        if not isinstance(data, list):
            raise TriageError(
                f"gh api pagination returned {type(data).__name__}, expected list"
            )
        flattened: list[Any] = []
        for page in data:
            if isinstance(page, list):
                flattened.extend(page)
            else:
                flattened.append(page)
        return flattened

    def graphql(
        self, query: str, variables: Mapping[str, Any], *, timeout: float = 120.0
    ) -> Any:
        self.runner.ensure_executable()
        args = [
            self.runner.executable,
            "api",
            "graphql",
            "--input",
            "-",
        ]
        payload = {"query": query, "variables": dict(variables)}
        result = self.runner.run(
            args, timeout=timeout, input_text=canonical_json(payload)
        )
        return parse_gh_result(result)


@dataclass(frozen=True)
class PreflightResult:
    operation_id: str
    status: str
    message: str
    current: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "status": self.status,
            "message": self.message,
            "current": self.current,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def ascii_text(value: Any) -> str:
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def parse_gh_result(result: CommandResult) -> Any:
    if result.returncode != 0:
        detail = sanitize_cli_error(
            result.stderr.strip() or result.stdout.strip() or "gh command failed"
        )
        rendered = " ".join(result.args[1:]) if result.args else "gh"
        raise TriageError(f"gh {rendered}: {detail}")
    text = result.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        rendered = " ".join(result.args[1:]) if result.args else "gh"
        raise TriageError(f"gh {rendered} returned non-JSON output") from exc


def sanitize_cli_error(value: str, limit: int = 500) -> str:
    text = value.replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(r"\1\2<redacted>", text)
        else:
            text = pattern.sub("<redacted>", text)
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def validate_repo_name(repo: str) -> str:
    if not REPO_RE.fullmatch(repo):
        raise TriageError(f"repository must be owner/name: {repo!r}")
    return repo


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TriageError(f"{label} must be a JSON/TOML object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TriageError(f"{label} must be a list")
    return value


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    try:
        policy = repo_config.load_policy_mapping(path)
        repo_config.policy_from_mapping(policy, source=path)
    except repo_config.RepoConfigError as exc:
        raise TriageError(str(exc)) from exc
    validate_policy(policy)
    return policy


def validate_policy(policy: Mapping[str, Any]) -> None:
    repository = policy.get("repository")
    if not isinstance(repository, dict):
        raise TriageError("policy [repository] table is required")
    owner = repository.get("owner")
    name = repository.get("name")
    if not isinstance(owner, str) or not isinstance(name, str):
        raise TriageError("policy repository.owner and repository.name must be strings")
    validate_repo_name(f"{owner}/{name}")

    labels = policy.get("labels", {})
    if not isinstance(labels, dict):
        raise TriageError("policy [labels] must be a table")
    seen: dict[str, str] = {}
    for category, values in labels.items():
        if (
            not isinstance(category, str)
            or not isinstance(values, list)
            or not all(isinstance(item, str) and item for item in values)
        ):
            raise TriageError(
                f"policy labels.{category} must be a list of non-empty strings"
            )
        for label in values:
            folded = label.casefold()
            previous = seen.get(folded)
            if previous is not None and previous != label:
                raise TriageError(
                    f"policy labels contain case-insensitive duplicate: {previous!r}, {label!r}"
                )
            seen[folded] = label

    release = policy.get("release", {})
    if not isinstance(release, dict):
        raise TriageError("policy [release] must be a table")
    milestone_number = release.get("milestone_number", 0)
    if (
        not isinstance(milestone_number, int)
        or isinstance(milestone_number, bool)
        or milestone_number < 0
    ):
        raise TriageError("release.milestone_number must be a non-negative integer")
    for key in ("epic_numbers", "additional_issue_numbers"):
        values = release.get(key, [])
        if not isinstance(values, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in values
        ):
            raise TriageError(f"release.{key} must be a list of positive issue numbers")
    headings = release.get("section_headings", [])
    if not isinstance(headings, list) or not all(
        isinstance(item, str) and item.strip() for item in headings
    ):
        raise TriageError(
            "release.section_headings must be a list of non-empty strings"
        )

    type_inference = policy.get("type_inference", {})
    if not isinstance(type_inference, dict):
        raise TriageError("policy [type_inference] must be a table")
    prefixes = type_inference.get("prefixes", {})
    if not isinstance(prefixes, dict):
        raise TriageError("policy [type_inference.prefixes] must be a table")
    for label, values in prefixes.items():
        if not isinstance(label, str) or not label:
            raise TriageError("type-inference labels must be non-empty strings")
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise TriageError(
                f"type_inference.prefixes.{label} must be a list of non-empty strings"
            )

    project = policy.get("project", {})
    if not isinstance(project, dict):
        raise TriageError("policy [project] must be a table")
    if project.get("enabled", False):
        if project.get("owner_type") not in {"user", "organization"}:
            raise TriageError("project.owner_type must be user or organization")
        if not isinstance(project.get("owner"), str) or not project.get("owner"):
            raise TriageError("project.owner is required when project.enabled=true")
        if not isinstance(project.get("number"), int) or project.get("number", 0) <= 0:
            raise TriageError(
                "project.number must be positive when project.enabled=true"
            )

    desired = policy.get("desired", {})
    if not isinstance(desired, dict):
        raise TriageError("policy [desired] must be a table")
    issues = desired.get("issue", [])
    if not isinstance(issues, list):
        raise TriageError("policy [[desired.issue]] entries must form a list")
    desired_numbers: set[int] = set()
    for index, entry in enumerate(issues):
        validate_desired_issue(entry, f"desired.issue[{index}]")
        number = int(entry["number"])
        if number in desired_numbers:
            raise TriageError(f"policy has duplicate desired.issue entry for #{number}")
        desired_numbers.add(number)

    planning = policy.get("planning", {})
    if not isinstance(planning, dict):
        raise TriageError("policy [planning] must be a table")
    default_batch = planning.get("default_batch", "remaining")
    if not isinstance(default_batch, str) or not default_batch:
        raise TriageError("planning.default_batch must be a non-empty string")
    for key in (
        "bootstrap_issue_numbers",
        "canary_issue_numbers",
        "remaining_issue_numbers",
    ):
        values = planning.get(key, [])
        if not isinstance(values, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in values
        ):
            raise TriageError(
                f"planning.{key} must be a list of positive issue numbers"
            )

    batch_membership: dict[int, str] = {}
    for batch, key in (
        ("bootstrap", "bootstrap_issue_numbers"),
        ("canary", "canary_issue_numbers"),
        ("remaining", "remaining_issue_numbers"),
    ):
        for number in planning.get(key, []):
            previous = batch_membership.get(number)
            if previous is not None:
                raise TriageError(
                    f"issue #{number} is assigned to multiple planning batches: "
                    f"{previous}, {batch}"
                )
            batch_membership[number] = batch


def validate_desired_issue(entry: Any, label: str) -> None:
    if not isinstance(entry, dict):
        raise TriageError(f"{label} must be a table")
    number = entry.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise TriageError(f"{label}.number must be a positive integer")
    batch = entry.get("batch", "bootstrap")
    if not isinstance(batch, str) or not batch:
        raise TriageError(f"{label}.batch must be a non-empty string")
    for key in ("labels_add", "labels_remove"):
        values = entry.get(key, [])
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise TriageError(f"{label}.{key} must be a list of non-empty strings")
        folded = [item.casefold() for item in values]
        if len(folded) != len(set(folded)):
            raise TriageError(f"{label}.{key} contains duplicate labels")
    added = {item.casefold() for item in entry.get("labels_add", [])}
    removed = {item.casefold() for item in entry.get("labels_remove", [])}
    overlap = sorted(added & removed)
    if overlap:
        raise TriageError(
            f"{label} adds and removes the same label(s): {', '.join(overlap)}"
        )
    milestone = entry.get("milestone_number")
    if milestone is not None and (
        not isinstance(milestone, int) or isinstance(milestone, bool) or milestone < 0
    ):
        raise TriageError(
            f"{label}.milestone_number must be a non-negative integer or omitted"
        )


def policy_repo(policy: Mapping[str, Any]) -> str:
    repository = require_mapping(policy.get("repository"), "policy repository")
    return validate_repo_name(f"{repository['owner']}/{repository['name']}")


def normalize_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for value in raw:
        if isinstance(value, str):
            name = value
        elif isinstance(value, dict):
            name = value.get("name")
        else:
            continue
        if isinstance(name, str) and name:
            labels.append(name)
    return sorted(set(labels), key=str.casefold)


def normalize_assignees(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    result = []
    for value in raw:
        if isinstance(value, dict) and isinstance(value.get("login"), str):
            result.append(value["login"])
    return sorted(set(result), key=str.casefold)


def normalize_milestone_ref(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    number = raw.get("number")
    if not isinstance(number, int):
        return None
    return {
        "number": number,
        "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
        "state": raw.get("state") if isinstance(raw.get("state"), str) else "",
        "due_on": raw.get("due_on") if isinstance(raw.get("due_on"), str) else None,
        "html_url": raw.get("html_url")
        if isinstance(raw.get("html_url"), str)
        else None,
    }


def normalize_issue(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "number": raw.get("number"),
        "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
        "state": raw.get("state") if isinstance(raw.get("state"), str) else "",
        "state_reason": raw.get("state_reason")
        if isinstance(raw.get("state_reason"), str)
        else None,
        "author": (raw.get("user") or {}).get("login")
        if isinstance(raw.get("user"), dict)
        else None,
        "assignees": normalize_assignees(raw.get("assignees")),
        "labels": normalize_labels(raw.get("labels")),
        "milestone": normalize_milestone_ref(raw.get("milestone")),
        "created_at": raw.get("created_at")
        if isinstance(raw.get("created_at"), str)
        else None,
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else None,
        "closed_at": raw.get("closed_at")
        if isinstance(raw.get("closed_at"), str)
        else None,
        "comments": raw.get("comments") if isinstance(raw.get("comments"), int) else 0,
        "locked": bool(raw.get("locked")),
        "body": raw.get("body") if isinstance(raw.get("body"), str) else "",
        "html_url": raw.get("html_url")
        if isinstance(raw.get("html_url"), str)
        else raw.get("url"),
    }


def normalize_tracker_pull(raw: Mapping[str, Any]) -> dict[str, Any]:
    result = normalize_issue(raw)
    pull = raw.get("pull_request") if isinstance(raw.get("pull_request"), dict) else {}
    result.update(
        {
            "draft": bool(raw.get("draft")),
            "merged_at": pull.get("merged_at")
            if isinstance(pull.get("merged_at"), str)
            else None,
        }
    )
    return result


def normalize_open_pull(raw: Mapping[str, Any]) -> dict[str, Any]:
    base = raw.get("base") if isinstance(raw.get("base"), dict) else {}
    head = raw.get("head") if isinstance(raw.get("head"), dict) else {}
    repo = head.get("repo") if isinstance(head.get("repo"), dict) else {}
    return {
        "number": raw.get("number"),
        "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
        "state": raw.get("state") if isinstance(raw.get("state"), str) else "",
        "draft": bool(raw.get("draft")),
        "author": (raw.get("user") or {}).get("login")
        if isinstance(raw.get("user"), dict)
        else None,
        "labels": normalize_labels(raw.get("labels")),
        "milestone": normalize_milestone_ref(raw.get("milestone")),
        "base_ref": base.get("ref") if isinstance(base.get("ref"), str) else None,
        "head_ref": head.get("ref") if isinstance(head.get("ref"), str) else None,
        "head_repo": repo.get("full_name")
        if isinstance(repo.get("full_name"), str)
        else None,
        "created_at": raw.get("created_at")
        if isinstance(raw.get("created_at"), str)
        else None,
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else None,
        "html_url": raw.get("html_url")
        if isinstance(raw.get("html_url"), str)
        else raw.get("url"),
        "body": raw.get("body") if isinstance(raw.get("body"), str) else "",
    }


def normalize_label(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": raw.get("name") if isinstance(raw.get("name"), str) else "",
        "description": raw.get("description")
        if isinstance(raw.get("description"), str)
        else "",
        "color": raw.get("color") if isinstance(raw.get("color"), str) else "",
        "default": bool(raw.get("default")),
    }


def normalize_milestone(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "number": raw.get("number"),
        "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
        "description": raw.get("description")
        if isinstance(raw.get("description"), str)
        else "",
        "state": raw.get("state") if isinstance(raw.get("state"), str) else "",
        "open_issues": raw.get("open_issues")
        if isinstance(raw.get("open_issues"), int)
        else 0,
        "closed_issues": raw.get("closed_issues")
        if isinstance(raw.get("closed_issues"), int)
        else 0,
        "due_on": raw.get("due_on") if isinstance(raw.get("due_on"), str) else None,
        "created_at": raw.get("created_at")
        if isinstance(raw.get("created_at"), str)
        else None,
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else None,
        "closed_at": raw.get("closed_at")
        if isinstance(raw.get("closed_at"), str)
        else None,
        "html_url": raw.get("html_url")
        if isinstance(raw.get("html_url"), str)
        else None,
    }


def normalize_repository(raw: Mapping[str, Any], repo: str) -> dict[str, Any]:
    owner, name = repo.split("/", 1)
    return {
        "full_name": raw.get("full_name")
        if isinstance(raw.get("full_name"), str)
        else repo,
        "owner": owner,
        "name": name,
        "default_branch": raw.get("default_branch")
        if isinstance(raw.get("default_branch"), str)
        else None,
        "visibility": raw.get("visibility")
        if isinstance(raw.get("visibility"), str)
        else None,
        "archived": bool(raw.get("archived")),
        "disabled": bool(raw.get("disabled")),
        "has_issues": bool(raw.get("has_issues", True)),
        "html_url": raw.get("html_url")
        if isinstance(raw.get("html_url"), str)
        else f"https://github.com/{repo}",
        "updated_at": raw.get("updated_at")
        if isinstance(raw.get("updated_at"), str)
        else None,
        "pushed_at": raw.get("pushed_at")
        if isinstance(raw.get("pushed_at"), str)
        else None,
    }


def item_map(snapshot: Mapping[str, Any]) -> dict[int, tuple[str, dict[str, Any]]]:
    result: dict[int, tuple[str, dict[str, Any]]] = {}
    for kind, collection_name in (
        ("issue", "issues"),
        ("pull_request", "pull_requests"),
    ):
        values = snapshot.get(collection_name, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("number"), int):
                result[int(item["number"])] = (kind, item)
    return result


def issue_map(snapshot: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for issue in (
        snapshot.get("issues", []) if isinstance(snapshot.get("issues"), list) else []
    ):
        if isinstance(issue, dict) and isinstance(issue.get("number"), int):
            result[int(issue["number"])] = issue
    return result


def pull_map(snapshot: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for pull in (
        snapshot.get("pull_requests", [])
        if isinstance(snapshot.get("pull_requests"), list)
        else []
    ):
        if isinstance(pull, dict) and isinstance(pull.get("number"), int):
            result[int(pull["number"])] = pull
    return result


def refs_in_text(text: str) -> set[int]:
    return {int(match.group("number")) for match in ISSUE_REF_RE.finditer(text or "")}


def relationship_refs(issue: Mapping[str, Any]) -> dict[str, set[int]]:
    relations: dict[str, set[int]] = defaultdict(set)
    body = issue.get("body") if isinstance(issue.get("body"), str) else ""
    for match in RELATION_LINE_RE.finditer(body):
        kind = " ".join(match.group("kind").casefold().split())
        relations[kind].update(refs_in_text(match.group("refs")))
    return dict(relations)


def dependency_refs(issue: Mapping[str, Any]) -> set[int]:
    relations = relationship_refs(issue)
    result: set[int] = set()
    for key in ("depends on", "blocked by", "requires", "must land after"):
        result.update(relations.get(key, set()))
    return result


def build_dependency_edges(snapshot: Mapping[str, Any]) -> dict[int, set[int]]:
    issues = issue_map(snapshot)
    open_numbers = {
        number for number, issue in issues.items() if issue.get("state") == "open"
    }
    edges: dict[int, set[int]] = {number: set() for number in open_numbers}
    for number in sorted(open_numbers):
        relations = relationship_refs(issues[number])
        for key in ("depends on", "blocked by", "requires", "must land after"):
            edges[number].update(
                ref for ref in relations.get(key, set()) if ref in open_numbers
            )
        for blocker in relations.get("blocks", set()) | relations.get(
            "must land before", set()
        ):
            if blocker in open_numbers:
                edges[blocker].add(number)
    return edges


def find_cycles(edges: Mapping[int, set[int]]) -> list[list[int]]:
    cycles: list[list[int]] = []
    visiting: set[int] = set()
    visited: set[int] = set()
    stack: list[int] = []

    def visit(node: int) -> None:
        if node in visiting:
            index = stack.index(node)
            cycles.append(stack[index:] + [node])
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

    canonical: dict[tuple[int, ...], list[int]] = {}
    for cycle in cycles:
        ring = cycle[:-1]
        if not ring:
            continue
        rotations = [tuple(ring[index:] + ring[:index]) for index in range(len(ring))]
        key = min(rotations)
        canonical[key] = list(key) + [key[0]]
    return [canonical[key] for key in sorted(canonical)]


def markdown_section(text: str, heading: str) -> str | None:
    wanted = heading.strip().casefold()
    matches = list(MARKDOWN_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        title = re.sub(r"\s+", " ", match.group("title").strip()).casefold()
        if title != wanted:
            continue
        level = len(match.group("marks"))
        end = len(text)
        for following in matches[index + 1 :]:
            if len(following.group("marks")) <= level:
                end = following.start()
                break
        return text[match.end() : end]
    return None


def derive_release_issue_numbers(
    snapshot: Mapping[str, Any], policy: Mapping[str, Any]
) -> set[int]:
    release = (
        policy.get("release", {}) if isinstance(policy.get("release"), dict) else {}
    )
    issues = issue_map(snapshot)
    selected: set[int] = {
        int(value)
        for value in release.get("additional_issue_numbers", [])
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    }
    epic_numbers = [
        int(value)
        for value in release.get("epic_numbers", [])
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    ]
    headings = [
        str(value)
        for value in release.get("section_headings", [])
        if isinstance(value, str)
    ]
    include_epics = bool(release.get("include_epics", True))
    for epic_number in epic_numbers:
        epic = issues.get(epic_number)
        if epic is None:
            continue
        if include_epics:
            selected.add(epic_number)
        body = epic.get("body") if isinstance(epic.get("body"), str) else ""
        for heading in headings:
            section = markdown_section(body, heading)
            if section is not None:
                selected.update(refs_in_text(section))

    if bool(release.get("include_dependency_closure", True)):
        queue = list(selected)
        while queue:
            number = queue.pop()
            issue = issues.get(number)
            if issue is None:
                continue
            for dependency in dependency_refs(issue):
                if dependency not in selected:
                    selected.add(dependency)
                    queue.append(dependency)

    return {
        number
        for number in selected
        if number in issues and issues[number].get("state") == "open"
    }


def collect_project_snapshot(
    client: GitHubClient, policy: Mapping[str, Any]
) -> dict[str, Any]:
    project = (
        policy.get("project", {}) if isinstance(policy.get("project"), dict) else {}
    )
    if not project.get("enabled", False):
        return {"configured": False, "status": "not_configured"}

    owner_type = project["owner_type"]
    root_field = "user" if owner_type == "user" else "organization"
    query = f"""
query($login: String!, $number: Int!, $after: String) {{
  {root_field}(login: $login) {{
    projectV2(number: $number) {{
      id
      number
      title
      closed
      url
      fields(first: 100) {{
        nodes {{
          ... on ProjectV2FieldCommon {{ id name dataType }}
        }}
      }}
      items(first: 100, after: $after) {{
        nodes {{
          id
          type
          content {{
            __typename
            ... on Issue {{ number title url repository {{ nameWithOwner }} }}
            ... on PullRequest {{ number title url repository {{ nameWithOwner }} }}
            ... on DraftIssue {{ title }}
          }}
        }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}
  }}
}}
""".strip()
    variables: dict[str, Any] = {
        "login": project["owner"],
        "number": project["number"],
        "after": None,
    }
    pages: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    metadata: dict[str, Any] | None = None
    while True:
        raw = client.graphql(query, variables)
        if not isinstance(raw, dict):
            raise TriageError("GitHub Project query returned a non-object response")
        if raw.get("errors"):
            raise TriageError(
                "GitHub Project query failed: "
                + sanitize_cli_error(canonical_json(raw["errors"]))
            )
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        owner_data = (
            data.get(root_field) if isinstance(data.get(root_field), dict) else None
        )
        project_data = (
            owner_data.get("projectV2") if isinstance(owner_data, dict) else None
        )
        if not isinstance(project_data, dict):
            raise TriageError(
                "configured GitHub Project was not found or is not visible"
            )
        if metadata is None:
            metadata = {
                "id": project_data.get("id"),
                "number": project_data.get("number"),
                "title": project_data.get("title"),
                "closed": bool(project_data.get("closed")),
                "url": project_data.get("url"),
            }
            field_nodes = (
                (project_data.get("fields") or {}).get("nodes")
                if isinstance(project_data.get("fields"), dict)
                else []
            )
            if isinstance(field_nodes, list):
                fields = [dict(node) for node in field_nodes if isinstance(node, dict)]
        items = (
            project_data.get("items")
            if isinstance(project_data.get("items"), dict)
            else {}
        )
        nodes = items.get("nodes") if isinstance(items.get("nodes"), list) else []
        pages.extend(dict(node) for node in nodes if isinstance(node, dict))
        page_info = (
            items.get("pageInfo") if isinstance(items.get("pageInfo"), dict) else {}
        )
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise TriageError("GitHub Project pagination did not return an end cursor")
        variables["after"] = cursor

    assert metadata is not None
    return {
        "configured": True,
        "status": "ok",
        "owner_type": owner_type,
        "owner": project["owner"],
        **metadata,
        "fields": sorted(
            fields, key=lambda item: str(item.get("name") or "").casefold()
        ),
        "items": sorted(pages, key=lambda item: str(item.get("id") or "")),
    }


def build_label_usage(
    labels: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    spelling: dict[str, str] = {}
    for label in labels:
        name = label.get("name")
        if isinstance(name, str) and name:
            spelling.setdefault(name.casefold(), name)
    for kind, items in (("issue", issues), ("pull_request", pulls)):
        for item in items:
            state = str(item.get("state") or "")
            bucket = f"{state}_{kind}s"
            for name in (
                item.get("labels", []) if isinstance(item.get("labels"), list) else []
            ):
                if not isinstance(name, str):
                    continue
                folded = name.casefold()
                spelling.setdefault(folded, name)
                counts[folded][bucket] += 1
                counts[folded]["total"] += 1
    result = []
    for folded in sorted(set(spelling) | set(counts)):
        counter = counts[folded]
        result.append(
            {
                "name": spelling.get(folded, folded),
                "open_issues": counter.get("open_issues", 0),
                "closed_issues": counter.get("closed_issues", 0),
                "open_pull_requests": counter.get("open_pull_requests", 0),
                "closed_pull_requests": counter.get("closed_pull_requests", 0),
                "total": counter.get("total", 0),
            }
        )
    return result


def build_milestone_usage(
    milestones: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[int, Counter[str]] = defaultdict(Counter)
    known = {
        int(item["number"]): item
        for item in milestones
        if isinstance(item.get("number"), int)
    }
    for kind, items in (("issue", issues), ("pull_request", pulls)):
        for item in items:
            milestone = item.get("milestone")
            if not isinstance(milestone, dict) or not isinstance(
                milestone.get("number"), int
            ):
                continue
            number = int(milestone["number"])
            bucket = f"{item.get('state')}_{kind}s"
            counts[number][bucket] += 1
            counts[number]["total"] += 1
    result: list[dict[str, Any]] = []
    for number in sorted(set(known) | set(counts)):
        milestone = known.get(number, {"number": number, "title": "", "state": ""})
        counter = counts[number]
        result.append(
            {
                "number": number,
                "title": milestone.get("title") or "",
                "state": milestone.get("state") or "",
                "open_issues": counter.get("open_issues", 0),
                "closed_issues": counter.get("closed_issues", 0),
                "open_pull_requests": counter.get("open_pull_requests", 0),
                "closed_pull_requests": counter.get("closed_pull_requests", 0),
                "total_assignments": counter.get("total", 0),
            }
        )
    return result


def snapshot_without_digest(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"generated_at", "snapshot_sha256"}
    }


def validate_snapshot(
    snapshot: Mapping[str, Any],
    *,
    repository: str | None = None,
    policy_sha256: str | None = None,
) -> None:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise TriageError(
            f"unsupported snapshot schema_version: {snapshot.get('schema_version')}"
        )
    repo_data = snapshot.get("repository")
    if not isinstance(repo_data, dict):
        raise TriageError("snapshot repository must be an object")
    full_name = validate_repo_name(str(repo_data.get("full_name") or ""))
    if repository is not None and full_name != repository:
        raise TriageError(
            f"snapshot repository {full_name!r} does not match {repository!r}"
        )
    generated_at = snapshot.get("generated_at")
    if parse_timestamp(generated_at) is None:
        raise TriageError("snapshot generated_at must be an ISO-8601 timestamp")
    for key in (
        "issues",
        "pull_requests",
        "open_pull_requests",
        "labels",
        "label_usage",
        "milestones",
        "milestone_usage",
        "referenced_closed_items",
        "recently_closed_items",
    ):
        if not isinstance(snapshot.get(key), list):
            raise TriageError(f"snapshot {key} must be a list")
    project = snapshot.get("project")
    if not isinstance(project, dict):
        raise TriageError("snapshot project must be an object")
    if policy_sha256 is not None and snapshot.get("policy_sha256") != policy_sha256:
        raise TriageError("snapshot was generated under a different policy")
    actual = sha256_json(snapshot_without_digest(snapshot))
    if snapshot.get("snapshot_sha256") != actual:
        raise TriageError(f"snapshot digest mismatch: expected {actual}")


def collect_snapshot(
    runner: Runner,
    repo: str,
    policy: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = validate_repo_name(repo)
    client = GitHubClient(runner=runner, repo=repo)
    repo_raw = client.api(f"/repos/{repo}")
    if not isinstance(repo_raw, dict):
        raise TriageError("repository metadata response was not an object")

    tracker_raw = client.api_paginated(
        f"/repos/{repo}/issues",
        query={"state": "all", "per_page": 100, "sort": "updated", "direction": "desc"},
    )
    labels_raw = client.api_paginated(f"/repos/{repo}/labels", query={"per_page": 100})
    milestones_raw = client.api_paginated(
        f"/repos/{repo}/milestones",
        query={"state": "all", "per_page": 100},
    )
    open_pulls_raw = client.api_paginated(
        f"/repos/{repo}/pulls",
        query={
            "state": "open",
            "per_page": 100,
            "sort": "updated",
            "direction": "desc",
        },
    )

    issues: list[dict[str, Any]] = []
    pull_requests: list[dict[str, Any]] = []
    for raw in tracker_raw:
        if not isinstance(raw, dict) or not isinstance(raw.get("number"), int):
            continue
        if isinstance(raw.get("pull_request"), dict):
            pull_requests.append(normalize_tracker_pull(raw))
        else:
            issues.append(normalize_issue(raw))
    labels = [normalize_label(raw) for raw in labels_raw if isinstance(raw, dict)]
    milestones = [
        normalize_milestone(raw) for raw in milestones_raw if isinstance(raw, dict)
    ]
    open_pulls = [
        normalize_open_pull(raw) for raw in open_pulls_raw if isinstance(raw, dict)
    ]

    issues.sort(key=lambda item: int(item.get("number") or 0))
    pull_requests.sort(key=lambda item: int(item.get("number") or 0))
    labels.sort(key=lambda item: str(item.get("name") or "").casefold())
    milestones.sort(key=lambda item: int(item.get("number") or 0))
    open_pulls.sort(key=lambda item: int(item.get("number") or 0))

    open_issue_refs: set[int] = set()
    for issue in issues:
        if issue.get("state") == "open":
            open_issue_refs.update(refs_in_text(str(issue.get("body") or "")))
    all_items = {
        int(item["number"]): ("issue", item)
        for item in issues
        if isinstance(item.get("number"), int)
    }
    all_items.update(
        {
            int(item["number"]): ("pull_request", item)
            for item in pull_requests
            if isinstance(item.get("number"), int)
        }
    )
    referenced_closed = []
    for number in sorted(open_issue_refs):
        record = all_items.get(number)
        if record is None:
            continue
        kind, item = record
        if item.get("state") == "closed":
            referenced_closed.append({"kind": kind, **item})

    generated = now or utc_now()
    audit_policy = (
        policy.get("audit", {}) if isinstance(policy.get("audit"), dict) else {}
    )
    recent_days = audit_policy.get("recent_closed_days", 90)
    if (
        not isinstance(recent_days, int)
        or isinstance(recent_days, bool)
        or recent_days < 0
    ):
        recent_days = 90
    cutoff = generated - timedelta(days=recent_days)
    recent_closed: list[dict[str, Any]] = []
    for kind, items in (("issue", issues), ("pull_request", pull_requests)):
        for item in items:
            closed_at = parse_timestamp(item.get("closed_at"))
            if (
                item.get("state") == "closed"
                and closed_at is not None
                and closed_at >= cutoff
            ):
                recent_closed.append({"kind": kind, **item})
    recent_closed.sort(
        key=lambda item: (
            str(item.get("closed_at") or ""),
            int(item.get("number") or 0),
        ),
        reverse=True,
    )

    project_snapshot = collect_project_snapshot(client, policy)
    snapshot: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": isoformat_utc(generated),
        "repository": normalize_repository(repo_raw, repo),
        "policy_sha256": sha256_json(policy),
        "issues": issues,
        "pull_requests": pull_requests,
        "open_pull_requests": open_pulls,
        "labels": labels,
        "label_usage": build_label_usage(labels, issues, pull_requests),
        "milestones": milestones,
        "milestone_usage": build_milestone_usage(milestones, issues, pull_requests),
        "referenced_closed_items": referenced_closed,
        "recently_closed_items": recent_closed,
        "project": project_snapshot,
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot_without_digest(snapshot))
    validate_snapshot(
        snapshot,
        repository=repo,
        policy_sha256=sha256_json(policy),
    )
    return snapshot


def classify_labels(policy: Mapping[str, Any]) -> dict[str, set[str]]:
    configured = policy.get("labels", {})
    if not isinstance(configured, dict):
        return {}
    return {
        str(key): {str(item) for item in value if isinstance(item, str)}
        for key, value in configured.items()
        if isinstance(value, list)
    }


def planning_batch_for_issue(policy: Mapping[str, Any], issue_number: int) -> str:
    planning = (
        policy.get("planning", {}) if isinstance(policy.get("planning"), dict) else {}
    )
    configured = (
        ("bootstrap", planning.get("bootstrap_issue_numbers", [])),
        ("canary", planning.get("canary_issue_numbers", [])),
        ("remaining", planning.get("remaining_issue_numbers", [])),
    )
    for batch, values in configured:
        if isinstance(values, list) and issue_number in values:
            return batch
    default = planning.get("default_batch", "remaining")
    return str(default) if isinstance(default, str) and default else "remaining"


def inferred_type_label(title: str, policy: Mapping[str, Any]) -> str | None:
    configured = policy.get("type_inference", {})
    pairs: list[tuple[str, str]] = []
    if isinstance(configured, dict):
        raw_prefixes = configured.get("prefixes", {})
        if isinstance(raw_prefixes, dict):
            for label, prefixes in raw_prefixes.items():
                if isinstance(label, str) and isinstance(prefixes, list):
                    pairs.extend(
                        (str(prefix).casefold(), label)
                        for prefix in prefixes
                        if isinstance(prefix, str)
                    )
    if not pairs:
        pairs = list(TYPE_LABEL_PREFIX_DEFAULTS)
    folded = title.strip().casefold()
    for prefix, label in sorted(pairs, key=lambda item: len(item[0]), reverse=True):
        if folded.startswith(prefix):
            return label
    return None


def latest_progress_entry(path: Path) -> tuple[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    matches = list(PROGRESS_DATE_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    end = len(text)
    next_match = PROGRESS_DATE_RE.search(text, match.end())
    if next_match is not None:
        end = next_match.start()
    return match.group("date"), text[match.start() : end]


def finding_sort_key(finding: Mapping[str, Any]) -> tuple[int, int, str, str]:
    issue = finding.get("issue")
    issue_number = int(issue) if isinstance(issue, int) else 0
    return (
        SEVERITY_ORDER.get(str(finding.get("level")), 99),
        issue_number,
        str(finding.get("code") or ""),
        str(finding.get("message") or ""),
    )


def audit_snapshot(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    issue_filter: set[int] | None = None,
    root: Path = ROOT,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> list[dict[str, Any]]:
    active_policy = repo_policy or repo_config.load_repo_policy()
    findings: list[dict[str, Any]] = []
    issues_by_number = issue_map(snapshot)
    pulls_by_number = pull_map(snapshot)
    items_by_number = item_map(snapshot)
    audit_policy = (
        policy.get("audit", {}) if isinstance(policy.get("audit"), dict) else {}
    )
    label_classes = classify_labels(policy)
    allowed_labels = set().union(*label_classes.values()) if label_classes else set()

    if issue_filter is not None:
        unknown_filter = sorted(
            number for number in issue_filter if number not in issues_by_number
        )
        if unknown_filter:
            raise TriageError(
                f"issue filter contains unknown issue number(s): {unknown_filter}"
            )

    def add(
        level: str,
        code: str,
        message: str,
        *,
        issue: int | None = None,
        data: Any = None,
        suggested_operation: dict[str, Any] | None = None,
    ) -> None:
        if issue_filter is not None and issue is not None and issue not in issue_filter:
            return
        record = {
            "level": level,
            "code": code,
            "message": message,
            "issue": issue,
            "data": data,
        }
        if suggested_operation is not None:
            record["suggested_operation"] = suggested_operation
        findings.append(record)

    label_names = [
        str(label.get("name") or "")
        for label in snapshot.get("labels", [])
        if isinstance(label, dict)
    ]
    folded_counts = Counter(name.casefold() for name in label_names if name)
    for folded, count in sorted(folded_counts.items()):
        if count > 1:
            spellings = sorted(
                name for name in label_names if name.casefold() == folded
            )
            add(
                "error",
                "duplicate-label",
                "duplicate label name after case normalization",
                data=spellings,
            )

    live_label_folded = {name.casefold(): name for name in label_names if name}
    for expected in sorted(allowed_labels, key=str.casefold):
        if expected.casefold() not in live_label_folded:
            add(
                "warning",
                "policy-label-missing",
                f"policy label does not exist in GitHub: {expected}",
                data=expected,
            )

    if allowed_labels:
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            unknown = sorted(
                (
                    label
                    for label in issue.get("labels", [])
                    if isinstance(label, str) and label not in allowed_labels
                ),
                key=str.casefold,
            )
            if unknown:
                add(
                    "info",
                    "unclassified-label",
                    f"open issue has labels outside current policy: {', '.join(unknown)}",
                    issue=issue.get("number")
                    if isinstance(issue.get("number"), int)
                    else None,
                    data=unknown,
                )

    if audit_policy.get("check_title_label_alignment", True):
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            number = (
                issue.get("number") if isinstance(issue.get("number"), int) else None
            )
            if number is None:
                continue
            inferred = inferred_type_label(str(issue.get("title") or ""), policy)
            present_labels = set(issue.get("labels", []))
            if inferred is None or inferred in present_labels:
                continue
            can_plan = inferred.casefold() in live_label_folded
            add(
                "warning",
                "title-label-mismatch",
                f"issue title implies label {inferred!r}, but that label is absent",
                issue=number,
                data={
                    "inferred": inferred,
                    "labels": sorted(present_labels, key=str.casefold),
                },
                suggested_operation=(
                    {
                        "kind": "issue.labels.add",
                        "issue_number": number,
                        "labels": [live_label_folded[inferred.casefold()]],
                        "batch": planning_batch_for_issue(policy, number),
                        "reason": f"Add the title-inferred label {inferred!r}.",
                    }
                    if can_plan
                    else None
                ),
            )

    if audit_policy.get("require_open_issue_type_label", False):
        type_labels = label_classes.get("type", set())
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            number = (
                issue.get("number") if isinstance(issue.get("number"), int) else None
            )
            present = sorted(
                set(issue.get("labels", [])) & type_labels, key=str.casefold
            )
            if len(present) == 1:
                continue
            suggestion = None
            inferred = inferred_type_label(str(issue.get("title") or ""), policy)
            if (
                len(present) == 0
                and inferred in type_labels
                and inferred is not None
                and inferred.casefold() in live_label_folded
            ):
                suggestion = {
                    "kind": "issue.labels.add",
                    "issue_number": number,
                    "labels": [live_label_folded[inferred.casefold()]],
                    "batch": planning_batch_for_issue(policy, number),
                    "reason": f"Add the title-inferred type label {inferred!r}.",
                }
            add(
                "error",
                "type-label-count",
                "open issue must have exactly one type label",
                issue=number,
                data={"present": present, "inferred": inferred},
                suggested_operation=suggestion,
            )

    if audit_policy.get("check_issue_references", True):
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            refs = refs_in_text(str(issue.get("body") or ""))
            missing = sorted(ref for ref in refs if ref not in items_by_number)
            if missing:
                add(
                    "warning",
                    "missing-tracker-reference",
                    f"issue body references tracker item(s) that do not exist: {missing}",
                    issue=issue.get("number")
                    if isinstance(issue.get("number"), int)
                    else None,
                    data=missing,
                )

    if audit_policy.get("check_closed_checklist_refs", True):
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            stale: list[dict[str, Any]] = []
            for match in UNCHECKED_LINE_RE.finditer(str(issue.get("body") or "")):
                for number in sorted(refs_in_text(match.group("body"))):
                    record = items_by_number.get(number)
                    if record is None:
                        continue
                    kind, target = record
                    if target.get("state") == "closed":
                        stale.append(
                            {
                                "number": number,
                                "kind": kind,
                                "state_reason": target.get("state_reason"),
                                "closed_at": target.get("closed_at"),
                            }
                        )
            if stale:
                add(
                    "warning",
                    "unchecked-closed-reference",
                    "open issue has unchecked checklist item(s) for closed tracker items",
                    issue=issue.get("number")
                    if isinstance(issue.get("number"), int)
                    else None,
                    data=stale,
                )

    if audit_policy.get("check_closed_dependencies", True):
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            closed_dependencies: list[dict[str, Any]] = []
            for dependency in sorted(dependency_refs(issue)):
                record = items_by_number.get(dependency)
                if record is None:
                    continue
                kind, target = record
                if target.get("state") == "closed":
                    closed_dependencies.append(
                        {
                            "number": dependency,
                            "kind": kind,
                            "state_reason": target.get("state_reason"),
                            "closed_at": target.get("closed_at"),
                        }
                    )
            if closed_dependencies:
                add(
                    "warning",
                    "closed-dependency-reference",
                    "open issue declares a dependency that is already closed",
                    issue=issue.get("number")
                    if isinstance(issue.get("number"), int)
                    else None,
                    data=closed_dependencies,
                )

    if audit_policy.get("check_missing_repo_paths", True):
        for issue in (
            snapshot.get("issues", [])
            if isinstance(snapshot.get("issues"), list)
            else []
        ):
            if not isinstance(issue, dict) or issue.get("state") != "open":
                continue
            missing_files: set[str] = set()
            missing_directories: set[str] = set()
            body = str(issue.get("body") or "")
            for ref in governance_common.parse_file_references(
                body, reference_roots=active_policy.paths.reference_roots
            ):
                path_text = ref.path
                if not path_text or (root / path_text).exists():
                    continue
                if ref.is_directory:
                    missing_directories.add(path_text)
                else:
                    missing_files.add(path_text)
            number = (
                issue.get("number") if isinstance(issue.get("number"), int) else None
            )
            if missing_files:
                add(
                    "warning",
                    "missing-repo-path",
                    "issue body references repository file paths that do not exist in this checkout",
                    issue=number,
                    data=sorted(missing_files),
                )
            if missing_directories:
                add(
                    "info",
                    "missing-repo-directory",
                    "issue body references repository directories that do not exist yet",
                    issue=number,
                    data=sorted(missing_directories),
                )

    if audit_policy.get("check_dependency_cycles", True):
        for cycle in find_cycles(build_dependency_edges(snapshot)):
            affected = set(cycle[:-1])
            if issue_filter is not None and not (affected & issue_filter):
                continue
            add(
                "error",
                "dependency-cycle",
                f"dependency cycle detected: {cycle}",
                data=cycle,
            )

    if audit_policy.get("check_release_milestone", True):
        release = (
            policy.get("release", {}) if isinstance(policy.get("release"), dict) else {}
        )
        milestone_number = release.get("milestone_number", 0)
        release_numbers = derive_release_issue_numbers(snapshot, policy)
        milestone_numbers = {
            int(item["number"])
            for item in snapshot.get("milestones", [])
            if isinstance(item, dict) and isinstance(item.get("number"), int)
        }
        if release_numbers and milestone_number <= 0:
            add(
                "warning",
                "release-milestone-unconfigured",
                "release issues were derived from policy, but release.milestone_number is not configured",
                data=sorted(release_numbers),
            )
        elif milestone_number > 0 and milestone_number not in milestone_numbers:
            add(
                "error",
                "release-milestone-missing",
                f"configured release milestone #{milestone_number} does not exist",
                data={
                    "milestone_number": milestone_number,
                    "issues": sorted(release_numbers),
                },
            )
        elif milestone_number > 0:
            for number in sorted(release_numbers):
                issue = issues_by_number[number]
                milestone = issue.get("milestone")
                current = (
                    milestone.get("number") if isinstance(milestone, dict) else None
                )
                if current == milestone_number:
                    continue
                add(
                    "warning",
                    "release-issue-milestone",
                    f"release-tracked issue is not assigned to milestone #{milestone_number}",
                    issue=number,
                    data={"current": current, "expected": milestone_number},
                    suggested_operation={
                        "kind": "issue.milestone.set",
                        "issue_number": number,
                        "milestone_number": milestone_number,
                        "batch": planning_batch_for_issue(policy, number),
                        "reason": f"Assign release-tracked issue #{number} to milestone #{milestone_number}.",
                    },
                )

    if audit_policy.get("check_open_pr_base", True):
        repository = (
            snapshot.get("repository")
            if isinstance(snapshot.get("repository"), dict)
            else {}
        )
        expected_base = repository.get("default_branch") or (
            policy.get("repository", {}) or {}
        ).get("default_branch")
        for pull in (
            snapshot.get("open_pull_requests", [])
            if isinstance(snapshot.get("open_pull_requests"), list)
            else []
        ):
            if not isinstance(pull, dict):
                continue
            if expected_base and pull.get("base_ref") != expected_base:
                add(
                    "warning",
                    "open-pr-base",
                    f"open pull request targets {pull.get('base_ref')!r}, expected {expected_base!r}",
                    data={
                        "pull_request": pull.get("number"),
                        "base_ref": pull.get("base_ref"),
                    },
                )

    if audit_policy.get("check_project_configuration", True):
        project = snapshot.get("project")
        if (
            isinstance(project, dict)
            and project.get("configured")
            and project.get("status") != "ok"
        ):
            add(
                "error",
                "project-unavailable",
                "configured GitHub Project could not be read",
                data=project,
            )
        elif isinstance(project, dict) and not project.get("configured"):
            add(
                "info",
                "project-not-configured",
                "GitHub Project audits are disabled until an exact project identity is configured",
            )

    if audit_policy.get("check_progress_log_staleness", True):
        progress_log = root / active_policy.repository.progress_log_path
        progress = latest_progress_entry(progress_log)
        if progress is None:
            add(
                "warning",
                "progress-log-missing",
                f"{active_policy.repository.progress_log_path} has no dated entry",
            )
        else:
            latest_date, section = progress
            tracker_updates: list[dict[str, Any]] = []
            for kind, values in (
                ("issue", snapshot.get("issues", [])),
                ("pull_request", snapshot.get("pull_requests", [])),
            ):
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict) or not isinstance(
                        item.get("number"), int
                    ):
                        continue
                    if (
                        kind == "issue"
                        and issue_filter is not None
                        and item["number"] not in issue_filter
                    ):
                        continue
                    updated = item.get("updated_at")
                    if isinstance(updated, str) and updated[:10] > latest_date:
                        tracker_updates.append(
                            {
                                "kind": kind,
                                "number": item["number"],
                                "updated_at": updated,
                                "state": item.get("state"),
                            }
                        )
            if tracker_updates:
                tracker_updates.sort(
                    key=lambda item: (str(item["updated_at"]), int(item["number"])),
                    reverse=True,
                )
                add(
                    "warning",
                    "progress-log-stale",
                    f"progress log latest entry is {latest_date}, but live tracker items were updated later",
                    data=tracker_updates[:100],
                )

            declared = list(DECLARED_OPEN_RE.finditer(section))
            for match in declared:
                declared_numbers = refs_in_text(match.group("refs"))
                kind = match.group("kind").casefold()
                live_map = (
                    issues_by_number if kind.startswith("issue") else pulls_by_number
                )
                closed = sorted(
                    number
                    for number in declared_numbers
                    if number in live_map and live_map[number].get("state") != "open"
                )
                missing = sorted(
                    number for number in declared_numbers if number not in live_map
                )
                if closed or missing:
                    add(
                        "warning",
                        "progress-log-state-drift",
                        f"latest progress entry declares open {kind}, but live state differs",
                        data={
                            "declared": sorted(declared_numbers),
                            "closed": closed,
                            "missing": missing,
                        },
                    )

    findings.sort(key=finding_sort_key)
    return findings


def print_audit(findings: Sequence[Mapping[str, Any]]) -> int:
    counts = Counter(str(finding.get("level")) for finding in findings)
    for finding in findings:
        issue = f" #{finding['issue']}" if isinstance(finding.get("issue"), int) else ""
        print(
            f"[{str(finding.get('level')).upper()}] {finding.get('code')}{issue}: {finding.get('message')}"
        )
        if finding.get("data") is not None:
            print(
                f"  data: {json.dumps(finding['data'], sort_keys=True, ensure_ascii=True)}"
            )
        if finding.get("suggested_operation") is not None:
            print(
                "  suggested operation: "
                + json.dumps(
                    finding["suggested_operation"], sort_keys=True, ensure_ascii=True
                )
            )
    print(
        "audit summary: "
        f"{counts.get('error', 0)} error(s), "
        f"{counts.get('warning', 0)} warning(s), "
        f"{counts.get('info', 0)} info item(s)"
    )
    return 1 if counts.get("error", 0) else 0


def operation_without_id(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in operation.items() if key != "operation_id"}


def operation_id(operation: Mapping[str, Any]) -> str:
    return "op1:" + sha256_json(operation_without_id(operation))[:24]


def make_operation(
    *,
    kind: str,
    repository: str,
    issue: Mapping[str, Any],
    batch: str,
    reason: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    request: Mapping[str, Any],
    destructive: bool = False,
) -> dict[str, Any]:
    if kind in FORBIDDEN_OPERATION_KINDS or kind not in SUPPORTED_OPERATION_KINDS:
        raise TriageError(f"unsupported or forbidden operation kind: {kind}")
    number = issue.get("number")
    if not isinstance(number, int):
        raise TriageError("operation target issue number is missing")
    operation: dict[str, Any] = {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "kind": kind,
        "batch": batch,
        "destructive": destructive,
        "reason": reason,
        "target": {"repository": repository, "issue_number": number},
        "before": dict(before),
        "after": dict(after),
        "preconditions": {
            "issue_state": issue.get("state"),
            "issue_number": number,
        },
        "request": dict(request),
    }
    operation["operation_id"] = operation_id(operation)
    return operation


def operation_from_suggestion(
    suggestion: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    issues = issue_map(snapshot)
    repository = (
        (snapshot.get("repository") or {}).get("full_name")
        if isinstance(snapshot.get("repository"), dict)
        else None
    )
    if not isinstance(repository, str) or not repository:
        raise TriageError("snapshot repository.full_name is missing")
    number = suggestion.get("issue_number")
    if not isinstance(number, int) or number not in issues:
        return []
    issue = issues[number]
    kind = suggestion.get("kind")
    batch = suggestion.get("batch") or "bootstrap"
    reason = suggestion.get("reason") or "Apply explicit governance policy."
    if (
        not isinstance(kind, str)
        or not isinstance(batch, str)
        or not isinstance(reason, str)
    ):
        raise TriageError("invalid suggested operation")

    if kind == "issue.milestone.set":
        desired = suggestion.get("milestone_number")
        if not isinstance(desired, int) or desired <= 0:
            raise TriageError(
                "milestone set suggestion requires a positive milestone_number"
            )
        milestone_numbers = {
            int(item["number"])
            for item in snapshot.get("milestones", [])
            if isinstance(item, dict) and isinstance(item.get("number"), int)
        }
        if desired not in milestone_numbers:
            raise TriageError(
                f"desired milestone #{desired} does not exist in the snapshot"
            )
        current_ref = issue.get("milestone")
        current = current_ref.get("number") if isinstance(current_ref, dict) else None
        if current == desired:
            return []
        return [
            make_operation(
                kind=kind,
                repository=repository,
                issue=issue,
                batch=batch,
                reason=reason,
                before={"milestone_number": current},
                after={"milestone_number": desired},
                request={
                    "transport": "rest",
                    "method": "PATCH",
                    "path": f"/repos/{repository}/issues/{number}",
                    "body": {"milestone": desired},
                },
                destructive=current is not None,
            )
        ]

    if kind in {"issue.labels.add", "issue.labels.remove"}:
        labels = suggestion.get("labels")
        if not isinstance(labels, list) or not all(
            isinstance(item, str) and item for item in labels
        ):
            raise TriageError(f"{kind} suggestion requires labels")
        live_labels = {
            str(item.get("name") or "").casefold(): str(item.get("name") or "")
            for item in snapshot.get("labels", [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and item.get("name")
        }
        missing_live = sorted(
            label for label in labels if label.casefold() not in live_labels
        )
        if kind == "issue.labels.add" and missing_live:
            raise TriageError(
                "cannot plan label membership for undefined label(s): "
                + ", ".join(missing_live)
            )
        labels = [live_labels.get(label.casefold(), label) for label in labels]
        current = set(issue.get("labels", []))
        desired_labels = sorted(set(labels), key=str.casefold)
        if kind == "issue.labels.add":
            effective = [label for label in desired_labels if label not in current]
            if not effective:
                return []
            if len(effective) != 1:
                operations: list[dict[str, Any]] = []
                for label in effective:
                    operations.extend(
                        operation_from_suggestion(
                            {**suggestion, "labels": [label]},
                            snapshot=snapshot,
                        )
                    )
                return operations
            request = {
                "transport": "rest",
                "method": "POST",
                "path": f"/repos/{repository}/issues/{number}/labels",
                "body": {"labels": effective},
            }
            after_labels = sorted(current | set(effective), key=str.casefold)
        else:
            effective = [label for label in desired_labels if label in current]
            if not effective:
                return []
            if len(effective) != 1:
                operations: list[dict[str, Any]] = []
                for label in effective:
                    operations.extend(
                        operation_from_suggestion(
                            {**suggestion, "labels": [label]},
                            snapshot=snapshot,
                        )
                    )
                return operations
            label = effective[0]
            request = {
                "transport": "rest",
                "method": "DELETE",
                "path": f"/repos/{repository}/issues/{number}/labels/{quote(label, safe='')}",
                "body": None,
            }
            after_labels = sorted(current - {label}, key=str.casefold)
        return [
            make_operation(
                kind=kind,
                repository=repository,
                issue=issue,
                batch=batch,
                reason=reason,
                before={"labels": sorted(current, key=str.casefold)},
                after={"labels": after_labels},
                request=request,
                destructive=kind == "issue.labels.remove",
            )
        ]

    raise TriageError(f"suggested operation kind is not supported: {kind}")


def desired_issue_suggestions(policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    desired = (
        policy.get("desired", {}) if isinstance(policy.get("desired"), dict) else {}
    )
    suggestions: list[dict[str, Any]] = []
    for entry in (
        desired.get("issue", []) if isinstance(desired.get("issue"), list) else []
    ):
        if not isinstance(entry, dict):
            continue
        number = entry["number"]
        batch = entry.get("batch", "bootstrap")
        reason = (
            entry.get("reason") or "Apply explicit desired issue metadata from policy."
        )
        labels_add = entry.get("labels_add", [])
        labels_remove = entry.get("labels_remove", [])
        if labels_add:
            suggestions.append(
                {
                    "kind": "issue.labels.add",
                    "issue_number": number,
                    "labels": labels_add,
                    "batch": batch,
                    "reason": reason,
                }
            )
        if labels_remove:
            suggestions.append(
                {
                    "kind": "issue.labels.remove",
                    "issue_number": number,
                    "labels": labels_remove,
                    "batch": batch,
                    "reason": reason,
                }
            )
        if "milestone_number" in entry:
            milestone = entry.get("milestone_number")
            if milestone == 0:
                suggestions.append(
                    {
                        "kind": "issue.milestone.clear",
                        "issue_number": number,
                        "batch": batch,
                        "reason": reason,
                    }
                )
            elif isinstance(milestone, int):
                suggestions.append(
                    {
                        "kind": "issue.milestone.set",
                        "issue_number": number,
                        "milestone_number": milestone,
                        "batch": batch,
                        "reason": reason,
                    }
                )
    return suggestions


def operation_from_desired_suggestion(
    suggestion: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if suggestion.get("kind") != "issue.milestone.clear":
        return operation_from_suggestion(suggestion, snapshot=snapshot)
    issues = issue_map(snapshot)
    repository = (
        (snapshot.get("repository") or {}).get("full_name")
        if isinstance(snapshot.get("repository"), dict)
        else None
    )
    number = suggestion.get("issue_number")
    if (
        not isinstance(repository, str)
        or not isinstance(number, int)
        or number not in issues
    ):
        return []
    issue = issues[number]
    current_ref = issue.get("milestone")
    current = current_ref.get("number") if isinstance(current_ref, dict) else None
    if current is None:
        return []
    return [
        make_operation(
            kind="issue.milestone.clear",
            repository=repository,
            issue=issue,
            batch=str(suggestion.get("batch") or "bootstrap"),
            reason=str(
                suggestion.get("reason")
                or "Clear milestone from explicit desired policy."
            ),
            before={"milestone_number": current},
            after={"milestone_number": None},
            request={
                "transport": "rest",
                "method": "PATCH",
                "path": f"/repos/{repository}/issues/{number}",
                "body": {"milestone": None},
            },
            destructive=True,
        )
    ]


def normalized_plan_without_digest(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key != "plan_sha256"}


def semantic_operation_key(operation: Mapping[str, Any]) -> tuple[Any, ...]:
    target = require_mapping(operation.get("target"), "operation target")
    repository = target.get("repository")
    number = target.get("issue_number")
    kind = operation.get("kind")
    if kind in {"issue.milestone.set", "issue.milestone.clear"}:
        return ("milestone", repository, number)
    before = require_mapping(operation.get("before"), "operation before")
    after = require_mapping(operation.get("after"), "operation after")
    before_labels = set(before.get("labels", []))
    after_labels = set(after.get("labels", []))
    changed = (
        after_labels - before_labels
        if kind == "issue.labels.add"
        else before_labels - after_labels
    )
    if len(changed) != 1:
        raise TriageError(f"label operation must change exactly one label: {kind}")
    return ("label", repository, number, next(iter(changed)).casefold())


def validate_operation_conflicts(operations: Sequence[Mapping[str, Any]]) -> None:
    seen: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for operation in operations:
        key = semantic_operation_key(operation)
        previous = seen.get(key)
        if previous is None:
            seen[key] = operation
            continue
        if previous.get("kind") != operation.get("kind") or previous.get(
            "after"
        ) != operation.get("after"):
            raise TriageError(
                "plan contains conflicting operations for the same metadata field: "
                f"{previous.get('operation_id')} and {operation.get('operation_id')}"
            )
        raise TriageError(
            "plan contains duplicate semantic operations: "
            f"{previous.get('operation_id')} and {operation.get('operation_id')}"
        )


def make_plan(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    repository = (
        (snapshot.get("repository") or {}).get("full_name")
        if isinstance(snapshot.get("repository"), dict)
        else None
    )
    if not isinstance(repository, str):
        repository = str(snapshot.get("repository") or "")
    validate_snapshot(
        snapshot,
        repository=repository,
        policy_sha256=sha256_json(policy),
    )
    normalized_findings = sorted(
        (dict(finding) for finding in findings),
        key=finding_sort_key,
    )
    operations: list[dict[str, Any]] = []
    for finding in normalized_findings:
        suggestion = finding.get("suggested_operation")
        if isinstance(suggestion, dict):
            operations.extend(operation_from_suggestion(suggestion, snapshot=snapshot))
    for suggestion in desired_issue_suggestions(policy):
        operations.extend(
            operation_from_desired_suggestion(suggestion, snapshot=snapshot)
        )

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for operation in operations:
        validate_operation(operation)
        key = semantic_operation_key(operation)
        previous = deduped.get(key)
        if previous is not None and (
            previous.get("kind") != operation.get("kind")
            or previous.get("after") != operation.get("after")
        ):
            raise TriageError(
                "policy and audit propose conflicting operations for the same metadata field: "
                f"{previous.get('operation_id')} and {operation.get('operation_id')}"
            )
        # Explicit desired-state entries are appended after audit suggestions,
        # so a semantically identical desired operation controls batch/reason.
        deduped[key] = operation
    operations = sorted(
        deduped.values(),
        key=lambda item: (
            str(item.get("batch")),
            int((item.get("target") or {}).get("issue_number") or 0),
            str(item.get("kind")),
            str(item.get("operation_id")),
        ),
    )

    decisions: list[dict[str, Any]] = []
    release = (
        policy.get("release", {}) if isinstance(policy.get("release"), dict) else {}
    )
    if not release.get("milestone_number"):
        decisions.append(
            {
                "decision_id": "release.milestone.identity",
                "summary": "Choose the exact release milestone identity before milestone enforcement.",
            }
        )
    project = (
        policy.get("project", {}) if isinstance(policy.get("project"), dict) else {}
    )
    if not project.get("enabled", False):
        decisions.append(
            {
                "decision_id": "project.identity",
                "summary": "Choose an exact GitHub Project identity before Project field planning is enabled.",
            }
        )

    generated = now or utc_now()
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "generated_at": isoformat_utc(generated),
        "repository": repository,
        "snapshot_sha256": snapshot.get("snapshot_sha256")
        or sha256_json(snapshot_without_digest(snapshot)),
        "policy_sha256": sha256_json(policy),
        "findings_sha256": sha256_json(normalized_findings),
        "operations": operations,
        "maintainer_decisions": decisions,
        "safety": {
            "body_updates_supported": False,
            "issue_creation_supported": False,
            "issue_state_changes_supported": False,
            "label_definition_changes_supported": False,
            "milestone_definition_changes_supported": False,
            "project_definition_changes_supported": False,
            "live_preflight_required": True,
        },
    }
    plan["plan_sha256"] = sha256_json(normalized_plan_without_digest(plan))
    return plan


def validate_operation(operation: Mapping[str, Any]) -> None:
    if operation.get("schema_version") != OPERATION_SCHEMA_VERSION:
        raise TriageError("operation has unsupported schema_version")
    kind = operation.get("kind")
    if (
        not isinstance(kind, str)
        or kind in FORBIDDEN_OPERATION_KINDS
        or kind not in SUPPORTED_OPERATION_KINDS
    ):
        raise TriageError(f"operation kind is unsupported or forbidden: {kind}")
    if operation.get("destructive") not in {True, False}:
        raise TriageError("operation destructive flag must be boolean")
    if not isinstance(operation.get("batch"), str) or not operation.get("batch"):
        raise TriageError("operation batch must be a non-empty string")
    target = operation.get("target")
    if (
        not isinstance(target, dict)
        or not isinstance(target.get("issue_number"), int)
        or isinstance(target.get("issue_number"), bool)
        or int(target.get("issue_number")) <= 0
    ):
        raise TriageError("operation target must contain issue_number")
    validate_repo_name(str(target.get("repository") or ""))
    preconditions = operation.get("preconditions")
    if not isinstance(preconditions, dict):
        raise TriageError("operation preconditions must be an object")
    if preconditions.get("issue_number") != target.get("issue_number"):
        raise TriageError("operation precondition issue number does not match target")
    if preconditions.get("issue_state") not in {"open", "closed"}:
        raise TriageError("operation precondition issue state is invalid")
    request = operation.get("request")
    if not isinstance(request, dict) or request.get("transport") != "rest":
        raise TriageError("operation request must use the supported REST transport")
    if set(request) != {"transport", "method", "path", "body"}:
        raise TriageError("operation request has unsupported fields")
    method = request.get("method")
    if method not in {"POST", "PATCH", "DELETE"}:
        raise TriageError(f"operation request uses unsupported method: {method}")
    path = request.get("path")
    if not isinstance(path, str) or not path.startswith("/repos/"):
        raise TriageError("operation request path must be a repository REST path")
    target_repo = str(target.get("repository"))
    issue_number = int(target["issue_number"])
    issue_path = f"/repos/{target_repo}/issues/{issue_number}"
    body = request.get("body")
    if kind in {"issue.milestone.set", "issue.milestone.clear"}:
        if method != "PATCH" or path != issue_path or not isinstance(body, dict):
            raise TriageError("milestone operation request does not match its target")
        if set(body) != {"milestone"}:
            raise TriageError("milestone operation body may contain only milestone")
        desired = operation.get("after")
        desired_number = (
            desired.get("milestone_number") if isinstance(desired, dict) else None
        )
        if body.get("milestone") != desired_number:
            raise TriageError(
                "milestone request body does not match operation after-state"
            )
    elif kind == "issue.labels.add":
        if (
            method != "POST"
            or path != f"{issue_path}/labels"
            or not isinstance(body, dict)
        ):
            raise TriageError("label-add operation request does not match its target")
        labels = body.get("labels")
        if set(body) != {"labels"} or not isinstance(labels, list) or not labels:
            raise TriageError("label-add body must contain a non-empty labels list")
        if not all(isinstance(label, str) and label for label in labels):
            raise TriageError("label-add labels must be non-empty strings")
        before = operation.get("before")
        after = operation.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise TriageError("label-add operation states must be objects")
        before_labels = set(before.get("labels", []))
        after_labels = set(after.get("labels", []))
        if set(labels) != after_labels - before_labels:
            raise TriageError("label-add body does not match operation after-state")
    elif kind == "issue.labels.remove":
        expected_prefix = f"{issue_path}/labels/"
        if (
            method != "DELETE"
            or not path.startswith(expected_prefix)
            or body is not None
        ):
            raise TriageError(
                "label-remove operation request does not match its target"
            )
        if path == expected_prefix:
            raise TriageError("label-remove operation is missing the encoded label")
        before = operation.get("before")
        after = operation.get("after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise TriageError("label-remove operation states must be objects")
        removed = set(before.get("labels", [])) - set(after.get("labels", []))
        if len(removed) != 1:
            raise TriageError("label-remove operation must remove exactly one label")
        expected_label = quote(next(iter(removed)), safe="")
        if path != expected_prefix + expected_label:
            raise TriageError("label-remove path does not match operation after-state")
    expected_id = operation_id(operation)
    if operation.get("operation_id") != expected_id:
        raise TriageError(f"operation_id mismatch: expected {expected_id}")


def validate_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise TriageError(
            f"unsupported plan schema_version: {plan.get('schema_version')}"
        )
    repository = validate_repo_name(str(plan.get("repository") or ""))
    if parse_timestamp(plan.get("generated_at")) is None:
        raise TriageError("plan generated_at must be an ISO-8601 timestamp")
    operations = plan.get("operations")
    if not isinstance(operations, list):
        raise TriageError("plan operations must be a list")
    seen: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise TriageError("plan operation must be an object")
        validate_operation(operation)
        target = require_mapping(operation.get("target"), "operation target")
        if target.get("repository") != repository:
            raise TriageError(
                "operation target repository does not match plan repository"
            )
        op_id = operation["operation_id"]
        if op_id in seen:
            raise TriageError(f"duplicate operation_id in plan: {op_id}")
        seen.add(op_id)
    validate_operation_conflicts(operations)
    actual = sha256_json(normalized_plan_without_digest(plan))
    if plan.get("plan_sha256") != actual:
        raise TriageError(f"embedded plan_sha256 mismatch: expected {actual}")


def approval_template(plan: Mapping[str, Any]) -> dict[str, Any]:
    batches = sorted(
        {
            str(operation.get("batch"))
            for operation in plan.get("operations", [])
            if isinstance(operation, dict)
        }
    )
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "repository": plan.get("repository"),
        "plan_sha256": plan.get("plan_sha256"),
        "approved_batches": [],
        "approved_operation_ids": [],
        "available_batches": batches,
        "allow_destructive": False,
        "approved_by": "",
        "approved_at": "",
    }


def validate_approval(
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
    expected_sha: str,
    batch: str,
) -> list[dict[str, Any]]:
    validate_plan(plan)
    actual_sha = str(plan["plan_sha256"])
    if actual_sha != expected_sha:
        raise TriageError(
            f"plan digest mismatch: expected {expected_sha}, got {actual_sha}"
        )
    if approval.get("schema_version") != APPROVAL_SCHEMA_VERSION:
        raise TriageError("approval file has unsupported schema_version")
    if approval.get("repository") != plan.get("repository"):
        raise TriageError("approval file is for a different repository")
    if approval.get("plan_sha256") != actual_sha:
        raise TriageError("approval file is for a different plan")
    approved_batches = approval.get("approved_batches")
    approved_ids = approval.get("approved_operation_ids")
    if not isinstance(approved_batches, list) or not all(
        isinstance(item, str) for item in approved_batches
    ):
        raise TriageError("approval approved_batches must be a list of strings")
    if not isinstance(approved_ids, list) or not all(
        isinstance(item, str) for item in approved_ids
    ):
        raise TriageError("approval approved_operation_ids must be a list of strings")
    if len(approved_batches) != len(set(approved_batches)):
        raise TriageError("approval approved_batches contains duplicates")
    if len(approved_ids) != len(set(approved_ids)):
        raise TriageError("approval approved_operation_ids contains duplicates")
    approved_by = approval.get("approved_by")
    approved_at = approval.get("approved_at")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise TriageError("approval approved_by must be a non-empty string")
    if parse_timestamp(approved_at) is None:
        raise TriageError("approval approved_at must be an ISO-8601 timestamp")
    if batch not in set(approved_batches):
        raise TriageError(f"batch is not approved: {batch}")

    operations_by_id = {
        operation["operation_id"]: operation for operation in plan.get("operations", [])
    }
    unknown = sorted(set(approved_ids) - set(operations_by_id))
    if unknown:
        raise TriageError(f"approval references unknown operation IDs: {unknown}")
    unapproved_batches = sorted(
        {
            str(operations_by_id[op_id].get("batch"))
            for op_id in approved_ids
            if operations_by_id[op_id].get("batch") not in set(approved_batches)
        }
    )
    if unapproved_batches:
        raise TriageError(
            "approval operation IDs belong to unapproved batch(es): "
            + ", ".join(unapproved_batches)
        )
    selected = [
        operations_by_id[op_id]
        for op_id in approved_ids
        if operations_by_id[op_id].get("batch") == batch
    ]
    allow_destructive = approval.get("allow_destructive") is True
    for operation in selected:
        if operation.get("destructive") and not allow_destructive:
            raise TriageError(
                f"destructive operation is not allowed: {operation['operation_id']}"
            )
    return selected


def load_json_file(path: Path, label: str = "JSON file") -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TriageError(f"{label} not found: {path}") from exc
    except OSError as exc:
        raise TriageError(f"could not read {label}: {path}: {exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TriageError(f"invalid {label}: {path}: {exc}") from exc
    return require_mapping(value, label)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )


def render_plan_markdown(
    plan: Mapping[str, Any], findings: Sequence[Mapping[str, Any]]
) -> str:
    lines = [
        "# Issue governance plan",
        "",
        f"Repository: `{plan['repository']}`",
        f"Snapshot SHA-256: `{plan['snapshot_sha256']}`",
        f"Plan SHA-256: `{plan['plan_sha256']}`",
        "",
        "## Operations",
        "",
    ]
    operations = plan.get("operations", [])
    if not operations:
        lines.append(
            "No metadata mutations are proposed by the current policy and audit findings."
        )
    else:
        for operation in operations:
            target = operation.get("target") or {}
            lines.append(
                f"- `{operation['operation_id']}` [{operation['batch']}] "
                f"`{operation['kind']}` issue #{target.get('issue_number')}: "
                f"{ascii_text(operation['reason'])}"
            )
            lines.append(f"  - Before: `{canonical_json(operation['before'])}`")
            lines.append(f"  - After: `{canonical_json(operation['after'])}`")
    lines.extend(["", "## Maintainer decisions", ""])
    decisions = plan.get("maintainer_decisions", [])
    if not decisions:
        lines.append("No unresolved policy identity decisions were recorded.")
    else:
        for decision in decisions:
            lines.append(
                f"- `{decision['decision_id']}`: {ascii_text(decision['summary'])}"
            )
    lines.extend(["", "## Audit findings", ""])
    if not findings:
        lines.append("No audit findings.")
    else:
        for finding in findings:
            issue = (
                f" #{finding['issue']}" if isinstance(finding.get("issue"), int) else ""
            )
            lines.append(
                f"- **{finding['level']}** `{finding['code']}`{issue}: "
                f"{ascii_text(finding['message'])}"
            )
    lines.extend(
        [
            "",
            "## Approval",
            "",
            "Copy `approval.template.json` to a separate approval file. Record the exact plan SHA,",
            "batch, and operation IDs. A dry run performs live preflight reads before any write is",
            "eligible. The template approves nothing.",
            "",
        ]
    )
    return "\n".join(lines)


def write_plan_bundle(
    plan: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
    output_dir: Path,
    *,
    readiness_audit: Mapping[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "snapshot.json", snapshot)
    write_json(
        output_dir / "audit.json",
        dict(readiness_audit) if readiness_audit is not None else list(findings),
    )
    write_json(output_dir / "plan.json", plan)
    atomic_write_text(output_dir / "plan.md", render_plan_markdown(plan, findings))
    write_json(output_dir / "approval.template.json", approval_template(plan))


def acquire_lock(path: Path, *, repository: str, plan_sha: str, batch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise TriageError(f"metadata writer lock already exists: {path}") from exc
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(f"pid={os.getpid()}\n")
        handle.write(f"repository={repository}\n")
        handle.write(f"plan_sha256={plan_sha}\n")
        handle.write(f"batch={batch}\n")
        handle.write(f"created_at={isoformat_utc(utc_now())}\n")


def release_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def current_issue_state(
    client: GitHubClient, operation: Mapping[str, Any]
) -> dict[str, Any]:
    target = require_mapping(operation.get("target"), "operation target")
    number = target.get("issue_number")
    raw = client.api(f"/repos/{client.repo}/issues/{number}")
    if not isinstance(raw, dict):
        raise TriageError(f"issue #{number} preflight returned a non-object response")
    if isinstance(raw.get("pull_request"), dict):
        raise TriageError(f"operation target #{number} is a pull request, not an issue")
    return normalize_issue(raw)


def preflight_operation(
    client: GitHubClient, operation: Mapping[str, Any]
) -> PreflightResult:
    validate_operation(operation)
    current = current_issue_state(client, operation)
    op_id = str(operation["operation_id"])
    preconditions = require_mapping(
        operation.get("preconditions"), "operation preconditions"
    )
    if current.get("state") != preconditions.get("issue_state"):
        return PreflightResult(op_id, "stale", "issue state changed", current)

    kind = operation["kind"]
    before = require_mapping(operation.get("before"), "operation before")
    after = require_mapping(operation.get("after"), "operation after")
    if kind.startswith("issue.milestone"):
        milestone = current.get("milestone")
        current_number = (
            milestone.get("number") if isinstance(milestone, dict) else None
        )
        desired = after.get("milestone_number")
        expected = before.get("milestone_number")
        if current_number == desired:
            return PreflightResult(
                op_id, "noop", "desired milestone is already present", current
            )
        if current_number != expected:
            return PreflightResult(
                op_id, "stale", "milestone changed since planning", current
            )
        return PreflightResult(op_id, "ready", "milestone preconditions match", current)

    if kind.startswith("issue.labels"):
        current_labels = set(current.get("labels", []))
        before_labels = set(before.get("labels", []))
        after_labels = set(after.get("labels", []))
        if current_labels == after_labels:
            return PreflightResult(
                op_id, "noop", "desired labels are already present", current
            )
        if kind == "issue.labels.add":
            added = after_labels - before_labels
            if added <= current_labels:
                return PreflightResult(
                    op_id, "noop", "labels to add are already present", current
                )
            return PreflightResult(
                op_id, "ready", "label-add preconditions match", current
            )
        removed = before_labels - after_labels
        if not (removed & current_labels):
            return PreflightResult(
                op_id, "noop", "labels to remove are already absent", current
            )
        return PreflightResult(
            op_id, "ready", "label-remove preconditions match", current
        )

    return PreflightResult(
        op_id, "unsupported", f"unsupported operation kind: {kind}", current
    )


def execute_operation(client: GitHubClient, operation: Mapping[str, Any]) -> None:
    request = require_mapping(operation.get("request"), "operation request")
    method = str(request.get("method"))
    path = str(request.get("path"))
    body = request.get("body")
    if body is not None and not isinstance(body, dict):
        raise TriageError("operation request body must be an object or null")
    client.api(path, method=method, body=body)


def write_receipt(
    path: Path,
    *,
    plan: Mapping[str, Any],
    batch: str,
    preflight: Sequence[PreflightResult],
    executed: Sequence[str],
    status: str = "completed",
    error: str | None = None,
) -> None:
    receipt = {
        "schema_version": 1,
        "repository": plan.get("repository"),
        "plan_sha256": plan.get("plan_sha256"),
        "batch": batch,
        "created_at": isoformat_utc(utc_now()),
        "status": status,
        "preflight": [result.to_dict() for result in preflight],
        "executed_operation_ids": list(executed),
        "error": error,
    }
    write_json(path, receipt)


def apply_plan(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    expected_repo: str | None = None,
) -> int:
    plan = load_json_file(args.plan, "plan JSON")
    approval = load_json_file(args.approval, "approval JSON")
    if expected_repo is not None and plan.get("repository") != expected_repo:
        raise TriageError(
            f"plan repository {plan.get('repository')!r} does not match {expected_repo!r}"
        )
    selected = validate_approval(plan, approval, args.plan_sha, args.batch)

    if not selected:
        print(f"No operations selected for approved batch {args.batch}.")
        return 0

    repository = str(plan["repository"])
    client = GitHubClient(runner=runner or Runner(), repo=repository)
    preflight = [preflight_operation(client, operation) for operation in selected]
    print("Selected operations and live preflight:")
    for operation, result in zip(selected, preflight):
        print(
            json.dumps(
                {
                    "operation": operation,
                    "preflight": result.to_dict(),
                },
                sort_keys=True,
                ensure_ascii=True,
            )
        )

    blocking = [
        result for result in preflight if result.status not in {"ready", "noop"}
    ]
    if blocking:
        print("Preflight failed; no GitHub mutations executed.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Dry run only; no GitHub mutations executed.")
        return 0

    if not args.execute:
        raise TriageError("apply requires either --dry-run or --execute")
    if args.confirm_repo != repository:
        raise TriageError(f"--confirm-repo must exactly match {repository}")
    if os.environ.get("TRIAGE_ENABLE_GITHUB_WRITES") != "1":
        raise TriageError(
            "set TRIAGE_ENABLE_GITHUB_WRITES=1 to enable an approved write session"
        )

    lock_path = args.lock_path or LOCK_PATH
    receipt_path = args.receipt or (
        DEFAULT_OUTPUT_DIR / "receipts" / f"{plan['plan_sha256']}-{args.batch}.json"
    )
    acquire_lock(
        lock_path,
        repository=repository,
        plan_sha=str(plan["plan_sha256"]),
        batch=args.batch,
    )
    executed: list[str] = []
    try:
        for operation, result in zip(selected, preflight):
            if result.status == "noop":
                continue
            just_in_time = preflight_operation(client, operation)
            if just_in_time.status == "noop":
                continue
            if just_in_time.status != "ready":
                raise TriageError(
                    "operation became stale after batch preflight: "
                    f"{operation['operation_id']}: {just_in_time.message}"
                )
            execute_operation(client, operation)
            verification = preflight_operation(client, operation)
            if verification.status != "noop":
                raise TriageError(
                    f"operation did not reach its desired state: {operation['operation_id']}: {verification.message}"
                )
            executed.append(str(operation["operation_id"]))
        write_receipt(
            receipt_path,
            plan=plan,
            batch=args.batch,
            preflight=preflight,
            executed=executed,
        )
        print(f"Executed {len(executed)} operation(s).")
        print(f"Wrote receipt {receipt_path}")
        return 0
    except Exception as exc:
        error = str(exc) if isinstance(exc, TriageError) else type(exc).__name__
        try:
            write_receipt(
                receipt_path,
                plan=plan,
                batch=args.batch,
                preflight=preflight,
                executed=executed,
                status="failed",
                error=sanitize_cli_error(error),
            )
        except Exception:
            pass
        raise
    finally:
        release_lock(lock_path)


def parse_issue_filter(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    result: set[int] = set()
    for raw in value.split(","):
        token = raw.strip()
        if not re.fullmatch(r"[1-9][0-9]*", token):
            raise TriageError(f"invalid issue number in --issues: {token!r}")
        result.add(int(token))
    return result


def parse_frontier_issue_filter(
    value: str | None, *, force_empty: bool = False
) -> set[int] | None:
    """Parse a frontier filter, including an explicit empty selection."""

    if force_empty:
        if value is not None:
            raise TriageError("--empty-selection cannot be combined with --issues")
        return set()
    if value is None:
        return None
    if value.strip().casefold() in {"", "none", "empty"}:
        return set()
    return parse_issue_filter(value)


def issue_from_snapshot(snapshot: Mapping[str, Any], number: int) -> dict[str, Any]:
    issues = governance_common.issue_map(snapshot)
    issue = issues.get(number)
    if issue is None:
        raise TriageError(f"issue #{number} is not present in the snapshot")
    return issue


def load_semantic_evidence(path: Path | None) -> dict[int, dict[str, Any]] | None:
    if path is None:
        return None
    raw = load_json_file(path, "semantic evidence JSON")
    result: dict[int, dict[str, Any]] = {}
    entries = raw.get("issues")
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise TriageError(
                    f"semantic evidence issues[{index}] must be an object"
                )
            number = entry.get("issue_number", entry.get("number"))
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                raise TriageError(
                    f"semantic evidence issues[{index}] has an invalid issue number"
                )
            evidence = entry.get("semantic_review", entry.get("evidence"))
            if evidence is None:
                evidence = {
                    key: item
                    for key, item in entry.items()
                    if key not in {"issue_number", "number"}
                }
            if not isinstance(evidence, dict):
                raise TriageError(
                    f"semantic evidence for issue #{number} must be an object"
                )
            if number in result:
                raise TriageError(
                    f"semantic evidence contains duplicate issue #{number}"
                )
            result[number] = dict(evidence)
        return result

    for key, evidence in raw.items():
        if not isinstance(key, str) or not re.fullmatch(r"[1-9][0-9]*", key):
            raise TriageError(
                "semantic evidence must map positive issue-number strings to objects"
            )
        if not isinstance(evidence, dict):
            raise TriageError(f"semantic evidence for issue #{key} must be an object")
        result[int(key)] = dict(evidence)
    return result


def make_readiness_audit(
    snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    repo_policy: repo_config.RepoPolicy | None = None,
    semantic_evidence: Mapping[int, Mapping[str, Any]] | None = None,
    issue_filter: set[int] | None = None,
) -> dict[str, Any]:
    active_policy = repo_policy or repo_config.load_repo_policy()
    if issue_filter is not None:
        unknown = sorted(issue_filter - set(governance_common.issue_map(snapshot)))
        if unknown:
            raise TriageError(
                f"issue filter contains unknown issue number(s): {unknown}"
            )
    readiness = issue_readiness.audit_all_issues(
        snapshot,
        policy,
        root=ROOT,
        repo_policy=active_policy,
        semantic_evidence=semantic_evidence,
        issue_filter=issue_filter,
    )
    # Scope the metadata audit to the same issue filter so cross-issue global
    # findings (for example a dependency cycle among issues outside the filter)
    # cannot make a single-issue audit fail. audit_snapshot already drops
    # out-of-scope issue-keyed findings and suppresses cycles that do not touch
    # the filter, so no separate post-filter is needed.
    metadata_findings = audit_snapshot(
        snapshot,
        policy,
        root=ROOT,
        issue_filter=issue_filter,
        repo_policy=active_policy,
    )
    readiness["metadata_findings"] = metadata_findings
    readiness["metadata_finding_count"] = len(metadata_findings)
    # Record the scope this audit was built with so consumers can detect a
    # partial audit; null means the full snapshot was audited.
    readiness["audit_scope"] = (
        sorted(issue_filter) if issue_filter is not None else None
    )
    readiness["audit_digest"] = governance_common.sha256_json(
        {key: item for key, item in readiness.items() if key != "audit_digest"}
    )
    return readiness


def validate_readiness_audit(
    audit: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> None:
    if audit.get("schema_version") != 1:
        raise TriageError(
            f"unsupported readiness audit schema_version: {audit.get('schema_version')}"
        )
    repository = governance_common.repository_name(snapshot)
    if audit.get("repository") != repository:
        raise TriageError("audit repository does not match the snapshot")
    expected_snapshot_digest = governance_common.snapshot_digest(snapshot)
    if audit.get("snapshot_digest") != expected_snapshot_digest:
        raise TriageError("audit snapshot digest does not match the snapshot")
    issues = audit.get("issues")
    if not isinstance(issues, list):
        raise TriageError("readiness audit issues must be a list")
    declared_issue_count = audit.get("issue_count")
    if (
        isinstance(declared_issue_count, bool)
        or not isinstance(declared_issue_count, int)
        or declared_issue_count != len(issues)
    ):
        raise TriageError("readiness audit issue_count does not match issues")
    snapshot_issues = set(governance_common.issue_map(snapshot))
    seen: set[int] = set()
    for index, entry in enumerate(issues):
        if not isinstance(entry, dict):
            raise TriageError(f"readiness audit issues[{index}] must be an object")
        number = entry.get("issue_number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise TriageError(
                f"readiness audit issues[{index}] has an invalid issue number"
            )
        if number in seen:
            raise TriageError(f"readiness audit contains duplicate issue #{number}")
        if number not in snapshot_issues:
            raise TriageError(
                f"readiness audit contains unknown snapshot issue #{number}"
            )
        seen.add(number)
    actual = governance_common.sha256_json(
        {key: item for key, item in audit.items() if key != "audit_digest"}
    )
    if audit.get("audit_digest") != actual:
        raise TriageError(f"readiness audit digest mismatch: expected {actual}")


def audit_coverage_gap(
    audit: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    issue_filter: set[int] | None,
) -> list[int]:
    """Issue numbers the frontier will rank that the audit does not cover.

    With no filter the frontier ranks the whole snapshot, so the audit must
    cover every snapshot issue. With a filter it must cover that filter. An
    empty filter (explicit empty selection) requires no coverage.
    """
    audited = {
        entry.get("issue_number")
        for entry in audit.get("issues", [])
        if isinstance(entry, Mapping)
    }
    required = (
        issue_filter
        if issue_filter is not None
        else set(governance_common.issue_map(snapshot))
    )
    return sorted(number for number in required if number not in audited)


def require_full_audit_coverage(
    audit: Mapping[str, Any], snapshot: Mapping[str, Any], *, artifact_name: str
) -> None:
    uncovered = audit_coverage_gap(audit, snapshot, None)
    if uncovered:
        raise TriageError(
            f"readiness audit does not cover the requested {artifact_name} "
            f"issue(s): {uncovered}; rerun the audit without --issues"
        )


def readiness_audit_has_errors(audit: Mapping[str, Any]) -> bool:
    findings: list[Mapping[str, Any]] = []
    global_findings = audit.get("global_findings")
    if isinstance(global_findings, list):
        findings.extend(item for item in global_findings if isinstance(item, Mapping))
    metadata_findings = audit.get("metadata_findings")
    if isinstance(metadata_findings, list):
        findings.extend(item for item in metadata_findings if isinstance(item, Mapping))
    for issue in audit.get("issues") or []:
        if not isinstance(issue, Mapping):
            continue
        for key in ("contract_findings", "tracker_findings"):
            values = issue.get(key)
            if isinstance(values, list):
                findings.extend(item for item in values if isinstance(item, Mapping))
    return any(item.get("level") == "error" for item in findings)


def print_readiness_audit(audit: Mapping[str, Any]) -> int:
    print(f"Repository: {audit.get('repository')}")
    print(f"Snapshot digest: {audit.get('snapshot_digest')}")
    print(f"Audit digest: {audit.get('audit_digest')}")
    print(f"Issues audited: {audit.get('issue_count', 0)}")
    print(
        "Governance states: "
        + canonical_json(audit.get("governance_state_counts") or {})
    )
    print(
        "Implementation states: "
        + canonical_json(audit.get("implementation_state_counts") or {})
    )
    for finding in audit.get("global_findings") or []:
        if isinstance(finding, Mapping):
            print(
                f"{str(finding.get('level') or 'info').upper()}: "
                f"{finding.get('code')}: {finding.get('message')}"
            )
    for finding in audit.get("metadata_findings") or []:
        if isinstance(finding, Mapping):
            prefix = (
                f"#{finding.get('issue')} "
                if isinstance(finding.get("issue"), int)
                else ""
            )
            print(
                f"{str(finding.get('level') or 'info').upper()}: "
                f"{prefix}{finding.get('code')}: {finding.get('message')}"
            )
    for issue in audit.get("issues") or []:
        if not isinstance(issue, Mapping):
            continue
        print(
            f"#{issue.get('issue_number')} "
            f"governance={issue.get('governance_state')} "
            f"implementation={issue.get('implementation_state')} "
            f"disposition={issue.get('recommended_disposition')}"
        )
    return 1 if readiness_audit_has_errors(audit) else 0


def contract_result(
    issue: Mapping[str, Any],
    *,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> dict[str, Any]:
    result = issue_contract.audit_contract(issue, repo_policy=repo_policy)
    result.update(
        {
            "issue_number": issue.get("number"),
            "title": issue.get("title"),
            "body_digest": governance_common.sha256_json(issue.get("body") or ""),
        }
    )
    return result


def print_contract_result(result: Mapping[str, Any]) -> int:
    print(f"Issue: #{result.get('issue_number')} {result.get('title')}")
    print(f"Contract: {result.get('contract_id')} {result.get('contract_version')}")
    print(f"Kind: {result.get('issue_kind')}")
    print(f"Governance state: {result.get('governance_state')}")
    for finding in result.get("findings") or []:
        if isinstance(finding, Mapping):
            print(
                f"{str(finding.get('level') or 'info').upper()}: "
                f"{finding.get('code')}: {finding.get('message')}"
            )
    return 0 if result.get("contract_accepted") else 1


def issue_output_dir(issue_number: int, configured: Path | None) -> Path:
    return configured or (DEFAULT_OUTPUT_DIR / "issues" / str(issue_number))


def read_ascii_file(path: Path, label: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise TriageError(f"{label} not found: {path}") from exc
    except OSError as exc:
        raise TriageError(f"could not read {label}: {path}: {exc}") from exc
    try:
        governance_common.ensure_ascii_text(text, label=label)
    except governance_common.TriageError as exc:
        raise TriageError(str(exc)) from exc
    return text


def load_optional_mapping(path: Path | None, label: str) -> dict[str, Any]:
    if path is None:
        return {}
    return load_json_file(path, label)


def latest_progress_context(
    repo_policy: repo_config.RepoPolicy | None = None,
) -> str | None:
    active_policy = repo_policy or repo_config.load_repo_policy()
    entry = latest_progress_entry(ROOT / active_policy.repository.progress_log_path)
    if entry is None:
        return None
    _date, text = entry
    return text[:4000]


def resolve_snapshot(
    args: argparse.Namespace,
    *,
    runner: Runner,
    repo: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot_path = getattr(args, "snapshot_file", None)
    if snapshot_path is not None:
        snapshot = load_json_file(snapshot_path, "snapshot JSON")
        validate_snapshot(
            snapshot,
            repository=repo,
            policy_sha256=sha256_json(policy),
        )
        return snapshot
    return collect_snapshot(runner, repo, policy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository in owner/name form")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser(
        "snapshot", help="read live tracker metadata and emit a normalized snapshot"
    )
    snapshot.add_argument("--output", type=Path)

    audit = subparsers.add_parser("audit", help="run read-only governance checks")
    audit.add_argument("--issues", help="comma-separated issue numbers to display")
    audit.add_argument("--json", action="store_true", help="emit findings as JSON")
    audit.add_argument("--output", type=Path, help="also write findings as JSON")
    audit.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="audit an existing snapshot without GitHub reads",
    )
    audit.add_argument(
        "--semantic-evidence",
        type=Path,
        help="optional local semantic-review evidence JSON",
    )

    plan = subparsers.add_parser(
        "plan", help="write snapshot, audit, plan, and empty approval template"
    )
    plan.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    plan.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="plan from an existing snapshot without GitHub reads",
    )
    plan.add_argument(
        "--semantic-evidence",
        type=Path,
        help="optional local semantic-review evidence JSON for audit.json",
    )

    contract = subparsers.add_parser(
        "contract", help="audit one issue against issue contract v1"
    )
    contract.add_argument("--issue", type=int, required=True)
    contract.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="use an existing snapshot without GitHub reads",
    )
    contract.add_argument("--json", action="store_true", help="emit JSON")
    contract.add_argument("--output", type=Path, help="also write JSON locally")

    review_packet = subparsers.add_parser(
        "review-packet", help="write one bounded local issue review packet"
    )
    review_packet.add_argument("--issue", type=int, required=True)
    review_packet.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="use an existing snapshot without GitHub reads",
    )
    review_packet.add_argument(
        "--semantic-evidence",
        type=Path,
        help="optional local semantic-review evidence JSON",
    )
    review_packet.add_argument("--output-dir", type=Path)
    review_packet.add_argument("--json", action="store_true", help="emit packet JSON")

    standardize = subparsers.add_parser(
        "standardize", help="validate and package a proposed issue body locally"
    )
    standardize.add_argument("--issue", type=int, required=True)
    standardize.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="use an existing snapshot without GitHub reads",
    )
    standardize.add_argument("--proposed-body", type=Path, required=True)
    standardize.add_argument("--output-dir", type=Path)
    standardize.add_argument("--json", action="store_true", help="emit result JSON")

    frontier = subparsers.add_parser(
        "frontier", help="select a deterministic audit or implementation frontier"
    )
    frontier.add_argument("--mode", choices=("audit", "implement"), required=True)
    frontier.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        help="use an existing snapshot without GitHub reads",
    )
    frontier_audit_source = frontier.add_mutually_exclusive_group()
    frontier_audit_source.add_argument(
        "--audit-file",
        type=Path,
        help="consume an existing readiness audit JSON",
    )
    frontier_audit_source.add_argument(
        "--semantic-evidence",
        type=Path,
        help="optional local semantic-review evidence JSON when auditing",
    )
    frontier.add_argument(
        "--issues",
        help="comma-separated eligible issue numbers; use 'none' for an explicit empty selection",
    )
    frontier.add_argument(
        "--empty-selection",
        action="store_true",
        help="force an explicit empty frontier without selecting an issue",
    )
    frontier.add_argument("--json", action="store_true", help="emit coordinator JSON")
    frontier.add_argument("--output", type=Path, help="write coordinator JSON locally")
    frontier.add_argument(
        "--packet-output",
        type=Path,
        help="write a bounded worker packet when an issue is selected",
    )
    frontier.add_argument(
        "--branch-state",
        type=Path,
        help="optional caller-supplied local branch/worktree state JSON",
    )
    frontier.add_argument(
        "--progress-context",
        type=Path,
        help="optional caller-supplied historical progress excerpt",
    )

    project_plan = subparsers.add_parser(
        "project-plan",
        help="emit a read-only desired GitHub Project layout from an audit",
    )
    project_plan.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        required=True,
        help="use an existing snapshot without GitHub reads",
    )
    project_plan.add_argument(
        "--audit-file",
        type=Path,
        required=True,
        help="consume an existing readiness audit JSON",
    )
    project_plan.add_argument("--json", action="store_true", help="emit plan JSON")
    project_plan.add_argument("--output", type=Path, help="write plan JSON locally")

    backlog_synthesis = subparsers.add_parser(
        "backlog-synthesis",
        help="emit read-only backlog-level synthesis candidate signals",
    )
    backlog_synthesis.add_argument(
        "--snapshot",
        dest="snapshot_file",
        type=Path,
        required=True,
        help="use an existing snapshot without GitHub reads",
    )
    backlog_synthesis_audit_source = backlog_synthesis.add_mutually_exclusive_group()
    backlog_synthesis_audit_source.add_argument(
        "--audit-file",
        type=Path,
        help="consume an existing readiness audit JSON",
    )
    backlog_synthesis_audit_source.add_argument(
        "--semantic-evidence",
        type=Path,
        help="optional local semantic-review evidence JSON when auditing",
    )
    backlog_synthesis.add_argument(
        "--json", action="store_true", help="emit synthesis JSON"
    )
    backlog_synthesis.add_argument(
        "--output", type=Path, help="write synthesis JSON locally"
    )

    apply = subparsers.add_parser(
        "apply",
        help="preflight and optionally execute an explicitly approved plan batch",
    )
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--approval", type=Path, required=True)
    apply.add_argument("--plan-sha", required=True)
    apply.add_argument("--batch", required=True)
    mode = apply.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="perform live read-only preflight and print exact operations",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="execute after live preflight and all write gates",
    )
    apply.add_argument(
        "--confirm-repo", help="required with --execute; must exactly match owner/name"
    )
    apply.add_argument("--lock-path", type=Path, help=argparse.SUPPRESS)
    apply.add_argument(
        "--receipt", type=Path, help="write execution receipt to this path"
    )
    return parser


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    active_runner = runner or Runner()

    try:
        policy = load_policy(args.policy)
        repo_policy = repo_config.policy_from_mapping(policy, source=args.policy)
        repo = validate_repo_name(args.repo or repo_policy.repository.full_name)
        if args.command == "apply":
            return apply_plan(args, runner=active_runner, expected_repo=repo)
        if args.command == "project-plan":
            snapshot = load_json_file(args.snapshot_file, "snapshot JSON")
            validate_snapshot(
                snapshot,
                repository=repo,
                policy_sha256=sha256_json(policy),
            )
            readiness_audit = load_json_file(
                args.audit_file, "readiness audit JSON"
            )
            validate_readiness_audit(readiness_audit, snapshot)
            require_full_audit_coverage(
                readiness_audit, snapshot, artifact_name="project-plan"
            )
            plan = issue_frontier.build_project_plan(
                snapshot,
                readiness_audit,
                policy=policy,
                repo_policy=repo_policy,
            )
            plan_errors = issue_frontier.validate_project_plan(plan)
            if plan_errors:
                raise TriageError(
                    "project-plan validation failed: " + "; ".join(plan_errors)
                )
            status_stream = sys.stderr if args.json else sys.stdout
            if args.output:
                write_json(args.output, plan)
                print(f"Wrote {args.output}", file=status_stream)
            if args.json or not args.output:
                print(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=True))
            return 0

        snapshot = resolve_snapshot(
            args, runner=active_runner, repo=repo, policy=policy
        )
        if args.command == "snapshot":
            text = (
                json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
            )
            if args.output:
                atomic_write_text(args.output, text)
                print(f"Wrote {args.output}")
                print(f"Snapshot SHA-256: {snapshot['snapshot_sha256']}")
            else:
                print(text, end="")
            return 0

        if args.command == "contract":
            issue = issue_from_snapshot(snapshot, args.issue)
            result = contract_result(issue, repo_policy=repo_policy)
            if args.output:
                write_json(args.output, result)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
                return 0 if result.get("contract_accepted") else 1
            return print_contract_result(result)

        if args.command == "review-packet":
            issue = issue_from_snapshot(snapshot, args.issue)
            semantic = load_semantic_evidence(args.semantic_evidence)
            readiness_audit = make_readiness_audit(
                snapshot,
                policy,
                repo_policy=repo_policy,
                semantic_evidence=semantic,
            )
            validate_readiness_audit(readiness_audit, snapshot)
            packet = issue_frontier.build_worker_packet(
                args.issue,
                snapshot,
                readiness_audit,
                root=ROOT,
                repo_policy=repo_policy,
                progress_context=latest_progress_context(repo_policy),
            )
            packet_errors = issue_frontier.validate_worker_packet(packet)
            if packet_errors:
                raise TriageError(
                    "worker packet validation failed: " + "; ".join(packet_errors)
                )
            result = contract_result(issue, repo_policy=repo_policy)
            output_dir = issue_output_dir(args.issue, args.output_dir)
            write_json(output_dir / "review-packet.json", packet)
            write_json(output_dir / "contract.json", result)
            atomic_write_text(
                output_dir / "proposed-body.md",
                issue_contract.propose_normalized_body(
                    issue, repo_policy=repo_policy
                ),
            )
            status_stream = sys.stderr if args.json else sys.stdout
            print(f"Wrote {output_dir / 'review-packet.json'}", file=status_stream)
            print(f"Wrote {output_dir / 'contract.json'}", file=status_stream)
            print(f"Wrote {output_dir / 'proposed-body.md'}", file=status_stream)
            if args.json:
                print(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=True))
            return 0

        if args.command == "standardize":
            issue = issue_from_snapshot(snapshot, args.issue)
            proposed_body = read_ascii_file(args.proposed_body, "proposed issue body")
            proposed_issue = dict(issue)
            proposed_issue["body"] = proposed_body
            result = contract_result(proposed_issue, repo_policy=repo_policy)
            # Bind content-anchor verification to standardize so a fabricated or
            # stale quote/symbol cannot pass the gate the agent trusts. Every
            # path:symbol and path "snippet" in the proposed body must resolve in
            # the current files; an unresolved anchor or a past-EOF line citation
            # blocks acceptance just like a missing contract section.
            anchor_report = issue_readiness.verify_file_anchors(
                proposed_issue,
                ROOT,
                reference_roots=repo_policy.paths.reference_roots,
            )
            unresolved_anchors = anchor_report["unresolved_anchors"]
            past_eof_citations = anchor_report["line_citations_past_eof"]
            anchors_resolved = not unresolved_anchors and not past_eof_citations
            accepted = bool(result.get("contract_accepted")) and anchors_resolved
            payload = {
                "schema_version": 1,
                "repository": governance_common.repository_name(snapshot),
                "issue_number": args.issue,
                "source_body_digest": governance_common.sha256_json(
                    issue.get("body") or ""
                ),
                "proposed_body_digest": governance_common.sha256_json(proposed_body),
                "local_only": True,
                "github_mutation": False,
                "contract": result,
                "unresolved_file_anchors": unresolved_anchors,
                "line_citations_past_eof": past_eof_citations,
                "anchors_resolved": anchors_resolved,
                "accepted": accepted,
            }
            payload["standardization_digest"] = governance_common.sha256_json(payload)
            output_dir = issue_output_dir(args.issue, args.output_dir)
            atomic_write_text(output_dir / "proposed-body.md", proposed_body)
            write_json(output_dir / "standardization.json", payload)
            status_stream = sys.stderr if args.json else sys.stdout
            print(f"Wrote {output_dir / 'proposed-body.md'}", file=status_stream)
            print(f"Wrote {output_dir / 'standardization.json'}", file=status_stream)
            for item in unresolved_anchors:
                print(
                    f"unresolved anchor: {item['path']} :: {item['anchor']} "
                    f"({item['anchor_type']})",
                    file=sys.stderr,
                )
            for item in past_eof_citations:
                print(
                    f"line citation past EOF: {item['path']}:{item['line']} "
                    f"(file has {item['line_count']} lines)",
                    file=sys.stderr,
                )
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
            return 0 if accepted else 1

        if args.command == "frontier":
            if args.audit_file:
                readiness_audit = load_json_file(
                    args.audit_file, "readiness audit JSON"
                )
                validate_readiness_audit(readiness_audit, snapshot)
            else:
                semantic = load_semantic_evidence(args.semantic_evidence)
                readiness_audit = make_readiness_audit(
                    snapshot,
                    policy,
                    repo_policy=repo_policy,
                    semantic_evidence=semantic,
                )
                validate_readiness_audit(readiness_audit, snapshot)
            issue_filter = parse_frontier_issue_filter(
                args.issues, force_empty=args.empty_selection
            )
            if issue_filter:
                unknown = sorted(
                    issue_filter - set(governance_common.issue_map(snapshot))
                )
                if unknown:
                    raise TriageError(
                        f"frontier issue filter contains unknown issue number(s): {unknown}"
                    )
            # The frontier may only rank issues the audit actually covers. A
            # partial (issue-filtered) audit must not be ranked as if it were the
            # whole snapshot, or it would silently hide other ready issues.
            uncovered = audit_coverage_gap(readiness_audit, snapshot, issue_filter)
            if uncovered:
                raise TriageError(
                    "readiness audit does not cover the requested frontier issue(s): "
                    f"{uncovered}; rerun the audit with the same --issues scope "
                    "(or without --issues for the full snapshot)"
                )
            coordinator = issue_frontier.build_coordinator_result(
                args.mode,
                snapshot,
                readiness_audit,
                issue_filter=issue_filter,
            )
            validation_errors = issue_frontier.validate_coordinator_result(coordinator)
            if validation_errors:
                raise TriageError(
                    "coordinator validation failed: " + "; ".join(validation_errors)
                )
            status_stream = sys.stderr if args.json else sys.stdout
            if args.output:
                write_json(args.output, coordinator)
                print(f"Wrote {args.output}", file=status_stream)
            selected = coordinator.get("selected_issue")
            if args.packet_output and isinstance(selected, int):
                branch_state = load_optional_mapping(
                    args.branch_state, "branch/worktree state JSON"
                )
                progress_context = (
                    read_ascii_file(args.progress_context, "progress context")[:4000]
                    if args.progress_context
                    else latest_progress_context(repo_policy)
                )
                packet = issue_frontier.build_worker_packet(
                    selected,
                    snapshot,
                    readiness_audit,
                    root=ROOT,
                    repo_policy=repo_policy,
                    branch_state=branch_state,
                    progress_context=progress_context,
                )
                packet_errors = issue_frontier.validate_worker_packet(packet)
                if packet_errors:
                    raise TriageError(
                        "worker packet validation failed: " + "; ".join(packet_errors)
                    )
                write_json(args.packet_output, packet)
                print(f"Wrote {args.packet_output}", file=status_stream)
            elif args.packet_output:
                print(
                    "Frontier is empty; no worker packet was written.",
                    file=status_stream,
                )
            if args.json:
                print(
                    json.dumps(coordinator, indent=2, sort_keys=True, ensure_ascii=True)
                )
            else:
                print(f"Frontier mode: {args.mode}")
                print(f"Selected issue: {selected}")
                print(f"Reason: {coordinator.get('selection_reason')}")
                print(f"Coordinator digest: {coordinator.get('coordinator_digest')}")
            return 0

        if args.command == "backlog-synthesis":
            if args.audit_file:
                readiness_audit = load_json_file(
                    args.audit_file, "readiness audit JSON"
                )
                validate_readiness_audit(readiness_audit, snapshot)
            else:
                semantic = load_semantic_evidence(args.semantic_evidence)
                readiness_audit = make_readiness_audit(
                    snapshot,
                    policy,
                    repo_policy=repo_policy,
                    semantic_evidence=semantic,
                )
                validate_readiness_audit(readiness_audit, snapshot)
            require_full_audit_coverage(
                readiness_audit, snapshot, artifact_name="backlog-synthesis"
            )
            report = issue_frontier.build_backlog_synthesis_report(
                snapshot, readiness_audit
            )
            validation_errors = issue_frontier.validate_backlog_synthesis_report(
                report
            )
            if validation_errors:
                raise TriageError(
                    "backlog-synthesis validation failed: "
                    + "; ".join(validation_errors)
                )
            status_stream = sys.stderr if args.json else sys.stdout
            if args.output:
                write_json(args.output, report)
                print(f"Wrote {args.output}", file=status_stream)
            if args.json or not args.output:
                print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
            return 0

        semantic = load_semantic_evidence(getattr(args, "semantic_evidence", None))
        issue_filter = parse_issue_filter(getattr(args, "issues", None))
        readiness_audit = make_readiness_audit(
            snapshot,
            policy,
            repo_policy=repo_policy,
            semantic_evidence=semantic,
            issue_filter=issue_filter if args.command == "audit" else None,
        )
        validate_readiness_audit(readiness_audit, snapshot)

        if args.command == "audit":
            if args.output:
                write_json(args.output, readiness_audit)
            if args.json:
                print(
                    json.dumps(
                        readiness_audit, indent=2, sort_keys=True, ensure_ascii=True
                    )
                )
                return 1 if readiness_audit_has_errors(readiness_audit) else 0
            return print_readiness_audit(readiness_audit)

        if args.command == "plan":
            findings = audit_snapshot(
                snapshot, policy, root=ROOT, repo_policy=repo_policy
            )
            plan_data = make_plan(snapshot, policy, findings)
            write_plan_bundle(
                plan_data,
                findings,
                snapshot,
                args.output_dir,
                readiness_audit=readiness_audit,
            )
            for name in (
                "snapshot.json",
                "audit.json",
                "plan.json",
                "plan.md",
                "approval.template.json",
            ):
                print(f"Wrote {args.output_dir / name}")
            print(f"Plan SHA-256: {plan_data['plan_sha256']}")
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2
    except (TriageError, governance_common.TriageError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
