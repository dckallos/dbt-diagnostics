#!/usr/bin/env python3
"""Check repository instructions for unsafe GitHub mutation authorization."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Iterable, Iterator, Mapping, Sequence

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
TOML_COMMAND_KEYS = frozenset({"command", "commands"})
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
    r"requires\s+explicit\s+maintainer\s+approval|"
    r"not\s+available\s+from\s+read-only|"
    r"without\s+mutating|without\s+mutation|"
    r"no\s+github\s+writes?|no\s+github\s+mutation|"
    r"no\s+tracker\s+mutation|no\s+issue-body\s+write|"
    r"maintainer applies|maintainer-applied|applied by hand"
    r")\b",
    re.IGNORECASE,
)

SAFE_WRITER_CONTEXT_RE = re.compile(
    r"\b("
    r"real\s+writer\s+session|real\s+execution\s+gate|"
    r"approval[- ]gated|explicit\s+write\s+path|"
    r"writer\s+path|write\s+path|TRIAGE_ENABLE_GITHUB_WRITES|"
    r"confirm-repo|maintainer-gated|maintainer\s+approval"
    r")\b",
    re.IGNORECASE,
)
CONTRAST_RE = re.compile(r"\b(?:but|however|except|then)\b", re.IGNORECASE)

FORBIDDEN_OPERATION_IDS = tuple(sorted(repo_config.FORBIDDEN_OPERATION_IDS))

COMMAND_INTRO_RE = re.compile(
    r"\b(?:run|use|execute|command|allowed command|recommended command)\s*:?\s+"
    r"((?:gh|python|python3|\.venv/bin/python|bash|sh|zsh|command|env|pytest|rg)\b.+)",
    re.IGNORECASE,
)
COMMAND_WITH_RE = re.compile(
    r"\bwith\s+((?:gh|python|python3|\.venv/bin/python)\b.+)",
    re.IGNORECASE,
)
SHELL_PROMPT_RE = re.compile(r"^\s*(?:[$>])\s+(.+)$")
BARE_COMMAND_RE = re.compile(
    r"^\s*(?:gh|python|python3|\.venv/bin/python|bash|sh|zsh|command|env|pytest)\b.+",
    re.IGNORECASE,
)

FORBIDDEN_OPERATION_IDS_RE = (
    r"(?<![A-Za-z0-9_.-])(?:"
    + "|".join(re.escape(operation_id) for operation_id in FORBIDDEN_OPERATION_IDS)
    + r")(?![A-Za-z0-9_.-])"
)

MUTATION_VERB_RE = (
    r"(?:create|edit|update|write|close|reopen|label|move|merge|mutate|set|assign)"
)
SENTENCE_GAP_RE = r"(?:(?!\b(?:but|however|except|then)\b)[^.!?]){0,80}"
IMPERATIVE_START_RE = r"(?:^|[.!?]\s+|[-*]\s+|\d+\.\s+|\b(?:but|however|then)\s+)"
TRACKER_OBJECT_RE = (
    r"(?:"
    r"GitHub\s+(?:issue|issues|item|items|Project|Projects|"
    r"pull request|pull requests|PR|PRs|metadata)|"
    r"issue[- ]body|live\s+issue\s+body|issue\s+(?:body|title|state)|"
    r"issue\s+milestone|release\s+milestone|labels?|milestones?|"
    r"repository\s+(?:secret|variable)|secrets?|variables?|"
    r"workflow\s+(?:dispatch(?:es)?|run|runs|toggle|toggles|metadata)|"
    r"Project\s+(?:item|items|field|fields)|"
    r"PR\s+merge|pull\s+request\s+merge|"
    r"tracker\s+(?:item|items|metadata|text)|"
    r"(?:the|a|this|that|current|live)\s+issue\b|"
    r"(?:the|a|this|that|current|live)\s+Project\s+item\b|"
    r"(?:the|a|this|that|current|live)\s+(?:label|milestone|"
    r"workflow|secret|variable|PR|pull request)\b"
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
            rf"\b(?:may|can|allowed to|permitted to|should|must|"
            rf"required to|is required to|are required to)\b{SENTENCE_GAP_RE}"
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


def is_eligible_scan_path(path: Path, root: Path) -> bool:
    """Return whether the governance scanner can inspect this path."""
    return _eligible(path, root)


def _path_violation(
    raw_path: Path, root: Path, *, code: str, message: str
) -> Violation:
    path = raw_path if raw_path.is_absolute() else root / raw_path
    return Violation(
        path=_relative(path, root),
        line=0,
        code=code,
        message=message,
        excerpt=raw_path.as_posix(),
    )


def _expand(
    paths: Iterable[Path], root: Path, *, explicit: bool = False
) -> tuple[list[Path], list[Violation]]:
    expanded: set[Path] = set()
    violations: list[Violation] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            if explicit:
                violations.append(
                    _path_violation(
                        raw_path,
                        root,
                        code="explicit-path-outside-root",
                        message="explicit path must stay inside the repository root",
                    )
                )
            continue
        if not path.exists():
            if explicit:
                violations.append(
                    _path_violation(
                        raw_path,
                        root,
                        code="explicit-path-missing",
                        message="explicit path does not exist",
                    )
                )
            continue
        if not _eligible(path, root):
            if explicit:
                violations.append(
                    _path_violation(
                        raw_path,
                        root,
                        code="explicit-path-ineligible",
                        message="explicit path is not an eligible text file or directory",
                    )
                )
            continue
        found_eligible_file = False
        if path.is_dir():
            candidates = path.rglob("*")
        else:
            candidates = (path,)
        for candidate in candidates:
            if _eligible(candidate, root) and candidate.is_file():
                found_eligible_file = True
                expanded.add(candidate.resolve())
        if explicit and not found_eligible_file:
            violations.append(
                _path_violation(
                    raw_path,
                    root,
                    code="explicit-path-empty",
                    message="explicit path did not contain eligible text files",
                )
            )
    return sorted(expanded, key=lambda item: _relative(item, root)), violations


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


def _sentence_bounds_for_span(text: str, start: int, end: int) -> tuple[int, int]:
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
    return sentence_start, sentence_end


def _sentence_for_span(text: str, start: int, end: int) -> str:
    sentence_start, sentence_end = _sentence_bounds_for_span(text, start, end)
    return text[sentence_start:sentence_end].strip()


def _safe_context(text: str, start: int, end: int) -> bool:
    sentence_start, sentence_end = _sentence_bounds_for_span(text, start, end)
    sentence = text[sentence_start:sentence_end]
    local_start = max(start - sentence_start, 0)
    local_end = max(end - sentence_start, local_start)
    for match in SAFE_CONTEXT_RE.finditer(sentence):
        if match.end() <= local_start and CONTRAST_RE.search(
            sentence[match.end() : local_start]
        ):
            continue
        if match.end() <= local_end and CONTRAST_RE.search(
            sentence[match.end() : local_end]
        ):
            continue
        if match.start() >= local_end and CONTRAST_RE.search(
            sentence[local_end : match.start()]
        ):
            continue
        return True
    return False


def _safe_preceding_context(code: str, paragraph: str, previous_paragraph: str) -> bool:
    if code != "forbidden-operation-id":
        return False
    if not paragraph.startswith("```") or not paragraph.endswith("```"):
        return False
    return bool(SAFE_CONTEXT_RE.search(previous_paragraph))


def _normalize_command(command: str) -> str:
    stripped = command.strip().strip("`")
    if stripped.endswith("\\"):
        stripped = stripped[:-1].rstrip()
    return stripped


def _command_candidates(
    paragraph: str, *, line_number: int
) -> Iterator[tuple[int, str, int, int]]:
    offset = 0
    for line_offset, raw_line in enumerate(paragraph.splitlines()):
        stripped = raw_line.strip()
        command = ""
        command_start = -1
        if stripped and not stripped.startswith("```"):
            prompt_match = SHELL_PROMPT_RE.match(raw_line)
            if prompt_match is not None:
                command = prompt_match.group(1)
                command_start = offset + prompt_match.start(1)
            else:
                intro_match = COMMAND_INTRO_RE.search(raw_line)
                with_match = COMMAND_WITH_RE.search(raw_line)
                if intro_match is not None:
                    command = intro_match.group(1)
                    command_start = offset + intro_match.start(1)
                elif with_match is not None:
                    command = with_match.group(1)
                    command_start = offset + with_match.start(1)
                elif BARE_COMMAND_RE.match(raw_line):
                    command = raw_line
                    command_start = offset + raw_line.index(stripped)
        normalized_command = _normalize_command(command)
        if normalized_command:
            yield (
                line_number + line_offset,
                normalized_command,
                command_start,
                command_start + len(command),
            )
        offset += len(raw_line) + 1


def _safe_command_context(
    paragraph: str,
    previous_paragraph: str,
    *,
    start: int,
    end: int,
) -> bool:
    if _safe_context(paragraph, start, end):
        return True
    context = f"{previous_paragraph}\n{paragraph}"
    return bool(SAFE_CONTEXT_RE.search(previous_paragraph)) or bool(
        SAFE_WRITER_CONTEXT_RE.search(context)
    )


def _normalized_toml_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def _toml_command_values(
    value: object, *, key_path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            path = (*key_path, key)
            normalized = _normalized_toml_key(key)
            if normalized in TOML_COMMAND_KEYS:
                if isinstance(item, str):
                    yield path, item
                elif isinstance(item, list):
                    for child in item:
                        if isinstance(child, str):
                            yield path, child
                        else:
                            yield from _toml_command_values(child, key_path=path)
                elif isinstance(item, Mapping):
                    yield from _toml_command_values(item, key_path=path)
                continue
            yield from _toml_command_values(item, key_path=path)
        return
    if isinstance(value, list):
        for item in value:
            yield from _toml_command_values(item, key_path=key_path)


def _toml_key_line(
    text: str, key_path: tuple[str, ...], *, command: str | None = None
) -> int:
    if not key_path:
        return 1
    leaf_key = re.escape(key_path[-1])
    pattern = re.compile(rf"^\s*{leaf_key}\s*=", re.IGNORECASE)
    inline_pattern = re.compile(rf"\b{leaf_key}\s*=", re.IGNORECASE)
    if command is not None:
        for line_number, line in enumerate(text.splitlines(), start=1):
            if command in line and inline_pattern.search(line):
                return line_number
    for line_number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line) and (command is None or command in line):
            return line_number
    for line_number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            return line_number
    return 1


def _scan_toml_commands(text: str, *, path: str) -> list[Violation]:
    if not path.casefold().endswith(".toml"):
        return []
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    violations: list[Violation] = []
    for key_path, command in _toml_command_values(parsed):
        reason = repo_config.governance_mutation_command_reason(command)
        if reason is None:
            continue
        key = ".".join(key_path)
        violations.append(
            Violation(
                path=path,
                line=_toml_key_line(text, key_path, command=command),
                code="forbidden-mutation-command",
                message=(
                    "possible executable mutation command in structured TOML "
                    "governance surface"
                ),
                excerpt=f"{key} = {command}"[:240],
            )
        )
    return violations


def scan_text(text: str, *, path: str) -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(_scan_toml_commands(text, path=path))
    seen: set[tuple[int, str, int]] = set()
    previous_normalized = ""
    previous_paragraph = ""
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
        for command_line, command, start, end in _command_candidates(
            paragraph, line_number=line_number
        ):
            reason = repo_config.governance_mutation_command_reason(command)
            if reason is None:
                continue
            if _safe_command_context(
                paragraph,
                previous_paragraph,
                start=start,
                end=end,
            ):
                continue
            key = (command_line, "forbidden-mutation-command", start)
            if key in seen:
                continue
            seen.add(key)
            violations.append(
                Violation(
                    path=path,
                    line=command_line,
                    code="forbidden-mutation-command",
                    message=(
                        "possible executable mutation command in a read-only "
                        "governance surface"
                    ),
                    excerpt=command[:240],
                )
            )
        previous_normalized = normalized
        previous_paragraph = paragraph
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
    files, violations = _expand(requested, root, explicit=paths is not None)
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
