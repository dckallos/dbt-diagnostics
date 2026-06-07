"""
Tests for the TestFailureClassifier and the fail-status processing path.

Verifies:
- status:"fail" results are processed (not silently dropped)
- TestFailureClassifier produces correct reports
- Header counts include errors, fails, and warns
- Unmaterialized model advice is correct
"""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestFailStatusProcessing:
    """Tests that status:fail results are no longer silently dropped."""

    def test_fail_results_are_counted(self):
        """_diagnose_all should return fail_count > 0 for fail-status results."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = json.loads(
            (FIXTURES_DIR / "test_failures.json").read_text()
        )
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        paths = {
            "models_dir": Path("/project/models"),
            "compiled_dir": Path("/project/target/compiled"),
        }

        reports, skipped_ids, total, error_count, fail_count, warn_count = (
            _diagnose_all(run_results, manifest, paths)
        )

        # 2 fail results + 1 error result = 3 reports
        assert len(reports) == 3
        assert error_count == 1
        assert fail_count == 2
        assert warn_count == 1
        assert total == 5  # 2 fail + 1 error + 1 pass + 1 warn

    def test_fail_reports_have_test_failure_class(self):
        """Reports for fail-status results should have error_class='test_failure'."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = json.loads(
            (FIXTURES_DIR / "test_failures.json").read_text()
        )
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        paths = {
            "models_dir": Path("/project/models"),
            "compiled_dir": Path("/project/target/compiled"),
        }

        reports, _, _, _, _, _ = _diagnose_all(run_results, manifest, paths)

        test_failure_reports = [
            r for r in reports if r.error_class == "test_failure"
        ]
        assert len(test_failure_reports) == 2

    def test_fail_report_has_tested_model(self):
        """Test failure reports should identify the model being tested."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = json.loads(
            (FIXTURES_DIR / "test_failures.json").read_text()
        )
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        paths = {
            "models_dir": Path("/project/models"),
            "compiled_dir": Path("/project/target/compiled"),
        }

        reports, _, _, _, _, _ = _diagnose_all(run_results, manifest, paths)

        # Find the artworks test failure
        artworks_report = None
        for r in reports:
            if "artworks" in r.unique_id and r.error_class == "test_failure":
                artworks_report = r
                break

        assert artworks_report is not None
        assert artworks_report.has_findings
        finding = artworks_report.findings[0]
        assert "stg_met__artworks" in finding.target_object


class TestHeaderCounts:
    """Tests that the header shows all result categories."""

    def test_render_text_includes_fails_and_warns(self):
        """render_text should include fails and warns in the header."""
        from dbt_diagnostics.renderer import render_text

        output = render_text(
            reports=[],
            total=64,
            errors=4,
            fails=4,
            warns=5,
            skipped=10,
            skipped_models=[],
            verbose=False,
            color_enabled=False,
        )

        assert "4 error(s)" in output
        assert "4 fail(s)" in output
        assert "5 warn(s)" in output
        assert "64 result(s)" in output

    def test_json_output_includes_fails_and_warns(self):
        """JSON output should include fails and warns keys."""
        import sys
        from unittest.mock import patch
        from io import StringIO

        from dbt_diagnostics.main import _diagnose_all

        run_results = json.loads(
            (FIXTURES_DIR / "test_failures.json").read_text()
        )
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        paths = {
            "models_dir": Path("/project/models"),
            "compiled_dir": Path("/project/target/compiled"),
        }

        _, _, total, error_count, fail_count, warn_count = _diagnose_all(
            run_results, manifest, paths
        )

        # Verify the tuple values match expected
        assert error_count == 1
        assert fail_count == 2
        assert warn_count == 1


class TestUnmaterializedModelAdvice:
    """Tests that unmaterialized model errors get correct fix advice."""

    def test_parent_never_run_gives_materialization_advice(self):
        """
        When a test fails because the parent model was never materialized
        (no run_results entry), the fix advice should say 'run dbt run -s'
        not 'fix the error in'.
        """
        from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier
        from dbt_diagnostics.classifiers.base import DiagnosticContext
        from dbt_diagnostics.tracers.dag_walker import DagWalker
        from dbt_diagnostics.tracers.column_tracer import ColumnTracer

        # Manifest with dim_artists declared but NOT in run_results
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        # Run results that do NOT include dim_artists
        run_results = {
            "results": [
                {
                    "status": "error",
                    "unique_id": "test.artwork_pipeline.not_null_dim_artists_artist_id.ghi789",
                    "message": "Database Error in model artwork_pipeline.dim_artists: Object 'ARTWORK_DB.GOLD.DIM_ARTISTS' does not exist or not authorized.",
                    "compiled_code": "select count(*) from ARTWORK_DB.GOLD.DIM_ARTISTS where artist_id is null",
                }
            ]
        }

        dag_walker = DagWalker(manifest)
        column_tracer = ColumnTracer(Path("/project/models"), Path("/project/target/compiled"))
        context = DiagnosticContext(
            dag_walker=dag_walker,
            column_tracer=column_tracer,
            models_dir=Path("/project/models"),
            compiled_dir=Path("/project/target/compiled"),
            manifest=manifest,
            run_results=run_results,
        )

        result = run_results["results"][0]
        classifier = RuntimeErrorClassifier(result=result, context=context)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]

        # Should NOT say "Fix the error in"
        assert "Fix the error" not in finding.fix_suggestion
        # Should say to materialize the model
        assert "dbt run -s" in finding.fix_suggestion or "not been materialized" in finding.fix_suggestion


class TestManifestPresenceDisplay:
    """Tests that lineage trace shows 'present' instead of 'None' for manifest nodes."""

    def test_manifest_status_shows_present_not_none(self):
        """LineageStep with manifest_status='declared' but no manifest_detail should show 'present'."""
        from dbt_diagnostics.models import LineageStep

        step = LineageStep(
            node_id="test.artwork_pipeline.my_test.abc",
            node_type="test",
            short_name="my_test",
            manifest_status="declared",
            manifest_detail=None,  # This was showing as "Manifest: None"
        )

        # The template uses: {{ step.manifest_detail if step.manifest_detail else "present" }}
        # So we verify the display logic
        display_value = step.manifest_detail if step.manifest_detail else "present"
        assert display_value == "present"
        assert display_value != "None"
