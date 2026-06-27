"""Deterministic official-documentation evidence checks for issue contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class OfficialDocsProvider:
    key: str
    display_name: str
    trigger_patterns: tuple[str, ...]
    official_domains: tuple[str, ...]


@dataclass(frozen=True)
class OfficialDocsRequirement:
    provider: OfficialDocsProvider
    matched_patterns: tuple[str, ...]


UNKNOWN_EXTERNAL_PROVIDER = OfficialDocsProvider(
    key="unknown_external",
    display_name="Unknown external provider",
    trigger_patterns=(),
    official_domains=(),
)

PROVIDERS = (
    OfficialDocsProvider(
        key="openai",
        display_name="OpenAI/Codex",
        trigger_patterns=(
            r"\bopenai\b",
            r"\bcodex\b",
            r"\bchatgpt\b",
            r"\bresponses api\b",
            r"\bagents sdk\b",
        ),
        official_domains=(
            "developers.openai.com",
            "platform.openai.com",
            "help.openai.com",
        ),
    ),
    OfficialDocsProvider(
        key="dbt",
        display_name="dbt",
        trigger_patterns=(
            r"(?<![a-z0-9-])dbt(?![a-z0-9-])",
            r"\bdbt[- ]core\b",
            r"\bdbt cloud\b",
            r"\bdbt docs?\b",
        ),
        official_domains=("docs.getdbt.com",),
    ),
    OfficialDocsProvider(
        key="github",
        display_name="GitHub",
        trigger_patterns=(
            r"\bgithub actions\b",
            r"\bgithub api\b",
            r"\bgithub cli\b",
            r"\bgithub graphql\b",
            r"\bgithub rest\b",
            r"\bgithub workflow\b",
            r"\bgh api\b",
            r"\bworkflow_dispatch\b",
            r"\bclosingissuesreferences\b",
            r"\bauto-?close keywords?\b",
        ),
        official_domains=("docs.github.com",),
    ),
    OfficialDocsProvider(
        key="snowflake",
        display_name="Snowflake",
        trigger_patterns=(
            r"\bsnowflake\b",
            r"\binformation_schema\b",
            r"\bquery history\b",
        ),
        official_domains=("docs.snowflake.com",),
    ),
    OfficialDocsProvider(
        key="bigquery",
        display_name="BigQuery",
        trigger_patterns=(r"\bbigquery\b", r"\bgoogle cloud\b"),
        official_domains=("cloud.google.com", "docs.cloud.google.com"),
    ),
    OfficialDocsProvider(
        key="postgres",
        display_name="Postgres",
        trigger_patterns=(r"\bpostgres\b", r"\bpostgresql\b"),
        official_domains=("postgresql.org", "www.postgresql.org"),
    ),
    OfficialDocsProvider(
        key="duckdb",
        display_name="DuckDB",
        trigger_patterns=(r"\bduckdb\b",),
        official_domains=("duckdb.org",),
    ),
    OfficialDocsProvider(
        key="python",
        display_name="Python",
        trigger_patterns=(
            r"\bpython api\b",
            r"\bpython version\b",
            r"\bpython packaging\b",
            r"\bpep\s*[0-9]",
        ),
        official_domains=("docs.python.org", "packaging.python.org"),
    ),
    OfficialDocsProvider(
        key="pypi",
        display_name="PyPI",
        trigger_patterns=(r"\bpypi\b", r"\bpip\b", r"\bpackaging\b"),
        official_domains=(
            "docs.pypi.org",
            "pypi.org",
            "packaging.python.org",
            "pip.pypa.io",
        ),
    ),
    OfficialDocsProvider(
        key="npm",
        display_name="npm",
        trigger_patterns=(r"\bnpm\b", r"\bpackage manager\b"),
        official_domains=("docs.npmjs.com",),
    ),
    OfficialDocsProvider(
        key="uv",
        display_name="uv",
        trigger_patterns=(r"\buv\b", r"\bastral uv\b"),
        official_domains=("docs.astral.sh",),
    ),
)

CONTEXT_PATTERNS = (
    r"\bofficial docs?\b",
    r"\bofficial documentation\b",
    r"\bproduct documentation\b",
    r"\bplatform behavior\b",
    r"\bexternal platform behavior\b",
    r"\bapi\b",
    r"\bcli\b",
    r"\bcontract\b",
    r"\bschema guarantees?\b",
    r"\bhosted service\b",
    r"\bsemantics?\b",
    r"\bworkflow_dispatch\b",
    r"\bactions?\b",
    r"\bversion\b",
)

EXTERNAL_SCOPE_PATTERNS = (
    r"\bexternal (product|platform|provider|service|source|contract)\b",
    r"\boutside this repository\b",
    r"\bthird[- ]party\b",
    r"\bvendor\b",
    r"\bhosted\b",
    r"\bci service\b",
    r"\bpackage[- ]manager\b",
    r"\bpublished schema\b",
)

GENERIC_CONTRACT_PATTERNS = (
    r"\bapi\b",
    r"\bcli\b",
    r"\bcontract\b",
    r"\bschema guarantees?\b",
    r"\bpublished schema\b",
    r"\bhosted api\b",
    r"\bhosted service\b",
    r"\bci service\b",
    r"\bpackage[- ]manager\b",
    r"\bsemantics?\b",
    r"\bbehavior\b",
    r"\bguarantee\b",
    r"\bofficial source\b",
    r"\bofficial docs?\b",
    r"\bofficial documentation\b",
)

META_PATTERNS = (
    r"\bofficial documentation evidence\b",
    r"\bofficial docs evidence\b",
    r"\bissue-governance\b",
    r"\bissue contract\b",
    r"\bcontract and standardize\b",
    r"\bsection should be required\b",
    r"\brequires? the new section\b",
    r"\bnew section\b",
    r"\bsection is not required\b",
    r"\bcondition is triggered\b",
    r"\bplaceholder when .*condition is triggered\b",
    r"\bcontract enforces the section\b",
    r"\bofficial domains are accepted\b",
    r"\bpublic official documentation urls? as examples\b",
)

META_EXAMPLE_PATTERNS = (
    r"\btrigger list\b",
    r"\bprovider trigger\b",
    r"\bknown-provider trigger\b",
    r"\bexamples? such as\b",
    r"\bmay include examples\b",
    r"\bprovider list\b",
)

EXTERNAL_DEPENDENCY_ACTION_PATTERNS = (
    r"\bdepends on\b",
    r"\brelies on\b",
    r"\brequires\b",
    r"\bsupports the api\b",
    r"\bapi behavior\b",
    r"\bcli contract\b",
    r"\bschema guarantee\b",
    r"\bhosted api\b",
    r"\bci service behavior\b",
    r"\bpackage[- ]manager behavior\b",
)

PROVIDER_LABELS = {
    "snowflake": "snowflake",
    "bigquery": "bigquery",
    "postgres": "postgres",
    "postgresql": "postgres",
    "duckdb": "duckdb",
}

URL_RE = re.compile(r"https?://[^\s<>)\]]+")
PROVIDER_LINE_RE = re.compile(r"(?im)^\s*[-*]?\s*provider\s*:\s*(.+?)\s*$")
RESIDUAL_UNCERTAINTY_RE = re.compile(
    r"(?im)^\s*[-*]?\s*residual uncertainty\s*:\s*(.+?)\s*$"
)
DATE_RE = re.compile(r"\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b")
_NEG_PREFIX_RE = re.compile(r"\b(?:no|not|none|without|never|n/?a)\b[\s:,;.\-]*$")
_NEGATED_LINE_PREFIX_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:no|not|none|without|never|n/?a)\b"
)


def _matches_any_pattern(text: str, patterns: Iterable[str]) -> tuple[str, ...]:
    lower = text.lower()
    return tuple(pattern for pattern in patterns if re.search(pattern, lower))


def _requires_any_pattern(text: str, patterns: Iterable[str]) -> tuple[str, ...]:
    lower = text.lower()
    required: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            prefix = lower[max(0, match.start() - 24): match.start()]
            line_start = lower.rfind("\n", 0, match.start()) + 1
            line_prefix = lower[line_start: match.start()]
            if not _NEG_PREFIX_RE.search(prefix) and not _NEGATED_LINE_PREFIX_RE.search(
                line_prefix
            ):
                required.append(pattern)
                break
    return tuple(required)


def _line_is_meta_example(line: str) -> bool:
    return bool(
        _matches_any_pattern(line, META_PATTERNS)
        or _matches_any_pattern(line, META_EXAMPLE_PATTERNS)
    )


def _line_has_external_dependency_action(line: str) -> bool:
    return bool(_matches_any_pattern(line, EXTERNAL_DEPENDENCY_ACTION_PATTERNS))


def _provider_example_only_line(line: str) -> bool:
    if _line_has_external_dependency_action(line):
        return False
    return bool(
        _matches_any_pattern(
            line,
            tuple(
                pattern
                for provider in PROVIDERS
                for pattern in provider.trigger_patterns
            ),
        )
    )


def _non_meta_requirement_text(text: str) -> str:
    kept: list[str] = []
    previous_was_meta_example = False
    for line in text.splitlines():
        is_meta_example = _line_is_meta_example(line)
        if is_meta_example:
            previous_was_meta_example = True
            continue
        if previous_was_meta_example and _provider_example_only_line(line):
            continue
        kept.append(line)
        previous_was_meta_example = False
    return "\n".join(kept)


def _generic_external_matches(text: str) -> tuple[str, ...]:
    scope_matches = _requires_any_pattern(text, EXTERNAL_SCOPE_PATTERNS)
    contract_matches = _requires_any_pattern(text, GENERIC_CONTRACT_PATTERNS)
    if scope_matches and contract_matches:
        return tuple(sorted(set(scope_matches + contract_matches)))
    return ()


def requirements(
    title: str, labels: Iterable[str], body: str
) -> tuple[OfficialDocsRequirement, ...]:
    text = "\n".join([title, " ".join(labels), body])
    requirement_text = _non_meta_requirement_text(text)
    if not requirement_text.strip() and _matches_any_pattern(text, META_PATTERNS):
        return ()

    context_matches = _matches_any_pattern(requirement_text, CONTEXT_PATTERNS)
    label_set = {label.lower() for label in labels}
    required: list[OfficialDocsRequirement] = []
    for provider in PROVIDERS:
        provider_matches = list(
            _matches_any_pattern(requirement_text, provider.trigger_patterns)
        )
        for label, key in PROVIDER_LABELS.items():
            if key == provider.key and label in label_set:
                provider_matches.append(f"label:{label}")
        if provider_matches and (
            context_matches or provider_matches[0].startswith("label:")
        ):
            required.append(
                OfficialDocsRequirement(
                    provider=provider,
                    matched_patterns=tuple(sorted(set(provider_matches))),
                )
            )
    generic_matches = _generic_external_matches(requirement_text)
    if generic_matches and not required:
        required.append(
            OfficialDocsRequirement(
                provider=UNKNOWN_EXTERNAL_PROVIDER,
                matched_patterns=generic_matches,
            )
        )
    return tuple(required)


def _extract_urls(text: str) -> tuple[str, ...]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        urls.append(match.group(0).rstrip(".,;:"))
    return tuple(urls)


def _url_host(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.lower().strip(".")


def _host_matches(host: str, domains: Iterable[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _provider_matches_host(provider: OfficialDocsProvider, host: str) -> bool:
    return _host_matches(host, provider.official_domains)


def _known_providers_for_host(host: str) -> tuple[OfficialDocsProvider, ...]:
    return tuple(
        provider for provider in PROVIDERS if _provider_matches_host(provider, host)
    )


def _provider_field_values(content: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in PROVIDER_LINE_RE.finditer(content))


def _residual_uncertainty_values(content: str) -> tuple[str, ...]:
    return tuple(
        match.group(1).strip() for match in RESIDUAL_UNCERTAINTY_RE.finditer(content)
    )


def _provider_field_known_providers(value: str) -> tuple[OfficialDocsProvider, ...]:
    return tuple(
        provider for provider in PROVIDERS if _content_mentions_provider(value, provider)
    )


def _content_mentions_provider(content: str, provider: OfficialDocsProvider) -> bool:
    if _matches_any_pattern(content, provider.trigger_patterns):
        return True
    lower = content.lower()
    return provider.key in lower or provider.display_name.lower() in lower


def _unknown_provider_requires_verification(
    content: str,
    *,
    unknown_provider_values: Iterable[str] = (),
    unknown_hosts: Iterable[str] = (),
) -> bool:
    residual = "\n".join(_residual_uncertainty_values(content)) or content
    lower = residual.lower()
    if (
        "unknown provider" in lower
        or "unknown source" in lower
        or "unknown url" in lower
        or "unknown host" in lower
        or "unverified provider" in lower
        or "unverified source" in lower
        or "cannot verify" in lower
    ):
        return True
    maintainer_verification = re.search(
        r"\b(maintainer|manual|human)\s+(review|verification|check)\b",
        lower,
    )
    if not maintainer_verification:
        return False
    if re.search(r"\b(provider|source|host|domain|official url|url)\b", lower):
        return True
    for value in unknown_provider_values:
        if value and value.lower() in lower:
            return True
    for host in unknown_hosts:
        if host and host.lower() in lower:
            return True
    return False


def _unknown_provider_blocks_implementation(
    content: str,
    *,
    unknown_provider_values: Iterable[str] = (),
    unknown_hosts: Iterable[str] = (),
) -> bool:
    lower = content.lower()
    return _unknown_provider_requires_verification(
        content,
        unknown_provider_values=unknown_provider_values,
        unknown_hosts=unknown_hosts,
    ) and bool(
        "critical" in lower
        or "before implementation" in lower
        or "before implementation starts" in lower
        or "implementation blocker" in lower
        or "blocks implementation" in lower
        or "blocked until" in lower
    )


def _field_findings(content: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    checks = (
        ("provider", r"\bprovider\s*:"),
        ("supported claim or decision", r"\b(supported claim|claim|decision)\s*:"),
        (
            "docs version or product version",
            r"\b(docs version|product version|version)\s*:",
        ),
        ("retrieval date", r"\b(retrieval date|retrieved|accessed)\s*:"),
        ("residual uncertainty", r"\b(residual uncertainty|uncertainty)\s*:"),
    )
    for label, pattern in checks:
        if not re.search(pattern, content, flags=re.IGNORECASE):
            findings.append(
                {
                    "level": "error",
                    "code": "official-docs-incomplete-section",
                    "message": (
                        "Official documentation evidence must include "
                        f"{label}."
                    ),
                    "section": "official_docs",
                    "data": label,
                }
            )
    if not _extract_urls(content):
        findings.append(
            {
                "level": "error",
                "code": "official-docs-incomplete-section",
                "message": "Official documentation evidence must include an official URL.",
                "section": "official_docs",
                "data": "official URL",
            }
        )
    if not DATE_RE.search(content):
        findings.append(
            {
                "level": "error",
                "code": "official-docs-incomplete-section",
                "message": (
                    "Official documentation evidence must include a retrieval "
                    "date in YYYY-MM-DD form."
                ),
                "section": "official_docs",
                "data": "retrieval date",
            }
        )
    return findings


def section_findings(
    content: str,
    requirements: Iterable[OfficialDocsRequirement],
    *,
    unresolved_placeholder: str,
    has_decisions_blockers: bool = False,
) -> list[dict[str, Any]]:
    urls = _extract_urls(content)
    required = tuple(requirements)
    known_required_providers = tuple(
        item.provider for item in required if item.provider.official_domains
    )
    findings = _field_findings(content)
    if unresolved_placeholder in content:
        return findings

    for provider in known_required_providers:
        if not any(_provider_matches_host(provider, _url_host(url)) for url in urls):
            findings.append(
                {
                    "level": "error",
                    "code": "official-docs-unofficial-url",
                    "message": (
                        "Official documentation evidence for "
                        f"{provider.display_name} must use one of: "
                        + ", ".join(provider.official_domains)
                    ),
                    "section": "official_docs",
                    "provider": provider.key,
                }
            )

    if known_required_providers:
        for url in urls:
            host = _url_host(url)
            if not any(
                _provider_matches_host(provider, host)
                for provider in known_required_providers
            ):
                findings.append(
                    {
                        "level": "error",
                        "code": "official-docs-unofficial-url",
                        "message": (
                            "Official documentation evidence includes an "
                            f"unofficial URL for the triggered provider: {url}"
                        ),
                        "section": "official_docs",
                        "data": url,
                    }
                )

    unknown_hosts = tuple(
        _url_host(url)
        for url in urls
        if _url_host(url) and not _known_providers_for_host(_url_host(url))
    )
    provider_values = _provider_field_values(content)
    unknown_provider_values = tuple(
        value
        for value in provider_values
        if value and not _provider_field_known_providers(value)
    )
    unknown_source = bool(unknown_provider_values or unknown_hosts)
    if unknown_source and not _unknown_provider_requires_verification(
        content,
        unknown_provider_values=unknown_provider_values,
        unknown_hosts=unknown_hosts,
    ):
        findings.append(
            {
                "level": "error",
                "code": "official-docs-unknown-provider",
                "message": (
                    "Unknown official documentation providers require explicit "
                    "maintainer verification or residual uncertainty."
                ),
                "section": "official_docs",
                "data": {
                    "providers": sorted(unknown_provider_values),
                    "hosts": sorted(unknown_hosts),
                },
            }
        )
    if (
        unknown_source
        and _unknown_provider_blocks_implementation(
            content,
            unknown_provider_values=unknown_provider_values,
            unknown_hosts=unknown_hosts,
        )
        and not has_decisions_blockers
    ):
        findings.append(
            {
                "level": "error",
                "code": "official-docs-missing-verification-blocker",
                "message": (
                    "Critical unverified official documentation providers must "
                    "also be recorded in Maintainer decisions and blockers."
                ),
                "section": "official_docs",
            }
        )
    return findings
