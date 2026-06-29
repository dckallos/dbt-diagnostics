from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / ".codex" / "agent-regression-cases-v1.json"
FIXTURE_ROOT = ROOT / ".codex" / "agent-regression" / "fixtures"


def _load_codex_script(name: str):
    path = ROOT / ".codex" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _base_case(fixture_path: str) -> dict[str, object]:
    return {
        "case_id": "governance-boundary-must-close-issue",
        "risk_class": "read_only_write_boundary",
        "fixture_files": [fixture_path],
        "expected_checker": "governance-boundary",
        "expected_status": "failed",
        "expected_finding_code": "authorized-tracker-mutation",
        "repair_guidance": "Keep read-only guidance from authorizing mutation.",
    }


def _write_manifest(root: Path, cases: list[dict[str, object]], **extra: object) -> Path:
    manifest = root / ".codex" / "agent-regression-cases-v1.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"schema_version": 1, "cases": cases}
    payload.update(extra)
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return manifest


def _write_fixture(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def _case_results_by_id(result) -> dict[str, object]:
    return {case.case_id: case for case in result.case_results}


def test_agent_regression_manifest_self_validation_passes() -> None:
    checker = _load_codex_script("check_agent_regression")

    result = checker.run_check(root=ROOT)
    payload = result.to_json()

    assert payload["name"] == "agent-regression"
    assert payload["status"] == "passed"
    assert result.passed is True
    assert len(result.case_results) == 30
    assert ".codex/agent-regression-cases-v1.json" in result.checked_files
    assert all(case.matched for case in result.case_results)


def test_agent_regression_committed_suite_covers_required_checker_groups() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="ascii"))
    cases = data["cases"]
    assert isinstance(cases, list)

    groups = {
        case["expected_checker"]
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("expected_checker"), str)
    }

    assert groups >= {
        "governance-boundary",
        "shared-command-classifier",
        "artifact-contracts",
        "synthesis-review-packet-validator",
        "backlog-review-validate",
        "hook-policy",
        "codex-quality-receipt",
        "limitation-record",
    }


def test_agent_regression_committed_cases_have_required_shape() -> None:
    data = json.loads(CASES_PATH.read_text(encoding="ascii"))
    cases = data["cases"]
    assert isinstance(cases, list)
    seen: set[str] = set()

    for case in cases:
        assert isinstance(case, dict)
        case_id = case["case_id"]
        assert isinstance(case_id, str)
        assert case_id not in seen
        seen.add(case_id)
        assert isinstance(case["risk_class"], str)
        assert isinstance(case["fixture_files"], list)
        assert case["fixture_files"]
        assert isinstance(case["expected_checker"], str)
        assert case["expected_status"] in {"failed", "passed", "warning", "omission"}
        if case["expected_status"] == "warning":
            assert isinstance(case["expected_warning_code"], str)
        elif case["expected_status"] == "omission":
            assert isinstance(case["expected_omission_code"], str)
        else:
            assert isinstance(case["expected_finding_code"], str)
        assert case.get("repair_guidance") or case.get("expectation_rationale")
        for fixture in case["fixture_files"]:
            assert isinstance(fixture, str)
            assert fixture.startswith(".codex/agent-regression/fixtures/")
            assert (ROOT / fixture).is_file()


def test_agent_regression_output_is_deterministic() -> None:
    checker = _load_codex_script("check_agent_regression")

    first = checker.run_check(root=ROOT).to_json()
    second = checker.run_check(root=ROOT).to_json()

    assert first == second


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda payload: payload.pop("schema_version"),
            "manifest-schema-version",
        ),
        (
            lambda payload: payload["cases"].append(dict(payload["cases"][0])),
            "manifest-duplicate-case",
        ),
        (
            lambda payload: payload["cases"][0].__setitem__(
                "expected_checker", "unknown-checker"
            ),
            "manifest-expected-checker",
        ),
        (
            lambda payload: payload["cases"][0].__setitem__(
                "expected_status", "unknown-status"
            ),
            "manifest-expected-status",
        ),
        (
            lambda payload: payload["cases"][0].pop("expected_finding_code"),
            "manifest-expected-code",
        ),
    ],
)
def test_agent_regression_rejects_malformed_manifest_fields(
    tmp_path: Path, mutate, expected_code: str
) -> None:
    checker = _load_codex_script("check_agent_regression")
    fixture = (
        ".codex/agent-regression/fixtures/governance-boundary-must-close-issue/"
        ".agents/skills/bad/SKILL.md"
    )
    _write_fixture(
        tmp_path,
        fixture,
        "This read-only skill must close GitHub issues after review.\n",
    )
    payload = {"schema_version": 1, "cases": [_base_case(fixture)]}
    mutate(payload)
    manifest = tmp_path / ".codex" / "agent-regression-cases-v1.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )

    result = checker.run_check(root=tmp_path, cases_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {expected_code}


def test_agent_regression_rejects_missing_fixture_file(tmp_path: Path) -> None:
    checker = _load_codex_script("check_agent_regression")
    fixture = (
        ".codex/agent-regression/fixtures/governance-boundary-must-close-issue/"
        ".agents/skills/bad/SKILL.md"
    )
    manifest = _write_manifest(tmp_path, [_base_case(fixture)])

    result = checker.run_check(root=tmp_path, cases_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {"fixture-missing"}


def test_agent_regression_rejects_non_ascii_fixture_file(tmp_path: Path) -> None:
    checker = _load_codex_script("check_agent_regression")
    fixture = (
        ".codex/agent-regression/fixtures/governance-boundary-must-close-issue/"
        ".agents/skills/bad/SKILL.md"
    )
    path = tmp_path / fixture
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("This fixture contains cafe accent: caf\u00e9\n", encoding="utf-8")
    manifest = _write_manifest(tmp_path, [_base_case(fixture)])

    result = checker.run_check(root=tmp_path, cases_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {"fixture-non-ascii"}


def test_agent_regression_rejects_fixture_outside_fixture_root(tmp_path: Path) -> None:
    checker = _load_codex_script("check_agent_regression")
    fixture = "AGENTS.md"
    _write_fixture(tmp_path, fixture, "This read-only skill must close GitHub issues.\n")
    manifest = _write_manifest(tmp_path, [_base_case(fixture)])

    result = checker.run_check(root=tmp_path, cases_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {
        "fixture-path-outside-root"
    }


def test_agent_regression_reports_case_mismatch_when_expected_failure_disappears(
    tmp_path: Path,
) -> None:
    checker = _load_codex_script("check_agent_regression")
    fixture = (
        ".codex/agent-regression/fixtures/governance-boundary-must-close-issue/"
        ".agents/skills/bad/SKILL.md"
    )
    _write_fixture(tmp_path, fixture, "Do not close GitHub issues.\n")
    manifest = _write_manifest(tmp_path, [_base_case(fixture)])

    result = checker.run_check(root=tmp_path, cases_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {"case-mismatch"}
    case = result.case_results[0]
    assert case.observed_status == "passed"
    assert case.observed_codes == ()


def test_agent_regression_records_warning_and_hard_stale_expectations() -> None:
    checker = _load_codex_script("check_agent_regression")
    result = checker.run_check(root=ROOT)
    by_id = _case_results_by_id(result)

    warning = by_id["packet-validator-warning-only-reviewable"]
    assert warning.observed_status == "warning"
    assert warning.observed_codes == ("packet_freshness_warning",)

    hard_stale = by_id["packet-validator-stale-reviewable-lie"]
    assert hard_stale.observed_status == "failed"
    assert "packet_hard_stale" in hard_stale.observed_codes


def test_agent_regression_records_fabricated_refs_as_integrated_failures() -> None:
    checker = _load_codex_script("check_agent_regression")
    result = checker.run_check(root=ROOT)
    by_id = _case_results_by_id(result)

    for case_id in (
        "backlog-review-fabricated-evidence-ref",
        "backlog-review-fabricated-near-miss-ref",
        "backlog-review-fabricated-omission-ref",
    ):
        case = by_id[case_id]
        assert case.observed_status == "failed"
        assert case.observed_codes == ("unknown_packet_reference",)


def test_agent_regression_fixture_root_contains_only_ascii_files() -> None:
    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_file():
            path.read_text(encoding="ascii")
