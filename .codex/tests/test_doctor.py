from __future__ import annotations

from conftest import ROOT, load_codex_script


doctor = load_codex_script("doctor")


def test_redact_remote_strips_embedded_credentials() -> None:
    value = "https://token@example.com/owner/repo.git"
    assert doctor._redact_remote(value) == "https://example.com/owner/repo.git"


def test_static_codex_configuration_has_no_failures() -> None:
    checks = doctor.collect_checks(ROOT, config_only=True)
    assert checks
    assert [check for check in checks if check.level == "FAIL"] == []


def test_environment_validation_rejects_missing_file(tmp_path) -> None:
    valid, detail = doctor._validate_environment(tmp_path)
    assert valid is False
    assert "cannot parse" in detail
