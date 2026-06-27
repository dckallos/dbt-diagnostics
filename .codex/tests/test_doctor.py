from __future__ import annotations

import json

from conftest import ROOT, load_codex_script


doctor = load_codex_script("doctor")


def test_redact_remote_strips_embedded_credentials() -> None:
    value = "https://token@example.com/owner/repo.git"
    assert doctor._redact_remote(value) == "https://example.com/owner/repo.git"


def test_static_codex_configuration_has_no_failures() -> None:
    checks = doctor.collect_checks(ROOT, config_only=True)
    assert checks
    assert [check for check in checks if check.level == "FAIL"] == []
    assert [check for check in checks if check.name == "Codex hooks"]


def test_environment_validation_rejects_missing_file(tmp_path) -> None:
    valid, detail = doctor._validate_environment(tmp_path)
    assert valid is False
    assert "cannot parse" in detail


def _write_hook_fixture(root, command: str) -> None:
    hooks_dir = root / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "run_hook.sh").write_text(
        "#!/usr/bin/env bash\n"
        "root=\"$(git rev-parse --show-toplevel)\"\n"
        "exec \"$root/.venv/bin/python\" \"$root/.codex/hooks/$1\"\n",
        encoding="ascii",
    )
    (hooks_dir / "run_hook.sh").chmod(0o755)
    for script in ("pre_tool_use.py", "permission_request.py", "stop.py"):
        (hooks_dir / script).write_text("#!/usr/bin/env python3\n", encoding="ascii")
    (root / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": command,
                                    "timeout": 10,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="ascii",
    )


def test_hooks_validation_rejects_root_relative_launcher_command(tmp_path) -> None:
    _write_hook_fixture(
        tmp_path,
        "bash -lc 'exec .codex/hooks/run_hook.sh pre_tool_use.py PreToolUse'",
    )

    valid, detail = doctor._validate_hooks(tmp_path)

    assert valid is False
    assert "must resolve the git root before launching hooks" in detail
