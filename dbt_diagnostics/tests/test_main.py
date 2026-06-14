"""
CLI integration tests for dbt-diagnostics.
Tests argument parsing, subcommand dispatch, output formats, and exit codes.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestDemoCommand:
    """Tests for the demo subcommand."""

    def test_demo_produces_output(self, capsys, monkeypatch):
        """Demo subcommand should produce diagnostic output from bundled fixtures."""
        monkeypatch.setattr(sys, "argv", ["dbt-diagnostics", "demo"])
        from dbt_diagnostics.main import main

        main()
        captured = capsys.readouterr()
        assert len(captured.out) > 0
        # Should reference at least one model
        assert "model" in captured.out.lower() or "error" in captured.out.lower()

    def test_demo_verbose(self, capsys, monkeypatch):
        """Demo with --verbose should produce more detail."""
        monkeypatch.setattr(sys, "argv", ["dbt-diagnostics", "--verbose", "demo"])
        from dbt_diagnostics.main import main

        main()
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestDiagnoseCommand:
    """Tests for the diagnose subcommand with explicit artifact paths."""

    def test_diagnose_with_fixtures(self, capsys, monkeypatch, tmp_path):
        """Diagnose with explicit --run-results and --manifest should work offline."""
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0'\n")
        (tmp_path / "target").mkdir()

        rr_path = str(FIXTURES_DIR / "contract_type_mismatch.json")
        manifest_path = str(FIXTURES_DIR / "manifest_minimal.json")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--no-fail",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        from dbt_diagnostics.main import main

        main()
        captured = capsys.readouterr()
        assert "contract" in captured.out.lower() or "error" in captured.out.lower()

    def test_diagnose_json_output(self, capsys, monkeypatch, tmp_path):
        """--json flag should produce valid JSON with expected top-level keys."""
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0'\n")
        (tmp_path / "target").mkdir()

        rr_path = str(FIXTURES_DIR / "contract_type_mismatch.json")
        manifest_path = str(FIXTURES_DIR / "manifest_minimal.json")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--json",
                "--no-fail",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        from dbt_diagnostics.main import main

        main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Top-level schema keys
        assert data["schema_version"] == "1.1"
        assert "total_results" in data
        assert "errors" in data
        assert "reports" in data
        assert isinstance(data["reports"], list)
        # Additive in schema_version 1.1: root-cause groups are always present.
        assert "root_cause_groups" in data
        assert isinstance(data["root_cause_groups"], list)
        # Per-report stable keys
        report = data["reports"][0]
        assert "schema_version" in report
        assert "unique_id" in report
        assert "model_name" in report
        assert "error_class" in report
        assert "findings" in report
        # Per-finding stable keys
        finding = report["findings"][0]
        assert "summary" in finding
        assert "fix_suggestion" in finding

    def test_diagnose_verbose_adds_detail(self, capsys, monkeypatch, tmp_path):
        """--verbose should produce longer output than default."""
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0'\n")
        (tmp_path / "target").mkdir()

        rr_path = str(FIXTURES_DIR / "contract_type_mismatch.json")
        manifest_path = str(FIXTURES_DIR / "manifest_minimal.json")

        # Run without verbose
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--no-fail",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        from dbt_diagnostics.main import main

        main()
        default_out = capsys.readouterr().out

        # Run with verbose
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--verbose",
                "--no-fail",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        main()
        verbose_out = capsys.readouterr().out

        # Verbose output should be at least as long (usually longer)
        assert len(verbose_out) >= len(default_out)

    def test_diagnose_exits_1_when_errors_found(self, monkeypatch, tmp_path):
        """Without --no-fail, diagnose should exit 1 when errors are found."""
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0'\n")
        (tmp_path / "target").mkdir()

        rr_path = str(FIXTURES_DIR / "contract_type_mismatch.json")
        manifest_path = str(FIXTURES_DIR / "manifest_minimal.json")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        from dbt_diagnostics.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_no_fail_exits_0(self, monkeypatch, tmp_path, capsys):
        """--no-fail should exit 0 even when errors exist."""
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0'\n")
        (tmp_path / "target").mkdir()

        rr_path = str(FIXTURES_DIR / "contract_type_mismatch.json")
        manifest_path = str(FIXTURES_DIR / "manifest_minimal.json")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "dbt-diagnostics",
                "--no-fail",
                "--project-dir", str(tmp_path),
                "--run-results", rr_path,
                "--manifest", manifest_path,
            ],
        )
        from dbt_diagnostics.main import main

        # Should not raise SystemExit
        main()
        captured = capsys.readouterr()
        assert len(captured.out) > 0


class TestMissingProject:
    """Tests for error handling when project is not found."""

    def test_missing_project_exits_nonzero(self, monkeypatch, tmp_path):
        """When no dbt project is found, should exit with a clear error."""
        monkeypatch.setattr(sys, "argv", ["dbt-diagnostics"])
        monkeypatch.chdir(tmp_path)  # empty dir, no dbt_project.yml
        from dbt_diagnostics.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0

    def test_missing_run_results_exits_nonzero(self, monkeypatch, tmp_path):
        """When run_results.json doesn't exist, should exit with clear error."""
        # Create a minimal dbt_project.yml so project detection works
        (tmp_path / "dbt_project.yml").write_text("name: test\n")
        monkeypatch.setattr(
            sys,
            "argv",
            ["dbt-diagnostics", "--project-dir", str(tmp_path)],
        )
        from dbt_diagnostics.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0
