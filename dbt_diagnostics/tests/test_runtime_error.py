"""
Tests for the runtime_error classifier.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def runtime_errors_results():
    path = FIXTURES_DIR / "runtime_errors.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def runtime_manifest():
    """Manifest with nodes matching the runtime errors fixture."""
    return {
        "nodes": {
            "model.artwork_pipeline.stg_met__artworks": {
                "unique_id": "model.artwork_pipeline.stg_met__artworks",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__artworks.sql",
                "relation_name": "ARTWORK_DB.SILVER.STG_MET__ARTWORKS",
                "compiled_code": "",
                "depends_on": {
                    "nodes": ["source.artwork_pipeline.met.raw_met_objects"],
                    "macros": [],
                },
                "columns": {},
            },
            "model.artwork_pipeline.dim_artworks": {
                "unique_id": "model.artwork_pipeline.dim_artworks",
                "resource_type": "model",
                "original_file_path": "models/marts/dim_artworks.sql",
                "relation_name": "ARTWORK_DB.GOLD.DIM_ARTWORKS",
                "compiled_code": "",
                "depends_on": {
                    "nodes": ["model.artwork_pipeline.stg_met__artworks"],
                    "macros": [],
                },
                "columns": {
                    "artwork_id": {"name": "artwork_id"},
                    "title": {"name": "title"},
                },
            },
            "model.artwork_pipeline.stg_met__departments": {
                "unique_id": "model.artwork_pipeline.stg_met__departments",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__departments.sql",
                "relation_name": "ARTWORK_DB.SILVER.STG_MET__DEPARTMENTS",
                "compiled_code": "",
                "depends_on": {
                    "nodes": ["source.artwork_pipeline.met.raw_met_departments"],
                    "macros": [],
                },
                "columns": {},
            },
            "model.dbt_snowflake_monitoring.stg_metering_daily_history": {
                "unique_id": "model.dbt_snowflake_monitoring.stg_metering_daily_history",
                "resource_type": "model",
                "original_file_path": "models/staging/stg_metering_daily_history.sql",
                "relation_name": "ARTWORK_DB.SILVER.STG_METERING_DAILY_HISTORY",
                "compiled_code": "",
                "depends_on": {
                    "nodes": [],
                    "macros": [],
                },
                "columns": {},
            },
            "model.dbt_project_evaluator.stg_naming_convention_prefixes": {
                "unique_id": "model.dbt_project_evaluator.stg_naming_convention_prefixes",
                "resource_type": "model",
                "original_file_path": "models/staging/variables/stg_naming_convention_prefixes.sql",
                "relation_name": "ARTWORK_DB.DBT_TEST__AUDIT.STG_NAMING_CONVENTION_PREFIXES",
                "compiled_code": "",
                "depends_on": {
                    "nodes": [],
                    "macros": [],
                },
                "columns": {},
            },
        },
        "sources": {
            "source.artwork_pipeline.met.raw_met_objects": {
                "unique_id": "source.artwork_pipeline.met.raw_met_objects",
                "resource_type": "source",
                "relation_name": "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS",
                "columns": {},
            },
        },
        "parent_map": {
            "model.artwork_pipeline.stg_met__artworks": [
                "source.artwork_pipeline.met.raw_met_objects"
            ],
            "model.artwork_pipeline.dim_artworks": [
                "model.artwork_pipeline.stg_met__artworks"
            ],
            "model.artwork_pipeline.stg_met__departments": [
                "source.artwork_pipeline.met.raw_met_departments"
            ],
            "model.dbt_snowflake_monitoring.stg_metering_daily_history": [],
            "model.dbt_project_evaluator.stg_naming_convention_prefixes": [],
        },
    }


def _make_context(manifest):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/fake/models"), Path("/fake/compiled")),
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
    )


class TestRuntimeErrorClassification:
    """Tests for the classify() dispatcher recognizing runtime errors."""

    def test_database_error_matches(self):
        msg = "Database Error in model foo\n  002003: Object does not exist"
        cls = classify(msg)
        assert cls is RuntimeErrorClassifier

    def test_contract_violation_takes_priority(self):
        """Contract violation contains 'Database Error' but should match first."""
        msg = "This model has an enforced contract that failed."
        cls = classify(msg)
        # ContractViolationClassifier is registered before RuntimeErrorClassifier
        assert cls is not RuntimeErrorClassifier


class TestObjectNotFound:
    """Tests for the 'object does not exist' sub-classifier."""

    def test_diagnose_object_not_found(self, runtime_errors_results, runtime_manifest):
        result = runtime_errors_results["results"][0]  # stg_met__artworks
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "runtime_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "RAW_MET_OBJECTS" in finding.summary
        assert finding.location.file_path == "models/staging/met/stg_met__artworks.sql"

    def test_identifies_known_source(self, runtime_errors_results, runtime_manifest):
        """The missing object IS a known source in the manifest (a parent)."""
        result = runtime_errors_results["results"][0]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        # The source is a direct parent -- classifier should identify it as
        # "produced by upstream model"
        assert "upstream" in finding.explanation.lower()


class TestInvalidIdentifier:
    """Tests for the 'invalid identifier' sub-classifier."""

    def test_diagnose_invalid_identifier(self, runtime_errors_results, runtime_manifest):
        result = runtime_errors_results["results"][1]  # dim_artworks
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        assert "ARTWORK_TITLE" in finding.summary

    def test_extracts_error_line(self, runtime_errors_results, runtime_manifest):
        result = runtime_errors_results["results"][1]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        # Error message says "error line 3 at position 4"
        assert finding.location.line_number == 3


class TestPermissionDenied:
    """Tests for the 'insufficient privileges' sub-classifier."""

    def test_diagnose_permission_denied(self, runtime_errors_results, runtime_manifest):
        result = runtime_errors_results["results"][2]  # stg_met__departments
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        assert "privileges" in finding.summary.lower() or "privileges" in finding.explanation.lower()
        assert "RAW_MET_DEPARTMENTS" in finding.summary
        assert "GRANT" in finding.fix_suggestion


class TestSchemaNotFound:
    """Tests for the 'schema does not exist' variant of 002003."""

    def test_diagnose_schema_not_found(self, runtime_errors_results, runtime_manifest):
        """Schema 'SNOWFLAKE.ACCOUNT_USAGE' does not exist should be classified correctly."""
        result = runtime_errors_results["results"][3]  # stg_metering_daily_history
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "runtime_error"
        assert report.has_findings
        finding = report.findings[0]
        # Should extract the actual schema name, not "UNKNOWN"
        assert "SNOWFLAKE.ACCOUNT_USAGE" in finding.summary
        assert "UNKNOWN" not in finding.summary

    def test_schema_not_found_suggests_imported_privileges(
        self, runtime_errors_results, runtime_manifest
    ):
        """Fix should suggest IMPORTED PRIVILEGES for shared databases."""
        result = runtime_errors_results["results"][3]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        assert "IMPORTED PRIVILEGES" in finding.fix_suggestion
        assert "SNOWFLAKE" in finding.fix_suggestion

    def test_schema_summary_says_schema_not_object(
        self, runtime_errors_results, runtime_manifest
    ):
        """Summary should say 'Schema not found' not 'Object not found'."""
        result = runtime_errors_results["results"][3]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        assert "Schema not found" in finding.summary


class TestPrivilegeExtraction:
    """Tests for extracting the specific required privilege from 003001 errors."""

    def test_extracts_create_view_privilege(self, runtime_errors_results, runtime_manifest):
        """Should extract 'CREATE VIEW' from the error message, not hardcode 'SELECT'."""
        result = runtime_errors_results["results"][4]  # stg_naming_convention_prefixes
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        assert "CREATE VIEW" in finding.fix_suggestion
        assert "SELECT" not in finding.fix_suggestion

    def test_privilege_fix_includes_fq_schema(self, runtime_errors_results, runtime_manifest):
        """Fix should use the fully-qualified schema name from the message."""
        result = runtime_errors_results["results"][4]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        assert "ARTWORK_DB.DBT_TEST__AUDIT" in finding.fix_suggestion

    def test_privilege_explanation_mentions_specific_privilege(
        self, runtime_errors_results, runtime_manifest
    ):
        """Explanation should name the specific missing privilege."""
        result = runtime_errors_results["results"][4]
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        assert "CREATE VIEW" in finding.explanation

    def test_legacy_privilege_without_must_have(self, runtime_errors_results, runtime_manifest):
        """Old-style 003001 without 'must have X granted' should still work."""
        result = runtime_errors_results["results"][2]  # RAW_MET_DEPARTMENTS (no 'must have')
        ctx = _make_context(runtime_manifest)

        classifier = RuntimeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        # Should fall back to USAGE suggestion when specific privilege isn't stated
        assert "GRANT" in finding.fix_suggestion
        assert "RAW_MET_DEPARTMENTS" in finding.summary
