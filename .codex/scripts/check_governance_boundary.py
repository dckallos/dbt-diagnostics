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

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.triage import repo_config

LEGACY_DEFAULT_SCAN_PATHS = (
    "AGENTS.md",
    "docs/ISSUE_GOVERNANCE.md",
    "docs/ISSUE_CONTRACT_V1.md",
    ".agents/skills",
    ".codex/README.md",
    ".codex/environments",
)

TEXT_SUFFIXES = {".md", ".toml", ".yaml", ".yml", ".txt"}
TEXT_FILE_NAMES = {
    ".gitignore",
    "CODEOWNERS",
    "Dockerfile",
    "Gemfile",
    "LICENSE",
    "Makefile",
    "NOTICE",
    "Procfile",
    "Rakefile",
    "SECURITY",
}
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
    r"do not|does not|will not|don't|never|must not|may not|cannot|can't|"
    r"forbid|forbidden|not supported|unsupported|reject|rejected|rejects|"
    r"without\s+mutating|without\s+mutation|"
    r"no\s+github\s+writes?|no\s+github\s+mutation|"
    r"no\s+tracker\s+mutation|no\s+issue-body\s+write|"
    r"maintainer applies|maintainer-applied|applied by hand"
    r")\b",
    re.IGNORECASE,
)

FORBIDDEN_OPERATION_IDS = (
    "issue.create",
    "issue.close",
    "issue.reopen",
    "issue.body.update",
    "issue.title.update",
    "label.create",
    "label.delete",
    "label.rename",
    "milestone.create",
    "milestone.close",
    "project.create",
)

FORBIDDEN_OPERATION_IDS_RE = (
    r"(?<![A-Za-z0-9_.-])(?:"
    + "|".join(re.escape(operation_id) for operation_id in FORBIDDEN_OPERATION_IDS)
    + r")(?![A-Za-z0-9_.-])"
)

MUTATION_VERB_RE = (
    r"(?:create|edit|update|write|close|reopen|label|move|merge|mutate)"
)
SENTENCE_GAP_RE = r"[^.!?]{0,80}"
IMPERATIVE_START_RE = r"(?:^|[.!?]\s+|[-*]\s+|\d+\.\s+)"
TRACKER_OBJECT_RE = (
    r"(?:"
    r"GitHub\s+(?:issue|issues|item|items|Project|Projects|"
    r"pull request|pull requests|PR|PRs|metadata)|"
    r"issue[- ]body|live\s+issue\s+body|issue\s+(?:body|title|state)|"
    r"Project\s+(?:item|items|field|fields)|"
    r"tracker\s+(?:item|items|metadata|text)|"
    r"(?:the|a|this|that|current|live)\s+issue\b|"
    r"(?:the|a|this|that|current|live)\s+Project\s+item\b"
    r")"
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
            r"(?<!-)\b(?:only|sole)\b.{0,120}\bGitHub metadata mutation\b"
            r".{0,120}\b(?:allowed|permitted)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "authorized-tracker-mutation",
        re.compile(
            rf"\b(?:may|can|allowed to|permitted to|should)\b{SENTENCE_GAP_RE}"
            rf"\b{MUTATION_VERB_RE}\b{SENTENCE_GAP_RE}\b{TRACKER_OBJECT_RE}\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "verb-first-tracker-mutation",
        re.compile(
            rf"{IMPERATIVE_START_RE}\b{MUTATION_VERB_RE}\b"
            rf"{SENTENCE_GAP_RE}\b{TRACKER_OBJECT_RE}\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "forbidden-operation-id",
        re.compile(FORBIDDEN_OPERATION_IDS_RE, re.IGNORECASE),
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
    return path.is_file() and (
        path.suffix.lower() in TEXT_SUFFIXES
        or path.name in TEXT_FILE_NAMES
        or (not path.suffix and path.name[:1].isupper())
    )


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


def default_paths(
    root: Path, *, repo_policy: repo_config.RepoPolicy | None = None
) -> list[Path]:
    policy = repo_policy
    if policy is None:
        try:
            policy = repo_config.load_repo_policy()
        except repo_config.RepoConfigError:
            if repo_config.DEFAULT_POLICY_PATH.exists():
                raise
            return [
                root / item
                for item in LEGACY_DEFAULT_SCAN_PATHS
                if (root / item).exists()
            ]
    return [
        root / item
        for item in policy.paths.semantic_scan_roots
        if (root / item).exists()
    ]


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


def _sentence_for_span(text: str, start: int, end: int) -> str:
    sentence_start = max(
        text.rfind(".", 0, start),
        text.rfind("!", 0, start),
        text.rfind("?", 0, start),
        text.rfind("\n", 0, start),
    )
    if sentence_start == -1:
        sentence_start = 0
    else:
        sentence_start += 1
    sentence_end_candidates = [
        index for index in (
            text.find(".", end),
            text.find("!", end),
            text.find("?", end),
            text.find("\n", end),
        )
        if index != -1
    ]
    sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(text)
    return text[sentence_start:sentence_end].strip()


def _safe_context(text: str, start: int, end: int) -> bool:
    sentence = _sentence_for_span(text, start, end)
    return bool(SAFE_CONTEXT_RE.search(sentence))


def _safe_preceding_context(code: str, paragraph: str, previous_paragraph: str) -> bool:
    if code != "forbidden-operation-id":
        return False
    if not paragraph.startswith("```") or not paragraph.endswith("```"):
        return False
    return bool(SAFE_CONTEXT_RE.search(previous_paragraph))


def scan_text(text: str, *, path: str) -> list[Violation]:
    violations: list[Violation] = []
    seen: set[tuple[int, str, int]] = set()
    previous_normalized = ""
    for line_number, paragraph in _paragraphs(text):
        normalized = re.sub(r"\s+", " ", paragraph.strip())
        for code, pattern in AUTHORIZATION_PATTERNS:
            for match in pattern.finditer(normalized):
                if _safe_context(
                    normalized, match.start(), match.end()
                ) or _safe_preceding_context(code, normalized, previous_normalized):
                    continue
                key = (line_number, code, match.start())
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
        previous_normalized = normalized
    return violations


def run_check(
    paths: Sequence[Path] | None = None,
    *,
    root: Path | None = None,
    repo_policy: repo_config.RepoPolicy | None = None,
) -> CheckResult:
    root = (root or Path.cwd()).resolve()
    requested = (
        list(paths)
        if paths is not None
        else default_paths(root, repo_policy=repo_policy)
    )
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
    try:
        result = run_check(paths, root=root)
    except repo_config.RepoConfigError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "checked_files": [],
                        "violations": [],
                        "error": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=True,
                )
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

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
