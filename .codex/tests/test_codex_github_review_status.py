from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / ".codex" / "scripts" / "codex_github_review_status.py"
EXPECTED_FOCUSED_REVIEW_COMMENT = (
    "@codex review for regressions in protected Codex/governance surfaces. "
    "Focus on whether the codex_reviewer custom agent remains packet-only and "
    "aligned with $codex-review; whether .codex/config.toml and "
    ".codex/agents/** are protected and semantically scanned; whether "
    "same-context review cannot satisfy #133; and whether this PR adds any "
    "GitHub comments/reviews/mutation, apply payloads, issue-body writes, "
    "full-repository prompt bundles, or packet schema changes."
)


def _module():
    spec = importlib.util.spec_from_file_location("codex_github_review_status", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _user(login: str) -> dict[str, object]:
    return {"login": login}


def _payloads(
    module: object,
    *,
    head_sha: str = "abcdef1234567890abcdef1234567890abcdef12",
    reviews: list[dict[str, object]] | None = None,
    inline_comments: list[dict[str, object]] | None = None,
    issue_comments: list[dict[str, object]] | None = None,
    reactions_by_comment_id: dict[int, list[dict[str, object]]] | None = None,
):
    return module.GhPayloads(
        pr={
            "number": 148,
            "url": "https://github.example/pr/148",
            "state": "OPEN",
            "isDraft": False,
            "headRefOid": head_sha,
        },
        reviews=reviews or [],
        inline_comments=inline_comments or [],
        issue_comments=issue_comments or [],
        reactions_by_comment_id=reactions_by_comment_id or {},
    )


def _status(module: object, **kwargs: object) -> dict[str, object]:
    return module.build_review_status(
        repository="dckallos/dbt-diagnostics",
        pr_number=148,
        payloads=_payloads(module, **kwargs),
    )


def _codex_review(
    *,
    review_id: int,
    commit_id: str | None,
    submitted_at: str,
    body: str = "",
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": review_id,
        "user": _user("chatgpt-codex-connector[bot]"),
        "state": "COMMENTED",
        "submitted_at": submitted_at,
        "body": body,
    }
    if commit_id is not None:
        value["commit_id"] = commit_id
    return value


def test_no_codex_review_exists() -> None:
    module = _module()
    status = _status(module)

    assert status["status"] == "no_codex_review"
    assert status["codex_review_current"] is False
    assert status["recommended_next_step"] == (
        "maintainer_post_focused_codex_review_comment"
    )


def test_current_review_without_inline_findings() -> None:
    module = _module()
    head = "abcdef1234567890abcdef1234567890abcdef12"
    status = _status(
        module,
        head_sha=head,
        reviews=[
            _codex_review(
                review_id=1,
                commit_id=head,
                submitted_at="2026-06-30T00:00:00Z",
            )
        ],
    )

    assert status["status"] == "current_without_inline_findings"
    assert status["codex_review_current"] is True
    assert status["codex_inline_findings_on_current_head_count"] == 0


def test_current_review_with_inline_findings_on_current_head() -> None:
    module = _module()
    head = "abcdef1234567890abcdef1234567890abcdef12"
    status = _status(
        module,
        head_sha=head,
        reviews=[
            _codex_review(
                review_id=1,
                commit_id=head,
                submitted_at="2026-06-30T00:00:00Z",
            )
        ],
        inline_comments=[
            {
                "id": 10,
                "user": _user("chatgpt-codex-connector[bot]"),
                "commit_id": head,
                "body": "finding",
            },
            {
                "id": 11,
                "user": _user("chatgpt-codex-connector[bot]"),
                "commit_id": "1111111111111111111111111111111111111111",
                "body": "old finding",
            },
        ],
    )

    assert status["status"] == "current_with_findings"
    assert status["codex_inline_findings_count"] == 2
    assert status["codex_inline_findings_on_current_head_count"] == 1


def test_latest_review_on_different_sha_is_stale() -> None:
    module = _module()
    status = _status(
        module,
        reviews=[
            _codex_review(
                review_id=1,
                commit_id="1111111111111111111111111111111111111111",
                submitted_at="2026-06-30T00:00:00Z",
            )
        ],
    )

    assert status["status"] == "stale_review"
    assert status["codex_review_current"] is False


def test_manual_codex_review_request_without_bot_review_is_pending() -> None:
    module = _module()
    status = _status(
        module,
        issue_comments=[
            {
                "id": 20,
                "user": _user("maintainer"),
                "created_at": "2026-06-30T00:01:00Z",
                "body": "@codex review for regressions",
            }
        ],
        reactions_by_comment_id={
            20: [
                {
                    "id": 30,
                    "user": _user("chatgpt-codex-connector[bot]"),
                    "content": "eyes",
                }
            ]
        },
    )

    assert status["status"] == "manual_review_requested_pending"
    assert status["manual_review_request_comment_id"] == 20
    assert status["bot_reacted_to_manual_request"] is True
    assert status["warnings"]


def test_review_body_commit_fallback_is_used_when_commit_id_is_absent() -> None:
    module = _module()
    head = "abcdef1234567890abcdef1234567890abcdef12"
    status = _status(
        module,
        head_sha=head,
        reviews=[
            _codex_review(
                review_id=1,
                commit_id=None,
                submitted_at="2026-06-30T00:00:00Z",
                body="Reviewed commit: abcdef1",
            )
        ],
    )

    assert status["status"] == "current_without_inline_findings"
    assert status["latest_codex_review_sha"] == "abcdef1"
    assert status["latest_codex_review_commit_source"] == "review.body"


def test_latest_codex_review_by_timestamp_wins() -> None:
    module = _module()
    head = "abcdef1234567890abcdef1234567890abcdef12"
    status = _status(
        module,
        head_sha=head,
        reviews=[
            _codex_review(
                review_id=1,
                commit_id="1111111111111111111111111111111111111111",
                submitted_at="2026-06-30T00:00:00Z",
            ),
            _codex_review(
                review_id=2,
                commit_id=head,
                submitted_at="2026-06-30T00:02:00Z",
            ),
        ],
    )

    assert status["latest_codex_review_id"] == 2
    assert status["status"] == "current_without_inline_findings"


def test_non_codex_comments_are_ignored_and_raw_bodies_are_not_emitted() -> None:
    module = _module()
    status = _status(
        module,
        inline_comments=[
            {
                "id": 10,
                "user": _user("reviewer"),
                "commit_id": "abcdef1234567890abcdef1234567890abcdef12",
                "body": "raw inline comment body that should not be emitted",
            }
        ],
        issue_comments=[
            {
                "id": 20,
                "user": _user("reviewer"),
                "created_at": "2026-06-30T00:00:00Z",
                "body": "raw issue comment body that should not be emitted",
            }
        ],
    )
    rendered = module.canonical_json(status)

    assert status["codex_inline_findings_count"] == 0
    assert status["codex_issue_comments_count"] == 0
    assert "raw inline comment body" not in rendered
    assert "raw issue comment body" not in rendered


def test_focused_review_comment_text_is_exact() -> None:
    module = _module()

    assert module.FOCUSED_REVIEW_COMMENT == EXPECTED_FOCUSED_REVIEW_COMMENT
    assert _status(module)["focused_review_comment"] == EXPECTED_FOCUSED_REVIEW_COMMENT


def test_gh_unavailable_status_is_graceful() -> None:
    module = _module()
    status = module.unavailable_status(
        repository="dckallos/dbt-diagnostics",
        pr_number=148,
        error="gh not found",
    )

    assert status["status"] == "gh_unavailable"
    assert status["recommended_next_step"] == "rerun_when_gh_available"
    assert "gh not found" in status["warnings"][0]


def test_agents_review_guidelines_cover_codex_governance_risks() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="ascii")

    assert "## Review guidelines" in text
    for expected in (
        "packet-only and bounded-review input boundary drift",
        ".agents/skills/**",
        ".codex/agents/**",
        ".codex/config.toml",
        "semantic-scan coverage",
        "GitHub comments/reviews/mutation paths",
        "same-context self-review being described as independent review",
        "stale Codex GitHub review evidence",
        "non-UTF-8 filenames",
        "secret redaction around truncation boundaries",
    ):
        assert expected in text


def test_codex_readme_documents_review_status_boundaries() -> None:
    text = (ROOT / ".codex" / "README.md").read_text(encoding="ascii")

    for expected in (
        "codex-review-status",
        "read-only",
        "does not post `@codex review`",
        EXPECTED_FOCUSED_REVIEW_COMMENT,
        "`@codex review` is GitHub PR code review",
        "$codex-security:security-diff-scan",
        "not automated in this PR",
        "`@codex fix` is not the default",
    ):
        assert expected in text

    for unsupported in (
        "@codex deep review",
        "@codex review --deep",
        "@codex review deep",
    ):
        assert unsupported not in text
