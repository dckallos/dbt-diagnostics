from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest
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
    assert status["focused_review_comment"] == EXPECTED_FOCUSED_REVIEW_COMMENT


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
    assert status["focused_review_comment"] is None
    assert EXPECTED_FOCUSED_REVIEW_COMMENT not in module.render_human(status)


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
    assert status["focused_review_comment"] is None


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
    assert status["focused_review_comment"] == EXPECTED_FOCUSED_REVIEW_COMMENT


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
    assert status["focused_review_comment"] is None
    assert status["warnings"]


def test_manual_codex_review_false_positive_text_is_ignored() -> None:
    module = _module()
    status = _status(
        module,
        issue_comments=[
            {
                "id": 20,
                "user": _user("maintainer"),
                "created_at": "2026-06-30T00:01:00Z",
                "body": "do not post @codex review",
            },
            {
                "id": 21,
                "user": _user("maintainer"),
                "created_at": "2026-06-30T00:02:00Z",
                "body": "```text\n@codex review\n```",
            },
            {
                "id": 22,
                "user": _user("maintainer"),
                "created_at": "2026-06-30T00:03:00Z",
                "body": "> @codex review",
            },
            {
                "id": 23,
                "user": _user("chatgpt-codex-connector[bot]"),
                "created_at": "2026-06-30T00:04:00Z",
                "body": "@codex review",
            },
        ],
    )

    assert status["status"] == "no_codex_review"
    assert status["manual_review_request_comment_id"] is None


def test_usage_limit_response_after_manual_request_fails_closed() -> None:
    module = _module()
    status = _status(
        module,
        issue_comments=[
            {
                "id": 20,
                "user": _user("maintainer"),
                "created_at": "2026-06-30T00:01:00Z",
                "body": "@codex review",
            },
            {
                "id": 21,
                "user": _user("chatgpt-codex-connector[bot]"),
                "created_at": "2026-06-30T00:02:00Z",
                "body": "You have reached your Codex usage limits for code reviews.",
            },
        ],
    )

    assert status["status"] == "manual_review_request_failed"
    assert status["recommended_next_step"] == "maintainer_retry_focused_codex_review_later"
    assert status["codex_review_unavailable_comment_id"] == 21
    assert status["focused_review_comment"] == EXPECTED_FOCUSED_REVIEW_COMMENT
    assert any("usage limits" in warning for warning in status["warnings"])


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


def test_pull_request_review_id_is_not_treated_as_sha() -> None:
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
                "pull_request_review_id": 123456,
                "body": "visible finding without commit evidence",
            }
        ],
    )

    assert status["status"] == "current_without_inline_findings"
    assert status["codex_inline_findings_count"] == 1
    assert status["codex_inline_findings_on_current_head_count"] == 0


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
    assert status["focused_review_comment"] is None
    assert "gh not found" in status["warnings"][0]


def test_unavailable_status_sanitizes_secret_shaped_errors() -> None:
    module = _module()
    status = module.unavailable_status(
        repository="dckallos/dbt-diagnostics",
        pr_number=148,
        error="fatal: token=ghp_abcdefghijklmnopqrstuvwxyz1234567890",
    )
    rendered = module.canonical_json(status)

    assert "ghp_" not in rendered
    assert "token=" not in rendered
    assert "[REDACTED]" in rendered


def test_flatten_paginated_lists_from_gh_slurp() -> None:
    module = _module()
    payload = [[{"id": 1}], [{"id": 2}], []]

    assert module._flatten_paginated_list(payload, "reviews") == [
        {"id": 1},
        {"id": 2},
    ]


def test_load_payloads_uses_paginated_review_and_comment_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    calls: list[list[str]] = []

    def fake_load(args: list[str]) -> object:
        calls.append(args)
        if args[:2] == ["pr", "view"]:
            return {
                "number": 148,
                "url": "https://github.example/pr/148",
                "state": "OPEN",
                "isDraft": False,
                "headRefOid": "abcdef1234567890abcdef1234567890abcdef12",
            }
        if args[:1] == ["api"]:
            return [[]]
        raise AssertionError(args)

    monkeypatch.setattr(module, "_load_json_with_gh", fake_load)

    module._load_payloads(repository="dckallos/dbt-diagnostics", pr_number=148)

    assert [
        "api",
        "repos/dckallos/dbt-diagnostics/pulls/148/reviews",
        "--paginate",
        "--slurp",
    ] in calls
    assert [
        "api",
        "repos/dckallos/dbt-diagnostics/pulls/148/comments",
        "--paginate",
        "--slurp",
    ] in calls
    assert [
        "api",
        "repos/dckallos/dbt-diagnostics/issues/148/comments",
        "--paginate",
        "--slurp",
    ] in calls


def test_invalid_cli_inputs_fail_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    module = _module()

    with pytest.raises(SystemExit) as pr_error:
        module.main(["0", "--json"])
    assert pr_error.value.code == 2
    assert "positive integer" in capsys.readouterr().err

    with pytest.raises(SystemExit) as repo_error:
        module.main(["148", "--repo", "not-a-repo", "--json"])
    assert repo_error.value.code == 2
    assert "owner/name" in capsys.readouterr().err


def test_json_output_stays_clean_for_json_mode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()

    def fake_load_payloads(*, repository: str, pr_number: int) -> object:
        return _payloads(module)

    monkeypatch.setattr(module, "_load_payloads", fake_load_payloads)

    assert module.main(["148", "--json"]) == 0
    output = capsys.readouterr()
    parsed = json.loads(output.out)

    assert output.err == ""
    assert parsed["status"] == "no_codex_review"


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
        "manual `@codex review` request is\npending",
        "usage limits or unavailable review",
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
