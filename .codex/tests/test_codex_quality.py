from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest

from scripts.triage import repo_config


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"
SYNTHETIC_AGENT_PATHS = [
    ".codex/agent-regression-cases-v1.json",
    ".codex/agent-regression/fixtures/synthetic-artifact-manifest-missing/rationale.md",
    ".codex/agent-regression/fixtures/synthetic-backlog-fabricated-evidence-ref/case.json",
    ".codex/agent-regression/fixtures/synthetic-governance-safe/SKILL.md",
    ".codex/agent-regression/fixtures/synthetic-hook-gh-issue-close/command.txt",
    ".codex/agent-regression/fixtures/synthetic-limitation/rationale.md",
    ".codex/agent-regression/fixtures/synthetic-shared-inert/command.txt",
    ".codex/agent-regression/fixtures/synthetic-synthesis-packet-serialized-bytes-lie/case.json",
]


def _load_codex_script(name: str):
    path = ROOT / ".codex" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_pending_artifact_contract_manifest(root: Path) -> None:
    source = json.loads(
        (ROOT / ".codex" / "artifact-contracts-v1.json").read_text(
            encoding="ascii"
        )
    )
    artifacts = source["artifacts"]
    assert isinstance(artifacts, list)
    pending = {
        "schema_version": 1,
        "artifacts": [
            {
                "artifact": item["artifact"],
                "status": "pending",
                "reason": "synthetic codex-quality fixture",
            }
            for item in artifacts
            if isinstance(item, dict)
        ],
    }
    manifest = root / ".codex" / "artifact-contracts-v1.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(pending, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    _write_minimal_agent_regression_manifest(root)


def _write_text(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def _write_json(root: Path, relative: str, payload: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def _write_minimal_agent_regression_manifest(root: Path) -> None:
    cases = [
        {
            "case_id": "synthetic-artifact-manifest-missing",
            "risk_class": "artifact_contract_drift",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-artifact-manifest-missing/rationale.md"
            ],
            "expected_checker": "artifact-contracts",
            "expected_status": "failed",
            "expected_finding_code": "manifest-missing",
            "repair_guidance": "Synthetic quality fixture.",
            "case_data": {
                "fixture_root": ".codex/agent-regression/fixtures/synthetic-artifact-manifest-missing",
                "manifest_path": ".codex/artifact-contracts-v1.json",
            },
        },
        {
            "case_id": "synthetic-backlog-fabricated-evidence-ref",
            "risk_class": "bounded_artifact_reference_integrity",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-backlog-fabricated-evidence-ref/case.json"
            ],
            "expected_checker": "backlog-review-validate",
            "expected_status": "failed",
            "expected_finding_code": "unknown_packet_reference",
            "repair_guidance": "Synthetic quality fixture.",
            "case_data": {"variant": "fabricated-evidence-ref"},
        },
        {
            "case_id": "synthetic-governance-safe",
            "risk_class": "read_only_write_boundary",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-governance-safe/SKILL.md"
            ],
            "expected_checker": "governance-boundary",
            "expected_status": "passed",
            "expected_finding_code": "no_findings",
            "repair_guidance": "Synthetic quality fixture.",
        },
        {
            "case_id": "synthetic-hook-gh-issue-close",
            "risk_class": "hook_mutation_blocking",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-hook-gh-issue-close/command.txt"
            ],
            "expected_checker": "hook-policy",
            "expected_status": "failed",
            "expected_finding_code": "hook_denied_github_mutation",
            "repair_guidance": "Synthetic quality fixture.",
        },
        {
            "case_id": "synthetic-limitation",
            "risk_class": "quality_receipt_limitation",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-limitation/rationale.md"
            ],
            "expected_checker": "limitation-record",
            "expected_status": "omission",
            "expected_omission_code": "synthetic_limitation",
            "expectation_rationale": "Synthetic quality fixture.",
            "case_data": {"omission_code": "synthetic_limitation"},
        },
        {
            "case_id": "synthetic-shared-inert",
            "risk_class": "shared_mutation_classifier",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-shared-inert/command.txt"
            ],
            "expected_checker": "shared-command-classifier",
            "expected_status": "passed",
            "expected_finding_code": "no_findings",
            "repair_guidance": "Synthetic quality fixture.",
        },
        {
            "case_id": "synthetic-synthesis-packet-serialized-bytes-lie",
            "risk_class": "bounded_packet_safety",
            "fixture_files": [
                ".codex/agent-regression/fixtures/synthetic-synthesis-packet-serialized-bytes-lie/case.json"
            ],
            "expected_checker": "synthesis-review-packet-validator",
            "expected_status": "failed",
            "expected_finding_code": "packet_serialized_bytes_mismatch",
            "repair_guidance": "Synthetic quality fixture.",
            "case_data": {"variant": "serialized-bytes-lie"},
        },
    ]
    agent_manifest = root / ".codex" / "agent-regression-cases-v1.json"
    agent_manifest.parent.mkdir(parents=True, exist_ok=True)
    agent_manifest.write_text(
        json.dumps(
            {"schema_version": 1, "cases": cases},
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n",
        encoding="ascii",
    )
    _write_text(
        root,
        ".codex/agent-regression/fixtures/synthetic-artifact-manifest-missing/rationale.md",
        "Synthetic missing artifact-contract manifest fixture.\n",
    )
    _write_json(
        root,
        ".codex/agent-regression/fixtures/synthetic-backlog-fabricated-evidence-ref/case.json",
        {"variant": "fabricated-evidence-ref"},
    )
    _write_text(
        root,
        ".codex/agent-regression/fixtures/synthetic-governance-safe/SKILL.md",
        "Do not close GitHub issues.\n",
    )
    _write_text(
        root,
        ".codex/agent-regression/fixtures/synthetic-hook-gh-issue-close/command.txt",
        "gh issue close 1\n",
    )
    _write_text(
        root,
        ".codex/agent-regression/fixtures/synthetic-limitation/rationale.md",
        "Synthetic limitation fixture.\n",
    )
    _write_text(
        root,
        ".codex/agent-regression/fixtures/synthetic-shared-inert/command.txt",
        "rg -n 'gh issue edit' docs\n",
    )
    _write_json(
        root,
        ".codex/agent-regression/fixtures/synthetic-synthesis-packet-serialized-bytes-lie/case.json",
        {"variant": "serialized-bytes-lie"},
    )


def _checks_by_name(receipt: dict[str, object]) -> dict[str, dict[str, object]]:
    checks = receipt["checks"]
    assert isinstance(checks, list)
    return {
        check["name"]: check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("name"), str)
    }


def test_codex_quality_wrapper_is_exposed() -> None:
    action = (ROOT / ".codex" / "bin" / "action.sh").read_text(encoding="utf-8")
    wrapper = (ROOT / ".codex" / "bin" / "codex-quality.sh").read_text(
        encoding="utf-8"
    )

    assert "codex-quality  Run repository-specific Codex semantic quality gates" in action
    assert "\n  codex-quality)" in action
    assert ".codex/scripts/codex_quality.py" in wrapper


def test_issue_work_skill_does_not_authorize_issue_body_mutation() -> None:
    skill = (ROOT / ".agents" / "skills" / "issue-work" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "only GitHub metadata mutation allowed" not in skill
    assert "live issue body is updated" not in skill
    assert "authorized writer flow" not in skill
    assert "maintainer updates the live issue" not in skill
    assert "changes outside issue-work" in skill
    assert "issue-work skill never" in skill


def test_agents_records_single_progress_log_entry_per_pr() -> None:
    agents = re.sub(
        r"\s+", " ", (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )

    assert "Maintain exactly one dated entry per PR" in agents
    assert "otherwise edit that PR entry in place" in agents
    assert "single cohesive entry" in agents


def test_agents_records_direct_operator_delegation_boundary() -> None:
    agents = re.sub(
        r"\s+", " ", (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )

    assert "one exact GitHub operator action" in agents
    assert "outside issue-governance/issue-work outputs" in agents
    assert "triage artifacts, plans, and allowlists" in agents


def test_issue_work_skill_requires_pr_auto_close_keyword() -> None:
    skill = (ROOT / ".agents" / "skills" / "issue-work" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Closes #<issue>" in skill
    assert "Refs #<issue>" in skill
    assert "closingIssuesReferences" in skill


def test_issue_governance_skill_routes_issue_updates_through_connector() -> None:
    skill = (
        ROOT / ".agents" / "skills" / "issue-governance" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "cannot use direct `gh` mutation commands" in skill
    assert "use the GitHub Connector" in skill
    assert "if the connector is unavailable" in skill


def test_governance_boundary_checker_rejects_authorized_issue_body_write() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = (
        "The issue-body update is the only GitHub metadata mutation allowed "
        "by this prerequisite."
    )

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "issue-body-write",
        "allowed-github-metadata-mutation",
    }


def test_governance_boundary_checker_rejects_mixed_safe_and_unsafe_prose() -> None:
    checker = _load_codex_script("check_governance_boundary")
    mixed = (
        "Never close issues from the read-only governance workflow. "
        "The issue-body update is the only GitHub metadata mutation allowed "
        "by this prerequisite."
    )

    violations = checker.scan_text(mixed, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "issue-body-write",
        "allowed-github-metadata-mutation",
    }


def test_governance_boundary_checker_rejects_read_only_authorization() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "This read-only skill may close GitHub issues."

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "authorized-tracker-mutation",
    }


@pytest.mark.parametrize(
    ("text", "expected_code"),
    [
        ("This read-only skill must set the issue milestone.", "authorized-tracker-mutation"),
        ("The agent is required to assign labels.", "authorized-tracker-mutation"),
        ("Set the Project item field from the skill.", "verb-first-tracker-mutation"),
        ("Assign the issue to the release milestone.", "verb-first-tracker-mutation"),
    ],
)
def test_governance_boundary_checker_rejects_required_set_assign_authorization(
    text: str, expected_code: str
) -> None:
    checker = _load_codex_script("check_governance_boundary")

    violations = checker.scan_text(text, path="fixture.md")

    assert {violation.code for violation in violations} >= {expected_code}


def test_governance_boundary_checker_rejects_mixed_same_sentence_safe_and_unsafe() -> None:
    checker = _load_codex_script("check_governance_boundary")
    mixed = "Do not close issues, but set the milestone from this skill."

    violations = checker.scan_text(mixed, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "verb-first-tracker-mutation"
    }


def test_governance_boundary_checker_allows_negated_read_only_sentence() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "This read-only skill must not close GitHub issues."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_allows_negated_project_mutation() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "The tool does not create a Project or mutate Project fields."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_allows_pr_auto_close_keyword() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = (
        "When creating a PR, make the PR body close this implemented issue with "
        "a GitHub auto-close keyword."
    )

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_rejects_forbidden_operation_allowlist() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "Allowed operations: issue.body.update"

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "forbidden-operation-id",
    }


def test_governance_boundary_checker_allows_forbidden_operation_id_docs() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = "The forbidden operation issue.body.update remains unsupported."

    assert checker.scan_text(safe, path="fixture.md") == []


def test_governance_boundary_checker_rejects_verb_first_tracker_mutation() -> None:
    checker = _load_codex_script("check_governance_boundary")
    bad = "Edit the GitHub issue body after approval."

    violations = checker.scan_text(bad, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "verb-first-tracker-mutation",
    }


def test_governance_boundary_checker_allows_forbidden_operation_docs() -> None:
    checker = _load_codex_script("check_governance_boundary")
    safe = (
        "Never create, edit, close, label, milestone, or move a GitHub item. "
        "Issue-body mutation remains forbidden."
    )

    assert checker.scan_text(safe, path="fixture.md") == []


@pytest.mark.parametrize(
    "text",
    [
        "Run gh issue edit 1 --body 'unsafe' after review.",
        "Run gh issue close 123 after review.",
        "Run gh pr merge 456.",
        "Run gh project item-edit --id PVTSSF_lADO.",
        "Run gh workflow run ci.yml.",
        "Set the repository secret with gh secret set TOKEN --body value.",
        "Set the variable with gh variable set FEATURE_FLAG --body true.",
        "Allowed command: python scripts/triage/triage.py apply --execute",
        "$ pytest -q && gh issue edit 1 --body-file proposed-body.md",
        "$ bash -lc 'gh issue close 1'",
        "$ env GH_REPO=example/widgets gh project item-edit --id item",
        "```bash\npython scripts/triage/triage.py apply --execute\n```",
    ],
)
def test_governance_boundary_checker_rejects_command_shaped_guidance(
    text: str,
) -> None:
    checker = _load_codex_script("check_governance_boundary")

    violations = checker.scan_text(text, path="fixture.md")

    assert {violation.code for violation in violations} >= {
        "forbidden-mutation-command"
    }


@pytest.mark.parametrize(
    "text",
    [
        "Do not close GitHub issues.",
        "gh issue close is forbidden.",
        "Unsupported operations: gh issue edit, gh pr merge, gh project item-edit.",
        "The maintainer applies changes manually outside read-only artifacts.",
        "Run rg -n 'gh issue edit' docs.",
        "Use apply --dry-run for read-only preflight.",
        (
            "triage.py apply --execute requires explicit maintainer approval "
            "and is not available from read-only skills."
        ),
        (
            "A real writer session is deliberately gated.\n\n"
            "```bash\npython scripts/triage/triage.py apply --execute\n```"
        ),
    ],
)
def test_governance_boundary_checker_allows_safe_command_documentation(
    text: str,
) -> None:
    checker = _load_codex_script("check_governance_boundary")

    assert checker.scan_text(text, path="fixture.md") == []


def test_governance_boundary_checker_uses_repo_config_for_operation_ids() -> None:
    checker = _load_codex_script("check_governance_boundary")

    assert set(checker.FORBIDDEN_OPERATION_IDS) == repo_config.FORBIDDEN_OPERATION_IDS


def test_governance_boundary_exposes_public_scan_eligibility_helper(
    tmp_path: Path,
) -> None:
    checker = _load_codex_script("check_governance_boundary")
    text_file = tmp_path / "config.toml"
    text_file.write_text("[tool]\n", encoding="ascii")
    python_file = tmp_path / "tool.py"
    python_file.write_text("# not a semantic text surface\n", encoding="ascii")

    assert checker.is_eligible_scan_path(text_file, tmp_path) is True
    assert checker.is_eligible_scan_path(python_file, tmp_path) is False


def test_governance_boundary_checker_rejects_toml_command_values() -> None:
    checker = _load_codex_script("check_governance_boundary")
    text = (
        "[hooks]\n"
        "command = \"gh issue edit 133 --body unsafe\"\n"
        "safe_command = \"rg -n 'gh issue edit' docs\"\n"
    )

    violations = checker.scan_text(text, path=".codex/config.toml")

    assert [(violation.line, violation.code) for violation in violations] == [
        (2, "forbidden-mutation-command")
    ]
    assert violations[0].excerpt.startswith("hooks.command = gh issue edit")


def test_governance_boundary_checker_rejects_toml_command_tables() -> None:
    checker = _load_codex_script("check_governance_boundary")
    text = (
        "[hooks]\n"
        "commands = [\n"
        "  { command = \"python scripts/triage/triage.py apply --execute\" },\n"
        "  { command = \"rg -n 'gh issue edit' docs\" },\n"
        "]\n"
        "[[tasks.commands]]\n"
        "command = \"gh pr merge 148\"\n"
    )

    violations = checker.scan_text(text, path=".codex/config.toml")

    assert [(violation.line, violation.code) for violation in violations] == [
        (3, "forbidden-mutation-command"),
        (7, "forbidden-mutation-command"),
    ]
    assert (
        "hooks.commands.command = python scripts/triage/triage.py apply --execute"
        in violations[0].excerpt
    )
    assert "tasks.commands.command = gh pr merge 148" in violations[1].excerpt


def test_governance_boundary_checker_allows_safe_toml_command_values() -> None:
    checker = _load_codex_script("check_governance_boundary")
    text = "[hooks]\ncommand = \"rg -n 'gh issue edit' docs\"\n"

    assert checker.scan_text(text, path=".codex/config.toml") == []


def test_default_governance_boundary_scan_includes_issue_contract() -> None:
    checker = _load_codex_script("check_governance_boundary")

    paths = {path.relative_to(ROOT).as_posix() for path in checker.default_paths(ROOT)}

    assert "docs/ISSUE_CONTRACT_V1.md" in paths
    assert ".codex/README.md" in paths


def test_governance_boundary_explicit_missing_path_fails_closed(tmp_path: Path) -> None:
    checker = _load_codex_script("check_governance_boundary")

    result = checker.run_check([Path("missing.md")], root=tmp_path)

    assert result.passed is False
    assert result.checked_files == ()
    assert [(violation.path, violation.line, violation.code) for violation in result.violations] == [
        ("missing.md", 0, "explicit-path-missing")
    ]


def test_governance_boundary_explicit_ineligible_path_fails_closed(
    tmp_path: Path,
) -> None:
    checker = _load_codex_script("check_governance_boundary")
    binary = tmp_path / "fixture.bin"
    binary.write_bytes(b"\x00\x01")

    result = checker.run_check([Path("fixture.bin")], root=tmp_path)

    assert result.passed is False
    assert result.checked_files == ()
    assert [(violation.path, violation.line, violation.code) for violation in result.violations] == [
        ("fixture.bin", 0, "explicit-path-ineligible")
    ]


def test_governance_boundary_explicit_empty_directory_fails_closed(
    tmp_path: Path,
) -> None:
    checker = _load_codex_script("check_governance_boundary")
    empty = tmp_path / "empty"
    empty.mkdir()

    result = checker.run_check([Path("empty")], root=tmp_path)

    assert result.passed is False
    assert result.checked_files == ()
    assert [(violation.path, violation.line, violation.code) for violation in result.violations] == [
        ("empty", 0, "explicit-path-empty")
    ]


def test_codex_quality_writes_receipt(tmp_path: Path) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    (tmp_path / ".agents" / "skills" / "issue-work").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text(
        "Never create, edit, close, label, milestone, or move a GitHub item.\n",
        encoding="ascii",
    )
    (tmp_path / ".agents" / "skills" / "issue-work" / "SKILL.md").write_text(
        "Issue-body mutation remains forbidden.\n",
        encoding="ascii",
    )

    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"
    receipt = quality.run_quality(root=tmp_path, receipt_path=receipt_path)

    assert receipt["passed"] is True
    assert receipt_path.is_file()
    saved = json.loads(receipt_path.read_text(encoding="ascii"))
    assert saved["schema_version"] == 1
    checks = _checks_by_name(saved)
    assert set(checks) == {
        "governance-boundary",
        "artifact-contracts",
        "agent-regression",
    }
    assert checks["governance-boundary"]["status"] == "passed"
    assert checks["artifact-contracts"]["status"] == "passed"
    assert checks["agent-regression"]["status"] == "passed"
    assert saved["semantically_checked_protected_paths"] == [
        ".agents/skills/issue-work/SKILL.md",
        *SYNTHETIC_AGENT_PATHS,
        ".codex/artifact-contracts-v1.json",
        "AGENTS.md",
    ]
    assert saved["freshness_bound_protected_paths"] == []
    assert saved["quality_receipt_digest"] == quality.receipt_digest(saved)


def test_codex_quality_missing_explicit_path_records_failed_receipt(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"

    receipt = quality.run_quality(
        root=tmp_path,
        receipt_path=receipt_path,
        paths=[Path("missing.md")],
    )

    assert receipt["passed"] is False
    check = _checks_by_name(receipt)["governance-boundary"]
    assert check["status"] == "failed"
    assert check["checked_files"] == []
    assert check["findings"][0]["code"] == "explicit-path-missing"


def test_codex_quality_nonprotected_ineligible_explicit_path_fails_closed(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    binary = tmp_path / "fixture.bin"
    binary.write_bytes(b"\x00\x01")

    receipt = quality.run_quality(root=tmp_path, paths=[Path("fixture.bin")])

    assert receipt["passed"] is False
    check = _checks_by_name(receipt)["governance-boundary"]
    assert check["status"] == "failed"
    assert check["checked_files"] == []
    assert check["findings"][0]["code"] == "explicit-path-ineligible"


def test_codex_quality_protected_symlink_outside_root_fails_closed(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    root = tmp_path / "repo"
    root.mkdir()
    _write_pending_artifact_contract_manifest(root)
    outside = tmp_path / "outside.py"
    outside.write_text("# outside\n", encoding="ascii")
    protected = root / ".codex" / "hooks" / "stop.py"
    protected.parent.mkdir(parents=True)
    protected.symlink_to(outside)

    receipt = quality.run_quality(root=root, paths=[Path(".codex/hooks/stop.py")])

    assert receipt["passed"] is False
    check = _checks_by_name(receipt)["governance-boundary"]
    assert check["status"] == "failed"
    assert check["checked_files"] == []
    assert check["findings"][0]["code"] == "explicit-path-outside-root"


def test_codex_quality_records_artifact_contract_failures_in_receipt(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    (tmp_path / "AGENTS.md").write_text(
        "Never create, edit, close, label, milestone, or move a GitHub item.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path)

    checks = _checks_by_name(receipt)
    assert receipt["passed"] is False
    assert checks["governance-boundary"]["status"] == "passed"
    assert checks["artifact-contracts"]["status"] == "failed"
    assert checks["agent-regression"]["status"] == "failed"
    assert checks["artifact-contracts"]["findings"][0]["code"] == "manifest-missing"


def test_codex_quality_digest_covers_artifact_contract_findings() -> None:
    quality = _load_codex_script("codex_quality")
    receipt = {
        "schema_version": 1,
        "generated_at": "2026-06-29T00:00:00Z",
        "tool": "codex-quality",
        "passed": False,
        "freshness_bound_protected_paths": [],
        "semantically_checked_protected_paths": [],
        "checks": [
            {
                "name": "artifact-contracts",
                "status": "failed",
                "checked_files": [],
                "findings": [{"code": "manifest-missing"}],
            }
        ],
    }
    changed = dict(receipt)
    changed["checks"] = [
        {
            "name": "artifact-contracts",
            "status": "failed",
            "checked_files": [],
            "findings": [{"code": "validator-import"}],
        }
    ]

    assert quality.receipt_digest(receipt) != quality.receipt_digest(changed)


def test_codex_quality_digest_covers_agent_regression_case_results() -> None:
    quality = _load_codex_script("codex_quality")
    receipt = {
        "schema_version": 1,
        "generated_at": "2026-06-29T00:00:00Z",
        "tool": "codex-quality",
        "passed": True,
        "freshness_bound_protected_paths": [],
        "semantically_checked_protected_paths": [],
        "checks": [
            {
                "name": "agent-regression",
                "status": "passed",
                "checked_files": [],
                "case_results": [{"case_id": "fixture", "matched": True}],
                "findings": [],
            }
        ],
    }
    changed = dict(receipt)
    changed["checks"] = [
        {
            "name": "agent-regression",
            "status": "failed",
            "checked_files": [],
            "case_results": [{"case_id": "fixture", "matched": False}],
            "findings": [{"code": "case-mismatch"}],
        }
    ]

    assert quality.receipt_digest(receipt) != quality.receipt_digest(changed)


def test_codex_quality_records_deterministic_freshness_bound_protected_paths(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    (tmp_path / ".codex" / "hooks").mkdir(parents=True)
    (tmp_path / ".codex" / "hooks" / "stop.py").write_text(
        "# stop hook\n", encoding="ascii"
    )
    (tmp_path / "README.md").write_text("unprotected\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"

    receipt = quality.run_quality(
        root=tmp_path,
        receipt_path=receipt_path,
        paths=[
            Path("README.md"),
            Path(".codex/hooks/stop.py"),
            Path("./.codex/hooks/stop.py"),
        ],
    )

    assert receipt["semantically_checked_protected_paths"] == [
        *SYNTHETIC_AGENT_PATHS,
        ".codex/artifact-contracts-v1.json",
    ]
    assert receipt["freshness_bound_protected_paths"] == [".codex/hooks/stop.py"]
    saved = json.loads(receipt_path.read_text(encoding="ascii"))
    assert saved["semantically_checked_protected_paths"] == [
        *SYNTHETIC_AGENT_PATHS,
        ".codex/artifact-contracts-v1.json",
    ]
    assert saved["freshness_bound_protected_paths"] == [".codex/hooks/stop.py"]
    assert saved["quality_receipt_digest"] == quality.receipt_digest(saved)


def test_codex_quality_freshness_binds_agent_regression_paths(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    fixture = tmp_path / ".codex" / "agent-regression" / "fixtures" / "case.md"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text("fixture\n", encoding="ascii")
    policy = repo_config.load_repo_policy()

    assert quality.freshness_bound_protected_paths(
        root=tmp_path,
        requested_paths=[
            Path(".codex/agent-regression-cases-v1.json"),
            Path(".codex/agent-regression/fixtures/case.md"),
        ],
        repo_policy=policy,
    ) == (
        ".codex/agent-regression-cases-v1.json",
        ".codex/agent-regression/fixtures/case.md",
    )

    receipt = quality.run_quality(
        root=tmp_path,
        paths=[
            Path(".codex/agent-regression/fixtures/case.md"),
        ],
    )

    assert receipt["passed"] is True
    assert receipt["freshness_bound_protected_paths"] == [
        ".codex/agent-regression/fixtures/case.md",
    ]


def test_codex_quality_uses_configured_receipt_and_protected_surfaces(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    data["codex"]["quality_receipt_path"] = "custom/receipt.json"  # type: ignore[index]
    data["governance"]["paths"]["protected_surfaces"] = ["custom/**"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    protected = tmp_path / "custom" / "tool.py"
    protected.parent.mkdir()
    protected.write_text("# protected\n", encoding="ascii")

    receipt = quality.run_quality(
        root=tmp_path,
        paths=[Path("custom/tool.py")],
        repo_policy=policy,
    )

    assert (tmp_path / "custom" / "receipt.json").is_file()
    assert receipt["freshness_bound_protected_paths"] == ["custom/tool.py"]


def test_codex_quality_default_scan_uses_policy_semantic_scan_roots(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    rules = tmp_path / "custom" / "governance" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        "This read-only tool must not close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is True
    checks = _checks_by_name(receipt)
    assert checks["governance-boundary"]["checked_files"] == [
        "custom/governance/rules.md"
    ]
    assert checks["artifact-contracts"]["status"] == "passed"
    assert checks["agent-regression"]["status"] == "passed"
    assert receipt["semantically_checked_protected_paths"] == [
        "custom/governance/rules.md"
    ]
    assert receipt["freshness_bound_protected_paths"] == []


def test_codex_quality_semantically_scans_configured_codex_agents_root(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["semantic_scan_roots"] = [".codex/agents"]  # type: ignore[index]
    paths["protected_surfaces"] = [".codex/agents/**"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    agent = tmp_path / ".codex" / "agents" / "codex-reviewer.toml"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        "developer_instructions = '''\n"
        "This read-only agent must not close GitHub issues.\n"
        "'''\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is True
    assert _checks_by_name(receipt)["governance-boundary"]["checked_files"] == [
        ".codex/agents/codex-reviewer.toml"
    ]
    assert receipt["semantically_checked_protected_paths"] == [
        ".codex/agents/codex-reviewer.toml"
    ]


def test_codex_quality_semantically_scans_configured_codex_config_file(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["semantic_scan_roots"] = [".codex/config.toml"]  # type: ignore[index]
    paths["protected_surfaces"] = [".codex/config.toml"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "[agents]\n"
        "max_depth = 1\n"
        "# This read-only config must not close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is True
    assert _checks_by_name(receipt)["governance-boundary"]["checked_files"] == [
        ".codex/config.toml"
    ]
    assert receipt["semantically_checked_protected_paths"] == [".codex/config.toml"]


def test_codex_quality_semantic_scan_catches_mutating_codex_config_text(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["semantic_scan_roots"] = [".codex/config.toml"]  # type: ignore[index]
    paths["protected_surfaces"] = [".codex/config.toml"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "[agents]\n"
        "max_depth = 1\n"
        "# This read-only config may close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is False
    check = _checks_by_name(receipt)["governance-boundary"]
    assert check["checked_files"] == [".codex/config.toml"]
    assert check["findings"]


def test_codex_quality_default_scan_reports_policy_semantic_violations(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    rules = tmp_path / "custom" / "governance" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        "This read-only tool may close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is False
    check = _checks_by_name(receipt)["governance-boundary"]
    assert check["status"] == "failed"
    assert check["checked_files"] == ["custom/governance/rules.md"]
    assert check["findings"]


def test_codex_quality_default_scan_includes_extensionless_semantic_root(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    paths = data["governance"]["paths"]  # type: ignore[index]
    paths["semantic_scan_roots"] = ["CODEOWNERS"]  # type: ignore[index]
    paths["protected_surfaces"] = ["CODEOWNERS"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    (tmp_path / "CODEOWNERS").write_text(
        "# This read-only tool must not close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(root=tmp_path, repo_policy=policy)

    assert receipt["passed"] is True
    assert _checks_by_name(receipt)["governance-boundary"]["checked_files"] == [
        "CODEOWNERS"
    ]
    assert receipt["semantically_checked_protected_paths"] == ["CODEOWNERS"]


def test_codex_quality_explicit_paths_override_policy_semantic_scan_roots(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    policy = repo_config.load_repo_policy(WIDGETS_POLICY)
    custom = tmp_path / "custom" / "governance" / "rules.md"
    custom.parent.mkdir(parents=True)
    custom.write_text(
        "This read-only tool may close GitHub issues.\n",
        encoding="ascii",
    )
    specific = tmp_path / "specific.md"
    specific.write_text(
        "This read-only tool must not close GitHub issues.\n",
        encoding="ascii",
    )

    receipt = quality.run_quality(
        root=tmp_path,
        paths=[Path("specific.md")],
        repo_policy=policy,
    )

    assert receipt["passed"] is True
    assert _checks_by_name(receipt)["governance-boundary"]["checked_files"] == [
        "specific.md"
    ]
    assert receipt["semantically_checked_protected_paths"] == []


def test_codex_quality_does_not_semantically_cover_unscanned_hook_files(
    tmp_path: Path,
) -> None:
    quality = _load_codex_script("codex_quality")
    _write_pending_artifact_contract_manifest(tmp_path)
    hooks_dir = tmp_path / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "stop.py").write_text("# stop hook\n", encoding="ascii")
    (hooks_dir / "run_hook.sh").write_text("#!/usr/bin/env bash\n", encoding="ascii")
    receipt_path = tmp_path / "output" / "codex" / "quality-receipt.json"

    receipt = quality.run_quality(
        root=tmp_path,
        receipt_path=receipt_path,
        paths=[
            Path(".codex/hooks/stop.py"),
            Path(".codex/hooks/run_hook.sh"),
        ],
    )

    checks = _checks_by_name(receipt)
    assert receipt["passed"] is True
    assert checks["governance-boundary"]["status"] == "passed"
    assert checks["governance-boundary"]["checked_files"] == []
    assert receipt["semantically_checked_protected_paths"] == [
        *SYNTHETIC_AGENT_PATHS,
        ".codex/artifact-contracts-v1.json",
    ]
    assert receipt["freshness_bound_protected_paths"] == [
        ".codex/hooks/run_hook.sh",
        ".codex/hooks/stop.py",
    ]
