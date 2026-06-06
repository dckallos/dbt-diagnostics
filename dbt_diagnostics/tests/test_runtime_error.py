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
