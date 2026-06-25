from __future__ import annotations

import os
from pathlib import Path
import shlex
import tomllib


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
