"""
Tests for the contract_violation classifier and supporting logic.
"""

import json
from pathlib import Path

from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.contract_violation import (
    ContractViolationClassifier,
    parse_mismatch_table,
)
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_context(manifest):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/nonexistent/models"), Path("/nonexistent/compiled")),
        models_dir=Path("/nonexistent/models"),
        compiled_dir=Path("/nonexistent/compiled"),
    )


class TestParseMismatchTable:
    """Unit tests for the regex parser that extracts mismatch records."""

    def test_parses_single_row(self):
        msg = (
            "| column_name | definition_type | contract_type | mismatch_reason    |\n"
            "| ----------- | --------------- | ------------- | ------------------ |\n"
            "| _LOADED_AT  | TIMESTAMP_LTZ   | TIMESTAMP_NTZ | data type mismatch |\n"
        )
        records = parse_mismatch_table(msg)
        assert len(records) == 1
        assert records[0]["column_name"] == "_LOADED_AT"
        assert records[0]["definition_type"] == "TIMESTAMP_LTZ"
        assert records[0]["contract_type"] == "TIMESTAMP_NTZ"
        assert records[0]["mismatch_reason"] == "data type mismatch"

    def test_parses_multiple_rows(self):
        msg = (
            "| column_name | definition_type | contract_type | mismatch_reason    |\n"
            "| ----------- | --------------- | ------------- | ------------------ |\n"
            "| _LOADED_AT  | TIMESTAMP_LTZ   | TIMESTAMP_NTZ | data type mismatch |\n"
            "| STATUS      |                 | VARCHAR(10)   | missing in definition |\n"
        )
        records = parse_mismatch_table(msg)
        assert len(records) == 2
        assert records[1]["column_name"] == "STATUS"
        assert records[1]["mismatch_reason"] == "missing in definition"

    def test_empty_message_returns_empty(self):
        assert parse_mismatch_table("") == []
        assert parse_mismatch_table("some random error text") == []

    def test_parses_from_full_fixture(self, contract_type_mismatch_results):
        msg = contract_type_mismatch_results["results"][0]["message"]
        records = parse_mismatch_table(msg)
        assert len(records) == 1
        assert records[0]["column_name"] == "_LOADED_AT"


class TestContractViolationClassifier:
    """Integration tests using the real fixture artifacts."""

    def test_diagnose_returns_report(
        self, contract_type_mismatch_results, manifest_minimal
    ):
        """Smoke test: classifier runs to completion and returns a report."""
        result = contract_type_mismatch_results["results"][0]
        ctx = _make_context(manifest_minimal)

        classifier = ContractViolationClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        assert report.error_class == "contract_violation"
        assert report.has_findings
        finding = report.findings[0]
        assert "_LOADED_AT" in finding.summary
        assert "TIMESTAMP_LTZ" in finding.summary
        assert "TIMESTAMP_NTZ" in finding.summary

    def test_traces_column_in_compiled_sql(
        self, contract_type_mismatch_results, manifest_minimal
    ):
        """Verifies the column tracer finds CURRENT_TIMESTAMP in compiled SQL."""
        result = contract_type_mismatch_results["results"][0]
        ctx = _make_context(manifest_minimal)

        classifier = ContractViolationClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        finding = report.findings[0]
        # The compiled SQL has CURRENT_TIMESTAMP() AS _loaded_at
        assert finding.location.expression is not None
        assert "CURRENT_TIMESTAMP" in finding.location.expression.upper()

    def test_identifies_column_as_introduced(
        self, contract_type_mismatch_results, manifest_minimal
    ):
        """
        _loaded_at is NOT in stg_met__artists columns, so it should be
        reported as INTRODUCED in dim_artists (upstream_origin is None).
        """
        result = contract_type_mismatch_results["results"][0]
        ctx = _make_context(manifest_minimal)

        classifier = ContractViolationClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        finding = report.findings[0]
        assert finding.upstream_origin is None
        assert "INTRODUCED" in finding.explanation

    def test_suggests_fix_for_timestamp(
        self, contract_type_mismatch_results, manifest_minimal
    ):
        """Should suggest casting to TIMESTAMP_NTZ."""
        result = contract_type_mismatch_results["results"][0]
        ctx = _make_context(manifest_minimal)

        classifier = ContractViolationClassifier(result=result, context=ctx)
        report = classifier.diagnose()

        finding = report.findings[0]
        assert finding.fix_suggestion is not None
        assert "TIMESTAMP_NTZ" in finding.fix_suggestion
        assert finding.session_params_to_check  # Should have timestamp params
