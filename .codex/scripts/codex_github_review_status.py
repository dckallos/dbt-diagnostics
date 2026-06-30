#!/usr/bin/env python3
"""Report whether the GitHub Codex review is current for a pull request."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.triage import repo_config


SCHEMA_VERSION = 1
CODEX_BOT_LOGIN = "chatgpt-codex-connector[bot]"
CODEX_BOT_LOGINS = frozenset({CODEX_BOT_LOGIN, "chatgpt-codex-connector"})
FOCUSED_REVIEW_COMMENT = (
    "@codex review for regressions in protected Codex/governance surfaces. "
    "Focus on whether the codex_reviewer custom agent remains packet-only and "
    "aligned with $codex-review; whether .codex/config.toml and "
    ".codex/agents/** are protected and semantically scanned; whether "
    "same-context review cannot satisfy #133; and whether this PR adds any "
    "GitHub comments/reviews/mutation, apply payloads, issue-body writes, "
    "full-repository prompt bundles, or packet schema changes."
)
STATUS_VALUES = frozenset(
    {
        "current_with_findings",
        "current_without_inline_findings",
        "stale_review",
        "manual_review_requested_pending",
        "manual_review_request_failed",
        "no_codex_review",
        "no_codex_review_for_current_head",
        "gh_unavailable",
        "unknown",
    }
)
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
REVIEWED_COMMIT_RE = re.compile(
    r"\bReviewed commit:\s*([0-9a-fA-F]{7,40})\b", re.IGNORECASE
)
MANUAL_REVIEW_RE = re.compile(r"^@codex\s+review\b", re.IGNORECASE)
CODEX_UNAVAILABLE_RE = re.compile(
    r"\b(usage limits?|limit reached|limits reached|unavailable|"
    r"unable to review|cannot review|can't review|could not review)\b",
    re.IGNORECASE,
)
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SECRET_SHAPED_RE = re.compile(
    r"(ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]+|"
    r"Bearer\s+[A-Za-z0-9._-]+|token=[^ \t\r\n]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GhPayloads:
    pr: Mapping[str, Any]
    reviews: Sequence[Mapping[str, Any]]
    inline_comments: Sequence[Mapping[str, Any]]
    issue_comments: Sequence[Mapping[str, Any]]
    reactions_by_comment_id: Mapping[int, Sequence[Mapping[str, Any]]]


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _user_login(item: Mapping[str, Any]) -> str | None:
    user = item.get("user")
    if not isinstance(user, Mapping):
        return None
    return _string(user.get("login"))


def _is_codex_bot(item: Mapping[str, Any]) -> bool:
    return _user_login(item) in CODEX_BOT_LOGINS


def _normalize_sha(value: object) -> str | None:
    text = _string(value)
    if text is None:
        return None
    candidate = text.strip().lower()
    if SHA_RE.fullmatch(candidate):
        return candidate
    return None


def _short_sha(value: str | None) -> str | None:
    normalized = _normalize_sha(value)
    if normalized is None:
        return None
    return normalized[:12]


def _timestamp(value: Mapping[str, Any]) -> str:
    return _string(value.get("submitted_at")) or _string(value.get("created_at")) or ""


def _sha_from_review(review: Mapping[str, Any]) -> tuple[str | None, str | None]:
    commit_id = _normalize_sha(review.get("commit_id"))
    if commit_id is not None:
        return commit_id, "review.commit_id"
    body = _string(review.get("body"))
    if body is None:
        return None, None
    match = REVIEWED_COMMIT_RE.search(body)
    if match:
        return match.group(1).lower(), "review.body"
    return None, None


def _sha_matches(candidate: str | None, current: str | None) -> bool:
    normalized_candidate = _normalize_sha(candidate)
    normalized_current = _normalize_sha(current)
    if normalized_candidate is None or normalized_current is None:
        return False
    return (
        normalized_candidate == normalized_current
        or normalized_current.startswith(normalized_candidate)
        or normalized_candidate.startswith(normalized_current)
    )


def _comment_head_sha(comment: Mapping[str, Any]) -> str | None:
    return (
        _normalize_sha(comment.get("commit_id"))
        or _normalize_sha(comment.get("original_commit_id"))
    )


def _untrusted_comment_lines(body: str) -> tuple[str, ...]:
    lines: list[str] = []
    in_fence = False
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or stripped.startswith(">"):
            continue
        lines.append(stripped)
    return tuple(lines)


def _is_manual_review_request(comment: Mapping[str, Any]) -> bool:
    if _is_codex_bot(comment):
        return False
    body = _string(comment.get("body"))
    if body is None:
        return False
    return any(MANUAL_REVIEW_RE.search(line) for line in _untrusted_comment_lines(body))


def _is_codex_unavailable_comment(comment: Mapping[str, Any]) -> bool:
    if not _is_codex_bot(comment):
        return False
    body = _string(comment.get("body"))
    return body is not None and CODEX_UNAVAILABLE_RE.search(body) is not None


def _latest_item(items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not items:
        return None
    return sorted(
        items,
        key=lambda item: (
            _timestamp(item),
            _int(item.get("id")) or 0,
        ),
    )[-1]


def _recommended_next_step(status: str) -> str:
    if status == "current_with_findings":
        return "review_codex_findings"
    if status == "current_without_inline_findings":
        return "no_codex_github_review_action_needed"
    if status == "manual_review_requested_pending":
        return "wait_for_codex_review"
    if status == "manual_review_request_failed":
        return "maintainer_retry_focused_codex_review_later"
    if status == "gh_unavailable":
        return "rerun_when_gh_available"
    if status == "unknown":
        return "inspect_codex_review_status_manually"
    return "maintainer_post_focused_codex_review_comment"


def _should_emit_focused_comment(status: str) -> bool:
    return status in {
        "stale_review",
        "manual_review_request_failed",
        "no_codex_review",
        "no_codex_review_for_current_head",
    }


def _safe_error(error: str) -> str:
    collapsed = " ".join(error.split())
    if not collapsed:
        collapsed = "gh unavailable"
    redacted = SECRET_SHAPED_RE.sub("[REDACTED]", collapsed)
    return redacted[:240]


def unavailable_status(
    *,
    repository: str,
    pr_number: int,
    error: str,
) -> dict[str, object]:
    safe_error = _safe_error(error)
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "pr_number": pr_number,
        "pr_url": None,
        "pr_state": None,
        "is_draft": None,
        "current_head_sha": None,
        "current_head_short_sha": None,
        "latest_codex_review_id": None,
        "latest_codex_review_state": None,
        "latest_codex_review_sha": None,
        "latest_codex_review_short_sha": None,
        "latest_codex_review_submitted_at": None,
        "latest_codex_review_commit_source": None,
        "codex_review_current": False,
        "codex_inline_findings_count": 0,
        "codex_inline_findings_on_current_head_count": 0,
        "codex_issue_comments_count": 0,
        "manual_review_requested_at": None,
        "manual_review_request_comment_id": None,
        "bot_reacted_to_manual_request": None,
        "codex_review_unavailable_at": None,
        "codex_review_unavailable_comment_id": None,
        "status": "gh_unavailable",
        "recommended_next_step": _recommended_next_step("gh_unavailable"),
        "focused_review_comment": None,
        "pagination_complete": False,
        "warnings": [f"GitHub review status unavailable: {safe_error}"],
    }


def build_review_status(
    *,
    repository: str,
    pr_number: int,
    payloads: GhPayloads,
) -> dict[str, object]:
    pr = payloads.pr
    current_head_sha = _string(pr.get("headRefOid"))
    codex_reviews = [review for review in payloads.reviews if _is_codex_bot(review)]
    latest_review = _latest_item(codex_reviews)
    latest_review_sha: str | None = None
    latest_review_commit_source: str | None = None
    if latest_review is not None:
        latest_review_sha, latest_review_commit_source = _sha_from_review(latest_review)

    codex_inline_comments = [
        comment for comment in payloads.inline_comments if _is_codex_bot(comment)
    ]
    current_head_inline_comments = [
        comment
        for comment in codex_inline_comments
        if _sha_matches(_comment_head_sha(comment), current_head_sha)
    ]
    codex_issue_comments = [
        comment for comment in payloads.issue_comments if _is_codex_bot(comment)
    ]
    manual_requests = [
        comment
        for comment in payloads.issue_comments
        if _is_manual_review_request(comment)
    ]
    latest_manual_request = _latest_item(manual_requests)
    latest_manual_id = (
        _int(latest_manual_request.get("id")) if latest_manual_request else None
    )
    latest_unavailable_comment: Mapping[str, Any] | None = None
    if latest_manual_request is not None:
        manual_timestamp = _timestamp(latest_manual_request)
        unavailable_comments = [
            comment
            for comment in codex_issue_comments
            if _is_codex_unavailable_comment(comment)
            and _timestamp(comment) >= manual_timestamp
        ]
        latest_unavailable_comment = _latest_item(unavailable_comments)
    bot_reacted: bool | None = None
    if latest_manual_id is not None and latest_manual_id in payloads.reactions_by_comment_id:
        reactions = payloads.reactions_by_comment_id[latest_manual_id]
        bot_reacted = any(_is_codex_bot(reaction) for reaction in reactions)

    codex_review_current = _sha_matches(latest_review_sha, current_head_sha)
    latest_review_timestamp = _timestamp(latest_review) if latest_review else ""
    latest_manual_timestamp = (
        _timestamp(latest_manual_request) if latest_manual_request else ""
    )
    latest_unavailable_timestamp = (
        _timestamp(latest_unavailable_comment) if latest_unavailable_comment else ""
    )
    manual_after_latest_review = (
        latest_manual_request is not None
        and (latest_review is None or latest_manual_timestamp > latest_review_timestamp)
    )
    unavailable_after_manual = (
        latest_unavailable_comment is not None
        and latest_manual_request is not None
        and latest_unavailable_timestamp >= latest_manual_timestamp
        and (
            latest_review is None
            or latest_unavailable_timestamp >= latest_review_timestamp
        )
    )
    warnings: list[str] = []
    if latest_review is not None and latest_review_sha is None:
        warnings.append(
            "Latest Codex review did not expose a commit SHA in review metadata "
            "or body text."
        )
    if latest_manual_request is not None:
        warnings.append(
            "Manual @codex review request timing is observable from comment "
            "timestamps only; this command does not verify head commit time."
        )
    if latest_unavailable_comment is not None:
        warnings.append(
            "Codex bot reported review usage limits or unavailable review "
            "after a manual @codex review request."
        )

    if codex_review_current and current_head_inline_comments:
        status = "current_with_findings"
    elif codex_review_current:
        status = "current_without_inline_findings"
    elif unavailable_after_manual:
        status = "manual_review_request_failed"
    elif manual_after_latest_review:
        status = "manual_review_requested_pending"
    elif current_head_sha is None:
        status = "unknown"
    elif latest_review_sha is not None and current_head_sha is not None:
        status = "stale_review"
    elif latest_review is not None:
        status = "no_codex_review_for_current_head"
    else:
        status = "no_codex_review"

    assert status in STATUS_VALUES
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "pr_number": pr_number,
        "pr_url": _string(pr.get("url")),
        "pr_state": _string(pr.get("state")),
        "is_draft": _bool(pr.get("isDraft")),
        "current_head_sha": current_head_sha,
        "current_head_short_sha": _short_sha(current_head_sha),
        "latest_codex_review_id": (
            _int(latest_review.get("id")) if latest_review is not None else None
        ),
        "latest_codex_review_state": (
            _string(latest_review.get("state")) if latest_review is not None else None
        ),
        "latest_codex_review_sha": latest_review_sha,
        "latest_codex_review_short_sha": _short_sha(latest_review_sha),
        "latest_codex_review_submitted_at": (
            _string(latest_review.get("submitted_at"))
            if latest_review is not None
            else None
        ),
        "latest_codex_review_commit_source": latest_review_commit_source,
        "codex_review_current": codex_review_current,
        "codex_inline_findings_count": len(codex_inline_comments),
        "codex_inline_findings_on_current_head_count": len(
            current_head_inline_comments
        ),
        "codex_issue_comments_count": len(codex_issue_comments),
        "manual_review_requested_at": (
            _string(latest_manual_request.get("created_at"))
            if latest_manual_request is not None
            else None
        ),
        "manual_review_request_comment_id": latest_manual_id,
        "bot_reacted_to_manual_request": bot_reacted,
        "codex_review_unavailable_at": (
            _string(latest_unavailable_comment.get("created_at"))
            if latest_unavailable_comment is not None
            else None
        ),
        "codex_review_unavailable_comment_id": (
            _int(latest_unavailable_comment.get("id"))
            if latest_unavailable_comment is not None
            else None
        ),
        "status": status,
        "recommended_next_step": _recommended_next_step(status),
        "focused_review_comment": (
            FOCUSED_REVIEW_COMMENT if _should_emit_focused_comment(status) else None
        ),
        "pagination_complete": True,
        "warnings": warnings,
    }


def _load_json_with_gh(args: Sequence[str]) -> object:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "gh command failed"
        raise RuntimeError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON: {exc}") from exc


def _flatten_paginated_list(payload: object, label: str) -> list[object]:
    if not isinstance(payload, list):
        raise RuntimeError(f"{label} API returned a non-array paginated payload")
    if all(isinstance(page, list) for page in payload):
        flattened: list[object] = []
        for page in payload:
            if isinstance(page, list):
                flattened.extend(page)
        return flattened
    return payload


def _load_paginated_list_with_gh(endpoint: str, label: str) -> list[object]:
    return _flatten_paginated_list(
        _load_json_with_gh(["api", endpoint, "--paginate", "--slurp"]),
        label,
    )


def _load_payloads(*, repository: str, pr_number: int) -> GhPayloads:
    owner, name = repository.split("/", 1)
    pr = _load_json_with_gh(
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repository,
            "--json",
            "number,url,state,isDraft,headRefOid,headRefName,baseRefName,reviewDecision",
        ]
    )
    reviews = _load_paginated_list_with_gh(
        f"repos/{owner}/{name}/pulls/{pr_number}/reviews",
        "pull reviews",
    )
    inline_comments = _load_paginated_list_with_gh(
        f"repos/{owner}/{name}/pulls/{pr_number}/comments",
        "pull review comments",
    )
    issue_comments = _load_paginated_list_with_gh(
        f"repos/{owner}/{name}/issues/{pr_number}/comments",
        "issue comments",
    )
    if not isinstance(pr, Mapping):
        raise RuntimeError("gh pr view returned a non-object payload")

    reactions_by_comment_id: dict[int, Sequence[Mapping[str, Any]]] = {}
    manual_ids = [
        _int(comment.get("id"))
        for comment in issue_comments
        if isinstance(comment, Mapping) and _is_manual_review_request(comment)
    ]
    for comment_id in sorted(item for item in manual_ids if item is not None):
        try:
            reactions = _load_paginated_list_with_gh(
                f"repos/{owner}/{name}/issues/comments/{comment_id}/reactions",
                "issue comment reactions",
            )
        except RuntimeError:
            continue
        reactions_by_comment_id[comment_id] = [
            reaction for reaction in reactions if isinstance(reaction, Mapping)
        ]

    return GhPayloads(
        pr=pr,
        reviews=[review for review in reviews if isinstance(review, Mapping)],
        inline_comments=[
            comment for comment in inline_comments if isinstance(comment, Mapping)
        ],
        issue_comments=[
            comment for comment in issue_comments if isinstance(comment, Mapping)
        ],
        reactions_by_comment_id=reactions_by_comment_id,
    )


def default_repository() -> str:
    return repo_config.load_repo_policy().repository.full_name


def positive_pr_number(value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "PR number must be a positive integer"
        ) from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("PR number must be a positive integer")
    return parsed


def repository_name(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("repository must use owner/name")
    return value


def render_human(status: Mapping[str, object]) -> str:
    lines = [
        "Codex GitHub review status",
        f"- repository: {status['repository']}",
        f"- PR: #{status['pr_number']} {status.get('pr_url') or ''}".rstrip(),
        f"- state: {status.get('pr_state')} draft={status.get('is_draft')}",
        f"- current head: {status.get('current_head_sha')}",
        f"- latest Codex review SHA: {status.get('latest_codex_review_sha')}",
        f"- latest Codex review state: {status.get('latest_codex_review_state')}",
        (
            "- latest Codex review submitted_at: "
            f"{status.get('latest_codex_review_submitted_at')}"
        ),
        f"- Codex review current: {status.get('codex_review_current')}",
        (
            "- visible Codex inline findings on current head: "
            f"{status.get('codex_inline_findings_on_current_head_count')}"
        ),
        (
            "- visible Codex inline findings total: "
            f"{status.get('codex_inline_findings_count')}"
        ),
        f"- Codex issue/PR comments: {status.get('codex_issue_comments_count')}",
        f"- manual @codex review requested_at: {status.get('manual_review_requested_at')}",
        (
            "- manual request bot reaction observable: "
            f"{status.get('bot_reacted_to_manual_request')}"
        ),
        (
            "- Codex unavailable/usage-limit response at: "
            f"{status.get('codex_review_unavailable_at')}"
        ),
        f"- pagination complete: {status.get('pagination_complete')}",
        f"- status: {status.get('status')}",
        f"- recommended next step: {status.get('recommended_next_step')}",
    ]
    warnings = status.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("- warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
    focused_comment = status.get("focused_review_comment")
    if isinstance(focused_comment, str) and focused_comment:
        lines.extend(
            [
                "",
                "Maintainer-posted focused review comment:",
                focused_comment,
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr_number", type=positive_pr_number)
    parser.add_argument(
        "--repo",
        type=repository_name,
        help="owner/name repository, defaults to policy",
    )
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON")
    args = parser.parse_args(argv)

    repository = args.repo or "unknown"
    try:
        if args.repo is None:
            repository = repository_name(default_repository())
        payloads = _load_payloads(repository=repository, pr_number=args.pr_number)
        status = build_review_status(
            repository=repository,
            pr_number=args.pr_number,
            payloads=payloads,
        )
    except (
        RuntimeError,
        repo_config.RepoConfigError,
        ValueError,
        argparse.ArgumentTypeError,
    ) as exc:
        status = unavailable_status(
            repository=repository,
            pr_number=args.pr_number,
            error=str(exc),
        )

    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True, ensure_ascii=True))
    else:
        print(render_human(status), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
