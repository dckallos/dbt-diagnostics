#!/usr/bin/env python3
"""Print a read-only live issue and local-checkout context packet."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.triage import common as governance_common
from scripts.triage import repo_config


class ContextError(RuntimeError):
    """Raised when live task context cannot be assembled safely."""


def run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = 30.0,
) -> str:
    process = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "command failed"
        raise ContextError(f"{' '.join(args)}: {message}")
    return process.stdout.strip()


def redact_remote(value: str | None) -> str | None:
    if not value or "://" not in value:
        return value
    parsed = urlsplit(value)
    if "@" not in parsed.netloc:
        return value
    host = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def git_value(root: Path, *args: str) -> str | None:
    try:
        return run(["git", *args], cwd=root, timeout=10) or None
    except (ContextError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def infer_issue_number(branch: str | None) -> int | None:
    if not branch:
        return None
    match = re.fullmatch(
        r"(?:[^/]+/)?(?:issue[-_/]?)?(?P<number>\d+)(?:[-_/].*)?",
        branch,
    )
    return int(match.group("number")) if match else None


def latest_progress_entry(path: Path, limit: int = 12_000) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(re.finditer(r"(?m)^## 20\d\d-\d\d-\d\d.*$", text))
    if not matches:
        return None
    entry = text[matches[-1].start() :].strip()
    if len(entry) > limit:
        return entry[:limit].rstrip() + "\n\n[truncated]"
    return entry


def referenced_paths(
    body: str,
    root: Path,
    *,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> list[dict[str, Any]]:
    active_policy = repo_policy or repo_config.load_repo_policy()
    values = governance_common.referenced_paths(
        body, reference_roots=active_policy.paths.reference_roots
    )
    return [{"path": value, "exists": (root / value).exists()} for value in values]


def issue_payload(
    *,
    root: Path,
    issue_number: int,
    repository: str,
    include_comments: bool,
) -> dict[str, Any]:
    fields = [
        "number",
        "title",
        "state",
        "url",
        "body",
        "labels",
        "milestone",
        "assignees",
        "createdAt",
        "updatedAt",
    ]
    if include_comments:
        fields.append("comments")

    raw = run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repository,
            "--json",
            ",".join(fields),
        ],
        cwd=root,
    )
    issue = json.loads(raw)
    if include_comments and isinstance(issue.get("comments"), list):
        issue["comments"] = issue["comments"][-5:]
    return issue


def discover_repository(root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    if configured := os.environ.get("CODEX_GITHUB_REPO"):
        return configured
    return repo_config.load_repo_policy().repository.full_name
    return run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=root,
    )


def local_payload(
    root: Path, *, repo_policy: repo_config.RepoPolicy | None = None
) -> dict[str, Any]:
    active_policy = repo_policy or repo_config.load_repo_policy()
    status = git_value(root, "status", "--porcelain")
    branch = git_value(root, "branch", "--show-current")
    return {
        "root": str(root),
        "is_git_checkout": git_value(root, "rev-parse", "--is-inside-work-tree") == "true",
        "branch": branch,
        "head": git_value(root, "rev-parse", "--short", "HEAD"),
        "origin": redact_remote(git_value(root, "remote", "get-url", "origin")),
        "changed_paths": 0 if not status else len(status.splitlines()),
        "inferred_issue": infer_issue_number(branch),
        "protected_branches": list(active_policy.repository.protected_branches),
        "latest_progress": latest_progress_entry(
            root / active_policy.repository.progress_log_path
        ),
    }


def render_local_markdown(local: dict[str, Any]) -> str:
    lines = [
        "# Codex local context",
        "",
        f"Root: {local['root']}",
        f"Git checkout: {'yes' if local['is_git_checkout'] else 'no'}",
        f"Branch: {local.get('branch') or 'unknown'}",
        f"HEAD: {local.get('head') or 'unknown'}",
        f"Changed paths: {local['changed_paths']}",
        f"Origin: {local.get('origin') or 'unknown'}",
        f"Inferred issue: {local.get('inferred_issue') or 'none'}",
    ]
    progress = local.get("latest_progress")
    if progress:
        lines.extend(["", "## Latest local progress entry", "", progress])
    lines.extend(
        [
            "",
            "## Next step",
            "",
            "Run `bash .codex/bin/action.sh context <issue-number>` before editing.",
            "The command reads the live issue and does not write a context cache.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_issue_markdown(payload: dict[str, Any]) -> str:
    issue = payload["issue"]
    local = payload["local"]
    labels = ", ".join(label["name"] for label in issue.get("labels", [])) or "none"
    assignees = ", ".join(user["login"] for user in issue.get("assignees", [])) or "none"
    milestone = issue.get("milestone")
    milestone_name = milestone.get("title") if isinstance(milestone, dict) else "none"

    lines = [
        "# Codex task context",
        "",
        f"Repository: {payload['repository']}",
        f"Issue: #{issue['number']} - {issue['title']}",
        f"State: {issue['state']}",
        f"URL: {issue['url']}",
        f"Updated: {issue.get('updatedAt') or 'unknown'}",
        f"Labels: {labels}",
        f"Milestone: {milestone_name}",
        f"Assignees: {assignees}",
        "",
        "## Local checkout",
        "",
        f"Branch: {local.get('branch') or 'unknown'}",
        f"HEAD: {local.get('head') or 'unknown'}",
        f"Changed paths: {local['changed_paths']}",
        f"Origin: {local.get('origin') or 'unknown'}",
        "",
        "## Live issue body",
        "",
        issue.get("body") or "[empty]",
    ]

    references = payload.get("referenced_paths", [])
    if references:
        lines.extend(["", "## Referenced repository paths", ""])
        for item in references:
            state = "present" if item["exists"] else "missing"
            lines.append(f"- {item['path']} ({state})")

    if issue.get("comments"):
        lines.extend(["", "## Most recent issue comments", ""])
        for comment in issue["comments"]:
            author = (comment.get("author") or {}).get("login", "unknown")
            lines.extend(
                [
                    f"### {author} at {comment.get('createdAt') or 'unknown'}",
                    "",
                    comment.get("body") or "[empty]",
                    "",
                ]
            )

    progress = local.get("latest_progress")
    if progress:
        lines.extend(["", "## Latest local progress entry", "", progress])

    lines.extend(
        [
            "",
            "## Start guard",
            "",
            "- Treat the live issue body above as current tracker state.",
            "- Read AGENTS.md before edits.",
            "- Confirm the branch is not "
            + " or ".join(local.get("protected_branches") or ["main"])
            + ".",
            "- Keep one issue per PR and run credential-free checks before handoff.",
            "- Do not mutate GitHub metadata unless this task explicitly authorizes it.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def issue_from_snapshot_file(path: Path, issue_number: int) -> dict[str, Any]:
    """Return one raw issue object from a tracker snapshot JSON.

    The snapshot is the read-only artifact produced by the triage toolchain;
    its ``issues`` list holds raw GitHub issue objects keyed by ``number``. This
    is the offline fallback when gh is unavailable or unauthenticated.
    """

    if not path.is_file():
        raise ContextError(f"snapshot not found: {path}")
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContextError(f"invalid snapshot JSON: {path}: {exc}") from exc
    issues = snapshot.get("issues") if isinstance(snapshot, dict) else None
    if not isinstance(issues, list):
        raise ContextError(f"snapshot has no issues list: {path}")
    for raw in issues:
        if isinstance(raw, dict) and raw.get("number") == issue_number:
            return raw
    raise ContextError(f"issue #{issue_number} not present in snapshot: {path}")


def default_snapshot_path(root: Path) -> Path:
    """Conventional snapshot location the triage toolchain writes and reads."""

    return root / "output" / "triage" / "snapshot.json"


def resolve_snapshot_path(explicit: Path | None, root: Path) -> Path | None:
    """Pick the snapshot to use: an explicit --snapshot wins; otherwise fall back
    to the conventional path only when it exists."""

    if explicit is not None:
        return explicit
    candidate = default_snapshot_path(root)
    return candidate if candidate.is_file() else None



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", nargs="?", type=int, help="GitHub issue number")
    parser.add_argument("--repo", help="repository in OWNER/NAME form")
    parser.add_argument(
        "--comments",
        action="store_true",
        help="include the five most recent comments",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--snapshot",
        type=Path,
        help=(
            "read the issue from a tracker snapshot JSON when gh is unavailable "
            "or unauthenticated (read-only offline fallback)"
        ),
    )
    args = parser.parse_args()

    root = Path(os.environ.get("CODEX_REPO_ROOT", Path.cwd())).resolve()
    try:
        active_policy = repo_config.load_repo_policy()
    except repo_config.RepoConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    local = local_payload(root, repo_policy=active_policy)
    configured_issue = os.environ.get("CODEX_ISSUE")
    if configured_issue:
        try:
            environment_issue = int(configured_issue)
        except ValueError:
            print("ERROR: CODEX_ISSUE must be an integer", file=sys.stderr)
            return 2
    else:
        environment_issue = None
    issue_number = args.issue or environment_issue or local.get("inferred_issue")

    if issue_number is None:
        payload = {"local": local, "issue": None}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(render_local_markdown(local), end="")
        return 0

    snapshot_path = resolve_snapshot_path(args.snapshot, root)
    gh_available = shutil.which("gh") is not None

    issue: dict[str, Any] | None = None
    repository: str | None = None
    source: str | None = None
    live_error: Exception | None = None

    # Attempt the live read first whenever gh is present. gh authentication is
    # not pre-gated: gh can read a public issue even when `gh auth status` is
    # imperfect, so try the read and fall back only if it actually fails. This
    # mirrors scripts/triage/triage.py, which has no auth pre-gate.
    if gh_available:
        try:
            repository = args.repo or os.environ.get("CODEX_GITHUB_REPO")
            if repository is None:
                repository = active_policy.repository.full_name
            issue = issue_payload(
                root=root,
                issue_number=int(issue_number),
                repository=repository,
                include_comments=args.comments,
            )
            source = "live"
        except (ContextError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            live_error = exc

    if issue is None:
        if snapshot_path is not None:
            try:
                issue = issue_from_snapshot_file(snapshot_path, int(issue_number))
            except (ContextError, json.JSONDecodeError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
            repository = args.repo or issue.get("repository") or "unknown/unknown"
            source = "snapshot"
            note = (
                "gh unavailable"
                if not gh_available
                else f"live gh read failed ({live_error})"
            )
            print(
                f"WARNING: {note}; read issue #{issue_number} from snapshot "
                f"{snapshot_path} (offline, read-only).",
                file=sys.stderr,
            )
        else:
            reason = (
                "gh is unavailable"
                if not gh_available
                else f"live gh read failed: {live_error}"
            )
            print(
                f"ERROR: {reason}; no snapshot at {default_snapshot_path(root)} and "
                "none passed via --snapshot. Generate one with 'python "
                "scripts/triage/triage.py snapshot --output "
                "output/triage/snapshot.json' or pass --snapshot PATH.",
                file=sys.stderr,
            )
            return 2

    payload = {
        "repository": repository,
        "issue": issue,
        "local": local,
        "source": source,
        "referenced_paths": referenced_paths(
            issue.get("body") or "", root, repo_policy=active_policy
        ),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_issue_markdown(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
