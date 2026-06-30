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
_OMIT = object()


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
    generated_at: object = "2026-06-29T00:00:00Z",
    check_statuses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    quality = _load_codex_script("codex_quality")
    checks = [
        {
            "name": name,
            "status": (
                check_statuses[name]
                if check_statuses is not None and name in check_statuses
                else "passed" if passed else "failed"
            ),
            "checked_files": [],
            "findings": (
                []
                if (
                    check_statuses[name]
                    if check_statuses is not None and name in check_statuses
                    else "passed" if passed else "failed"
                )
                == "passed"
                else [{"code": "failed"}]
            ),
        }
        for name in review_packet.REQUIRED_QUALITY_CHECKS
    ]
    value: dict[str, Any] = {
        "schema_version": 1,
        "tool": "codex-quality",
        "passed": passed,
        "freshness_bound_protected_paths": protected_paths or [],
        "semantically_checked_protected_paths": semantic_paths or [],
        "checks": checks,
    }
    if generated_at is not _OMIT:
        value["generated_at"] = generated_at
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


def test_cli_command_log_mutation_fails_closed_and_safe_log_works(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    script = ROOT / ".codex" / "scripts" / "codex_review_packet.py"
    unsafe_log = repo / "unsafe-command-log.json"
    safe_log = repo / "safe-command-log.json"
    unsafe_log.write_text(
        json.dumps(
            [
                {
                    "command": "python scripts/triage/triage.py apply --execute",
                    "returncode": 0,
                }
            ]
        ),
        encoding="ascii",
    )
    safe_log.write_text(
        json.dumps(
            [
                {
                    "command": "python scripts/triage/triage.py contract --issue 110",
                    "returncode": 0,
                    "stdout": "ok\n",
                }
            ]
        ),
        encoding="ascii",
    )

    unsafe_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--issue",
            "110",
            "--json",
            "--command-log",
            str(unsafe_log),
        ],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    assert unsafe_result.returncode == 1
    assert unsafe_result.stdout == ""
    assert "risk_findings contains error severity: mutation-command-rejected" in (
        unsafe_result.stderr
    )

    safe_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--issue",
            "110",
            "--json",
            "--command-log",
            str(safe_log),
        ],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )
    assert safe_result.returncode == 0, safe_result.stderr
    packet = json.loads(safe_result.stdout)
    assert review_packet.validate_codex_review_packet(packet) == []
    assert any(
        command["command"] == "python scripts/triage/triage.py contract --issue 110"
        and command["untrusted"] is True
        for command in packet["commands"]
    )


def test_command_log_redacts_all_string_fields(tmp_path: Path) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    raw_secret = "github_pat_" + ("A" * 40)
    command_log = repo / "command-log.json"
    command_log.write_text(
        json.dumps(
            [
                {
                    "command": "python scripts/triage/triage.py contract --issue 110",
                    "combined_output": f"captured {raw_secret}\n",
                    "metadata": {"note": f"nested {raw_secret}"},
                }
            ]
        ),
        encoding="ascii",
    )

    packet = _build_packet(repo, parent_epic=134, command_log=command_log)
    serialized = review_packet.canonical_json(packet)

    assert raw_secret not in serialized
    assert packet["commands"][-1]["combined_output"] == (
        f"captured {review_packet.REDACTED_SECRET}\n"
    )
    assert packet["commands"][-1]["metadata"]["note"] == (
        f"nested {review_packet.REDACTED_SECRET}"
    )
    assert review_packet.validate_codex_review_packet(packet) == []


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


def test_required_receipt_checks_must_pass_for_usable_evidence(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")
    _write_receipt(
        repo,
        _receipt(
            review_packet,
            protected_paths=[path],
            check_statuses={"governance-boundary": "failed"},
        ),
    )

    packet = _build_packet(repo, parent_epic=134)

    assert packet["quality_receipt"]["passed"] is True
    assert packet["quality_receipt"]["check_statuses"]["governance-boundary"] == "failed"
    assert packet["quality_receipt"]["usable_as_evidence"] is False
    assert "quality-receipt-required-check-failed" in {
        item["code"] for item in packet["risk_findings"]
    }

    forged = deepcopy(packet)
    forged["quality_receipt"]["usable_as_evidence"] = True
    forged = _resign(forged)
    assert any(
        "requires required checks to pass" in error
        for error in review_packet.validate_codex_review_packet(forged)
    )


def test_digest_valid_passed_receipt_missing_generated_at_is_not_usable(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")
    _write_receipt(
        repo,
        _receipt(review_packet, protected_paths=[path], generated_at=_OMIT),
    )

    packet = _build_packet(repo, parent_epic=134)

    assert packet["quality_receipt"]["digest_valid"] is True
    assert packet["quality_receipt"]["passed"] is True
    assert packet["quality_receipt"]["generated_at"] is None
    assert packet["quality_receipt"]["usable_as_evidence"] is False
    assert "missing-quality-receipt-generated-at" in {
        item["code"] for item in packet["risk_findings"]
    }


def test_digest_valid_passed_receipt_invalid_generated_at_is_not_usable(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")

    cases = [
        (None, "missing-quality-receipt-generated-at"),
        (123, "missing-quality-receipt-generated-at"),
        ("", "missing-quality-receipt-generated-at"),
        ("not-a-timestamp", "invalid-quality-receipt-generated-at"),
    ]
    for generated_at, expected_code in cases:
        _write_receipt(
            repo,
            _receipt(
                review_packet,
                protected_paths=[path],
                generated_at=generated_at,
            ),
        )
        packet = _build_packet(repo, parent_epic=134)

        assert packet["quality_receipt"]["digest_valid"] is True
        assert packet["quality_receipt"]["passed"] is True
        assert packet["quality_receipt"]["usable_as_evidence"] is False
        assert expected_code in {item["code"] for item in packet["risk_findings"]}


def test_forged_usable_receipt_with_invalid_generated_at_fails_validation(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")
    _write_receipt(repo, _receipt(review_packet, protected_paths=[path]))
    packet = _build_packet(repo, parent_epic=134)

    forged = deepcopy(packet)
    forged["quality_receipt"]["generated_at"] = "not-a-timestamp"
    forged["quality_receipt"]["usable_as_evidence"] = True
    forged = _resign(forged)

    assert "quality_receipt.usable_as_evidence requires valid generated_at" in (
        review_packet.validate_codex_review_packet(forged)
    )


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


def test_explicit_path_traversal_is_rejected_before_local_file_excerpt(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    outside = repo.parent / "outside-secret.txt"
    outside.write_text("leaked-file-body\n", encoding="ascii")

    packet = _build_packet(
        repo,
        parent_epic=134,
        explicit_paths=[".codex/scripts/../../../outside-secret.txt"],
    )
    serialized = review_packet.canonical_json(packet)

    assert "leaked-file-body" not in serialized
    assert packet["evidence_sources"]["explicit_paths"]["changed_paths"] == []
    assert "explicit-path-rejected" in {item["code"] for item in packet["omissions"]}
    assert review_packet.validate_codex_review_packet(packet) == []


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


def test_hard_budget_omissions_update_changed_file_flags_and_counts(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    first_path = ".codex/scripts/large_one.py"
    second_path = ".codex/scripts/large_two.py"
    _commit(repo, first_path, "x = '" + ("a" * 5000) + "'\n")
    _commit(repo, second_path, "x = '" + ("b" * 5000) + "'\n")
    baseline = _build_packet(repo, parent_epic=134, snippet_bytes=5000)
    hard_bytes = baseline["budget"]["serialized_bytes"] - 1000
    packet = _build_packet(
        repo,
        parent_epic=134,
        snippet_bytes=5000,
        target_bytes=hard_bytes,
        hard_bytes=hard_bytes,
    )

    omitted_paths = {
        item["path"]
        for item in packet["omissions"]
        if item["code"] == "diff-snippet-omitted-for-hard-budget"
    }
    snippets_by_path = {item["path"]: item for item in packet["diff_snippets"]}
    changed_by_path = {item["path"]: item for item in packet["changed_files"]}

    assert omitted_paths
    assert omitted_paths.isdisjoint(snippets_by_path)
    for path in omitted_paths:
        assert changed_by_path[path]["diff_snippet_included"] is False
        assert changed_by_path[path]["diff_snippet_omitted"] is True
        assert changed_by_path[path]["diff_snippet_truncated"] is False
    assert packet["budget"]["omitted_files_count"] == sum(
        1
        for item in packet["changed_files"]
        if item["diff_snippet_omitted"]
        and (item["protected"] or item["contract_surface"])
    )
    assert packet["budget"]["omitted_snippets_count"] == sum(
        1 for item in packet["omissions"] if "snippet" in item["code"]
    )
    assert review_packet.validate_codex_review_packet(packet) == []


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


def test_all_github_token_prefixes_are_redacted_and_rejected(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/github_tokens.py"
    tokens = [
        "ghp_" + ("a" * 24),
        "github_pat_" + ("b" * 40),
        "gho_" + ("c" * 24),
        "ghu_" + ("d" * 24),
        "ghs_" + ("e" * 24),
        "ghr_" + ("f" * 24),
        "ghs_APPID_JWT",
    ]
    _commit(repo, path, "\n".join(tokens) + "\n")

    packet = _build_packet(repo, parent_epic=134)
    serialized = review_packet.canonical_json(packet)

    for token in tokens:
        assert token not in serialized
    assert serialized.count(review_packet.REDACTED_SECRET) >= len(tokens)

    unsafe = deepcopy(packet)
    unsafe["diff_snippets"][0]["content"] = tokens[1]
    unsafe = _resign(unsafe)
    assert any(
        "unredacted secret-shaped text" in error
        for error in review_packet.validate_codex_review_packet(unsafe)
    )


def test_validator_recomputes_protected_classification_and_receipt_coverage(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/tool.py"
    _commit(repo, path, "print('review packet')\n")
    _write_receipt(repo, _receipt(review_packet, protected_paths=[path]))
    packet = _build_packet(repo, parent_epic=134)

    forged_classification = deepcopy(packet)
    changed = forged_classification["changed_files"][0]
    changed["protected"] = False
    changed["matched_protected_patterns"] = []
    changed["risk_classes"] = []
    changed["contract_surface"] = False
    changed["semantic_scan_applies"] = False
    forged_classification["protected_surfaces"] = []
    forged_classification = _resign(forged_classification)
    assert any(
        "protected classification mismatch" in error
        for error in review_packet.validate_codex_review_packet(forged_classification)
    )

    forged_coverage = deepcopy(packet)
    forged_coverage["quality_receipt"]["freshness_bound_protected_paths"] = []
    forged_coverage["quality_receipt"]["missing_freshness_bound_protected_paths"] = []
    forged_coverage["quality_receipt"]["usable_as_evidence"] = True
    forged_coverage = _resign(forged_coverage)
    assert any(
        "freshness coverage mismatch" in error
        for error in review_packet.validate_codex_review_packet(forged_coverage)
    )


def test_inert_forbidden_operation_text_is_allowed_in_evidence(
    tmp_path: Path,
) -> None:
    review_packet = _load_codex_script("codex_review_packet")
    repo = _init_repo(tmp_path)
    path = ".codex/scripts/inert.py"
    _commit(repo, path, "# documents inert issue.body.update text\n")
    command_log = repo / "command-log.json"
    command_log.write_text(
        json.dumps(
            [
                {
                    "command": "rg issue.close docs",
                    "stdout": "documentation mentions issue.close as forbidden text\n",
                }
            ]
        ),
        encoding="ascii",
    )

    packet = _build_packet(repo, parent_epic=134, command_log=command_log)

    assert review_packet.validate_codex_review_packet(packet) == []


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
        {"risk_findings": [{"issue.body.update": "unsafe"}]},
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
