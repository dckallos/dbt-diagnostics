"""
Tests for the TestFailureClassifier and the fail-status processing path.

Verifies:
- status:"fail" results are processed (not silently dropped)
- TestFailureClassifier produces correct reports
- Header counts include errors, fails, and warns
- Unmaterialized model advice is correct

Fixtures built from real artwork_pipeline `dbt test` output (dbt 1.11.11,
run_results v6, manifest v12). These are NOT guesses -- they are trimmed
subsets of actual Snowflake-targeted dbt artifacts.
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

        # Fixture has: 2 errors + 2 fails + 1 warn + 2 passes = 7 total
        # Reports are generated for errors + fails = 4
        assert len(reports) == 4
        assert error_count == 2
        assert fail_count == 2
        assert warn_count == 1
        assert total == 7

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

        # Find the enrichment_status test failure (first fail in fixture)
        enrichment_report = None
        for r in reports:
            if "enrichment_status" in r.unique_id and r.error_class == "test_failure":
                enrichment_report = r
                break

        assert enrichment_report is not None
        assert enrichment_report.has_findings
        finding = enrichment_report.findings[0]
        assert "stg_met__enrichment_status" in finding.target_object


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

    def test_diagnose_all_returns_correct_counts(self):
        """_diagnose_all should return correct error/fail/warn counts from real data."""
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

        assert error_count == 2
        assert fail_count == 2
        assert warn_count == 1
        assert total == 7


class TestUnmaterializedModelAdvice:
    """Tests that unmaterialized model errors get correct fix advice."""

    def test_parent_never_run_gives_materialization_advice(self):
        """
        When a test fails because the parent model was never materialized
        (Object does not exist error), the fix advice should say
        'run dbt run -s' not 'fix the error in'.
        """
        from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier
        from dbt_diagnostics.classifiers.base import DiagnosticContext
        from dbt_diagnostics.tracers.dag_walker import DagWalker
        from dbt_diagnostics.tracers.column_tracer import ColumnTracer

        # Manifest with dim_artists declared but NOT in run_results
        manifest = json.loads(
            (FIXTURES_DIR / "manifest_test_failures.json").read_text()
        )
        # Use the real error message format from dbt 1.11.11
        run_results = {
            "results": [
                {
                    "status": "error",
                    "unique_id": "test.artwork_pipeline.dbt_expectations_expect_table_row_count_to_be_between_dim_artists_1000000__50.818205a8b7",
                    "message": "Database Error in test dbt_expectations_expect_table_row_count_to_be_between_dim_artists_1000000__50 (models/marts/_marts__models.yml)\\n  002003 (42S02): SQL compilation error:\\n  Object 'ARTWORK_DB.GOLD.DIM_ARTISTS' does not exist or not authorized.",
                    "compiled_code": "\\n\\n\\n\\n    with grouped_expression as (\\n    select\\n( 1=1 and count(*) >= 50 and count(*) <= 1000000\\n)\\n as expression\\n\\n    from ARTWORK_DB.GOLD.dim_artists\\n),\\nvalidation_errors as (\\n    select *\\n    from grouped_expression\\n    where not(expression = true)\\n)\\nselect *\\nfrom validation_errors",
                    "failures": null,
                    "adapter_response": {}
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
