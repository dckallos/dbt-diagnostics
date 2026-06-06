"""
Tests for the data_error classifier.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.data_error import DataErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def data_errors_results():
    path = FIXTURES_DIR / "data_errors.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def data_error_manifest():
    return {
        "nodes": {
            "model.artwork_pipeline.stg_met__prices": {
                "unique_id": "model.artwork_pipeline.stg_met__prices",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__prices.sql",
                "compiled_code": "",
                "depends_on": {"nodes": [], "macros": []},
                "columns": {},
            },
            "model.artwork_pipeline.stg_met__descriptions": {
                "unique_id": "model.artwork_pipeline.stg_met__descriptions",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__descriptions.sql",
                "compiled_code": "",
                "depends_on": {"nodes": [], "macros": []},
                "columns": {},
            },
            "model.artwork_pipeline.fct_artwork_ratios": {
                "unique_id": "model.artwork_pipeline.fct_artwork_ratios",
                "resource_type": "model",
                "original_file_path": "models/marts/fct_artwork_ratios.sql",
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


class TestDataErrorClassification:
    """Tests for classify() dispatcher recognizing data errors."""

    def test_numeric_overflow_matches(self):
        msg = "Numeric value '99999999' is out of range for type NUMBER(5,0)"
        cls = classify(msg)
        assert cls is DataErrorClassifier

    def test_string_too_long_matches(self):
        msg = "String 'hello world...' is too long"
        cls = classify(msg)
        assert cls is DataErrorClassifier

    def test_division_by_zero_matches(self):
        msg = "Database Error\n  100035: Division by zero"
        cls = classify(msg)
        assert cls is DataErrorClassifier

    def test_unrelated_error_does_not_match(self):
        msg = "Database Error\n  Some other error"
        assert not DataErrorClassifier.matches(msg)


class TestNumericOverflow:
    """Tests for numeric overflow diagnosis."""

    def test_diagnose_numeric_overflow(self, data_errors_results, data_error_manifest):
        result = data_errors_results["results"][0]
        ctx = _make_context(data_error_manifest)

        classifier = DataErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "data_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "overflow" in finding.summary.lower() or "out of range" in finding.summary.lower()
        assert "TRY_CAST" in finding.fix_suggestion


class TestStringTooLong:
    """Tests for string too long diagnosis."""

    def test_diagnose_string_too_long(self, data_errors_results, data_error_manifest):
        result = data_errors_results["results"][1]
        ctx = _make_context(data_error_manifest)

        classifier = DataErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "data_error"
        finding = report.findings[0]
        assert "too long" in finding.summary.lower()
        assert "LEFT" in finding.fix_suggestion or "VARCHAR" in finding.fix_suggestion


class TestDivisionByZero:
    """Tests for division by zero diagnosis."""

    def test_diagnose_division_by_zero(self, data_errors_results, data_error_manifest):
        result = data_errors_results["results"][2]
        ctx = _make_context(data_error_manifest)

        classifier = DataErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "data_error"
        finding = report.findings[0]
        assert "division by zero" in finding.summary.lower()
        assert "NULLIF" in finding.fix_suggestion
