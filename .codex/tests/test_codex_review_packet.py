from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from scripts.triage import repo_config


ROOT = Path(__file__).resolve().parents[2]
WIDGETS_POLICY = ROOT / "scripts" / "triage" / "fixtures" / "widgets_policy.toml"


def _load_codex_script(name: str):
    path = ROOT / ".codex" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.test")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "checkout", "-b", "donkey-kong-sandbox")
    _write(tmp_path, "README.md", "base\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial")
    _git(tmp_path, "checkout", "-b", "feature")
    return tmp_path


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")
    return path


def _commit(root: Path, relative: str, text: str) -> Path:
    path = _write(root, relative, text)
    _git(root, "add", relative)
    _git(root, "commit", "-m", f"change {relative}")
    return path


def _receipt(
    review_packet,
    *,
    protected_paths: list[str] | None = None,
    semantic_paths: list[str] | None = None,
    passed: bool = True,
    digest_valid: bool = True,
) -> dict[str, Any]:
    quality = _load_codex_script("codex_quality")
    checks = [
        {
            "name": name,
            "status": "passed" if passed else "failed",
            "checked_files": [],
            "findings": [] if passed else [{"code": "failed"}],
        }
        for name in review_packet.REQUIRED_QUALITY_CHECKS
    ]
    value: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": "2026-06-29T00:00:00Z",
        "tool": "codex-quality",
        "passed": passed,
        "freshness_bound_protected_paths": protected_paths or [],
        "semantically_checked_protected_paths": semantic_paths or [],
        "checks": checks,
    }
    value["quality_receipt_digest"] = quality.receipt_digest(value)
    if not digest_valid:
        value["quality_receipt_digest"] = "0" * 64
    return value


def _write_receipt(root: Path, value: Mapping[str, Any]) -> Path:
    path = root / "output" / "codex" / "quality-receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return path


def _schema() -> Mapping[str, Any]:
    return json.loads(
        (ROOT / "docs" / "codex-review-packet-schema-v1.json").read_text(
            encoding="ascii"
        )
    )


def _schema_errors(packet: Mapping[str, Any]) -> list[str]:
    return sorted(error.message for error in Draft202012Validator(_schema()).iter_errors(packet))


def _resign(packet: dict[str, Any]) -> dict[str, Any]:
    review_packet = _load_codex_script("codex_review_packet")
    for _ in range(10):
        packet["budget"]["serialized_bytes"] = len(
            review_packet.canonical_json(packet).encode("utf-8")
        )
        packet["codex_review_packet_digest"] = review_packet.sha256_json(
            review_packet.codex_review_packet_without_digest(packet)
        )
    return packet


def _build_packet(root: Path, **kwargs: Any) -> dict[str, Any]:
    review_packet = _load_codex_script("codex_review_packet")
    return review_packet.build_codex_review_packet(
        issue=110,
        root=root,
        base_ref=kwargs.pop("base_ref", "donkey-kong-sandbox"),
        generated_at=kwargs.pop("generated_at", "2026-06-29T00:00:00Z"),
        repo_policy=kwargs.pop("repo_policy", repo_config.load_repo_policy()),
        **kwargs,
    )


def test_minimal_packet_validates_schema_digest_and_is_deterministic(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)

    first = _build_packet(repo, parent_epic=134)
    second = _build_packet(repo, parent_epic=134)

    assert first == second
    assert _schema_errors(first) == []
    assert review_packet.validate_codex_review_packet(first) == []
    assert first["codex_review_packet_digest"] == review_packet.sha256_json(
        review_packet.codex_review_packet_without_digest(first)
    )
    assert first["budget"]["serialized_bytes"] == len(
        review_packet.canonical_json(first).encode("utf-8")
    )


def test_cli_json_stdout_and_output_file_are_valid(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    script = ROOT / ".codex" / "scripts" / "codex_review_packet.py"

    json_result = subprocess.run(
        [sys.executable, str(script), "--issue", "110", "--json"],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    assert json_result.returncode == 0, json_result.stderr
    packet = json.loads(json_result.stdout)
    assert review_packet.validate_codex_review_packet(packet) == []

    output_path = repo / "output" / "packet.json"
    output_result = subprocess.run(
        [sys.executable, str(script), "--issue", "110", "--output", str(output_path)],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    assert output_result.returncode == 0, output_result.stderr
    saved = json.loads(output_path.read_text(encoding="ascii"))
    assert review_packet.validate_codex_review_packet(saved) == []
    assert saved["schema_version"] == 1


def test_valid_receipt_is_usable_evidence(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")
    _write_receipt(repo, _receipt(review_packet, protected_paths=[path]))

    packet = _build_packet(repo, parent_epic=134)

    assert packet["quality_receipt"]["present"] is True
    assert packet["quality_receipt"]["digest_valid"] is True
    assert packet["quality_receipt"]["passed"] is True
    assert packet["quality_receipt"]["usable_as_evidence"] is True
    assert packet["quality_receipt"]["missing_freshness_bound_protected_paths"] == []


def test_receipt_missing_malformed_digest_invalid_failed_noncovering_and_stale(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")

    missing = _build_packet(repo, parent_epic=134)
    assert missing["quality_receipt"]["usable_as_evidence"] is False
    assert "missing-quality-receipt" in {
        item["code"] for item in missing["risk_findings"]
    }

    receipt_path = repo / "output" / "codex" / "quality-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text("{", encoding="ascii")
    malformed = _build_packet(repo, parent_epic=134)
    assert malformed["quality_receipt"]["usable_as_evidence"] is False
    assert "malformed-quality-receipt" in {
        item["code"] for item in malformed["risk_findings"]
    }

    _write_receipt(
        repo,
        _receipt(review_packet, protected_paths=[path], digest_valid=False),
    )
    invalid = _build_packet(repo, parent_epic=134)
    assert invalid["quality_receipt"]["digest_valid"] is False
    assert invalid["quality_receipt"]["usable_as_evidence"] is False

    _write_receipt(repo, _receipt(review_packet, protected_paths=[path], passed=False))
    failed = _build_packet(repo, parent_epic=134)
    assert failed["quality_receipt"]["passed"] is False
    assert failed["quality_receipt"]["usable_as_evidence"] is False

    _write_receipt(repo, _receipt(review_packet, protected_paths=[]))
    noncovering = _build_packet(repo, parent_epic=134)
    assert noncovering["quality_receipt"]["missing_freshness_bound_protected_paths"] == [
        path
    ]
    assert noncovering["quality_receipt"]["usable_as_evidence"] is False

    _write_receipt(repo, _receipt(review_packet, protected_paths=[path]))
    time.sleep(0.01)
    os.utime(repo / path)
    stale = _build_packet(repo, parent_epic=134)
    assert stale["quality_receipt"]["stale_protected_paths"] == [path]
    assert stale["quality_receipt"]["usable_as_evidence"] is False


def test_semantic_coverage_caveat_for_semantic_protected_paths(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".agents/skills/custom/SKILL.md"
    _commit(repo, path, "---\nname: custom\n---\n")
    _write_receipt(repo, _receipt(review_packet, protected_paths=[path]))

    packet = _build_packet(repo, parent_epic=134)

    assert packet["quality_receipt"]["missing_semantically_checked_protected_paths"] == [
        path
    ]
    assert packet["quality_receipt"]["usable_as_evidence"] is False
    assert "semantic-coverage-caveat" in {
        item["code"] for item in packet["risk_findings"]
    }


def test_policy_derived_protected_surface_classification_supports_custom_policy(
    tmp_path: Path,
) -> None:
    data = repo_config.load_policy_mapping(WIDGETS_POLICY)
    data["governance"]["paths"]["protected_surfaces"] = ["custom/**"]  # type: ignore[index]
    data["governance"]["paths"]["semantic_scan_roots"] = ["custom"]  # type: ignore[index]
    policy = repo_config.policy_from_mapping(data)
    repo = _init_repo(tmp_path)
    _write(repo, "custom/tool.py", "# protected\n")

    packet = _build_packet(
        repo,
        parent_epic=134,
        explicit_paths=["custom/tool.py"],
        repo_policy=policy,
    )

    changed = packet["changed_files"][0]
    assert changed["path"] == "custom/tool.py"
    assert changed["protected"] is True
    assert changed["matched_protected_patterns"] == ["custom/**"]
    assert packet["protected_surfaces"][0]["matched_protected_patterns"] == [
        "custom/**"
    ]


def test_worktree_and_branch_base_evidence_are_reported_separately(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    branch_path = ".codex/scripts/branch.py"
    worktree_path = ".codex/bin/local.sh"
    _commit(repo, branch_path, "print('branch')\n")
    _write(repo, worktree_path, "#!/usr/bin/env bash\n")

    packet = _build_packet(repo, parent_epic=134)

    assert packet["evidence_sources"]["worktree_status"]["available"] is True
    assert packet["evidence_sources"]["branch_base_diff"]["available"] is True
    by_path = {item["path"]: item for item in packet["changed_files"]}
    assert by_path[branch_path]["change_sources"] == ["branch_base_diff"]
    assert by_path[worktree_path]["change_sources"] == ["worktree_status"]


def test_diff_snippet_combines_branch_base_and_worktree_sources(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/both.py"
    _commit(repo, path, "value = 'branch'\n")
    _write(repo, path, "value = 'worktree'\n")

    packet = _build_packet(repo, parent_epic=134)

    changed = {item["path"]: item for item in packet["changed_files"]}[path]
    snippet = {item["path"]: item for item in packet["diff_snippets"]}[path]
    assert changed["change_sources"] == ["branch_base_diff", "worktree_status"]
    assert "git diff donkey-kong-sandbox...HEAD" in snippet["source"]
    assert "git diff --" in snippet["source"]
    assert "branch" in snippet["content"]
    assert "worktree" in snippet["content"]


def test_clean_worktree_does_not_hide_branch_base_changes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    branch_path = ".codex/scripts/branch.py"
    _commit(repo, branch_path, "print('branch')\n")

    packet = _build_packet(repo, parent_epic=134)

    assert packet["evidence_sources"]["worktree_status"]["changed_paths"] == []
    assert packet["evidence_sources"]["branch_base_diff"]["changed_paths"] == [
        branch_path
    ]
    assert packet["changed_files"][0]["change_sources"] == ["branch_base_diff"]


def test_missing_branch_base_diff_records_omission_and_finding(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    packet = _build_packet(repo, parent_epic=134, base_ref="missing-base-ref")

    assert packet["evidence_sources"]["branch_base_diff"]["available"] is False
    assert "branch-base-diff-unavailable" in {
        item["code"] for item in packet["omissions"]
    }


def test_diff_snippet_budget_truncates_and_validator_recomputes_size(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/large.py"
    _commit(repo, path, "x = '" + ("a" * 400) + "'\n")

    packet = _build_packet(repo, parent_epic=134, snippet_bytes=80)

    snippet = packet["diff_snippets"][0]
    assert snippet["path"] == path
    assert snippet["truncated"] is True
    assert snippet["serialized_bytes"] <= 80
    assert "diff-snippet-truncated" in {item["code"] for item in packet["omissions"]}

    lied = deepcopy(packet)
    lied["budget"]["serialized_bytes"] = 1
    lied["codex_review_packet_digest"] = review_packet.sha256_json(
        review_packet.codex_review_packet_without_digest(lied)
    )
    assert "budget.serialized_bytes does not match canonical packet size" in (
        review_packet.validate_codex_review_packet(lied)
    )

    too_large = _resign(deepcopy(packet))
    too_large["budget"]["hard_bytes"] = 1
    too_large = _resign(too_large)
    assert "packet exceeds budget.hard_bytes" in (
        review_packet.validate_codex_review_packet(too_large)
    )


def test_secret_shaped_text_is_redacted_and_raw_secret_fails_validation(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/secret.py"
    raw_secret = "ghp_1234567890abcdefghijklmnopqrst"
    _commit(repo, path, f"TOKEN = '{raw_secret}'\n")

    packet = _build_packet(repo, parent_epic=134)
    serialized = review_packet.canonical_json(packet)

    assert raw_secret not in serialized
    assert review_packet.REDACTED_SECRET in serialized
    assert "secret-redacted" in {item["code"] for item in packet["risk_findings"]}

    unsafe = deepcopy(packet)
    unsafe["diff_snippets"][0]["content"] = raw_secret
    unsafe = _resign(unsafe)
    assert any(
        "unredacted secret-shaped text" in error
        for error in review_packet.validate_codex_review_packet(unsafe)
    )


def test_forbidden_shapes_and_mutation_commands_are_rejected(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    packet = _build_packet(_init_repo(tmp_path), parent_epic=134)

    variants = [
        {"operations": []},
        {"risk_findings": [{"github_request_payload": {"method": "PATCH"}}]},
        {"risk_findings": [{"issue_comments": ["unsafe"]}]},
        {"risk_findings": [{"issues": [], "pulls": []}]},
        {"risk_findings": [{"body": "new issue body"}]},
        {"risk_findings": [{"title_update": "new title"}]},
        {"risk_findings": [{"state": "closed"}]},
        {"risk_findings": [{"workflow_dispatch": "ci.yml"}]},
        {"risk_findings": [{"pr_merge": True}]},
    ]
    for mutation in variants:
        unsafe = deepcopy(packet)
        unsafe.update(mutation)
        unsafe = _resign(unsafe)
        assert review_packet.validate_codex_review_packet(unsafe)

    command_packet = deepcopy(packet)
    command_packet["commands"] = [
        {
            "command": "python scripts/triage/triage.py apply --execute",
            "untrusted": True,
        }
    ]
    command_packet = _resign(command_packet)
    assert any(
        "command string is mutation-shaped" in error
        for error in review_packet.validate_codex_review_packet(command_packet)
    )


def test_safety_flags_are_required_exactly(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    packet = _build_packet(_init_repo(tmp_path), parent_epic=134)

    unsafe = deepcopy(packet)
    unsafe["safety"]["github_api_calls"] = True
    unsafe = _resign(unsafe)

    assert "safety.github_api_calls must be False" in (
        review_packet.validate_codex_review_packet(unsafe)
    )
