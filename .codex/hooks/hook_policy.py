#!/usr/bin/env python3
"""Local Codex hook policy for protected repository surfaces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import codex_surface
from scripts.triage import repo_config


FALLBACK_RECEIPT = Path("output/codex/quality-receipt.json")

GITHUB_MUTATION_PATTERNS = (
    re.compile(
        r"\bgh\s+issue\s+"
        r"(?:create|edit|close|reopen|delete|comment|lock|unlock|pin|unpin|transfer)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgh\s+pr\s+(?:merge|close|edit|ready|lock|unlock|comment|review)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bgh\s+repo\s+edit\b", re.IGNORECASE),
    re.compile(r"\bgh\s+workflow\s+(?:run|disable|enable)\b", re.IGNORECASE),
    re.compile(r"\bgh\s+secret\s+set\b", re.IGNORECASE),
    re.compile(r"\bgh\s+variable\s+set\b", re.IGNORECASE),
    re.compile(
        r"\bgh\s+(?:label|milestone)\s+"
        r"(?:create|edit|delete|clone|close|reopen)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgh\s+project\s+(?:create|edit|delete|item-(?:add|edit|delete|move))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgh\s+api\b(?=.*(?:--method|-X)\s*(?:POST|PUT|PATCH|DELETE)\b)"
        r"(?=.*\b(?:issues|pulls|labels|milestones|projects)\b)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bgh\s+api\s+graphql\b"
        r"(?=.*(?:-f|--field|-F|--raw-field)\s+query\s*=\s*['\"]?\s*mutation\b)",
        re.IGNORECASE | re.DOTALL,
    ),
)

UNSAFE_COMMAND_PATTERNS = (
    re.compile(r"\brm\s+(?:-[^\s]*[rf][^\s]*|-[^\s]*[fr][^\s]*)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\s+-[^\s]*f", re.IGNORECASE),
    re.compile(r"\bgit\s+checkout\s+--\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\b(?=.*\s--force(?:-with-lease)?\b)", re.IGNORECASE),
    re.compile(r"\bchmod\s+-R\b", re.IGNORECASE),
    re.compile(r"\bcurl\b.+\|\s*(?:sh|bash|zsh)\b", re.IGNORECASE),
)


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def receipt_digest(receipt: Mapping[str, object]) -> str:
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key != "quality_receipt_digest"
    }
    return hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def load_payload(stdin: str) -> dict[str, object]:
    value = json.loads(stdin)
    if not isinstance(value, dict):
        raise ValueError("hook payload must be a JSON object")
    return value


def read_stdin_payload() -> dict[str, object]:
    return load_payload(sys.stdin.read())


def command_from_payload(payload: Mapping[str, object]) -> str:
    if payload.get("tool_name") != "Bash":
        return ""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        return tool_input
    if isinstance(tool_input, Mapping):
        for key in ("cmd", "command", "shell_command"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    return ""


def github_mutation_reason(command: str) -> str | None:
    if not command:
        return None
    if any(pattern.search(command) for pattern in GITHUB_MUTATION_PATTERNS):
        return (
            "Blocked GitHub metadata mutation command. Continue only with exact "
            "maintainer approval for a one-off operator action outside read-only "
            "governance artifacts."
        )
    return None


def unsafe_command_reason(command: str) -> str | None:
    if not command:
        return None
    if any(pattern.search(command) for pattern in UNSAFE_COMMAND_PATTERNS):
        return "Blocked known unsafe command shape."
    return None


def pre_tool_use_pass() -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}


def pre_tool_use_deny(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def permission_request_pass() -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest"}}


def permission_request_deny(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": reason,
            },
        }
    }


def evaluate_pre_tool_use(payload: Mapping[str, object]) -> dict[str, object]:
    command = command_from_payload(payload)
    reason = github_mutation_reason(command) or unsafe_command_reason(command)
    if reason:
        return pre_tool_use_deny(reason)
    return pre_tool_use_pass()


def evaluate_permission_request(payload: Mapping[str, object]) -> dict[str, object]:
    command = command_from_payload(payload)
    reason = unsafe_command_reason(command) or github_mutation_reason(command)
    if reason:
        return permission_request_deny(reason)
    return permission_request_pass()


normalize_path = codex_surface.normalize_path


def _load_repo_policy_for_hook() -> repo_config.RepoPolicy | None:
    try:
        return repo_config.load_repo_policy()
    except repo_config.RepoConfigError:
        return None


def is_protected_path(
    path: str, *, repo_policy: repo_config.RepoPolicy | None = None
) -> bool:
    return codex_surface.is_protected_path(path, repo_policy=repo_policy)


def changed_paths_from_git(root: Path) -> tuple[str, ...] | None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
    )
    if result.returncode != 0:
        return None
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            paths.extend(part for part in path.split(" -> ") if part)
        elif path:
            paths.append(path)
    return tuple(paths)


def load_receipt(receipt_path: Path) -> tuple[dict[str, object] | None, str | None]:
    if not receipt_path.is_file():
        return None, f"missing {receipt_path.as_posix()}"
    try:
        value = json.loads(receipt_path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"cannot read codex-quality receipt: {type(exc).__name__}"
    if not isinstance(value, dict):
        return None, "codex-quality receipt is not a JSON object"
    expected = value.get("quality_receipt_digest")
    if not isinstance(expected, str) or expected != receipt_digest(value):
        return None, "codex-quality receipt digest is invalid"
    if value.get("passed") is not True:
        return None, "codex-quality receipt did not pass"
    return value, None


def receipt_freshness_bound_paths(
    receipt: Mapping[str, object],
    *,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> tuple[tuple[str, ...] | None, str | None]:
    value = receipt.get("freshness_bound_protected_paths")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None, "codex-quality receipt has no valid freshness_bound_protected_paths"
    normalized = codex_surface.protected_paths(value, repo_policy=repo_policy)
    if list(normalized) != value:
        return (
            None,
            "codex-quality receipt freshness_bound_protected_paths is not deterministic",
        )
    return normalized, None


def receipt_covers_protected_paths(
    *,
    root: Path,
    receipt_path: Path,
    protected_paths: Sequence[str],
    repo_policy: repo_config.RepoPolicy | None = None,
) -> tuple[bool, str | None]:
    receipt, error = load_receipt(receipt_path)
    if error is not None:
        return False, error

    freshness_bound_paths, error = receipt_freshness_bound_paths(
        receipt, repo_policy=repo_policy
    )
    if error is not None:
        return False, error

    normalized_protected_paths = codex_surface.protected_paths(
        protected_paths, repo_policy=repo_policy
    )
    missing_local_paths = [
        path for path in normalized_protected_paths if not (root / path).exists()
    ]
    if missing_local_paths:
        return False, "protected paths deleted or unavailable: " + ", ".join(
            missing_local_paths
        )

    unbound_paths = sorted(set(normalized_protected_paths) - set(freshness_bound_paths))
    if unbound_paths:
        return (
            False,
            "protected paths not freshness-bound by codex-quality receipt: "
            + ", ".join(unbound_paths),
        )

    receipt_mtime = receipt_path.stat().st_mtime_ns
    stale_paths: list[str] = []
    for raw_path in normalized_protected_paths:
        path = root / raw_path
        if path.stat().st_mtime_ns > receipt_mtime:
            stale_paths.append(raw_path)
    if stale_paths:
        return False, "receipt is older than protected changes: " + ", ".join(
            sorted(stale_paths)
        )
    return True, None


def evaluate_stop(
    payload: Mapping[str, object],
    *,
    root: Path | None = None,
    changed_paths: Sequence[str] | None = None,
    receipt_path: Path | None = None,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> dict[str, object]:
    if payload.get("stop_hook_active") is True:
        return {"systemMessage": "stop hook already active; skipping nested run."}

    root = root or Path(str(payload.get("cwd") or ".")).resolve()
    active_policy = repo_policy or _load_repo_policy_for_hook()
    receipt_path = receipt_path or (
        root
        / (
            active_policy.codex.quality_receipt_path
            if active_policy is not None
            else FALLBACK_RECEIPT
        )
    )
    discovered_paths: Sequence[str] | None = changed_paths
    if discovered_paths is None:
        discovered_paths = changed_paths_from_git(root)
    if discovered_paths is None:
        return {
            "decision": "block",
            "reason": (
                "Unable to inspect local git status for protected Codex surfaces. "
                "Resolve git status visibility before finalizing."
            ),
        }

    protected_paths = tuple(
        path
        for path in discovered_paths
        if is_protected_path(path, repo_policy=active_policy)
    )
    if not protected_paths:
        return {"systemMessage": "no protected Codex surfaces changed."}

    covered, reason = receipt_covers_protected_paths(
        root=root,
        receipt_path=receipt_path,
        protected_paths=protected_paths,
        repo_policy=active_policy,
    )
    if covered:
        return {"systemMessage": "codex-quality receipt covers protected changes."}
    detail = f" ({reason})" if reason else ""
    return {
        "decision": "block",
        "reason": (
            "Protected Codex/governance files changed without a covering "
            f"codex-quality receipt before final response.{detail}"
        ),
    }


def emit_json(output: Mapping[str, object]) -> None:
    print(json.dumps(output, sort_keys=True, ensure_ascii=True))


def main_pre_tool_use() -> int:
    try:
        output = evaluate_pre_tool_use(read_stdin_payload())
    except Exception:
        output = pre_tool_use_deny("Invalid hook payload; refusing to evaluate tool use.")
    emit_json(output)
    return 0


def main_permission_request() -> int:
    try:
        output = evaluate_permission_request(read_stdin_payload())
    except Exception:
        output = permission_request_deny(
            "Invalid hook payload; refusing to approve permission request."
        )
    emit_json(output)
    return 0


def main_stop() -> int:
    try:
        output = evaluate_stop(read_stdin_payload())
    except Exception as exc:
        output = {
            "decision": "block",
            "reason": f"Stop hook failed safely: {type(exc).__name__}",
        }
    emit_json(output)
    return 0
