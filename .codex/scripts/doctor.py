#!/usr/bin/env python3
"""Read-only readiness checks for local Codex work."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit


DEFAULT_INSTRUCTION_LIMIT = 32 * 1024
ALLOWED_ACTION_ICONS = {"build", "check", "run", "test", "tool"}
ALLOWED_HOOK_EVENTS = {"PermissionRequest", "PreToolUse", "Stop"}
EXPECTED_HOOK_SCRIPTS = {
    "PermissionRequest": "permission_request.py",
    "PreToolUse": "pre_tool_use.py",
    "Stop": "stop.py",
}
IGNORED_PARTS = {".git", ".venv", "__pycache__"}


@dataclass(frozen=True)
class Check:
    level: str
    name: str
    detail: str


def _run(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _latest_progress_heading(path: Path) -> str | None:
    if not path.is_file():
        return None
    headings = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("## 20")
    ]
    return headings[-1] if headings else None


def _redact_remote(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        return value
    parsed = urlsplit(value)
    if "@" not in parsed.netloc:
        return value
    host = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _module_checks(names: Iterable[str]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ModuleNotFoundError):
            spec = None
        if spec is None:
            missing.append(name)
        else:
            present.append(name)
    return present, missing


def _instruction_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("AGENTS.md"):
        if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


def _maximum_instruction_bytes(root: Path, files: list[Path]) -> int:
    by_parent = {path.parent.resolve(): path.stat().st_size for path in files}
    maximum = 0
    for path in files:
        current = path.parent.resolve()
        total = 0
        while True:
            total += by_parent.get(current, 0)
            if current == root.resolve() or current.parent == current:
                break
            current = current.parent
        maximum = max(maximum, total)
    return maximum


def _validate_environment(root: Path) -> tuple[bool, str]:
    try:
        import tomllib

        path = root / ".codex" / "environments" / "environment.toml"
        with path.open("rb") as handle:
            environment = tomllib.load(handle)
    except (OSError, ValueError) as exc:
        return False, f"cannot parse environment.toml: {type(exc).__name__}"

    errors: list[str] = []
    if environment.get("version") != 1:
        errors.append("version must be 1")
    if environment.get("name") != "dbt-diagnostics":
        errors.append("name must be dbt-diagnostics")

    setup_script = environment.get("setup", {}).get("script")
    if not isinstance(setup_script, str) or ".codex/bin/setup.sh" not in setup_script:
        errors.append("setup must call .codex/bin/setup.sh")

    actions = environment.get("actions")
    if not isinstance(actions, list) or not actions:
        errors.append("actions must be a non-empty list")
        actions = []

    names: set[str] = set()
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            errors.append(f"action {index} is not a table")
            continue
        name = action.get("name")
        icon = action.get("icon")
        command = action.get("command")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"action {index} has no name")
        elif name in names:
            errors.append(f"duplicate action name: {name}")
        else:
            names.add(name)
        if icon not in ALLOWED_ACTION_ICONS:
            errors.append(f"action {name or index} has unsupported icon: {icon}")
        if not isinstance(command, str) or not command.strip():
            errors.append(f"action {name or index} has no command")
            continue
        try:
            argv = shlex.split(command)
        except ValueError:
            errors.append(f"action {name or index} has invalid shell quoting")
            continue
        if len(argv) < 2 or argv[0] != "bash":
            errors.append(f"action {name or index} must start with bash")
            continue
        script = root / argv[1]
        if not script.is_file():
            errors.append(f"action {name or index} references missing {argv[1]}")

    if errors:
        return False, "; ".join(errors)
    return True, f"valid version 1 configuration with {len(actions)} actions"


def _validate_hooks(root: Path) -> tuple[bool, str]:
    path = root / ".codex" / "hooks.json"
    if not path.exists():
        return False, "missing .codex/hooks.json"
    try:
        hooks_config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"cannot parse hooks.json: {type(exc).__name__}"

    errors: list[str] = []
    launcher_path = root / ".codex" / "hooks" / "run_hook.sh"
    launcher_text = ""
    if launcher_path.is_file():
        try:
            launcher_text = launcher_path.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"cannot read .codex/hooks/run_hook.sh: {type(exc).__name__}")
    else:
        errors.append("missing .codex/hooks/run_hook.sh")
    if launcher_text:
        if ".venv/bin/python" not in launcher_text:
            errors.append("hook launcher must use the repo .venv")
        if "git rev-parse --show-toplevel" not in launcher_text:
            errors.append("hook launcher must resolve the git root")
        if not os.access(launcher_path, os.X_OK):
            errors.append(".codex/hooks/run_hook.sh must be executable")
        syntax = _run(["bash", "-n", ".codex/hooks/run_hook.sh"], cwd=root)
        if syntax.returncode != 0:
            detail = (syntax.stderr or syntax.stdout).strip() or "unknown error"
            errors.append(f".codex/hooks/run_hook.sh has invalid syntax: {detail}")

    hooks = hooks_config.get("hooks") if isinstance(hooks_config, dict) else None
    if not isinstance(hooks, dict) or not hooks:
        errors.append("hooks must be a non-empty object")
        hooks = {}

    for event, groups in hooks.items():
        if event not in ALLOWED_HOOK_EVENTS:
            errors.append(f"unsupported hook event: {event}")
            continue
        if not isinstance(groups, list) or not groups:
            errors.append(f"{event} must be a non-empty list")
            continue
        for group_index, group in enumerate(groups, start=1):
            if not isinstance(group, dict):
                errors.append(f"{event} group {group_index} is not an object")
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list) or not handlers:
                errors.append(f"{event} group {group_index} has no hooks")
                continue
            for handler_index, handler in enumerate(handlers, start=1):
                if not isinstance(handler, dict):
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} is not an object"
                    )
                    continue
                if handler.get("type") != "command":
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} must be command"
                    )
                command = handler.get("command")
                if not isinstance(command, str) or not command.strip():
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} has no command"
                    )
                    continue
                try:
                    argv = shlex.split(command)
                except ValueError:
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} has invalid shell quoting"
                    )
                    continue
                if len(argv) < 3 or argv[:2] != ["bash", "-lc"]:
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} must run through bash -lc"
                    )
                marker = ".codex/hooks/run_hook.sh"
                if marker not in command:
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} must use the hook launcher"
                    )
                    continue
                expected_script = EXPECTED_HOOK_SCRIPTS[event]
                if expected_script not in command:
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} must launch {expected_script}"
                    )
                    continue
                if event not in command:
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} must pass {event}"
                    )
                    continue
                script_path = root / ".codex" / "hooks" / expected_script
                if not script_path.is_file():
                    errors.append(
                        f"{event} group {group_index} hook {handler_index} references missing {script_path.relative_to(root)}"
                    )

    if errors:
        return False, "; ".join(errors)
    handler_count = sum(
        len(group.get("hooks", []))
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
        if isinstance(group, dict)
    )
    return True, f"valid hooks.json with {len(hooks)} event(s) and {handler_count} handler(s)"


def collect_static_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    required_paths = (
        "AGENTS.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
        "dbt_diagnostics",
        ".codex/README.md",
        ".codex/environments/environment.toml",
        ".codex/bin/action.sh",
        ".codex/bin/setup.sh",
        ".codex/scripts/doctor.py",
        ".codex/scripts/task_context.py",
    )
    missing_paths = [path for path in required_paths if not (root / path).exists()]
    checks.append(
        Check(
            "FAIL" if missing_paths else "PASS",
            "repository layout",
            "missing: " + ", ".join(missing_paths)
            if missing_paths
            else "required project and Codex files are present",
        )
    )

    executable_paths = sorted((root / ".codex" / "bin").glob("*.sh"))
    non_executable = [
        str(path.relative_to(root))
        for path in executable_paths
        if not os.access(path, os.X_OK)
    ]
    checks.append(
        Check(
            "FAIL" if non_executable or not executable_paths else "PASS",
            "Codex script permissions",
            "not executable: " + ", ".join(non_executable)
            if non_executable
            else f"{len(executable_paths)} command scripts are executable",
        )
    )

    valid_environment, environment_detail = _validate_environment(root)
    checks.append(
        Check(
            "PASS" if valid_environment else "FAIL",
            "Codex environment file",
            environment_detail,
        )
    )

    valid_hooks, hooks_detail = _validate_hooks(root)
    checks.append(
        Check(
            "PASS" if valid_hooks else "FAIL",
            "Codex hooks",
            hooks_detail,
        )
    )

    agents_files = _instruction_files(root)
    maximum = _maximum_instruction_bytes(root, agents_files) if agents_files else 0
    checks.append(
        Check(
            "PASS" if agents_files and maximum <= DEFAULT_INSTRUCTION_LIMIT else "WARN",
            "Codex instruction size",
            (
                f"{len(agents_files)} AGENTS.md file(s); maximum applicable chain is "
                f"{maximum} bytes (default limit {DEFAULT_INSTRUCTION_LIMIT})"
            )
            if agents_files
            else "no AGENTS.md files found",
        )
    )

    progress_heading = _latest_progress_heading(root / "docs" / "PROGRESS_LOG.md")
    checks.append(
        Check(
            "PASS" if progress_heading else "WARN",
            "progress log",
            progress_heading or "no dated progress entry found",
        )
    )
    return checks


def collect_runtime_checks(root: Path, *, require_live: bool) -> list[Check]:
    checks: list[Check] = []
    version = sys.version_info
    checks.append(
        Check(
            "PASS" if version >= (3, 11) else "FAIL",
            "Python",
            f"{sys.executable} ({version.major}.{version.minor}.{version.micro})",
        )
    )

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    checks.append(
        Check(
            "PASS" if in_venv else "FAIL",
            "virtual environment",
            sys.prefix if in_venv else "not active; run bash .codex/bin/setup.sh",
        )
    )

    required_modules = (
        "dbt_diagnostics",
        "pytest",
        "hypothesis",
        "sqlglot",
        "yaml",
        "jinja2",
        "build",
        "twine",
        "pre_commit",
    )
    _, missing_modules = _module_checks(required_modules)
    checks.append(
        Check(
            "FAIL" if missing_modules else "PASS",
            "development dependencies",
            "missing: " + ", ".join(missing_modules)
            if missing_modules
            else "all required modules are importable",
        )
    )

    if in_venv:
        pip_check = _run([sys.executable, "-m", "pip", "check"], cwd=root, timeout=30)
        detail = (pip_check.stdout or pip_check.stderr).strip() or "pip check passed"
        checks.append(
            Check(
                "PASS" if pip_check.returncode == 0 else "FAIL",
                "dependency consistency",
                detail.splitlines()[0],
            )
        )

    git = shutil.which("git")
    if git is None:
        checks.append(Check("FAIL", "git", "git is not installed"))
    else:
        inside = _run([git, "rev-parse", "--is-inside-work-tree"], cwd=root)
        if inside.returncode != 0:
            checks.append(Check("FAIL", "git checkout", "not a git worktree"))
        else:
            branch = _run([git, "branch", "--show-current"], cwd=root).stdout.strip()
            if not branch:
                checks.append(Check("WARN", "git branch", "detached HEAD"))
            elif branch in {"main", "donkey-kong-sandbox"}:
                checks.append(
                    Check(
                        "WARN",
                        "git branch",
                        f"{branch} is protected; create an issue branch before edits",
                    )
                )
            else:
                checks.append(Check("PASS", "git branch", branch))

            status = _run([git, "status", "--porcelain"], cwd=root).stdout.splitlines()
            checks.append(
                Check(
                    "WARN" if status else "PASS",
                    "worktree state",
                    f"{len(status)} changed or untracked path(s)" if status else "clean",
                )
            )

            remote = _run([git, "remote", "get-url", "origin"], cwd=root)
            checks.append(
                Check(
                    "PASS" if remote.returncode == 0 else "WARN",
                    "origin remote",
                    _redact_remote(remote.stdout)
                    if remote.returncode == 0
                    else "not configured",
                )
            )

    gh = shutil.which("gh")
    if gh is None:
        checks.append(
            Check(
                "WARN",
                "GitHub CLI",
                "gh is not installed; live issue context and metadata work are unavailable",
            )
        )
    else:
        auth = _run([gh, "auth", "status"], cwd=root)
        checks.append(
            Check(
                "PASS" if auth.returncode == 0 else "WARN",
                "GitHub authentication",
                "authenticated" if auth.returncode == 0 else "run gh auth login",
            )
        )

    triage_path = root / "scripts" / "triage" / "triage.py"
    checks.append(
        Check(
            "PASS" if triage_path.is_file() else "WARN",
            "issue triage tool",
            "available" if triage_path.is_file() else "not created yet",
        )
    )

    schema_cache = root / "dbt_diagnostics" / "fixtures" / "schemas" / "manifest" / "v12.json"
    checks.append(
        Check(
            "PASS" if schema_cache.is_file() else "WARN",
            "compatibility schema cache",
            "present" if schema_cache.is_file() else "absent; current CI skips the schema gate",
        )
    )

    live_modules = ("snowflake.connector", "dotenv", "cryptography")
    _, missing_live = _module_checks(live_modules)
    live_level = "FAIL" if require_live and missing_live else "PASS"
    if missing_live:
        live_detail = (
            "missing: " + ", ".join(missing_live)
            if require_live
            else "not installed (safe offline baseline)"
        )
    else:
        live_detail = "installed; live execution still requires explicit approval and credentials"
    checks.append(Check(live_level, "live extras", live_detail))
    return checks


def collect_checks(
    root: Path,
    *,
    config_only: bool = False,
    require_live: bool = False,
) -> list[Check]:
    checks = collect_static_checks(root)
    if not config_only:
        checks.extend(collect_runtime_checks(root, require_live=require_live))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures",
    )
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="validate repository-local Codex files without runtime, git, or gh checks",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="require the optional Snowflake/live dependency set",
    )
    args = parser.parse_args()

    root = Path(os.environ.get("CODEX_REPO_ROOT", Path.cwd())).resolve()
    checks = collect_checks(
        root,
        config_only=args.config_only,
        require_live=args.require_live,
    )

    failures = sum(check.level == "FAIL" for check in checks)
    warnings = sum(check.level == "WARN" for check in checks)

    if args.json:
        print(
            json.dumps(
                {
                    "repository": str(root),
                    "checks": [asdict(check) for check in checks],
                    "summary": {"failures": failures, "warnings": warnings},
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("dbt-diagnostics Codex doctor")
        print(f"Repository: {root}")
        for check in checks:
            print(f"[{check.level:4}] {check.name}: {check.detail}")
        print(f"Summary: {failures} failure(s), {warnings} warning(s)")

    if failures or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
