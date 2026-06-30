from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from scripts.triage import frontier


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".codex" / "artifact-contracts-v1.json"


def _load_checker():
    path = ROOT / ".codex" / "scripts" / "check_artifact_contracts.py"
    spec = importlib.util.spec_from_file_location("check_artifact_contracts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_artifact_contracts"] = module
    spec.loader.exec_module(module)
    return module


def _manifest_data() -> dict[str, object]:
    return json.loads(MANIFEST.read_text(encoding="ascii"))


def _write_manifest(path: Path, data: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    return path


def _entries_by_artifact(checker) -> dict[str, object]:
    entries, findings = checker._load_manifest(ROOT, MANIFEST)
    assert findings == []
    return {entry.artifact: entry for entry in entries}


def test_manifest_self_validation_passes() -> None:
    checker = _load_checker()

    result = checker.run_check(root=ROOT)
    payload = result.to_json()

    assert payload["name"] == "artifact-contracts"
    assert payload["status"] == "passed"
    assert payload["findings"] == []
    assert ".codex/artifact-contracts-v1.json" in payload["checked_files"]
    assert "scripts/triage/frontier.py" in payload["checked_files"]

    data = _manifest_data()
    artifacts = data["artifacts"]
    assert isinstance(artifacts, list)
    active = {
        item["artifact"]
        for item in artifacts
        if isinstance(item, dict) and item.get("status") == "active"
    }
    pending = {
        item["artifact"]
        for item in artifacts
        if isinstance(item, dict) and item.get("status") == "pending"
    }
    assert active == {
        "project-plan",
        "backlog-synthesis",
        "synthesis-review-packet",
        "backlog-review-verdict",
        "codex-review-packet",
    }
    assert "codex-review-status" in pending
    for item in artifacts:
        assert isinstance(item, dict)
        if item["status"] in {"pending", "excluded"}:
            assert isinstance(item.get("reason"), str) and item["reason"]


def test_manifest_duplicate_artifact_names_fail(tmp_path: Path) -> None:
    checker = _load_checker()
    data = {
        "schema_version": 1,
        "artifacts": [
            {
                "artifact": artifact,
                "status": "pending",
                "reason": "synthetic coverage fixture",
            }
            for artifact in sorted(checker.KNOWN_SCHEMA_VERSION_ARTIFACTS)
        ],
    }
    data["artifacts"].append(  # type: ignore[index]
        {
            "artifact": "snapshot",
            "status": "pending",
            "reason": "duplicate fixture",
        }
    )
    manifest = _write_manifest(tmp_path / ".codex" / "artifact-contracts-v1.json", data)

    result = checker.run_check(root=tmp_path, manifest_path=manifest)

    assert result.passed is False
    assert {finding.code for finding in result.findings} >= {
        "manifest-duplicate-artifact"
    }


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (
            lambda data: _mutate_manifest_entry(
                data, "project-plan", "human_doc", "docs/MISSING.md"
            ),
            "human-doc-missing",
        ),
        (
            lambda data: _mutate_manifest_entry(
                data,
                "project-plan",
                "machine_schema",
                "docs/missing-schema.json",
            ),
            "machine-schema-missing",
        ),
        (
            lambda data: _mutate_manifest_entry(
                data,
                "project-plan",
                "validator",
                "scripts.triage.frontier:missing_validator",
            ),
            "validator-import",
        ),
    ],
)
def test_manifest_active_entry_path_and_validator_drift_fail(
    tmp_path: Path, mutator, expected_code: str
) -> None:
    checker = _load_checker()
    data = _manifest_data()
    mutator(data)
    manifest = _write_manifest(tmp_path / "manifest.json", data)

    result = checker.run_check(root=ROOT, manifest_path=manifest)

    assert result.passed is False
    assert expected_code in {finding.code for finding in result.findings}


def _mutate_manifest_entry(
    data: dict[str, object], artifact: str, key: str, value: object
) -> None:
    entries = data["artifacts"]
    assert isinstance(entries, list)
    for item in entries:
        assert isinstance(item, dict)
        if item.get("artifact") == artifact:
            item[key] = value
            return
    raise AssertionError(f"missing manifest artifact {artifact}")


def test_active_artifact_fixtures_validate_and_safety_tampering_fails() -> None:
    checker = _load_checker()

    for entry in _entries_by_artifact(checker).values():
        if entry.status != "active":
            continue
        assert entry.machine_schema is not None
        schema = json.loads((ROOT / entry.machine_schema).read_text(encoding="ascii"))
        fixture = checker._fixture_for(entry.artifact)

        assert checker._schema_validation_errors(schema, fixture) == []
        assert checker._validator_errors(entry, fixture) == []
        assert checker._validator_errors(
            entry, checker._tamper_digest(entry, fixture)
        )
        assert checker._validator_errors(entry, {**fixture, "operations": []})
        assert checker._validator_errors(
            entry, checker._unsafe_shape(entry, fixture)
        )


def test_required_fields_and_schema_invariants_match_manifest() -> None:
    checker = _load_checker()

    for entry in _entries_by_artifact(checker).values():
        if entry.status != "active":
            continue
        assert entry.machine_schema is not None
        schema = json.loads((ROOT / entry.machine_schema).read_text(encoding="ascii"))
        assert tuple(schema["required"]) == entry.required_fields
        assert schema["properties"]["schema_version"]["const"] == entry.schema_version

        fixture = checker._fixture_for(entry.artifact)
        missing = deepcopy(fixture)
        missing.pop(entry.required_fields[0])
        assert checker._schema_validation_errors(schema, missing)

        unsafe = deepcopy(fixture)
        unsafe["operations"] = []
        assert checker._schema_validation_errors(schema, unsafe)


def test_codex_review_packet_artifact_contract_imports_and_validates() -> None:
    checker = _load_checker()
    entry = _entries_by_artifact(checker)["codex-review-packet"]
    fixture = checker._fixture_for(entry.artifact)

    assert entry.validator == "codex_review_packet:validate_codex_review_packet"
    assert checker._validator_errors(entry, fixture) == []
    assert checker._validator_errors(entry, checker._tamper_digest(entry, fixture))
    assert checker._validator_errors(entry, checker._unsafe_shape(entry, fixture))


def test_synthesis_review_packet_freshness_semantics_are_enforced() -> None:
    checker = _load_checker()
    entry = _entries_by_artifact(checker)["synthesis-review-packet"]
    schema = json.loads((ROOT / entry.machine_schema).read_text(encoding="ascii"))
    packet = checker._fixture_for(entry.artifact)
    staleness_required = set(schema["properties"]["staleness"]["required"])

    assert {
        "source_generated_at",
        "evaluated_at",
        "source_age_hours",
        "warning_age_hours",
        "max_age_hours",
        "freshness_status",
        "freshness_warnings",
        "stale",
        "llm_review_allowed",
    }.issubset(staleness_required)
    assert checker._validator_errors(entry, packet) == []

    warning = checker._with_packet_staleness(
        packet, evaluated_at="2026-06-25T01:00:00Z"
    )
    assert warning["staleness"]["freshness_status"] == "warning"
    assert warning["staleness"]["stale"] is False
    assert warning["staleness"]["llm_review_allowed"] is True
    assert checker._validator_errors(entry, warning) == []

    stale = checker._with_packet_staleness(
        packet, evaluated_at="2026-07-02T01:00:01Z"
    )
    assert stale["staleness"]["stale"] is True
    assert checker._validator_errors(entry, stale)
    assert frontier.validate_synthesis_review_packet(
        stale, allow_stale_offline=True
    ) == []

    strict = checker._with_packet_staleness(
        packet, evaluated_at="2026-06-25T13:00:00Z", max_age_hours=24
    )
    assert strict["staleness"]["stale"] is True
    assert checker._validator_errors(entry, strict)

    with pytest.raises(frontier.TriageError, match="max_age_hours"):
        frontier.build_synthesis_review_packet_staleness(
            source_generated_at="2026-06-24T00:00:00Z",
            evaluated_at="2026-07-02T01:00:00Z",
            max_age_hours=240,
        )

    lied = deepcopy(packet)
    lied["budget"]["serialized_bytes"] = 1
    lied = checker._sign_packet_digest_only(lied)
    assert checker._validator_errors(entry, lied)

    age_lie = deepcopy(packet)
    age_lie["staleness"]["source_age_hours"] = 2.0
    age_lie = checker._finalize_packet(age_lie)
    assert checker._validator_errors(entry, age_lie)


def test_backlog_synthesis_diagnostic_ids_and_packet_preservation() -> None:
    checker = _load_checker()
    entry = _entries_by_artifact(checker)["backlog-synthesis"]

    assert checker._check_diagnostic_semantics(entry) == []

    snap = checker._snapshot(
        checker._issue(1, title="feat: deterministic backlog synthesis"),
        checker._issue(2, title="feat: deterministic backlog review"),
    )
    audit = checker._audit(checker._entry(1), checker._entry(2))
    report = frontier.build_backlog_synthesis_report(snap, audit)
    near_miss = report["near_misses"][0]["near_miss_id"]
    duplicate = deepcopy(report)
    duplicate["near_misses"].append(deepcopy(report["near_misses"][0]))
    duplicate["backlog_synthesis_digest"] = frontier.sha256_json(
        {
            key: value
            for key, value in duplicate.items()
            if key != "backlog_synthesis_digest"
        }
    )

    assert str(near_miss).startswith("near-miss-possible-duplicate-001-002-")
    assert checker._validator_errors(entry, duplicate)

    packet = frontier.build_synthesis_review_packet(
        snap, audit, report, evaluated_at="2026-06-24T01:00:00Z"
    )
    assert packet["near_misses"][0]["near_miss_id"] == near_miss
    assert "omission-no-issue-body-in-signals" in {
        item.get("omission_id")
        for item in packet["omissions"]
        if isinstance(item, dict)
    }


def test_backlog_review_verdict_refs_staleness_and_future_apply_are_enforced() -> None:
    checker = _load_checker()
    entry = _entries_by_artifact(checker)["backlog-review-verdict"]
    packet = checker._fixture_synthesis_review_packet()
    verdict = checker._verdict_for_packet(packet)

    assert checker._validator_errors(entry, verdict) == []
    assert checker._paired_validator_errors(entry, verdict, packet) == []

    for field, unknown in (
        ("evidence_refs", "missing-evidence"),
        ("near_miss_refs", "missing-near-miss"),
        ("omission_refs", "missing-omission"),
    ):
        bad = deepcopy(verdict)
        bad["verdicts"][0][field] = [unknown]
        bad = checker._sign_verdict(bad)
        assert checker._paired_validator_errors(entry, bad, packet)

    stale_packet = checker._with_packet_staleness(
        packet, evaluated_at="2026-07-02T01:00:01Z"
    )
    stale_verdict = checker._verdict_for_packet(stale_packet)
    assert checker._paired_validator_errors(entry, stale_verdict, stale_packet)

    unsafe = deepcopy(verdict)
    unsafe["future_apply_recommendations"] = [
        {
            "recommendation_id": "future-apply-001",
            "summary": "unsafe",
            "rationale": "unsafe",
            "advisory_only": True,
            "operation_id": "issue.body.update",
        }
    ]
    unsafe = checker._sign_verdict(unsafe)
    assert checker._validator_errors(entry, unsafe)


def test_inventory_requires_every_schema_versioned_artifact_to_have_status(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    data = _manifest_data()
    entries = data["artifacts"]
    assert isinstance(entries, list)
    data["artifacts"] = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("artifact") != "worker-packet"
    ]
    manifest = _write_manifest(tmp_path / "manifest.json", data)

    result = checker.run_check(root=ROOT, manifest_path=manifest)

    assert result.passed is False
    assert "inventory-artifact-missing" in {
        finding.code for finding in result.findings
    }
