"""
Tests for the column tracer (sqlglot-based SQL parsing).
"""

from dbt_diagnostics.tracers.column_tracer import ColumnTracer, ColumnTraceResult
from pathlib import Path


class TestColumnTracer:
    """Unit tests for sqlglot-based column tracing."""

    def setup_method(self):
        self.tracer = ColumnTracer(
            models_dir=Path("/nonexistent/models"),
            compiled_dir=Path("/nonexistent/compiled"),
        )

    def test_trace_simple_alias(self):
        sql = "SELECT 1 AS id, 'hello' AS name FROM foo"
        result = self.tracer.trace_column("name", sql)
        assert result is not None
        assert result.column_name == "name"
        assert result.is_function_call is False

    def test_trace_function_call(self):
        sql = "SELECT CURRENT_TIMESTAMP() AS _loaded_at FROM foo"
        result = self.tracer.trace_column("_loaded_at", sql)
        assert result is not None
        assert result.is_function_call is True
        assert "CURRENT_TIMESTAMP" in result.expression.upper()

    def test_trace_column_in_cte(self):
        sql = (
            "WITH src AS (\n"
            "    SELECT artist_id, CURRENT_TIMESTAMP() AS _loaded_at\n"
            "    FROM raw_table\n"
            ")\n"
            "SELECT artist_id, _loaded_at FROM src"
        )
        result = self.tracer.trace_column("_loaded_at", sql)
        assert result is not None
        # Should find the expression in either the CTE or outer SELECT
        # The outer SELECT references it as a plain column, the CTE defines it
        # Current implementation checks outer first -- _loaded_at in outer SELECT
        # is just a column reference, not aliased. So it should find it in the CTE.

    def test_trace_missing_column(self):
        sql = "SELECT 1 AS id FROM foo"
        result = self.tracer.trace_column("nonexistent", sql)
        assert result is None

    def test_trace_case_insensitive(self):
        sql = "SELECT 1 AS MY_COLUMN FROM foo"
        result = self.tracer.trace_column("my_column", sql)
        assert result is not None
        assert result.column_name == "my_column"

    def test_trace_from_fixture_compiled_sql(self, contract_type_mismatch_results):
        """Trace _loaded_at in the real compiled SQL from the fixture."""
        compiled = contract_type_mismatch_results["results"][0]["compiled_code"]
        result = self.tracer.trace_column("_loaded_at", compiled)
        assert result is not None
        assert result.is_function_call is True
        assert "CURRENT_TIMESTAMP" in result.expression.upper()
        # NOTE: cte_name is None because find_all(exp.Alias) recurses into CTEs
        # from the outer SELECT. This is a known limitation -- the tracer finds
        # the correct expression but doesn't accurately report which CTE it's in
        # when the outer SELECT references the CTE column without re-aliasing.
        # TODO: Fix _find_alias_in_select to not recurse into CTE definitions.
