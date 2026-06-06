"""
Tests for the timeout_error classifier.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.timeout_error import TimeoutErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def timeout_results():
    path = FIXTURES_DIR / "timeout_errors.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def timeout_manifest():
    return {
        "nodes": {
            "model.artwork_pipeline.fct_artwork_metrics": {
                "unique_id": "model.artwork_pipeline.fct_artwork_metrics",
                "resource_type": "model",
                "original_file_path": "models/marts/fct_artwork_metrics.sql",
                "compiled_code": "",
                "depends_on": {"nodes": [], "macros": []},
                "columns": {},
            },
            "model.artwork_pipeline.dim_departments": {
                "unique_id": "model.artwork_pipeline.dim_departments",
                "resource_type": "model",
                "original_file_path": "models/marts/dim_departments.sql",
                "compiled_code": "",
                "depends_on": {"nodes": [], "macros": []},
                "columns": {},
            },
        },
        "sources": {},
        "parent_map": {},
    }


def _make_context(manifest):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/fake/models"), Path("/fake/compiled")),
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
        manifest=manifest,
    )


class TestTimeoutClassification:
    """Tests for the classify() dispatcher recognizing timeout errors."""

    def test_timeout_matches(self):
        msg = "Statement reached its statement or warehouse timeout of 600 second(s)"
        cls = classify(msg)
        assert cls is TimeoutErrorClassifier

    def test_warehouse_suspended_matches(self):
        msg = "Database Error\n  Warehouse 'MY_WH' was suspended while the query was running."
        cls = classify(msg)
        assert cls is TimeoutErrorClassifier

    def test_non_timeout_does_not_match(self):
        msg = "Database Error\n  002003: Object does not exist"
        cls = classify(msg)
        assert cls is not TimeoutErrorClassifier


class TestTimeoutDiagnosis:
    """Tests for timeout error diagnosis."""

    def test_diagnose_statement_timeout(self, timeout_results, timeout_manifest):
        result = timeout_results["results"][0]
        ctx = _make_context(timeout_manifest)

        classifier = TimeoutErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "timeout_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "timeout" in finding.summary.lower()
        assert "STATEMENT_TIMEOUT_IN_SECONDS" in finding.session_params_to_check

    def test_diagnose_warehouse_suspended(self, timeout_results, timeout_manifest):
        result = timeout_results["results"][1]
        ctx = _make_context(timeout_manifest)

        classifier = TimeoutErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "timeout_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "suspended" in finding.summary.lower()
        assert "TRANSFORM_WH" in finding.summary

    def test_timeout_extracts_warehouse_name(self, timeout_results, timeout_manifest):
        result = timeout_results["results"][1]
        ctx = _make_context(timeout_manifest)

        classifier = TimeoutErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]
        assert "TRANSFORM_WH" in finding.summary
