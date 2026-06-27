"""Shared local Codex surface definitions."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable


PROTECTED_PATTERNS = (
    ".agents/skills/**",
    ".codex/bin/**",
    ".codex/scripts/**",
    ".codex/hooks/**",
    ".codex/hooks.json",
    "scripts/triage/**",
    "docs/*SCHEMA*.md",
    "docs/*schema*.json",
    "docs/ISSUE_GOVERNANCE.md",
    "AGENTS.md",
    ".github/workflows/**",
)


def normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def normalize_requested_path(path: Path, *, root: Path) -> str:
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return normalize_path(path.as_posix())
    return normalize_path(path.as_posix())


def is_protected_path(path: str) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in PROTECTED_PATTERNS)


def protected_paths(paths: Iterable[str]) -> tuple[str, ...]:
    normalized = {normalize_path(path) for path in paths}
    return tuple(
        sorted(path for path in normalized if path and is_protected_path(path))
    )
