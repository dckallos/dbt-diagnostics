"""
Tests for the granularity enhancements:
- Threshold parsing from compiled SQL
- Relation extraction from compiled SQL
- Query ID extraction from adapter_response
- Warn classification and name extraction
- Cross-result grouping
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from dbt_diagnostics.classifiers.test_failure import TestFailureClassifier
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.grouping import group_reports, _extract_schema_prefix
from dbt_diagnostics.models import DiagnosticReport, DiagnosticFinding, LineageStep


# -- Fixtures ---------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _make_context(manifest: dict = None) -> DiagnosticContext:
    """Build a minimal DiagnosticContext for testing."""
    from dbt_diagnostics.tracers.dag_walker import DagWalker
    from dbt_diagnostics.tracers.column_tracer import ColumnTracer

    manifest = manifest or {"nodes": {}}
    dag_walker = DagWalker(manifest)
    column_tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
    return DiagnosticContext(
        dag_walker=dag_walker,
        column_tracer=column_tracer,
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
        manifest=manifest,
    )


# -- Threshold parsing tests ------------------------------------------------

class TestThresholdParsing:
    """Test _extract_threshold against real compiled SQL patterns."""

    def test_standard_row_count_between(self):
        sql = """
        with grouped_expression as (
            select
                ( 1=1 and count(*) >= 100 and count(*) <= 1000000 ) as expression
            from ARTWORK_DB.SILVER.stg_met__artworks
        )
        """
        result = TestFailureClassifier._extract_threshold(sql)
        assert result == (100, 1000000)

    def test_small_threshold(self):
        sql = "( 1=1 and count(*) >= 50 and count(*) <= 500 ) as expression"
        result = TestFailureClassifier._extract_threshold(sql)
        assert result == (50, 500)

    def test_large_threshold(self):
        sql = "count(*) >= 100 and count(*) <= 5000000"
        result = TestFailureClassifier._extract_threshold(sql)
        assert result == (100, 5000000)

    def test_no_threshold_in_non_row_count_sql(self):
        sql = """
        select * from all_values
        where value_field not in ('primary', 'additional')
        """
        result = TestFailureClassifier._extract_threshold(sql)
        assert result is None

    def test_no_threshold_in_empty_sql(self):
        assert TestFailureClassifier._extract_threshold("") is None
        assert TestFailureClassifier._extract_threshold(None or "") is None


# -- Relation extraction tests ----------------------------------------------

class TestRelationExtraction:
    """Test _extract_relation against real compiled SQL patterns."""

    def test_three_part_name(self):
        sql = """
        from ARTWORK_DB.SILVER.stg_met__artworks
        """
        result = TestFailureClassifier._extract_relation(sql)
        assert result == "ARTWORK_DB.SILVER.stg_met__artworks"

    def test_case_insensitive(self):
        sql = "FROM ARTWORK_DB.GOLD.dim_artists"
        result = TestFailureClassifier._extract_relation(sql)
        assert result == "ARTWORK_DB.GOLD.dim_artists"

    def test_no_relation_in_cte_only(self):
        sql = """
        with cte as (select 1 as x)
        select * from cte where x > 0
        """
        # 'cte' is not three-part, so no match
        result = TestFailureClassifier._extract_relation(sql)
        assert result is None

    def test_first_match_wins(self):
        sql = """
        select * from ARTWORK_DB.SILVER.stg_met__artworks
        union all
        select * from ARTWORK_DB.SILVER.stg_met__artists
        """
        result = TestFailureClassifier._extract_relation(sql)
        assert result == "ARTWORK_DB.SILVER.stg_met__artworks"


# -- Query ID extraction tests ----------------------------------------------

class TestQueryIdExtraction:
    """Test _extract_query_id from adapter_response."""

    def test_extracts_query_id(self):
        result = {
            "unique_id": "test.pkg.some_test.abc123",
            "status": "fail",
            "message": "Got 1 result, configured to fail if != 0",
            "failures": 1,
            "adapter_response": {
                "_message": "SUCCESS 1",
                "code": "SUCCESS",
                "rows_affected": 1,
                "query_id": "01c4e509-0105-cf36-000e-8b8e00023e3a",
            },
            "compiled_code": "",
        }
        ctx = _make_context()
        classifier = TestFailureClassifier(result=result, context=ctx)
        assert classifier._extract_query_id() == "01c4e509-0105-cf36-000e-8b8e00023e3a"

    def test_none_when_empty_adapter_response(self):
        result = {
            "unique_id": "test.pkg.some_test.abc123",
            "status": "error",
            "message": "Database Error",
            "failures": None,
            "adapter_response": {},
            "compiled_code": "",
        }
        ctx = _make_context()
        classifier = TestFailureClassifier(result=result, context=ctx)
        assert classifier._extract_query_id() is None

    def test_none_when_no_adapter_response(self):
        result = {
            "unique_id": "test.pkg.some_test.abc123",
            "status": "fail",
            "message": "Got 1 result",
            "failures": 1,
            "compiled_code": "",
        }
        ctx = _make_context()
        classifier = TestFailureClassifier(result=result, context=ctx)
        assert classifier._extract_query_id() is None


# -- Warn classification tests ----------------------------------------------

class TestWarnClassification:
    """Test warn category classification and name extraction."""

    def test_project_evaluator_is_hygiene(self):
        from dbt_diagnostics.main import _classify_warn_category
        uid = "test.dbt_project_evaluator.is_empty_fct_missing_primary_key_tests_.abc123"
        assert _classify_warn_category(uid) == "project_hygiene"

    def test_user_test_is_data_quality(self):
        from dbt_diagnostics.main import _classify_warn_category
        uid = "test.artwork_pipeline.some_custom_warn_test.abc123"
        assert _classify_warn_category(uid) == "data_quality"

    def test_extract_warn_name_strips_prefix(self):
        from dbt_diagnostics.main import _extract_warn_name
        uid = "test.dbt_project_evaluator.is_empty_fct_missing_primary_key_tests_.abc123"
        name = _extract_warn_name(uid)
        assert name == "fct_missing_primary_key_tests"

    def test_extract_warn_name_no_prefix(self):
        from dbt_diagnostics.main import _extract_warn_name
        uid = "test.artwork_pipeline.custom_warn_check.abc123"
        name = _extract_warn_name(uid)
        assert name == "custom_warn_check"


# -- Report grouping tests --------------------------------------------------

class TestReportGrouping:
    """Test cross-result correlation and grouping."""

    def _make_report(self, uid: str, error_class: str, relation: str = None) -> DiagnosticReport:
        report = DiagnosticReport(
            unique_id=uid,
            error_class=error_class,
            raw_message="test",
        )
        report.relation = relation
        if relation:
            finding = DiagnosticFinding(
                summary="test",
                target_identifier=relation,
                target_object=f"model.pkg.{relation.split('.')[-1]}",
            )
            report.findings.append(finding)
        return report

    def test_groups_same_schema_errors(self):
        reports = [
            self._make_report("test.pkg.a.1", "runtime_error", "ARTWORK_DB.GOLD.dim_artists"),
            self._make_report("test.pkg.b.2", "runtime_error", "ARTWORK_DB.GOLD.dim_artworks"),
            self._make_report("test.pkg.c.3", "runtime_error", "ARTWORK_DB.GOLD.fct_images"),
        ]
        groups, ungrouped = group_reports(reports)
        assert len(groups) == 1
        assert len(groups[0].reports) == 3
        assert "ARTWORK_DB.GOLD" in groups[0].title
        assert len(ungrouped) == 0

    def test_no_grouping_for_single_report(self):
        reports = [
            self._make_report("test.pkg.a.1", "runtime_error", "ARTWORK_DB.GOLD.dim_artists"),
        ]
        groups, ungrouped = group_reports(reports)
        assert len(groups) == 0
        assert len(ungrouped) == 1

    def test_different_schemas_not_grouped(self):
        reports = [
            self._make_report("test.pkg.a.1", "runtime_error", "ARTWORK_DB.GOLD.dim_artists"),
            self._make_report("test.pkg.b.2", "test_failure", "ARTWORK_DB.SILVER.stg_met__artworks"),
        ]
        groups, ungrouped = group_reports(reports)
        assert len(groups) == 0
        assert len(ungrouped) == 2

    def test_combined_fix_contains_all_model_names(self):
        reports = [
            self._make_report("test.pkg.a.1", "runtime_error", "ARTWORK_DB.GOLD.dim_artists"),
            self._make_report("test.pkg.b.2", "runtime_error", "ARTWORK_DB.GOLD.dim_artworks"),
        ]
        groups, _ = group_reports(reports)
        assert len(groups) == 1
        fix = groups[0].combined_fix
        assert "dim_artists" in fix
        assert "dim_artworks" in fix
        assert "dbt run -s" in fix

    def test_schema_prefix_extraction(self):
        report = self._make_report("test.pkg.a.1", "test_failure", "ARTWORK_DB.SILVER.stg_met__x")
        prefix = _extract_schema_prefix(report)
        assert prefix == "ARTWORK_DB.SILVER"


# -- Integration: full diagnose with real fixtures --------------------------

class TestDiagnoseAllIntegration:
    """Test _diagnose_all with the real fixtures produces correct structure."""

    def test_warn_details_structure(self):
        """_diagnose_all returns structured warn_details, not just a count."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = _load_fixture("test_failures.json")
        manifest = _load_fixture("manifest_test_failures.json")
        paths = {
            "models_dir": Path("/fake/models"),
            "compiled_dir": Path("/fake/compiled"),
        }

        reports, skipped, total, errors, fails, warn_details = _diagnose_all(
            run_results, manifest, paths
        )

        # Fixture has 1 warn result
        assert isinstance(warn_details, list)
        assert len(warn_details) == 1
        assert warn_details[0]["category"] == "project_hygiene"
        assert warn_details[0]["failures"] == 5
        assert "name" in warn_details[0]

    def test_threshold_in_fail_report(self):
        """Fail reports include parsed threshold metadata."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = _load_fixture("test_failures.json")
        manifest = _load_fixture("manifest_test_failures.json")
        paths = {
            "models_dir": Path("/fake/models"),
            "compiled_dir": Path("/fake/compiled"),
        }

        reports, *_ = _diagnose_all(run_results, manifest, paths)

        # Find a test_failure report
        fail_reports = [r for r in reports if r.error_class == "test_failure"]
        assert len(fail_reports) >= 1

        # At least one should have a threshold (from the row count tests)
        reports_with_threshold = [r for r in fail_reports if r.threshold is not None]
        assert len(reports_with_threshold) >= 1

        # Check the threshold shape
        t = reports_with_threshold[0].threshold
        assert isinstance(t, tuple)
        assert len(t) == 2
        assert t[0] > 0  # min > 0
        assert t[1] > t[0]  # max > min

    def test_query_id_in_fail_report(self):
        """Fail reports include query_id from adapter_response."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = _load_fixture("test_failures.json")
        manifest = _load_fixture("manifest_test_failures.json")
        paths = {
            "models_dir": Path("/fake/models"),
            "compiled_dir": Path("/fake/compiled"),
        }

        reports, *_ = _diagnose_all(run_results, manifest, paths)

        fail_reports = [r for r in reports if r.error_class == "test_failure"]
        reports_with_qid = [r for r in fail_reports if r.query_id is not None]
        assert len(reports_with_qid) >= 1
        # Query IDs have a specific format
        qid = reports_with_qid[0].query_id
        assert "-" in qid  # Snowflake query IDs contain hyphens

    def test_relation_in_fail_report(self):
        """Fail reports include extracted relation name."""
        from dbt_diagnostics.main import _diagnose_all

        run_results = _load_fixture("test_failures.json")
        manifest = _load_fixture("manifest_test_failures.json")
        paths = {
            "models_dir": Path("/fake/models"),
            "compiled_dir": Path("/fake/compiled"),
        }

        reports, *_ = _diagnose_all(run_results, manifest, paths)

        fail_reports = [r for r in reports if r.error_class == "test_failure"]
        reports_with_rel = [r for r in fail_reports if r.relation is not None]
        assert len(reports_with_rel) >= 1
        # Relations are three-part names
        rel = reports_with_rel[0].relation
        assert rel.count(".") == 2
