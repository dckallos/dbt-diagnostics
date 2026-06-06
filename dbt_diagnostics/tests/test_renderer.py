"""
Tests for the renderer and verbose/default output modes.
"""

from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
    UpstreamOrigin,
    EnrichmentData,
)
from dbt_diagnostics.renderer import render_text


def _make_contract_report():
    """Build a contract_violation report with full detail for template testing."""
    return DiagnosticReport(
        unique_id="model.artwork_pipeline.dim_artists",
        error_class="contract_violation",
        raw_message="This model has an enforced contract that failed.",
        findings=[
            DiagnosticFinding(
                summary="Column _LOADED_AT: model produces TIMESTAMP_LTZ, contract expects TIMESTAMP_NTZ (data type mismatch)",
                location=TraceLocation(
                    file_path="models/marts/dim_artists.sql",
                    line_number=12,
                    cte_name="met_artists",
                    expression="CURRENT_TIMESTAMP()",
                ),
                upstream_origin=None,
                explanation=(
                    "CURRENT_TIMESTAMP() returns TIMESTAMP_LTZ by default in Snowflake. "
                    "The account parameter TIMESTAMP_TYPE_MAPPING controls this. "
                    "This column is INTRODUCED in this model (not inherited from upstream)."
                ),
                fix_suggestion="Cast explicitly: CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS _loaded_at",
                session_params_to_check=["TIMESTAMP_TYPE_MAPPING", "TIMEZONE"],
            ),
        ],
    )


def _make_runtime_report():
    """Build a runtime_error report with full detail."""
    return DiagnosticReport(
        unique_id="model.artwork_pipeline.stg_met__artworks",
        error_class="runtime_error",
        raw_message="Database Error\n  002003: Object does not exist",
        findings=[
            DiagnosticFinding(
                summary="Object not found: ARTWORK_DB.BRONZE.RAW_MET_OBJECTS",
                location=TraceLocation(
                    file_path="models/staging/met/stg_met__artworks.sql",
                ),
                upstream_origin=UpstreamOrigin(
                    model_id="source.artwork_pipeline.met.raw_met_objects",
                    file_path=None,
                ),
                explanation="Object ARTWORK_DB.BRONZE.RAW_MET_OBJECTS referenced in upstream source.",
                fix_suggestion="Run the DDL: CREATE TABLE ARTWORK_DB.BRONZE.RAW_MET_OBJECTS ...",
            ),
        ],
    )


class TestVerboseMode:
    """Tests that verbose=True shows full detail, and default omits it."""

    def test_default_shows_root_cause_and_fix(self):
        report = _make_contract_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "ROOT CAUSE" in output
        assert "FIX:" in output
        assert "CURRENT_TIMESTAMP()::TIMESTAMP_NTZ" in output

    def test_default_hides_origin_and_explanation(self):
        report = _make_contract_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "ORIGIN:" not in output
        assert "EXPLANATION:" not in output
        assert "SESSION PARAMETERS TO VERIFY:" not in output

    def test_verbose_shows_origin(self):
        report = _make_contract_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "ORIGIN:" in output
        assert "introduced in THIS model (dim_artists)" in output

    def test_verbose_shows_explanation(self):
        report = _make_contract_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "EXPLANATION:" in output
        assert "CURRENT_TIMESTAMP() returns TIMESTAMP_LTZ" in output

    def test_verbose_shows_session_params(self):
        report = _make_contract_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "SESSION PARAMETERS TO VERIFY:" in output
        assert "TIMESTAMP_TYPE_MAPPING" in output

    def test_runtime_default_shows_fix(self):
        report = _make_runtime_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "FIX:" in output
        assert "CREATE TABLE" in output

    def test_runtime_default_hides_explanation(self):
        report = _make_runtime_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "EXPLANATION:" not in output
        assert "UPSTREAM ORIGIN:" not in output

    def test_runtime_verbose_shows_upstream_origin(self):
        report = _make_runtime_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "UPSTREAM ORIGIN:" in output
        assert "source.artwork_pipeline.met.raw_met_objects" in output

    def test_runtime_verbose_shows_explanation(self):
        report = _make_runtime_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "EXPLANATION:" in output


class TestSkippedModelTruncation:
    """Tests that skipped models are shown with short names by default."""

    def test_default_shows_short_model_names(self):
        skipped = [
            "model.artwork_pipeline.dim_artworks",
            "model.artwork_pipeline.dim_artists",
        ]
        output = render_text(
            reports=[], total=5, errors=1, skipped=2,
            skipped_models=skipped, verbose=False,
        )
        assert "dim_artworks" in output
        assert "dim_artists" in output
        # Full unique_id should NOT appear
        assert "model.artwork_pipeline.dim_artworks" not in output

    def test_default_groups_tests(self):
        skipped = [
            "model.artwork_pipeline.dim_artworks",
            "test.artwork_pipeline.dbt_expectations_expect_table_row_count.abc123",
            "test.artwork_pipeline.not_null_dim_artworks_id.def456",
            "test.artwork_pipeline.unique_dim_artworks_id.ghi789",
        ]
        output = render_text(
            reports=[], total=10, errors=1, skipped=4,
            skipped_models=skipped, verbose=False,
        )
        assert "dim_artworks" in output
        assert "3 test(s) skipped (downstream)" in output
        # Test unique_ids should NOT appear in default mode
        assert "dbt_expectations_expect_table_row_count" not in output

    def test_verbose_shows_full_unique_ids(self):
        skipped = [
            "model.artwork_pipeline.dim_artworks",
            "test.artwork_pipeline.dbt_expectations_expect_table_row_count.abc123",
        ]
        output = render_text(
            reports=[], total=5, errors=1, skipped=2,
            skipped_models=skipped, verbose=True,
        )
        assert "model.artwork_pipeline.dim_artworks" in output
        assert "dbt_expectations_expect_table_row_count" in output


class TestSkippedModelTruncation:
    """Tests that skipped models show short names by default, full IDs in verbose."""

    def _skipped_list(self):
        return [
            "model.artwork_pipeline.dim_artworks",
            "model.artwork_pipeline.fct_exhibitions",
            "test.artwork_pipeline.dbt_expectations_expect_table_row_count_to_be_between_dim_artists_1000000__50.818205a8b7",
            "test.artwork_pipeline.not_null_dim_artworks_artwork_id.abc123",
            "test.artwork_pipeline.unique_dim_artworks_artwork_id.def456",
        ]

    def test_default_shows_short_model_names(self):
        report = DiagnosticReport(
            unique_id="model.artwork_pipeline.stg_met__artworks",
            error_class="runtime_error",
            raw_message="Database Error",
            findings=[DiagnosticFinding(summary="Object not found", location=TraceLocation(file_path="x.sql"))],
        )
        output = render_text(
            reports=[report], total=5, errors=1, skipped=4,
            skipped_models=self._skipped_list(), verbose=False,
        )
        assert "dim_artworks" in output
        assert "fct_exhibitions" in output
        # Full unique_id should NOT appear in default mode
        assert "model.artwork_pipeline.dim_artworks" not in output
        # Tests are grouped
        assert "3 test(s) skipped (downstream)" in output

    def test_verbose_shows_full_unique_ids(self):
        report = DiagnosticReport(
            unique_id="model.artwork_pipeline.stg_met__artworks",
            error_class="runtime_error",
            raw_message="Database Error",
            findings=[DiagnosticFinding(summary="Object not found", location=TraceLocation(file_path="x.sql"))],
        )
        output = render_text(
            reports=[report], total=5, errors=1, skipped=4,
            skipped_models=self._skipped_list(), verbose=True,
        )
        assert "model.artwork_pipeline.dim_artworks" in output
        assert "test.artwork_pipeline.dbt_expectations" in output


class TestDiagnosticVsContextualParams:
    """Tests that diagnostic params show in default mode, contextual only in verbose."""

    def _make_enriched_report(self):
        """Contract violation with enrichment data (4 params, 1 diagnostic)."""
        return DiagnosticReport(
            unique_id="model.artwork_pipeline.dim_artists",
            error_class="contract_violation",
            raw_message="This model has an enforced contract that failed.",
            findings=[
                DiagnosticFinding(
                    summary="Column _LOADED_AT: TIMESTAMP_LTZ vs TIMESTAMP_NTZ",
                    location=TraceLocation(
                        file_path="models/marts/dim_artists.sql",
                        expression="CURRENT_TIMESTAMP()",
                    ),
                    fix_suggestion="Cast explicitly: CURRENT_TIMESTAMP()::TIMESTAMP_NTZ",
                    session_params_to_check=[
                        "TIMESTAMP_TYPE_MAPPING",
                        "TIMESTAMP_INPUT_FORMAT",
                        "TIMESTAMP_OUTPUT_FORMAT",
                        "TIMEZONE",
                    ],
                    diagnostic_params=["TIMESTAMP_TYPE_MAPPING"],
                    enrichment=EnrichmentData(
                        actual_param_values={
                            "TIMESTAMP_TYPE_MAPPING": "TIMESTAMP_NTZ",
                            "TIMESTAMP_INPUT_FORMAT": "AUTO",
                            "TIMESTAMP_OUTPUT_FORMAT": "YYYY-MM-DD HH24:MI:SS.FF3 TZHTZM",
                            "TIMEZONE": "America/Los_Angeles",
                            "_TIMESTAMP_TYPE_MAPPING_LEVEL": "ACCOUNT",
                        }
                    ),
                ),
            ],
        )

    def test_default_shows_diagnostic_param_only(self):
        report = self._make_enriched_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "TIMESTAMP_TYPE_MAPPING = TIMESTAMP_NTZ" in output
        assert "TIMESTAMP_INPUT_FORMAT" not in output
        assert "TIMEZONE" not in output

    def test_verbose_shows_all_params(self):
        report = self._make_enriched_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        assert "TIMESTAMP_TYPE_MAPPING = TIMESTAMP_NTZ" in output
        assert "TIMESTAMP_INPUT_FORMAT = AUTO" in output
        assert "TIMEZONE = America/Los_Angeles" in output

    def test_default_shows_verified_header(self):
        report = self._make_enriched_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=False,
        )
        assert "VERIFIED (live):" in output

    def test_verbose_shows_session_context_section(self):
        report = self._make_enriched_report()
        output = render_text(
            reports=[report], total=1, errors=1, skipped=0,
            skipped_models=[], verbose=True,
        )
        # Verbose should show both VERIFIED and SESSION CONTEXT sections
        assert "VERIFIED (live):" in output
        assert "SESSION CONTEXT (live):" in output
