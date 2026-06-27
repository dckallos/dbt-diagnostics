from __future__ import annotations

from pathlib import Path

from conftest import load_codex_script
from scripts.triage import repo_config


task_context = load_codex_script("task_context")
ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"


def test_issue_number_inference_is_conservative() -> None:
    assert task_context.infer_issue_number("fix/54-object-unavailable") == 54
    assert task_context.infer_issue_number("54-object-unavailable") == 54
    assert task_context.infer_issue_number("issue-54") == 54
    assert task_context.infer_issue_number("release/v0.6.0") is None
    assert task_context.infer_issue_number("feature/no-number") is None


def test_remote_redaction_preserves_repository_path() -> None:
    value = "https://user:secret@github.com/dckallos/dbt-diagnostics.git"
    assert task_context.redact_remote(value) == "https://github.com/dckallos/dbt-diagnostics.git"


def test_referenced_paths_are_deduplicated_and_checked(tmp_path) -> None:
    existing = tmp_path / "docs" / "DESIGN.md"
    existing.parent.mkdir()
    existing.write_text("x", encoding="ascii")
    body = "Read `docs/DESIGN.md`, docs/DESIGN.md, and scripts/missing.py:12."

    assert task_context.referenced_paths(body, tmp_path) == [
        {"path": "docs/DESIGN.md", "exists": True},
        {"path": "scripts/missing.py", "exists": False},
    ]


def test_referenced_paths_use_configured_roots_for_non_dbt_policy(tmp_path) -> None:
    widgets_policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    script = tmp_path / "scripts" / "widget_check.py"
    script.parent.mkdir()
    script.write_text("x", encoding="ascii")
    body = (
        "Read scripts/widget_check.py and ignore "
        "dbt_diagnostics/fixtures/schemas/manifest/v12.json."
    )

    assert task_context.referenced_paths(
        body, tmp_path, repo_policy=widgets_policy
    ) == [{"path": "scripts/widget_check.py", "exists": True}]
