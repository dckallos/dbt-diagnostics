"""Typed repository policy loading for governance and Codex tooling."""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
from typing import Any, Iterable, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required.
    tomllib = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = ROOT / "scripts" / "triage" / "policy.toml"


class RepoConfigError(RuntimeError):
    """Raised when repository policy cannot be loaded safely."""


@dataclass(frozen=True)
class RepositoryIdentity:
    owner: str
    name: str
    default_branch: str
    protected_branches: tuple[str, ...]
    progress_log_path: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class GovernanceContract:
    id: str
    version: str


@dataclass(frozen=True)
class GovernancePaths:
    reference_roots: tuple[str, ...]
    protected_surfaces: tuple[str, ...]
    semantic_scan_roots: tuple[str, ...]


@dataclass(frozen=True)
class HookEvent:
    script: str
    matcher: str | None = None


@dataclass(frozen=True)
class CodexHooks:
    config_path: str
    launcher_path: str
    events: Mapping[str, HookEvent]


@dataclass(frozen=True)
class CodexPolicy:
    environment_name: str
    venv_dir: str
    quality_receipt_path: str
    hooks: CodexHooks


@dataclass(frozen=True)
class ProductCli:
    distribution_name: str | None
    commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ProductDist:
    required_wheel_suffixes: tuple[str, ...]
    required_sdist_suffixes: tuple[str, ...]


@dataclass(frozen=True)
class ProductChecks:
    package_roots: tuple[str, ...]
    python_compile_roots: tuple[str, ...]
    required_modules: tuple[str, ...]
    live_modules: tuple[str, ...]
    live_install_env_vars: tuple[str, ...]
    optional_checks: frozenset[str]
    cli: ProductCli
    dist: ProductDist


@dataclass(frozen=True)
class CompatSchemaSet:
    name: str
    sentinel: str
    artifact: str
    versions: tuple[int, ...]


@dataclass(frozen=True)
class OfficialDocsProviderPolicy:
    key: str
    display_name: str
    trigger_patterns: tuple[str, ...]
    official_domains: tuple[str, ...]


@dataclass(frozen=True)
class OfficialDocsPolicy:
    enabled: bool
    section_title: str
    providers: tuple[OfficialDocsProviderPolicy, ...]
    unknown_provider_policy: str
    critical_unverified_requires_blocker: bool


@dataclass(frozen=True)
class WorkerPacketPolicy:
    required_verification_commands: tuple[str, ...]


@dataclass(frozen=True)
class RepoPolicy:
    repository: RepositoryIdentity
    contract: GovernanceContract
    paths: GovernancePaths
    codex: CodexPolicy
    product: ProductChecks
    compat_schema_sets: tuple[CompatSchemaSet, ...]
    official_docs: OfficialDocsPolicy
    worker_packet: WorkerPacketPolicy

    def to_json(self) -> dict[str, Any]:
        return {
            "repository": {
                "owner": self.repository.owner,
                "name": self.repository.name,
                "full_name": self.repository.full_name,
                "default_branch": self.repository.default_branch,
                "protected_branches": list(self.repository.protected_branches),
                "progress_log_path": self.repository.progress_log_path,
            },
            "governance": {
                "contract": {
                    "id": self.contract.id,
                    "version": self.contract.version,
                },
                "paths": {
                    "reference_roots": list(self.paths.reference_roots),
                    "protected_surfaces": list(self.paths.protected_surfaces),
                    "semantic_scan_roots": list(self.paths.semantic_scan_roots),
                },
                "official_docs": {
                    "enabled": self.official_docs.enabled,
                    "section_title": self.official_docs.section_title,
                    "unknown_provider_policy": (
                        self.official_docs.unknown_provider_policy
                    ),
                    "critical_unverified_requires_blocker": (
                        self.official_docs.critical_unverified_requires_blocker
                    ),
                    "providers": [
                        {
                            "key": provider.key,
                            "display_name": provider.display_name,
                            "trigger_patterns": list(provider.trigger_patterns),
                            "official_domains": list(provider.official_domains),
                        }
                        for provider in self.official_docs.providers
                    ],
                },
            },
            "codex": {
                "environment_name": self.codex.environment_name,
                "venv_dir": self.codex.venv_dir,
                "quality_receipt_path": self.codex.quality_receipt_path,
                "hooks": {
                    "config_path": self.codex.hooks.config_path,
                    "launcher_path": self.codex.hooks.launcher_path,
                    "events": {
                        name: {"matcher": event.matcher, "script": event.script}
                        for name, event in sorted(self.codex.hooks.events.items())
                    },
                },
            },
            "product": {
                "package_roots": list(self.product.package_roots),
                "python_compile_roots": list(self.product.python_compile_roots),
                "required_modules": list(self.product.required_modules),
                "live_modules": list(self.product.live_modules),
                "live_install_env_vars": list(self.product.live_install_env_vars),
                "optional_checks": sorted(self.product.optional_checks),
                "cli": {
                    "distribution_name": self.product.cli.distribution_name,
                    "commands": [list(command) for command in self.product.cli.commands],
                },
                "dist": {
                    "required_wheel_suffixes": list(
                        self.product.dist.required_wheel_suffixes
                    ),
                    "required_sdist_suffixes": list(
                        self.product.dist.required_sdist_suffixes
                    ),
                },
            },
            "compat": {
                "schema_sets": [
                    {
                        "name": item.name,
                        "sentinel": item.sentinel,
                        "artifact": item.artifact,
                        "versions": list(item.versions),
                    }
                    for item in self.compat_schema_sets
                ],
            },
            "worker_packet": {
                "required_verification_commands": list(
                    self.worker_packet.required_verification_commands
                )
            },
        }


REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DOMAIN_RE = re.compile(r"^[a-z0-9.-]+$")
SHELL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CLI_TOKEN_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,-]+$")
SHELL_RECORD_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SUPPORTED_HOOK_EVENTS = frozenset({"PreToolUse", "PermissionRequest", "Stop"})
SUPPORTED_OPTIONAL_CHECKS = frozenset({"package", "compat_schema"})
UNKNOWN_PROVIDER_POLICY = "preserve_verification_or_uncertainty"
CANONICAL_OFFICIAL_DOCS_SECTION_TITLE = "Official documentation evidence"
SUPPORTED_CODEX_VENV_DIR = ".venv"
GH_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
GH_API_MUTATION_TARGET_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:issues|pulls|labels|milestones|projects|workflows|secrets|variables)"
    r"(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
GRAPHQL_MUTATION_RE = re.compile(r"\bmutation\b", re.IGNORECASE)
GH_MUTATING_SUBCOMMANDS = {
    "issue": frozenset(
        {
            "create",
            "edit",
            "close",
            "reopen",
            "delete",
            "comment",
            "lock",
            "unlock",
            "pin",
            "unpin",
            "transfer",
        }
    ),
    "pr": frozenset(
        {
            "merge",
            "close",
            "edit",
            "ready",
            "lock",
            "unlock",
            "comment",
            "review",
        }
    ),
    "workflow": frozenset({"run", "disable", "enable"}),
    "secret": frozenset({"set"}),
    "variable": frozenset({"set"}),
    "label": frozenset({"create", "edit", "delete", "clone", "close", "reopen"}),
    "milestone": frozenset(
        {"create", "edit", "delete", "clone", "close", "reopen"}
    ),
    "project": frozenset(
        {"create", "edit", "delete", "item-add", "item-edit", "item-delete", "item-move"}
    ),
}
GH_GLOBAL_OPTIONS_WITH_VALUE = frozenset(
    {"--repo", "-R", "--hostname", "--config", "--jq", "--template"}
)

FORBIDDEN_MUTATION_KEYS = frozenset(
    {
        "operations",
        "github_request",
        "github_requests",
        "github_request_payload",
        "github_request_payloads",
        "request_payload",
        "request_payloads",
        "rest_request",
        "rest_requests",
        "graphql_request",
        "graphql_requests",
        "mutation_request",
        "mutation_requests",
        "body_update",
        "body_updates",
        "title_update",
        "title_updates",
        "state_update",
        "state_updates",
        "label_update",
        "label_updates",
        "milestone_update",
        "milestone_updates",
        "project_update",
        "project_updates",
        "close_request",
        "close_requests",
        "reopen_request",
        "reopen_requests",
        "workflow_dispatch",
        "workflow_dispatches",
        "workflow_toggle",
        "workflow_toggles",
        "pr_merge",
        "pr_merges",
        "pull_request_merge",
        "pull_request_merges",
        "merge_instruction",
        "merge_instructions",
    }
)
FORBIDDEN_OPERATION_IDS = frozenset(
    {
        "issue.body.update",
        "issue.title.update",
        "issue.close",
        "issue.reopen",
        "project.create",
        "project.update",
        "label.create",
        "label.delete",
        "milestone.create",
        "pull_request.merge",
        "pull-request.merge",
        "pr.merge",
    }
)
FORBIDDEN_OPERATION_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    + "|".join(re.escape(item) for item in sorted(FORBIDDEN_OPERATION_IDS))
    + r")(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)


def load_policy_mapping(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    if tomllib is None:
        raise RepoConfigError("Python 3.11+ with tomllib is required")
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise RepoConfigError(f"policy file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RepoConfigError(f"invalid policy TOML: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RepoConfigError(f"policy must be a TOML table: {path}")
    return value


def load_repo_policy(path: Path = DEFAULT_POLICY_PATH) -> RepoPolicy:
    return policy_from_mapping(load_policy_mapping(path), source=path)


def policy_from_mapping(
    value: Mapping[str, Any], *, source: Path | str = "policy"
) -> RepoPolicy:
    label = str(source)
    errors: list[str] = []
    _reject_mutation_shapes(value, errors=errors, path=label)
    repository = _repository(value.get("repository"), errors, label)
    contract, paths, official_docs = _governance(value.get("governance"), errors, label)
    codex = _codex(value.get("codex"), errors, label)
    product = _product(value.get("product"), errors, label)
    compat = _compat(value.get("compat"), errors, label)
    worker_packet = _worker_packet(value.get("worker_packet"), errors, label)
    if errors:
        raise RepoConfigError("; ".join(errors))
    return RepoPolicy(
        repository=repository,
        contract=contract,
        paths=paths,
        codex=codex,
        product=product,
        compat_schema_sets=compat,
        official_docs=official_docs,
        worker_packet=worker_packet,
    )


def _reject_mutation_shapes(value: Any, *, errors: list[str], path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            normalized = _normalize_key(key)
            item_path = f"{path}.{key}"
            if normalized in FORBIDDEN_MUTATION_KEYS:
                errors.append(f"{item_path} is forbidden in repository policy")
            if FORBIDDEN_OPERATION_RE.search(key):
                errors.append(f"{item_path} names a forbidden operation id")
            _reject_mutation_shapes(raw_item, errors=errors, path=item_path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_mutation_shapes(item, errors=errors, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and FORBIDDEN_OPERATION_RE.search(value):
        errors.append(f"{path} contains a forbidden operation id")


def _normalize_key(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(".", "_")


def _repository(value: Any, errors: list[str], label: str) -> RepositoryIdentity:
    table = _table(value, errors, f"{label}.repository")
    owner = _required_string(table, "owner", errors, f"{label}.repository")
    name = _required_string(table, "name", errors, f"{label}.repository")
    default_branch = _required_string(
        table, "default_branch", errors, f"{label}.repository"
    )
    full_name = f"{owner}/{name}"
    if owner and name and not REPO_RE.fullmatch(full_name):
        errors.append(f"{label}.repository owner/name must form owner/name")
    protected_branches = _string_tuple(
        table.get("protected_branches"),
        errors,
        f"{label}.repository.protected_branches",
        required=True,
    )
    if default_branch and default_branch not in protected_branches:
        errors.append(
            f"{label}.repository.protected_branches must include default_branch"
        )
    progress_log_path = _required_relative_path(
        table, "progress_log_path", errors, f"{label}.repository"
    )
    return RepositoryIdentity(
        owner=owner,
        name=name,
        default_branch=default_branch,
        protected_branches=protected_branches,
        progress_log_path=progress_log_path,
    )


def _governance(
    value: Any, errors: list[str], label: str
) -> tuple[GovernanceContract, GovernancePaths, OfficialDocsPolicy]:
    table = _table(value, errors, f"{label}.governance")
    contract_table = _table(
        table.get("contract"), errors, f"{label}.governance.contract"
    )
    contract_id = _required_string(
        contract_table, "id", errors, f"{label}.governance.contract"
    )
    contract_version = _required_string(
        contract_table, "version", errors, f"{label}.governance.contract"
    )
    paths_table = _table(table.get("paths"), errors, f"{label}.governance.paths")
    reference_roots = _path_tuple(
        paths_table.get("reference_roots"),
        errors,
        f"{label}.governance.paths.reference_roots",
        required=True,
        allow_glob=False,
    )
    protected_surfaces = _path_tuple(
        paths_table.get("protected_surfaces"),
        errors,
        f"{label}.governance.paths.protected_surfaces",
        required=True,
        allow_glob=True,
    )
    semantic_scan_roots = _path_tuple(
        paths_table.get("semantic_scan_roots"),
        errors,
        f"{label}.governance.paths.semantic_scan_roots",
        required=True,
        allow_glob=False,
    )
    official_docs = _official_docs(
        table.get("official_docs"), errors, f"{label}.governance.official_docs"
    )
    return (
        GovernanceContract(id=contract_id, version=contract_version),
        GovernancePaths(
            reference_roots=reference_roots,
            protected_surfaces=protected_surfaces,
            semantic_scan_roots=semantic_scan_roots,
        ),
        official_docs,
    )


def _codex(value: Any, errors: list[str], label: str) -> CodexPolicy:
    table = _table(value, errors, f"{label}.codex")
    environment_name = _required_string(table, "environment_name", errors, f"{label}.codex")
    venv_dir = _required_relative_path(table, "venv_dir", errors, f"{label}.codex")
    if venv_dir and venv_dir != SUPPORTED_CODEX_VENV_DIR:
        errors.append(
            f"{label}.codex.venv_dir must be {SUPPORTED_CODEX_VENV_DIR!r}; "
            "configurable hook launcher venv_dir is deferred"
        )
    quality_receipt_path = _required_relative_path(
        table, "quality_receipt_path", errors, f"{label}.codex"
    )
    hooks_table = _table(table.get("hooks"), errors, f"{label}.codex.hooks")
    config_path = _required_relative_path(
        hooks_table, "config_path", errors, f"{label}.codex.hooks"
    )
    launcher_path = _required_relative_path(
        hooks_table, "launcher_path", errors, f"{label}.codex.hooks"
    )
    events_table = _table(
        hooks_table.get("events"), errors, f"{label}.codex.hooks.events"
    )
    events: dict[str, HookEvent] = {}
    for event_name, raw_event in events_table.items():
        if event_name not in SUPPORTED_HOOK_EVENTS:
            errors.append(f"{label}.codex.hooks.events.{event_name} is unsupported")
            continue
        event_table = _table(
            raw_event, errors, f"{label}.codex.hooks.events.{event_name}"
        )
        script = _required_relative_path(
            event_table, "script", errors, f"{label}.codex.hooks.events.{event_name}"
        )
        matcher = event_table.get("matcher")
        if matcher is not None and (
            not isinstance(matcher, str) or not matcher.strip()
        ):
            errors.append(
                f"{label}.codex.hooks.events.{event_name}.matcher must be a string"
            )
            matcher = None
        events[event_name] = HookEvent(script=script, matcher=matcher)
    missing = sorted(SUPPORTED_HOOK_EVENTS - set(events))
    if missing:
        errors.append(
            f"{label}.codex.hooks.events missing required event(s): {', '.join(missing)}"
        )
    return CodexPolicy(
        environment_name=environment_name,
        venv_dir=venv_dir,
        quality_receipt_path=quality_receipt_path,
        hooks=CodexHooks(
            config_path=config_path,
            launcher_path=launcher_path,
            events=dict(sorted(events.items())),
        ),
    )


def _product(value: Any, errors: list[str], label: str) -> ProductChecks:
    table = _table(value, errors, f"{label}.product")
    optional_checks = frozenset(
        _string_tuple(
            table.get("optional_checks", []),
            errors,
            f"{label}.product.optional_checks",
            required=False,
        )
    )
    unknown_checks = sorted(optional_checks - SUPPORTED_OPTIONAL_CHECKS)
    if unknown_checks:
        errors.append(
            f"{label}.product.optional_checks has unsupported value(s): "
            + ", ".join(unknown_checks)
        )
    package_roots = _path_tuple(
        table.get("package_roots", []),
        errors,
        f"{label}.product.package_roots",
        required=False,
        allow_glob=False,
    )
    python_compile_roots = _path_tuple(
        table.get("python_compile_roots", []),
        errors,
        f"{label}.product.python_compile_roots",
        required=False,
        allow_glob=False,
    )
    required_modules = _string_tuple(
        table.get("required_modules", []),
        errors,
        f"{label}.product.required_modules",
        required=False,
    )
    live_modules = _string_tuple(
        table.get("live_modules", []),
        errors,
        f"{label}.product.live_modules",
        required=False,
    )
    live_install_env_vars = _string_tuple(
        table.get("live_install_env_vars", []),
        errors,
        f"{label}.product.live_install_env_vars",
        required=False,
    )
    _validate_shell_identifiers(
        live_install_env_vars,
        errors,
        f"{label}.product.live_install_env_vars",
    )
    cli_table = _table(table.get("cli", {}), errors, f"{label}.product.cli")
    distribution_name = cli_table.get("distribution_name")
    if distribution_name is not None and not isinstance(distribution_name, str):
        errors.append(f"{label}.product.cli.distribution_name must be a string")
        distribution_name = None
    raw_commands = cli_table.get("commands", [])
    commands: list[tuple[str, ...]] = []
    if not isinstance(raw_commands, list):
        errors.append(f"{label}.product.cli.commands must be a list")
    else:
        for index, raw_command in enumerate(raw_commands):
            command = _string_tuple(
                raw_command,
                errors,
                f"{label}.product.cli.commands[{index}]",
                required=True,
            )
            if command:
                _validate_cli_command_tokens(
                    command,
                    errors,
                    f"{label}.product.cli.commands[{index}]",
                )
                commands.append(command)
    dist_table = _table(table.get("dist", {}), errors, f"{label}.product.dist")
    dist = ProductDist(
        required_wheel_suffixes=_path_tuple(
            dist_table.get("required_wheel_suffixes", []),
            errors,
            f"{label}.product.dist.required_wheel_suffixes",
            required=False,
            allow_glob=False,
        ),
        required_sdist_suffixes=_path_tuple(
            dist_table.get("required_sdist_suffixes", []),
            errors,
            f"{label}.product.dist.required_sdist_suffixes",
            required=False,
            allow_glob=False,
        ),
    )
    return ProductChecks(
        package_roots=package_roots,
        python_compile_roots=python_compile_roots,
        required_modules=required_modules,
        live_modules=live_modules,
        live_install_env_vars=live_install_env_vars,
        optional_checks=optional_checks,
        cli=ProductCli(
            distribution_name=distribution_name.strip()
            if isinstance(distribution_name, str) and distribution_name.strip()
            else None,
            commands=tuple(commands),
        ),
        dist=dist,
    )


def _compat(value: Any, errors: list[str], label: str) -> tuple[CompatSchemaSet, ...]:
    table = _table(value or {}, errors, f"{label}.compat")
    raw_sets = table.get("schema_sets", [])
    if not isinstance(raw_sets, list):
        errors.append(f"{label}.compat.schema_sets must be a list")
        return ()
    result: list[CompatSchemaSet] = []
    names: set[str] = set()
    for index, raw_item in enumerate(raw_sets):
        item_label = f"{label}.compat.schema_sets[{index}]"
        item = _table(raw_item, errors, item_label)
        name = _required_string(item, "name", errors, item_label)
        if name in names:
            errors.append(f"{item_label}.name duplicates {name!r}")
        names.add(name)
        sentinel = _required_relative_path(item, "sentinel", errors, item_label)
        artifact = _required_string(item, "artifact", errors, item_label)
        raw_versions = item.get("versions")
        if (
            not isinstance(raw_versions, list)
            or not raw_versions
            or not all(
                isinstance(version, int)
                and not isinstance(version, bool)
                and version > 0
                for version in raw_versions
            )
        ):
            errors.append(f"{item_label}.versions must be positive integers")
            versions: tuple[int, ...] = ()
        else:
            versions = tuple(raw_versions)
            if tuple(sorted(set(versions))) != versions:
                errors.append(f"{item_label}.versions must be sorted and unique")
        result.append(
            CompatSchemaSet(
                name=name,
                sentinel=sentinel,
                artifact=artifact,
                versions=versions,
            )
        )
    return tuple(result)


def _official_docs(value: Any, errors: list[str], label: str) -> OfficialDocsPolicy:
    table = _table(value, errors, label)
    enabled = table.get("enabled")
    if not isinstance(enabled, bool):
        errors.append(f"{label}.enabled must be a boolean")
        enabled = False
    section_title = _required_string(table, "section_title", errors, label)
    if (
        section_title
        and section_title != CANONICAL_OFFICIAL_DOCS_SECTION_TITLE
    ):
        errors.append(
            f"{label}.section_title must be "
            f"{CANONICAL_OFFICIAL_DOCS_SECTION_TITLE!r}; configurable official-doc "
            "section titles are deferred"
        )
    unknown_provider_policy = _required_string(
        table, "unknown_provider_policy", errors, label
    )
    if unknown_provider_policy and unknown_provider_policy != UNKNOWN_PROVIDER_POLICY:
        errors.append(
            f"{label}.unknown_provider_policy must be {UNKNOWN_PROVIDER_POLICY!r}"
        )
    critical = table.get("critical_unverified_requires_blocker")
    if critical is not True:
        errors.append(f"{label}.critical_unverified_requires_blocker must be true")
    for forbidden_flag in (
        "network_retrieval",
        "url_fetching",
        "browser_automation",
        "freshness_enforcement",
        "freshness_checks",
        "live_retrieval",
    ):
        if table.get(forbidden_flag) is True:
            errors.append(f"{label}.{forbidden_flag}=true is unsupported")
    raw_providers = table.get("providers", [])
    if not isinstance(raw_providers, list) or (enabled and not raw_providers):
        errors.append(f"{label}.providers must be a non-empty list when enabled")
        raw_providers = []
    providers: list[OfficialDocsProviderPolicy] = []
    keys: set[str] = set()
    for index, raw_provider in enumerate(raw_providers):
        item_label = f"{label}.providers[{index}]"
        item = _table(raw_provider, errors, item_label)
        key = _required_string(item, "key", errors, item_label)
        if key in keys:
            errors.append(f"{item_label}.key duplicates {key!r}")
        keys.add(key)
        display_name = _required_string(item, "display_name", errors, item_label)
        trigger_patterns = _string_tuple(
            item.get("trigger_patterns"),
            errors,
            f"{item_label}.trigger_patterns",
            required=True,
        )
        for pattern in trigger_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{item_label}.trigger_patterns has invalid regex: {exc}")
        official_domains = _string_tuple(
            item.get("official_domains"),
            errors,
            f"{item_label}.official_domains",
            required=True,
        )
        normalized_domains: list[str] = []
        for domain in official_domains:
            normalized = domain.lower().strip(".")
            if not DOMAIN_RE.fullmatch(normalized) or "/" in domain or ":" in domain:
                errors.append(f"{item_label}.official_domains has invalid domain {domain!r}")
            else:
                normalized_domains.append(normalized)
        providers.append(
            OfficialDocsProviderPolicy(
                key=key,
                display_name=display_name,
                trigger_patterns=trigger_patterns,
                official_domains=tuple(normalized_domains),
            )
        )
    return OfficialDocsPolicy(
        enabled=enabled,
        section_title=section_title,
        providers=tuple(providers),
        unknown_provider_policy=unknown_provider_policy,
        critical_unverified_requires_blocker=bool(critical),
    )


def _worker_packet(value: Any, errors: list[str], label: str) -> WorkerPacketPolicy:
    table = _table(value, errors, f"{label}.worker_packet")
    commands = _string_tuple(
        table.get("required_verification_commands"),
        errors,
        f"{label}.worker_packet.required_verification_commands",
        required=True,
    )
    _validate_worker_packet_commands(
        commands, errors, f"{label}.worker_packet.required_verification_commands"
    )
    return WorkerPacketPolicy(required_verification_commands=commands)


def _table(value: Any, errors: list[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be a table")
        return {}
    return value


def _required_string(
    table: Mapping[str, Any], key: str, errors: list[str], label: str
) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _string_tuple(
    value: Any, errors: list[str], label: str, *, required: bool
) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        errors.append(f"{label} must be a {'non-empty ' if required else ''}list")
        return ()
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        result.append(item.strip())
    if len(set(result)) != len(result):
        errors.append(f"{label} must not contain duplicates")
    return tuple(result)


def _path_tuple(
    value: Any,
    errors: list[str],
    label: str,
    *,
    required: bool,
    allow_glob: bool,
) -> tuple[str, ...]:
    items = _string_tuple(value, errors, label, required=required)
    normalized: list[str] = []
    for item in items:
        normalized.append(_validate_relative_path(item, errors, label, allow_glob=allow_glob))
    return tuple(item for item in normalized if item)


def _required_relative_path(
    table: Mapping[str, Any], key: str, errors: list[str], label: str
) -> str:
    value = _required_string(table, key, errors, label)
    if not value:
        return ""
    return _validate_relative_path(value, errors, f"{label}.{key}", allow_glob=False)


def _validate_relative_path(
    value: str, errors: list[str], label: str, *, allow_glob: bool
) -> str:
    if "\\" in value:
        errors.append(f"{label} must use forward slashes: {value!r}")
        return ""
    if not value or value.startswith("/"):
        errors.append(f"{label} must be a relative repository path: {value!r}")
        return ""
    if value.startswith("./"):
        errors.append(f"{label} must be normalized without './': {value!r}")
        return ""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{label} must not be absolute or escape the repository: {value!r}")
        return ""
    if not allow_glob and any(char in value for char in "*?[]"):
        errors.append(f"{label} must not contain glob characters: {value!r}")
        return ""
    normalized = path.as_posix()
    if normalized in {"", "."}:
        errors.append(f"{label} must be a repository path, not {value!r}")
        return ""
    return normalized


def _validate_shell_identifiers(
    values: Iterable[str], errors: list[str], label: str
) -> None:
    for index, value in enumerate(values):
        if not SHELL_IDENTIFIER_RE.fullmatch(value):
            errors.append(f"{label}[{index}] must be a safe shell identifier: {value!r}")


def _validate_cli_command_tokens(
    command: Sequence[str], errors: list[str], label: str
) -> None:
    for index, token in enumerate(command):
        if not CLI_TOKEN_RE.fullmatch(token):
            errors.append(
                f"{label}[{index}] must not contain shell metacharacters: {token!r}"
            )


def _validate_worker_packet_commands(
    commands: Sequence[str], errors: list[str], label: str
) -> None:
    for index, command in enumerate(commands):
        reason = github_mutation_command_reason(command)
        if reason is not None:
            errors.append(f"{label}[{index}] {reason}")


def github_mutation_command_reason(command: str) -> str | None:
    """Return a reason when a command string is shaped like a GitHub write."""

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return f"must be shell-tokenizable: {exc}"
    if not tokens or tokens[0] != "gh":
        return None
    gh_args = _gh_command_args(tokens)
    if not gh_args:
        return None

    area = gh_args[0].casefold()
    subcommand = gh_args[1].casefold() if len(gh_args) > 1 else ""
    mutating_subcommands = GH_MUTATING_SUBCOMMANDS.get(area)
    if mutating_subcommands is not None and subcommand in mutating_subcommands:
        return f"must not contain GitHub mutation command: gh {area} {subcommand}"

    if area == "api":
        if subcommand == "graphql":
            if GRAPHQL_MUTATION_RE.search(command):
                return "must not contain GitHub GraphQL mutation command"
            return None
        method = _gh_api_method(gh_args)
        if method in GH_MUTATING_METHODS and GH_API_MUTATION_TARGET_RE.search(command):
            return (
                "must not contain mutating gh api command against tracker, workflow, "
                "secret, or variable surfaces"
            )
    return None


def _gh_command_args(tokens: Sequence[str]) -> tuple[str, ...]:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in GH_GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if any(token.startswith(option + "=") for option in GH_GLOBAL_OPTIONS_WITH_VALUE):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    return tuple(tokens[index:])


def _gh_api_method(gh_args: Sequence[str]) -> str:
    method = "GET"
    index = 1
    while index < len(gh_args):
        token = gh_args[index]
        if token in {"--method", "-X"} and index + 1 < len(gh_args):
            method = gh_args[index + 1].upper()
            index += 2
            continue
        if token.startswith("--method="):
            method = token.split("=", 1)[1].upper()
        elif token.startswith("-X") and len(token) > 2:
            method = token[2:].upper()
        index += 1
    return method


def shell_exports(policy: RepoPolicy) -> dict[str, str]:
    exports = {
        "CODEX_POLICY_REPOSITORY_FULL_NAME": policy.repository.full_name,
        "CODEX_POLICY_DEFAULT_BRANCH": policy.repository.default_branch,
        "CODEX_POLICY_PROTECTED_BRANCHES": " ".join(
            policy.repository.protected_branches
        ),
        "CODEX_POLICY_PROGRESS_LOG_PATH": policy.repository.progress_log_path,
        "CODEX_POLICY_VENV_DIR": policy.codex.venv_dir,
        "CODEX_POLICY_ENVIRONMENT_NAME": policy.codex.environment_name,
        "CODEX_POLICY_QUALITY_RECEIPT_PATH": policy.codex.quality_receipt_path,
        "CODEX_POLICY_HOOK_CONFIG_PATH": policy.codex.hooks.config_path,
        "CODEX_POLICY_HOOK_LAUNCHER_PATH": policy.codex.hooks.launcher_path,
        "CODEX_POLICY_PACKAGE_ROOTS": " ".join(policy.product.package_roots),
        "CODEX_POLICY_PYTHON_COMPILE_ROOTS": " ".join(
            policy.product.python_compile_roots
        ),
        "CODEX_POLICY_REQUIRED_MODULES": " ".join(policy.product.required_modules),
        "CODEX_POLICY_LIVE_MODULES": " ".join(policy.product.live_modules),
        "CODEX_POLICY_LIVE_INSTALL_ENV_VARS": " ".join(
            policy.product.live_install_env_vars
        ),
        "CODEX_POLICY_OPTIONAL_CHECKS": " ".join(
            sorted(policy.product.optional_checks)
        ),
        "CODEX_POLICY_CLI_DISTRIBUTION_NAME": (
            policy.product.cli.distribution_name or ""
        ),
        "CODEX_POLICY_DIST_WHEEL_SUFFIXES": " ".join(
            policy.product.dist.required_wheel_suffixes
        ),
        "CODEX_POLICY_DIST_SDIST_SUFFIXES": " ".join(
            policy.product.dist.required_sdist_suffixes
        ),
    }
    for key, value in exports.items():
        if not SHELL_RECORD_KEY_RE.fullmatch(key):
            raise RepoConfigError(f"policy shell export key is unsafe: {key!r}")
        if any(char in value for char in "\n\t\0"):
            raise RepoConfigError(f"policy shell export value is unsafe for {key}")
    return exports


def export_shell(policy: RepoPolicy) -> str:
    lines = []
    for key, value in sorted(shell_exports(policy).items()):
        lines.append(f"{key}={shlex.quote(value)}")
    return "\n".join(lines) + "\n"


def export_env_records(policy: RepoPolicy) -> str:
    lines = []
    for key, value in sorted(shell_exports(policy).items()):
        lines.append(f"{key}\t{value}")
    return "\n".join(lines) + "\n"


def cli_command_lines(policy: RepoPolicy) -> tuple[str, ...]:
    return tuple(shlex.join(command) for command in policy.product.cli.commands)


def compat_record_lines(policy: RepoPolicy) -> tuple[str, ...]:
    return tuple(
        "\t".join(
            [
                item.name,
                item.artifact,
                item.sentinel,
                ",".join(str(version) for version in item.versions),
            ]
        )
        for item in policy.compat_schema_sets
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "export-json",
            "export-shell",
            "export-env",
            "cli-commands",
            "compat-records",
        ),
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    args = parser.parse_args(argv)
    try:
        policy = load_repo_policy(args.policy)
    except RepoConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "export-json":
            print(
                json.dumps(
                    policy.to_json(), indent=2, sort_keys=True, ensure_ascii=True
                )
            )
        elif args.command == "export-shell":
            print(export_shell(policy), end="")
        elif args.command == "export-env":
            print(export_env_records(policy), end="")
        elif args.command == "cli-commands":
            for line in cli_command_lines(policy):
                print(line)
        elif args.command == "compat-records":
            for line in compat_record_lines(policy):
                print(line)
    except RepoConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
