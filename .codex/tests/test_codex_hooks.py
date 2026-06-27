from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

from conftest import ROOT, load_codex_script


def load_codex_hook(name: str) -> ModuleType:
    path = ROOT / ".codex" / "hooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"codex_hook_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_hook(name: str, payload: object | str) -> dict[str, object]:
    raw_input = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(ROOT / ".codex" / "hooks" / f"{name}.py")],
        input=raw_input,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def bash_payload(command: str, *, event: str = "PreToolUse") -> dict[str, object]:
    payload: dict[str, object] = {
        "cwd": str(ROOT),
        "hook_event_name": event,
        "model": "gpt-5.5",
        "permission_mode": "default",
        "session_id": "session",
        "tool_input": {"cmd": command},
        "tool_name": "Bash",
        "transcript_path": None,
        "turn_id": "turn",
    }
    if event == "PreToolUse":
        payload["tool_use_id"] = "tool-use"
    return payload


def stop_payload(cwd: Path) -> dict[str, object]:
    return {
        "cwd": str(cwd),
        "hook_event_name": "Stop",
        "last_assistant_message": None,
        "model": "gpt-5.5",
        "permission_mode": "default",
        "session_id": "session",
        "stop_hook_active": False,
        "transcript_path": None,
        "turn_id": "turn",
    }


def test_hooks_config_uses_git_root_commands() -> None:
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))

    assert set(config["hooks"]) == {"PermissionRequest", "PreToolUse", "Stop"}
    commands = [
        handler["command"]
        for groups in config["hooks"].values()
        for group in groups
        for handler in group["hooks"]
    ]
    assert all("$(git rev-parse --show-toplevel)" in command for command in commands)
    assert all(".venv/bin/python" in command for command in commands)
    assert all(".codex/hooks/" in command for command in commands)


def test_pre_tool_use_blocks_direct_github_issue_mutation() -> None:
    output = run_hook(
        "pre_tool_use",
        bash_payload("gh issue edit 106 --repo dckallos/dbt-diagnostics --body-file body.md"),
    )

    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert "GitHub metadata mutation" in hook_output["permissionDecisionReason"]


def test_pre_tool_use_allows_safe_shell_command() -> None:
    output = run_hook(
        "pre_tool_use",
        bash_payload("python -m pytest -q .codex/tests/test_codex_hooks.py"),
    )

    assert output == {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}


def test_pre_tool_use_malformed_stdin_emits_valid_denial_json() -> None:
    output = run_hook("pre_tool_use", "{")

    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert "Invalid hook payload" in hook_output["permissionDecisionReason"]


def test_permission_request_denies_known_unsafe_command() -> None:
    output = run_hook(
        "permission_request",
        bash_payload("rm -rf .codex", event="PermissionRequest"),
    )

    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "unsafe command" in decision["message"]


def test_permission_request_leaves_safe_command_for_normal_approval() -> None:
    output = run_hook(
        "permission_request",
        bash_payload("python -m compileall -q .codex/hooks", event="PermissionRequest"),
    )

    assert output == {"hookSpecificOutput": {"hookEventName": "PermissionRequest"}}


def test_permission_request_malformed_stdin_emits_valid_denial_json() -> None:
    output = run_hook("permission_request", "{")

    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "Invalid hook payload" in decision["message"]


def test_protected_path_matching_keeps_dot_prefixed_paths() -> None:
    hook_policy = load_codex_hook("hook_policy")

    assert hook_policy.is_protected_path(".codex/hooks/stop.py")
    assert hook_policy.is_protected_path("./.codex/scripts/doctor.py")
    assert hook_policy.is_protected_path(".github/workflows/ci.yml")
    assert not hook_policy.is_protected_path("codex/hooks/stop.py")


def test_stop_malformed_stdin_emits_valid_block_json() -> None:
    output = run_hook("stop", "{")

    assert output["decision"] == "block"
    assert "Stop hook failed safely" in output["reason"]


def test_stop_nested_invocation_passes_without_git_status() -> None:
    payload = stop_payload(ROOT)
    payload["stop_hook_active"] = True

    output = run_hook("stop", payload)

    assert output["systemMessage"] == "stop hook already active; skipping nested run."


def test_stop_blocks_protected_change_without_fresh_receipt(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")
    protected = tmp_path / "AGENTS.md"
    protected.write_text("changed\n", encoding="ascii")

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=tmp_path / "output" / "codex" / "quality-receipt.json",
    )

    assert output["decision"] == "block"
    assert "codex-quality" in output["reason"]


def test_stop_allows_protected_change_with_fresh_receipt(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")
    quality = load_codex_script("codex_quality")
    protected = tmp_path / "AGENTS.md"
    protected.write_text("changed\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    quality.run_quality(root=tmp_path, receipt_path=receipt_path, paths=[])

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=receipt_path,
    )

    assert output["systemMessage"] == "codex-quality receipt is fresh for protected changes."


def test_stop_allows_unprotected_change_without_receipt(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("README.md",),
        receipt_path=tmp_path / "output" / "codex" / "quality-receipt.json",
    )

    assert output["systemMessage"] == "no protected Codex surfaces changed."
