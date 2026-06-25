"""Shared deterministic helpers for issue governance tooling."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Iterator, Mapping

ISSUE_REF_RE = re.compile(r"(?<![A-Za-z0-9_])#(?P<number>[1-9][0-9]*)")
PATH_REF_RE = re.compile(
    r"(?P<path>(?:AGENTS\.md|CONTRIBUTING\.md|README\.md|CHANGELOG\.md|"
    r"dbt_diagnostics|docs|scripts|\.github|\.codex|\.agents)/?"
    r"[A-Za-z0-9_./@+\-]*)(?::(?P<line>[0-9]+))?"
)
URL_RE = re.compile(r"https://github\.com/[^/]+/[^/]+/(?:issues|pull)/(\d+)")


class TriageError(RuntimeError):
    """Raised for controlled user-facing failures."""


def utc_now() -> str:
    """Return a timezone-aware timestamp with stable UTC spelling."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> str:
    """Encode a value deterministically and with ASCII-only output."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def stable_digest(value: Any, *, prefix: str | None = None) -> str:
    digest = sha256_json(value)
    return f"{prefix}:{digest}" if prefix else digest


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TriageError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TriageError(f"invalid JSON file: {path}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.write_text(text, encoding="ascii")


def write_ascii(path: Path, text: str) -> None:
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise TriageError(f"repository-authored output is not ASCII: {path}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def ensure_ascii_text(text: str, *, label: str = "text") -> None:
    try:
        text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise TriageError(f"{label} is not ASCII") from exc


def refs_in_text(text: str) -> set[int]:
    refs = {int(match.group("number")) for match in ISSUE_REF_RE.finditer(text or "")}
    refs.update(int(match.group(1)) for match in URL_RE.finditer(text or ""))
    return refs


def referenced_paths(text: str) -> list[str]:
    paths: set[str] = set()
    for match in PATH_REF_RE.finditer(text or ""):
        path = match.group("path").rstrip(".,;:)\"]}'")
        if not path or path.endswith("/"):
            continue
        paths.add(path)
    return sorted(paths)


def slugify(value: str, *, max_length: int = 48) -> str:
    value = value.lower()
    value = re.sub(r"\[[^]]+\]", " ", value)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    value = re.sub(r"-+", "-", value)
    if not value:
        return "issue"
    return value[:max_length].rstrip("-")


def sorted_unique(values: Iterable[Any]) -> list[Any]:
    return sorted(set(values))


def issue_number(issue: Mapping[str, Any]) -> int:
    raw = issue.get("number")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TriageError(f"issue has invalid number: {raw!r}")
    return raw


def normalize_labels(raw: Any) -> list[str]:
    labels: list[str] = []
    for value in raw or []:
        if isinstance(value, str):
            labels.append(value)
        elif isinstance(value, Mapping):
            name = value.get("name")
            if isinstance(name, str):
                labels.append(name)
    return sorted(set(labels), key=str.lower)


def normalize_milestone(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, int) and not isinstance(raw, bool):
        return {"number": raw, "title": None, "state": None}
    if not isinstance(raw, Mapping):
        return None
    number = raw.get("number")
    if number is None and isinstance(raw.get("id"), int):
        number = raw.get("id")
    return {
        "number": number
        if isinstance(number, int) and not isinstance(number, bool)
        else None,
        "title": raw.get("title") if isinstance(raw.get("title"), str) else None,
        "state": raw.get("state") if isinstance(raw.get("state"), str) else None,
    }


def normalize_issue(raw: Mapping[str, Any]) -> dict[str, Any]:
    number = raw.get("number", raw.get("issue_number"))
    if isinstance(number, str) and number.isdigit():
        number = int(number)
    state = raw.get("state") or "open"
    html_url = raw.get("html_url") or raw.get("url") or raw.get("display_url")
    assignees: list[str] = []
    for item in raw.get("assignees") or []:
        if isinstance(item, str):
            assignees.append(item)
        elif isinstance(item, Mapping):
            login = item.get("login")
            if isinstance(login, str):
                assignees.append(login)
    return {
        "number": number,
        "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
        "body": raw.get("body") if isinstance(raw.get("body"), str) else "",
        "state": state if isinstance(state, str) else "unknown",
        "state_reason": raw.get("state_reason"),
        "labels": normalize_labels(raw.get("labels")),
        "milestone": normalize_milestone(raw.get("milestone")),
        "assignees": sorted(set(assignees)),
        "updated_at": raw.get("updated_at") or raw.get("updatedAt"),
        "created_at": raw.get("created_at") or raw.get("createdAt"),
        "closed_at": raw.get("closed_at") or raw.get("closedAt"),
        "html_url": html_url,
        "comments": raw.get("comments")
        if isinstance(raw.get("comments"), list)
        else [],
    }


def normalize_pull(raw: Mapping[str, Any]) -> dict[str, Any]:
    result = normalize_issue(raw)
    result.update(
        {
            "base_ref": raw.get("base_ref") or raw.get("baseRefName"),
            "head_ref": raw.get("head_ref") or raw.get("headRefName"),
            "draft": bool(raw.get("draft") or raw.get("isDraft")),
            "merged_at": raw.get("merged_at") or raw.get("mergedAt"),
            "merge_commit_sha": raw.get("merge_commit_sha") or raw.get("mergeCommit"),
        }
    )
    return result


def issue_map(
    snapshot: Mapping[str, Any], *, include_closed: bool = True
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for raw in snapshot.get("issues") or []:
        if not isinstance(raw, Mapping):
            continue
        item = normalize_issue(raw)
        number = item.get("number")
        if not isinstance(number, int):
            continue
        if not include_closed and item.get("state") != "open":
            continue
        result[number] = item
    return result


def pull_map(snapshot: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    """Return pull requests from either synthetic or live snapshot schemas."""

    result: dict[int, dict[str, Any]] = {}
    for collection_name in ("pulls", "pull_requests", "open_pull_requests"):
        values = snapshot.get(collection_name) or []
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, Mapping):
                continue
            item = normalize_pull(raw)
            number = item.get("number")
            if isinstance(number, int):
                result[number] = item
    return result


def repository_name(snapshot: Mapping[str, Any]) -> str | None:
    """Return owner/name from either supported snapshot repository shape."""

    value = snapshot.get("repository")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        full_name = value.get("full_name")
        if isinstance(full_name, str) and full_name:
            return full_name
        owner = value.get("owner")
        name = value.get("name")
        if isinstance(owner, str) and owner and isinstance(name, str) and name:
            return f"{owner}/{name}"
    return None


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Return the declared digest from either supported snapshot schema."""

    for key in ("snapshot_sha256", "snapshot_digest"):
        value = snapshot.get(key)
        if isinstance(value, str) and value:
            return value
    return content_digest(snapshot)


def content_digest(snapshot: Mapping[str, Any]) -> str:
    excluded = {"generated_at", "snapshot_digest", "snapshot_sha256"}
    payload = {key: value for key, value in snapshot.items() if key not in excluded}
    for key, field in (
        ("issues", "number"),
        ("pulls", "number"),
        ("pull_requests", "number"),
        ("open_pull_requests", "number"),
        ("milestones", "number"),
        ("labels", "name"),
    ):
        values = payload.get(key)
        if isinstance(values, list):
            payload[key] = sorted(
                values,
                key=lambda item: (
                    str(item.get(field, "")).lower()
                    if isinstance(item, Mapping)
                    else str(item)
                ),
            )
    return sha256_json(payload)


def iter_markdown_lines(text: str) -> Iterator[tuple[int, str, bool]]:
    """Yield line number, text, and whether the line is inside a fenced block."""

    in_fence = False
    fence_char = ""
    fence_len = 0
    for number, line in enumerate((text or "").splitlines(), start=1):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            token = marker.group(1)
            char = token[0]
            if not in_fence:
                in_fence = True
                fence_char = char
                fence_len = len(token)
            elif char == fence_char and len(token) >= fence_len:
                in_fence = False
                fence_char = ""
                fence_len = 0
            yield number, line, True
            continue
        yield number, line, in_fence


def parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
