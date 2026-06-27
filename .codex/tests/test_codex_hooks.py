from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

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


def bash_payload(
    command: str,
    *,
    event: str = "PreToolUse",
    description: str | None = None,
) -> dict[str, object]:
    tool_input: dict[str, object] = {"command": command}
    if description is not None:
        tool_input["description"] = description
    payload: dict[str, object] = {
        "cwd": str(ROOT),
        "hook_event_name": event,
        "model": "gpt-5.5",
        "permission_mode": "default",
        "session_id": "session",
        "tool_input": tool_input,
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
    assert all(".codex/hooks/run_hook.sh" in command for command in commands)
    assert any("pre_tool_use.py" in command for command in commands)
    assert any("permission_request.py" in command for command in commands)
    assert any("stop.py" in command for command in commands)
    launcher = (ROOT / ".codex" / "hooks" / "run_hook.sh").read_text(
        encoding="ascii"
    )
    assert ".venv/bin/python" in launcher
    assert "git rev-parse --show-toplevel" in launcher


def test_pre_tool_use_blocks_direct_github_issue_mutation() -> None:
    output = run_hook(
        "pre_tool_use",
        bash_payload("gh issue edit 106 --repo dckallos/dbt-diagnostics --body-file body.md"),
    )

    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert "GitHub metadata mutation" in hook_output["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "gh api graphql -f query='mutation { closeIssue(input:{issueId:\"I\"}) { clientMutationId } }'",
        "gh pr comment 114 --body review",
        "gh pr review 114 --approve",
        "gh repo edit dckallos/dbt-diagnostics --description unsafe",
        "gh workflow run ci.yml",
        "gh workflow disable ci.yml",
        "gh workflow enable ci.yml",
        "gh secret set TOKEN --body value",
        "gh variable set FEATURE_FLAG --body true",
    ],
)
def test_pre_tool_use_blocks_github_write_commands(command: str) -> None:
    output = run_hook("pre_tool_use", bash_payload(command))

    hook_output = output["hookSpecificOutput"]
    assert hook_output["permissionDecision"] == "deny"
    assert "GitHub metadata mutation" in hook_output["permissionDecisionReason"]


def test_pre_tool_use_allows_safe_shell_command() -> None:
    output = run_hook(
        "pre_tool_use",
        bash_payload("python -m pytest -q .codex/tests/test_codex_hooks.py"),
    )

    assert output == {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 114 --json number,title",
        "gh issue view 106 --json number,state",
        "gh api graphql -f query='query { viewer { login } }'",
    ],
)
def test_pre_tool_use_allows_safe_github_read_commands(command: str) -> None:
    output = run_hook("pre_tool_use", bash_payload(command))

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
        bash_payload(
            "rm -rf .codex",
            event="PermissionRequest",
            description="remove generated files",
        ),
    )

    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "unsafe command" in decision["message"]


def test_permission_request_denies_github_write_command_with_description() -> None:
    output = run_hook(
        "permission_request",
        bash_payload(
            "gh pr review 114 --approve",
            event="PermissionRequest",
            description="approve pull request",
        ),
    )

    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "GitHub metadata mutation" in decision["message"]


def test_permission_request_leaves_safe_command_for_normal_approval() -> None:
    output = run_hook(
        "permission_request",
        bash_payload(
            "python -m compileall -q .codex/hooks",
            event="PermissionRequest",
            description="compile hook files",
        ),
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


def test_stop_blocks_protected_change_not_covered_by_receipt(tmp_path: Path) -> None:
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

    assert output["decision"] == "block"
    assert "not covered" in output["reason"]


def test_stop_allows_protected_change_covered_by_receipt(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")
    quality = load_codex_script("codex_quality")
    protected = tmp_path / "AGENTS.md"
    protected.write_text(
        "Never create, edit, close, label, milestone, or move a GitHub item.\n",
        encoding="ascii",
    )
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    quality.run_quality(
        root=tmp_path,
        receipt_path=receipt_path,
        paths=[Path("AGENTS.md")],
    )

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=receipt_path,
    )

    assert output["systemMessage"] == (
        "codex-quality receipt covers protected changes."
    )


def test_stop_blocks_receipt_with_invalid_digest(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")
    protected = tmp_path / "AGENTS.md"
    protected.write_text("changed\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-27T00:00:00Z",
                "tool": "codex-quality",
                "passed": True,
                "checks": [],
                "covered_protected_paths": ["AGENTS.md"],
                "quality_receipt_digest": "wrong",
            }
        ),
        encoding="ascii",
    )

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=receipt_path,
    )

    assert output["decision"] == "block"
    assert "digest is invalid" in output["reason"]


def test_stop_blocks_receipt_that_did_not_pass(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")
    protected = tmp_path / "AGENTS.md"
    protected.write_text("changed\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    receipt = {
        "schema_version": 1,
        "generated_at": "2026-06-27T00:00:00Z",
        "tool": "codex-quality",
        "passed": False,
        "checks": [],
        "covered_protected_paths": ["AGENTS.md"],
    }
    receipt["quality_receipt_digest"] = hook_policy.receipt_digest(receipt)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="ascii")

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=receipt_path,
    )

    assert output["decision"] == "block"
    assert "did not pass" in output["reason"]


def test_stop_blocks_deleted_protected_file_even_if_receipt_claims_coverage(
    tmp_path: Path,
) -> None:
    hook_policy = load_codex_hook("hook_policy")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    receipt = {
        "schema_version": 1,
        "generated_at": "2026-06-27T00:00:00Z",
        "tool": "codex-quality",
        "passed": True,
        "checks": [],
        "covered_protected_paths": ["AGENTS.md"],
    }
    receipt["quality_receipt_digest"] = hook_policy.receipt_digest(receipt)
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(json.dumps(receipt), encoding="ascii")

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("AGENTS.md",),
        receipt_path=receipt_path,
    )

    assert output["decision"] == "block"
    assert "deleted or unavailable" in output["reason"]


def test_stop_blocks_when_git_status_fails(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")

    output = hook_policy.evaluate_stop(stop_payload(tmp_path), root=tmp_path)

    assert output["decision"] == "block"
    assert "Unable to inspect local git status" in output["reason"]


def test_stop_allows_unprotected_change_without_receipt(tmp_path: Path) -> None:
    hook_policy = load_codex_hook("hook_policy")

    output = hook_policy.evaluate_stop(
        stop_payload(tmp_path),
        root=tmp_path,
        changed_paths=("README.md",),
        receipt_path=tmp_path / "output" / "codex" / "quality-receipt.json",
    )

    assert output["systemMessage"] == "no protected Codex surfaces changed."


def test_hook_launcher_git_root_failure_emits_valid_denial_json(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "bash",
            str(ROOT / ".codex" / "hooks" / "run_hook.sh"),
            "pre_tool_use.py",
            "PreToolUse",
        ],
        cwd=tmp_path,
        input=json.dumps(bash_payload("python -V")),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    output = json.loads(result.stdout)
    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert "cannot resolve git root" in hook_output["permissionDecisionReason"]


def test_hook_launcher_missing_venv_emits_valid_block_json(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    result = subprocess.run(
        [
            "bash",
            str(ROOT / ".codex" / "hooks" / "run_hook.sh"),
            "stop.py",
            "Stop",
        ],
        cwd=tmp_path,
        input=json.dumps(stop_payload(tmp_path)),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    output = json.loads(result.stdout)
    assert output["decision"] == "block"
    assert "missing repository .venv/bin/python" in output["reason"]


def test_hook_launcher_missing_script_emits_valid_denial_json(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    python_path = tmp_path / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/usr/bin/env sh\nexit 1\n", encoding="ascii")
    python_path.chmod(0o755)

    result = subprocess.run(
        [
            "bash",
            str(ROOT / ".codex" / "hooks" / "run_hook.sh"),
            "permission_request.py",
            "PermissionRequest",
        ],
        cwd=tmp_path,
        input=json.dumps(
            bash_payload(
                "python -V",
                event="PermissionRequest",
                description="check python",
            )
        ),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    output = json.loads(result.stdout)
    decision = output["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert "missing hook script" in decision["message"]
