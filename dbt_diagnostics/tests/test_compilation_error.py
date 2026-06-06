"""
Tests for the compilation_error classifier.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.compilation_error import CompilationErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def compilation_errors_results():
    path = FIXTURES_DIR / "compilation_errors.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def compilation_manifest():
    """Manifest with nodes matching the compilation errors fixture."""
    return {
        "nodes": {
            "model.artwork_pipeline.stg_met__departments": {
                "unique_id": "model.artwork_pipeline.stg_met__departments",
                "resource_type": "model",
                "original_file_path": "models/staging/met/stg_met__departments.sql",
                "path": "staging/met/stg_met__departments.sql",
                "columns": {},
                "depends_on": {"nodes": []},
            },
            "model.artwork_pipeline.stg_met__artworks": {
                "unique_id": "model.artwork_pipeline.stg_met__artworks",
                "resource_type": "model",
                "path": "staging/met/stg_met__artworks.sql",
                "columns": {},
                "depends_on": {"nodes": []},
            },
            "model.artwork_pipeline.dim_departments": {
                "unique_id": "model.artwork_pipeline.dim_departments",
                "resource_type": "model",
                "original_file_path": "models/marts/dim_departments.sql",
                "path": "marts/dim_departments.sql",
                "columns": {},
                "depends_on": {"nodes": ["model.artwork_pipeline.stg_met__departments"]},
            },
            "model.artwork_pipeline.fct_exhibitions": {
                "unique_id": "model.artwork_pipeline.fct_exhibitions",
                "resource_type": "model",
                "original_file_path": "models/marts/fct_exhibitions.sql",
                "path": "marts/fct_exhibitions.sql",
                "columns": {},
                "depends_on": {"nodes": []},
            },
        },
        "sources": {},
        "parent_map": {
            "model.artwork_pipeline.stg_met__departments": [],
            "model.artwork_pipeline.dim_departments": [
                "model.artwork_pipeline.stg_met__departments"
            ],
            "model.artwork_pipeline.fct_exhibitions": [],
        },
    }


def _make_context(manifest):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/fake/models"), Path("/fake/compiled")),
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
    )


class TestCompilationErrorClassification:
    """Tests for the classify() dispatcher recognizing compilation errors."""

    def test_compilation_error_matches(self):
        msg = "Compilation Error in model bar\n  'ref' is undefined"
        cls = classify(msg)
        assert cls is CompilationErrorClassifier

    def test_contract_violation_still_takes_priority(self):
        """Ensure ordering: contract > compilation > runtime."""
        msg = "This model has an enforced contract that failed."
        cls = classify(msg)
        assert cls is not CompilationErrorClassifier


class TestUndefinedName:
    """Tests for the 'undefined name' sub-classifier."""

    def test_diagnose_undefined_variable(
        self, compilation_errors_results, compilation_manifest
    ):
        result = compilation_errors_results["results"][0]
        ctx = _make_context(compilation_manifest)

        classifier = CompilationErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "compilation_error"
        assert report.has_findings
        finding = report.findings[0]
        assert "ref_typo" in finding.summary
        assert finding.location.line_number == 5
        assert finding.fix_suggestion is not None

    def test_file_path_populated(
        self, compilation_errors_results, compilation_manifest
    ):
        result = compilation_errors_results["results"][0]
        ctx = _make_context(compilation_manifest)

        classifier = CompilationErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()
        finding = report.findings[0]
        assert finding.location.file_path is not None


class TestRefNotFound:
    """Tests for the 'ref target not found' sub-classifier."""

    def test_diagnose_ref_not_found(
        self, compilation_errors_results, compilation_manifest
    ):
        result = compilation_errors_results["results"][1]
        ctx = _make_context(compilation_manifest)

        classifier = CompilationErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        assert "stg_met__departmens" in finding.summary
        # Should suggest the correct name (stg_met__departments)
        assert "stg_met__departments" in finding.fix_suggestion


class TestGenericCompilationError:
    """Tests for generic/unclassifiable compilation errors."""

    def test_diagnose_jinja_syntax_error(
        self, compilation_errors_results, compilation_manifest
    ):
        result = compilation_errors_results["results"][2]
        ctx = _make_context(compilation_manifest)

        classifier = CompilationErrorClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.has_findings
        finding = report.findings[0]
        assert finding.location.line_number == 12
        assert finding.fix_suggestion is not None
