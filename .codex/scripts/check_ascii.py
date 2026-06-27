#!/usr/bin/env python3
"""Reject non-ASCII bytes in repository-authored files changed by this work."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.triage import repo_config


TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".j2",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "htmlcov",
}


def _git(root: Path, *args: str) -> list[str]:
    process = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        return []
    return [line for line in process.stdout.splitlines() if line]


def _is_git_checkout(root: Path) -> bool:
    process = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return process.returncode == 0


def _changed_paths(root: Path) -> list[Path]:
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        names.update(_git(root, *args))

    try:
        default_branch = repo_config.load_repo_policy().repository.default_branch
    except repo_config.RepoConfigError:
        default_branch = "HEAD"
    for base in (f"origin/{default_branch}", default_branch):
        if _git(root, "rev-parse", "--verify", "--quiet", base):
            names.update(
                _git(
                    root,
                    "diff",
                    "--name-only",
                    "--diff-filter=ACMR",
                    f"{base}...HEAD",
                )
            )
            break

    return sorted((root / name for name in names), key=lambda path: str(path))


def _eligible(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(part in IGNORED_PARTS for part in relative.parts):
        return False
    return path.is_file() and path.suffix.lower() in TEXT_SUFFIXES


def _expand(paths: Iterable[Path], root: Path) -> list[Path]:
    expanded: set[Path] = set()
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        if path.is_dir():
            candidates = path.rglob("*")
        else:
            candidates = (path,)
        for candidate in candidates:
            candidate = candidate.resolve()
            if _eligible(candidate, root):
                expanded.add(candidate)
    return sorted(expanded, key=lambda item: str(item.relative_to(root)))


def _first_non_ascii(data: bytes) -> tuple[int, int, int] | None:
    for offset, value in enumerate(data):
        if value > 127:
            line = data.count(b"\n", 0, offset) + 1
            line_start = data.rfind(b"\n", 0, offset) + 1
            column = offset - line_start + 1
            return line, column, value
    return None


def find_violations(paths: Iterable[Path], root: Path) -> list[str]:
    violations: list[str] = []
    for path in _expand(paths, root):
        data = path.read_bytes()
        if b"\0" in data:
            continue
        location = _first_non_ascii(data)
        if location is None:
            continue
        line, column, value = location
        relative = path.relative_to(root)
        violations.append(
            f"{relative}:{line}:{column}: non-ASCII byte 0x{value:02x}"
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="file or directory to scan; may be repeated",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="scan every eligible repository file rather than changed paths",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path.cwd().resolve()
    if args.path:
        requested = [Path(value) for value in args.path]
    elif args.all:
        requested = [root]
    elif _is_git_checkout(root):
        requested = _changed_paths(root)
    else:
        requested = [root / ".codex", root / "AGENTS.md"]

    violations = find_violations(requested, root)
    if violations:
        print("ERROR: non-ASCII content found:", file=sys.stderr)
        for violation in violations[:50]:
            print(f"- {violation}", file=sys.stderr)
        if len(violations) > 50:
            print(f"- ... and {len(violations) - 50} more", file=sys.stderr)
        return 1

    if not args.quiet:
        print("OK: checked repository-authored text for ASCII-only content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
