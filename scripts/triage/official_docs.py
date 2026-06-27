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

META_PATTERNS = (
    r"\bofficial documentation evidence\b",
    r"\bofficial docs evidence\b",
    r"\bissue-governance\b",
    r"\bissue contract\b",
    r"\bcontract and standardize\b",
    r"\bsection should be required\b",
    r"\bcontract enforces the section\b",
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
DATE_RE = re.compile(r"\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b")


def _matches_any_pattern(text: str, patterns: Iterable[str]) -> tuple[str, ...]:
    lower = text.lower()
    return tuple(pattern for pattern in patterns if re.search(pattern, lower))


def requirements(
    title: str, labels: Iterable[str], body: str
) -> tuple[OfficialDocsRequirement, ...]:
    text = "\n".join([title, " ".join(labels), body])
    meta_matches = _matches_any_pattern(text, META_PATTERNS)
    has_meta_subject = any(
        "official doc" in match or "official documentation" in match
        for match in meta_matches
    )
    has_contract_context = any(
        "issue" in match or "contract" in match or "section" in match
        for match in meta_matches
    )
    if has_meta_subject and has_contract_context:
        return ()

    context_matches = _matches_any_pattern(text, CONTEXT_PATTERNS)
    label_set = {label.lower() for label in labels}
    required: list[OfficialDocsRequirement] = []
    for provider in PROVIDERS:
        provider_matches = list(_matches_any_pattern(text, provider.trigger_patterns))
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


def _content_mentions_provider(content: str, provider: OfficialDocsProvider) -> bool:
    if _matches_any_pattern(content, provider.trigger_patterns):
        return True
    lower = content.lower()
    return provider.key in lower or provider.display_name.lower() in lower


def _unknown_provider_requires_verification(content: str) -> bool:
    lower = content.lower()
    return bool(
        re.search(
            r"\b(maintainer|manual|human)\s+(review|verification|check)\b",
            lower,
        )
        or "unknown provider" in lower
        or "unverified provider" in lower
        or "cannot verify" in lower
    )


def _unknown_provider_blocks_implementation(content: str) -> bool:
    lower = content.lower()
    return _unknown_provider_requires_verification(content) and bool(
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
    required_providers = tuple(item.provider for item in required)
    findings = _field_findings(content)
    if unresolved_placeholder in content:
        return findings

    for requirement in required:
        provider = requirement.provider
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

    if required_providers:
        for url in urls:
            host = _url_host(url)
            if not any(
                _provider_matches_host(provider, host)
                for provider in required_providers
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

    known_url_provider = any(_known_providers_for_host(_url_host(url)) for url in urls)
    known_content_provider = any(
        _content_mentions_provider(content, provider) for provider in PROVIDERS
    )
    provider_values = _provider_field_values(content)
    unknown_provider_named = bool(provider_values) and not known_content_provider
    unknown_url = bool(urls) and not known_url_provider
    unknown_source = unknown_provider_named or unknown_url
    if unknown_source and not _unknown_provider_requires_verification(content):
        findings.append(
            {
                "level": "error",
                "code": "official-docs-unknown-provider",
                "message": (
                    "Unknown official documentation providers require explicit "
                    "maintainer verification or residual uncertainty."
                ),
                "section": "official_docs",
            }
        )
    if (
        unknown_source
        and _unknown_provider_blocks_implementation(content)
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
