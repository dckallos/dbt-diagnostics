#!/usr/bin/env python3
"""Check repository instructions for unsafe GitHub mutation authorization."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Iterable, Iterator, Sequence


DEFAULT_SCAN_PATHS = (
    "AGENTS.md",
    "docs/ISSUE_GOVERNANCE.md",
    ".agents/skills",
    ".codex/README.md",
    ".codex/environments",
)

TEXT_SUFFIXES = {".md", ".toml", ".yaml", ".yml", ".txt"}
IGNORED_PARTS = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}

SAFE_CONTEXT_RE = re.compile(
    r"\b("
    r"do not|don't|never|must not|may not|cannot|can't|"
    r"forbid|forbidden|not supported|unsupported|reject|rejected|"
    r"read-only|no\s+github\s+writes?|no\s+github\s+mutation|"
    r"no\s+tracker\s+mutation|no\s+issue-body\s+write|"
    r"separate(?:ly)?\s+(?:explicitly\s+)?authorized\s+writer|"
    r"maintainer applies|maintainer-applied|applied by hand|manual"
    r")\b",
    re.IGNORECASE,
)

AUTHORIZATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "issue-body-write",
        re.compile(
            r"\b(?:issue[- ]body|issue body|live issue body)\b"
            r".{0,160}\b(?:is updated|may be updated|can be updated|"
            r"allowed|permitted|write|writes|written|edit|edited|mutation)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "allowed-github-metadata-mutation",
        re.compile(
            r"\b(?:only|sole)\b.{0,120}\bGitHub metadata mutation\b"
            r".{0,120}\b(?:allowed|permitted)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "direct-gh-mutation-command",
        re.compile(
            r"\bgh\s+(?:"
            r"issue\s+(?:edit|close)|"
            r"pr\s+merge|"
            r"project"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "apply-execute",
        re.compile(
            r"\btriage\.py\s+" + "apply" + r"\b.{0,120}\b--" + "execute" + r"\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "authorized-tracker-mutation",
        re.compile(
            r"\b(?:may|can|allowed to|permitted to|should)\b.{0,80}"
            r"\b(?:create|edit|close|label|milestone|move|merge|mutate)\b"
            r".{0,100}\b(?:GitHub|issue|Project|pull request|PR|tracker)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    code: str
    message: str
    excerpt: str

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "code": self.code,
            "message": self.message,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True)
class CheckResult:
    checked_files: tuple[str, ...]
    violations: tuple[Violation, ...]

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_json(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checked_files": list(self.checked_files),
            "violations": [violation.to_json() for violation in self.violations],
        }


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _eligible(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    if any(part in IGNORED_PARTS for part in relative.parts):
        return False
    if path.is_dir():
        return True
    return path.is_file() and path.suffix.lower() in TEXT_SUFFIXES


def _expand(paths: Iterable[Path], root: Path) -> list[Path]:
    expanded: set[Path] = set()
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        if not path.exists() or not _eligible(path, root):
            continue
        if path.is_dir():
            candidates = path.rglob("*")
        else:
            candidates = (path,)
        for candidate in candidates:
            if _eligible(candidate, root) and candidate.is_file():
                expanded.add(candidate.resolve())
    return sorted(expanded, key=lambda item: _relative(item, root))


def default_paths(root: Path) -> list[Path]:
    return [root / item for item in DEFAULT_SCAN_PATHS if (root / item).exists()]


def _paragraphs(text: str) -> Iterator[tuple[int, str]]:
    lines = text.splitlines()
    start_line: int | None = None
    buffer: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.strip():
            if start_line is None:
                start_line = index
            buffer.append(line)
            continue
        if buffer and start_line is not None:
            yield start_line, "\n".join(buffer)
        start_line = None
        buffer = []
    if buffer and start_line is not None:
        yield start_line, "\n".join(buffer)


def _safe_context(excerpt: str) -> bool:
    normalized = re.sub(r"\s+", " ", excerpt.strip())
    return bool(SAFE_CONTEXT_RE.search(normalized))


def scan_text(text: str, *, path: str) -> list[Violation]:
    violations: list[Violation] = []
    seen: set[tuple[int, str]] = set()
    for line_number, paragraph in _paragraphs(text):
        normalized = re.sub(r"\s+", " ", paragraph.strip())
        if _safe_context(normalized):
            continue
        for code, pattern in AUTHORIZATION_PATTERNS:
            if not pattern.search(normalized):
                continue
            key = (line_number, code)
            if key in seen:
                continue
            seen.add(key)
            violations.append(
                Violation(
                    path=path,
                    line=line_number,
                    code=code,
                    message=(
                        "possible GitHub mutation authorization in a read-only "
                        "governance surface"
                    ),
                    excerpt=normalized[:240],
                )
            )
    return violations


def run_check(paths: Sequence[Path] | None = None, *, root: Path | None = None) -> CheckResult:
    root = (root or Path.cwd()).resolve()
    requested = list(paths) if paths is not None else default_paths(root)
    files = _expand(requested, root)
    violations: list[Violation] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        violations.extend(scan_text(text, path=_relative(path, root)))
    return CheckResult(
        checked_files=tuple(_relative(path, root) for path in files),
        violations=tuple(violations),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    paths = [Path(item) for item in args.path] if args.path else None
    result = run_check(paths, root=root)

    if args.json:
        print(json.dumps(result.to_json(), indent=2, sort_keys=True, ensure_ascii=True))
    elif result.violations:
        print("ERROR: governance boundary violations found:", file=sys.stderr)
        for violation in result.violations:
            print(
                f"- {violation.path}:{violation.line}: {violation.code}: "
                f"{violation.excerpt}",
                file=sys.stderr,
            )
    else:
        print(
            "OK: governance instructions do not authorize GitHub metadata mutation."
        )

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
