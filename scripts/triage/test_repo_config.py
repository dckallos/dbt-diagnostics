from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.triage import repo_config


ROOT = Path(__file__).resolve().parents[2]
DBT_POLICY = ROOT / "scripts" / "triage" / "policy.toml"
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"


def _policy_data() -> dict[str, object]:
    return repo_config.load_policy_mapping(DBT_POLICY)


def test_current_dbt_policy_loads_exact_adapter_values() -> None:
    policy = repo_config.load_repo_policy(DBT_POLICY)

    assert policy.repository.owner == "dckallos"
    assert policy.repository.name == "dbt-diagnostics"
    assert policy.repository.full_name == "dckallos/dbt-diagnostics"
    assert policy.repository.default_branch == "donkey-kong-sandbox"
    assert policy.repository.protected_branches == ("main", "donkey-kong-sandbox")
    assert policy.repository.progress_log_path == "docs/PROGRESS_LOG.md"
    assert policy.contract.id == "dbt-diagnostics.issue-contract.v1"
    assert policy.contract.version == "1.0"
    assert "dbt_diagnostics" in policy.paths.reference_roots
    assert ".codex/hooks/**" in policy.paths.protected_surfaces
    assert policy.codex.environment_name == "dbt-diagnostics"
    assert policy.codex.venv_dir == ".venv"
    assert policy.codex.quality_receipt_path == "output/codex/quality-receipt.json"
    assert policy.codex.hooks.config_path == ".codex/hooks.json"
    assert policy.codex.hooks.launcher_path == ".codex/hooks/run_hook.sh"
    assert policy.codex.hooks.events["PreToolUse"].script == "pre_tool_use.py"
    assert policy.codex.hooks.events["PermissionRequest"].script == (
        "permission_request.py"
    )
    assert policy.codex.hooks.events["Stop"].script == "stop.py"
    assert policy.product.package_roots == ("dbt_diagnostics",)
    assert ".codex/hooks" in policy.product.python_compile_roots
    assert policy.product.cli.distribution_name == "dbt-diagnostics"
    assert policy.product.cli.commands == (("dbt-diagnostics", "--help"),)
    assert policy.product.dist.required_wheel_suffixes == (
        "dbt_diagnostics/__init__.py",
        "dbt_diagnostics/templates/report.j2",
        ".dist-info/METADATA",
        ".dist-info/entry_points.txt",
    )
    assert policy.compat_schema_sets[0].sentinel == (
        "dbt_diagnostics/fixtures/schemas/manifest/v12.json"
    )
    assert policy.worker_packet.required_verification_commands == (
        "python -m compileall -q dbt_diagnostics scripts/triage",
        "pytest -q",
    )
    assert policy.official_docs.enabled is True
    assert policy.official_docs.section_title == "Official documentation evidence"
    assert {provider.key for provider in policy.official_docs.providers} >= {
        "dbt",
        "github",
        "openai",
    }


def test_synthetic_non_dbt_policy_loads_without_dbt_assumptions() -> None:
    policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    rendered = repr(policy.to_json())

    assert policy.repository.full_name == "example/widgets-service"
    assert policy.repository.default_branch == "trunk"
    assert policy.repository.protected_branches == ("main", "trunk")
    assert policy.contract.id == "widgets.issue-contract.v1"
    assert "dbt_diagnostics" not in policy.paths.reference_roots
    assert policy.product.package_roots == ()
    assert policy.product.cli.distribution_name is None
    assert policy.product.cli.commands == ()
    assert policy.compat_schema_sets == ()
    assert "dbt_diagnostics" not in rendered
    assert "dbt-diagnostics" not in rendered
    assert "donkey-kong-sandbox" not in rendered
    assert {provider.key for provider in policy.official_docs.providers} == {
        "github",
        "python_packaging",
    }
    assert policy.worker_packet.required_verification_commands == (
        "python -m compileall -q scripts .codex/scripts .codex/hooks .codex/tests",
        "pytest -q scripts/triage",
    )


@pytest.mark.parametrize("field", ["owner", "name", "default_branch"])
def test_missing_repository_identity_fails(field: str) -> None:
    data = _policy_data()
    repository = data["repository"]
    assert isinstance(repository, dict)
    repository.pop(field)

    with pytest.raises(repo_config.RepoConfigError, match=field):
        repo_config.policy_from_mapping(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("progress_log_path", "/tmp/progress.md"),
        ("progress_log_path", "../PROGRESS.md"),
    ],
)
def test_repository_paths_cannot_be_absolute_or_escape(key: str, value: str) -> None:
    data = _policy_data()
    repository = data["repository"]
    assert isinstance(repository, dict)
    repository[key] = value

    with pytest.raises(repo_config.RepoConfigError, match="relative|escape"):
        repo_config.policy_from_mapping(data)


def test_reference_roots_cannot_contain_absolute_paths() -> None:
    data = _policy_data()
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["reference_roots"].append("/outside")  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match="relative"):
        repo_config.policy_from_mapping(data)


def test_malformed_hook_event_mapping_fails() -> None:
    data = _policy_data()
    events = data["codex"]["hooks"]["events"]  # type: ignore[index]
    del events["Stop"]  # type: ignore[index]
    events["PostToolUse"] = {"script": "post.py"}  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError) as exc:
        repo_config.policy_from_mapping(data)

    message = str(exc.value)
    assert "PostToolUse is unsupported" in message
    assert "missing required event" in message


def test_invalid_official_docs_provider_domain_fails() -> None:
    data = _policy_data()
    provider = data["governance"]["official_docs"]["providers"][0]  # type: ignore[index]
    provider["official_domains"] = ["https://example.com/docs"]  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match="invalid domain"):
        repo_config.policy_from_mapping(data)


def test_invalid_official_docs_provider_regex_fails() -> None:
    data = _policy_data()
    provider = data["governance"]["official_docs"]["providers"][0]  # type: ignore[index]
    provider["trigger_patterns"] = ["["]  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match="invalid regex"):
        repo_config.policy_from_mapping(data)


@pytest.mark.parametrize(
    "bad_key",
    [
        "operations",
        "github_request_payload",
        "request_payloads",
        "body_update",
        "title_updates",
        "state_update",
        "label_updates",
        "milestone_update",
        "project_updates",
        "close_request",
        "reopen_requests",
        "merge_instructions",
    ],
)
def test_recursive_mutation_shaped_keys_fail(bad_key: str) -> None:
    data = _policy_data()
    data.setdefault("governance", {})
    data["governance"][bad_key] = []  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match="forbidden"):
        repo_config.policy_from_mapping(data)


@pytest.mark.parametrize(
    "operation_id",
    [
        "issue.body.update",
        "issue.title.update",
        "issue.close",
        "issue.reopen",
        "project.create",
        "project.update",
        "label.create",
        "label.delete",
        "milestone.create",
        "pr.merge",
    ],
)
def test_forbidden_operation_ids_fail_in_values(operation_id: str) -> None:
    data = _policy_data()
    worker_packet = data["worker_packet"]
    assert isinstance(worker_packet, dict)
    worker_packet["required_verification_commands"] = [operation_id]

    with pytest.raises(repo_config.RepoConfigError, match="forbidden operation id"):
        repo_config.policy_from_mapping(data)


@pytest.mark.parametrize(
    "flag",
    ["network_retrieval", "url_fetching", "browser_automation", "freshness_checks"],
)
def test_official_docs_live_retrieval_flags_are_unsupported(flag: str) -> None:
    data = _policy_data()
    official_docs = data["governance"]["official_docs"]  # type: ignore[index]
    official_docs[flag] = True  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match=f"{flag}=true"):
        repo_config.policy_from_mapping(data)


def test_official_docs_unknown_provider_policy_cannot_be_disabled() -> None:
    data = _policy_data()
    official_docs = data["governance"]["official_docs"]  # type: ignore[index]
    official_docs["unknown_provider_policy"] = "trust_any_url"  # type: ignore[index]

    with pytest.raises(repo_config.RepoConfigError, match="unknown_provider_policy"):
        repo_config.policy_from_mapping(data)


def test_official_docs_critical_unknown_blocker_requirement_cannot_be_disabled() -> None:
    data = _policy_data()
    official_docs = data["governance"]["official_docs"]  # type: ignore[index]
    official_docs["critical_unverified_requires_blocker"] = False  # type: ignore[index]

    with pytest.raises(
        repo_config.RepoConfigError, match="critical_unverified_requires_blocker"
    ):
        repo_config.policy_from_mapping(data)


def test_shell_exports_are_bounded_to_wrapper_values() -> None:
    policy = repo_config.load_repo_policy(DBT_POLICY)
    exports = repo_config.shell_exports(policy)

    assert exports["CODEX_POLICY_REPOSITORY_FULL_NAME"] == "dckallos/dbt-diagnostics"
    assert exports["CODEX_POLICY_VENV_DIR"] == ".venv"
    assert exports["CODEX_POLICY_PYTHON_COMPILE_ROOTS"].split() == [
        "dbt_diagnostics",
        "scripts",
        ".codex/scripts",
        ".codex/hooks",
        ".codex/tests",
    ]
    assert "CODEX_POLICY_PACKAGE_ROOTS" in exports
    assert "operations" not in "\n".join(exports)


def test_cli_and_compat_line_exports_are_deterministic() -> None:
    policy = repo_config.load_repo_policy(DBT_POLICY)

    assert repo_config.cli_command_lines(policy) == ("dbt-diagnostics --help",)
    assert repo_config.compat_record_lines(policy)[0] == (
        "manifest\tmanifest\tdbt_diagnostics/fixtures/schemas/manifest/v12.json\t"
        "4,5,6,7,8,9,10,11,12"
    )
