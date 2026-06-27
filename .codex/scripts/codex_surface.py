"""Shared local Codex surface definitions."""

from __future__ import annotations

import fnmatch
from pathlib import Path
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.triage import repo_config


FALLBACK_PROTECTED_PATTERNS = (
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


def protected_patterns(
    repo_policy: repo_config.RepoPolicy | None = None,
) -> tuple[str, ...]:
    if repo_policy is not None:
        return repo_policy.paths.protected_surfaces
    try:
        return repo_config.load_repo_policy().paths.protected_surfaces
    except repo_config.RepoConfigError:
        return FALLBACK_PROTECTED_PATTERNS


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


def is_protected_path(
    path: str, *, repo_policy: repo_config.RepoPolicy | None = None
) -> bool:
    normalized = normalize_path(path)
    return any(
        fnmatch.fnmatchcase(normalized, pattern)
        for pattern in protected_patterns(repo_policy)
    )


def protected_paths(
    paths: Iterable[str], *, repo_policy: repo_config.RepoPolicy | None = None
) -> tuple[str, ...]:
    normalized = {normalize_path(path) for path in paths}
    return tuple(
        sorted(
            path
            for path in normalized
            if path and is_protected_path(path, repo_policy=repo_policy)
        )
    )
