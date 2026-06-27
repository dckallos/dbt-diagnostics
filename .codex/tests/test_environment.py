from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib
from typing import Any

from scripts.triage import triage


ROOT = Path(__file__).resolve().parents[2]


def test_environment_actions_are_unique_and_resolvable() -> None:
    path = ROOT / ".codex" / "environments" / "environment.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    assert data["version"] == 1
    assert data["name"] == "dbt-diagnostics"
    assert ".codex/bin/setup.sh" in data["setup"]["script"]

    actions = data["actions"]
    names = [action["name"] for action in actions]
    assert len(names) == len(set(names))
    assert {
        "Context",
        "Doctor",
        "Check",
        "Tests (offline)",
        "Full pytest",
        "Compile",
        "Issue audit",
        "Package",
    } == set(names)

    for action in actions:
        argv = shlex.split(action["command"])
        assert argv[0] == "bash"
        script = ROOT / argv[1]
        assert script.is_file()
        assert os.access(script, os.X_OK)


def test_frontier_wrapper_is_exposed_and_dispatches() -> None:
    action = (ROOT / ".codex" / "bin" / "action.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / ".codex" / "bin" / "triage-frontier.sh").read_text(
        encoding="utf-8"
    )

    assert "frontier MODE" in action
    assert "\n  frontier)" in action
    assert 'exec "$python_path" "$tool" frontier --mode "$mode" "$@"' in wrapper


def test_common_policy_loader_uses_data_records_without_eval() -> None:
    common = (ROOT / ".codex" / "bin" / "common.sh").read_text(encoding="utf-8")

    assert "export-shell" not in common
    assert " export-env" in common
    assert "eval" not in common
    assert "codex_set_policy_value" in common


def _issue(number: int) -> dict[str, Any]:
    return {
        "number": number,
        "title": "feat: expose project plan",
        "state": "open",
        "body": "## Summary\n\nExpose project planning through the wrapper.",
        "labels": ["enhancement"],
        "milestone": None,
        "assignees": [],
        "author": "maintainer",
        "url": f"https://example.test/issues/{number}",
        "html_url": f"https://example.test/issues/{number}",
        "created_at": "2026-06-24T00:00:00Z",
        "updated_at": "2026-06-24T00:00:00Z",
        "closed_at": None,
    }


def _snapshot() -> dict[str, Any]:
    policy = triage.load_policy(triage.DEFAULT_POLICY)
    labels = sorted({label for values in policy["labels"].values() for label in values})
    value: dict[str, Any] = {
        "schema_version": triage.SNAPSHOT_SCHEMA_VERSION,
        "generated_at": "2026-06-24T00:00:00Z",
        "repository": {
            "full_name": "dckallos/dbt-diagnostics",
            "owner": "dckallos",
            "name": "dbt-diagnostics",
            "default_branch": "donkey-kong-sandbox",
            "visibility": "public",
            "archived": False,
            "disabled": False,
            "has_issues": True,
            "html_url": "https://example.test/repo",
            "updated_at": "2026-06-24T00:00:00Z",
            "pushed_at": "2026-06-24T00:00:00Z",
        },
        "policy_sha256": triage.sha256_json(policy),
        "issues": [_issue(91)],
        "pull_requests": [],
        "open_pull_requests": [],
        "labels": [
            {"name": name, "description": "", "color": "ededed", "default": False}
            for name in labels
        ],
        "label_usage": [],
        "milestones": [],
        "milestone_usage": [],
        "referenced_closed_items": [],
        "recently_closed_items": [],
        "project": {"configured": False, "status": "not_configured"},
    }
    value["snapshot_sha256"] = triage.sha256_json(triage.snapshot_without_digest(value))
    return value


def _write_project_plan_inputs(tmp_path: Path) -> tuple[Path, Path]:
    policy = triage.load_policy(triage.DEFAULT_POLICY)
    snapshot = _snapshot()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="ascii"
    )
    audit = triage.make_readiness_audit(snapshot, policy)
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="ascii")
    return snapshot_path, audit_path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def test_project_plan_wrapper_is_exposed_and_dispatches(
    tmp_path: Path,
) -> None:
    action = (ROOT / ".codex" / "bin" / "action.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / ".codex" / "bin" / "triage-project-plan.sh").read_text(
        encoding="utf-8"
    )
    snapshot_path, audit_path = _write_project_plan_inputs(tmp_path)

    assert "project-plan   Emit the read-only advisory Project plan" in action
    assert "\n  project-plan)" in action
    assert 'exec "$python_path" "$tool" project-plan "$@"' in wrapper

    direct = _run(
        sys.executable,
        "scripts/triage/triage.py",
        "project-plan",
        "--snapshot",
        str(snapshot_path),
        "--audit-file",
        str(audit_path),
        "--json",
    )
    wrapped = _run(
        "bash",
        ".codex/bin/action.sh",
        "project-plan",
        "--snapshot",
        str(snapshot_path),
        "--audit-file",
        str(audit_path),
        "--json",
    )

    assert direct.returncode == 0, direct.stderr
    assert wrapped.returncode == 0, wrapped.stderr
    direct_json = json.loads(direct.stdout)
    wrapped_json = json.loads(wrapped.stdout)
    assert wrapped_json == direct_json
    assert wrapped_json["safety"]["github_api_calls"] is False
    assert wrapped_json["safety"]["github_mutations"] is False
    assert "operations" not in wrapped_json


def test_project_plan_wrapper_requires_snapshot_and_audit() -> None:
    result = _run("bash", ".codex/bin/action.sh", "project-plan")

    assert result.returncode != 0
    assert "the following arguments are required" in result.stderr
    assert "--snapshot" in result.stderr
    assert "--audit-file" in result.stderr
