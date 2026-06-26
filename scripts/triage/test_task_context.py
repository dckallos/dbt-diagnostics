"""Focused tests for the .codex task-context snapshot fallback (issue #74 D3).

The wrapper script lives outside the package, so it is loaded by file path.
These tests cover only the offline snapshot reader added so that `context <n>`
no longer hard-fails on an unauthenticated `gh` for a public read-only issue.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / ".codex" / "scripts" / "task_context.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("codex_task_context", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


task_context = _load_module()


def _write_snapshot(tmp_path: Path, issues: list[dict]) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"issues": issues}), encoding="utf-8")
    return path


def test_snapshot_returns_matching_issue(tmp_path: Path) -> None:
    snapshot = _write_snapshot(
        tmp_path,
        [{"number": 73, "title": "other"}, {"number": 74, "title": "fixture"}],
    )
    issue = task_context.issue_from_snapshot_file(snapshot, 74)
    assert issue["number"] == 74
    assert issue["title"] == "fixture"


def test_snapshot_missing_issue_raises(tmp_path: Path) -> None:
    snapshot = _write_snapshot(tmp_path, [{"number": 73}])
    with pytest.raises(task_context.ContextError):
        task_context.issue_from_snapshot_file(snapshot, 74)


def test_snapshot_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(task_context.ContextError):
        task_context.issue_from_snapshot_file(tmp_path / "nope.json", 74)


def test_snapshot_without_issues_list_raises(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"not_issues": []}), encoding="utf-8")
    with pytest.raises(task_context.ContextError):
        task_context.issue_from_snapshot_file(path, 74)


def test_resolve_snapshot_prefers_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "given.json"
    assert task_context.resolve_snapshot_path(explicit, tmp_path) == explicit


def test_resolve_snapshot_auto_discovers_default_when_present(tmp_path: Path) -> None:
    default = task_context.default_snapshot_path(tmp_path)
    default.parent.mkdir(parents=True)
    default.write_text("{}", encoding="utf-8")
    assert task_context.resolve_snapshot_path(None, tmp_path) == default


def test_resolve_snapshot_returns_none_when_no_default(tmp_path: Path) -> None:
    assert task_context.resolve_snapshot_path(None, tmp_path) is None

