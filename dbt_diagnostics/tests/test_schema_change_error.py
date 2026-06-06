"""
Tests for the schema_change_error classifier.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.schema_change_error import SchemaChangeErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def schema_change_results():
    path = FIXTURES_DIR / "schema_change_errors.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def schema_change_manifest():
    """Manifest where upstream declares MEDIUM_DISPLAY but it was dropped."""
    return {
        "nodes": {
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
                "columns": {},
            },
            "model.artwork_pipeline.stg_met__artworks": {
                "unique_id": "model.artwork_pipeline.stg_met__artworks",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__artworks.sql",
                "relation_name": "ARTWORK_DB.SILVER.STG_MET__ARTWORKS",
                "compiled_code": "SELECT object_id, title, MEDIUM_DISPLAY FROM src",
                "depends_on": {"nodes": [], "macros": []},
                "columns": {
                    "medium_display": {"name": "medium_display", "data_type": "VARCHAR"}
                },
            },
        },
        "sources": {},
        "parent_map": {
            "model.artwork_pipeline.dim_artworks": [
                "model.artwork_pipeline.stg_met__artworks"
            ],
        },
    }


def _make_context(manifest):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/fake/models"), Path("/fake/compiled")),
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
        manifest=manifest,
    )


class TestSchemaChangeClassification:
    """Tests for classify() routing to SchemaChangeErrorClassifier."""

    def test_invalid_identifier_with_database_error_matches(self):
        msg = "Database Error in model foo\n  000904: invalid identifier 'COL_X'"
        cls = classify(msg)
        assert cls is SchemaChangeErrorClassifier

    def test_non_database_error_does_not_match(self):
        msg = "Some other error with invalid identifier 'X'"
        assert not SchemaChangeErrorClassifier.matches(msg)

    def test_no_invalid_identifier_does_not_match(self):
        msg = "Database Error\n  002003: Object does not exist"
        assert not SchemaChangeErrorClassifier.matches(msg)


class TestSchemaChangeDiagnosis:
    """Tests for schema drift detection."""

    def test_detects_drift_when_column_in_upstream_manifest(
        self, schema_change_results, schema_change_manifest
    ):
        """Column exists in manifest upstream but is missing at runtime = drift."""
        result = schema_change_results["results"][0]
        ctx = _make_context(schema_change_manifest)

        classifier = SchemaChangeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "schema_change_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "MEDIUM_DISPLAY" in finding.summary
        assert "drift" in finding.summary.lower() or "schema" in finding.summary.lower()
        assert finding.upstream_origin is not None
        assert "stg_met__artworks" in finding.upstream_origin.model_id

    def test_no_drift_when_column_not_in_manifest(self, schema_change_results):
        """Column NOT in any upstream manifest = possible typo, no drift claim."""
        manifest = {
            "nodes": {
                "model.artwork_pipeline.dim_artworks": {
                    "unique_id": "model.artwork_pipeline.dim_artworks",
                    "resource_type": "model",
                    "original_file_path": "models/marts/dim_artworks.sql",
                    "compiled_code": "",
                    "depends_on": {"nodes": [], "macros": []},
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {},
        }
        result = schema_change_results["results"][0]
        ctx = _make_context(manifest)

        classifier = SchemaChangeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        finding = report.findings[0]
        # No upstream_origin when column isn't in any manifest node
        assert finding.upstream_origin is None
        assert "MEDIUM_DISPLAY" in finding.summary

    def test_fix_suggestion_includes_rebuild_step(
        self, schema_change_results, schema_change_manifest
    ):
        result = schema_change_results["results"][0]
        ctx = _make_context(schema_change_manifest)

        classifier = SchemaChangeErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]

        assert "dbt run" in finding.fix_suggestion or "dbt parse" in finding.fix_suggestion
