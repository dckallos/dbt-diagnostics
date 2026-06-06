"""
Tests for the column tracer (sqlglot-based SQL parsing).
"""

import sqlglot
from sqlglot import exp

from dbt_diagnostics.tracers.column_tracer import ColumnTracer, ColumnTraceResult
from pathlib import Path


class TestSqlglotASTCanary:
    """
    Canary tests that fail early if sqlglot changes its AST representation.
    These validate assumptions the column tracer relies on.
    """

    def test_select_projections_are_alias_nodes(self):
        """Fails if sqlglot changes how it represents SELECT projections."""
        parsed = sqlglot.parse_one("SELECT 1 AS x", dialect="snowflake")
        select = parsed.find(exp.Select)
        assert isinstance(select.expressions[0], exp.Alias)
        assert select.expressions[0].alias == "x"

    def test_cte_has_alias_property(self):
        """Fails if sqlglot changes CTE alias access."""
        parsed = sqlglot.parse_one(
            "WITH my_cte AS (SELECT 1 AS a) SELECT a FROM my_cte",
            dialect="snowflake",
        )
        ctes = list(parsed.find_all(exp.CTE))
        assert len(ctes) == 1
        assert ctes[0].alias == "my_cte"

    def test_build_scope_returns_root(self):
        """Fails if build_scope API changes."""
        from sqlglot.optimizer.scope import build_scope

        parsed = sqlglot.parse_one(
            "WITH src AS (SELECT 1 AS x) SELECT x FROM src",
            dialect="snowflake",
        )
        root = build_scope(parsed)
        assert root is not None
        assert isinstance(root.expression, exp.Select)


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
        assert result.cte_name == "src"
        assert "CURRENT_TIMESTAMP" in result.expression.upper()

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

    def test_trace_nested_ctes_finds_correct_cte(self):
        """build_scope correctly resolves outer SELECT vs CTE definitions."""
        sql = (
            "WITH a AS (SELECT 1 AS x), "
            "b AS (SELECT x, CURRENT_TIMESTAMP() AS y FROM a) "
            "SELECT x, y FROM b"
        )
        result = self.tracer.trace_column("y", sql)
        assert result is not None
        # y is defined in CTE b, not in the outer SELECT (which just passes through)
        assert result.cte_name == "b"
        assert "CURRENT_TIMESTAMP" in result.expression.upper()

    def test_trace_union_finds_column(self):
        """build_scope handles UNION ALL statements correctly."""
        sql = (
            "WITH cte AS (SELECT 1 AS id, 'hello' AS name) "
            "SELECT id, name FROM cte "
            "UNION ALL "
            "SELECT 2 AS id, 'world' AS name"
        )
        # The outer SELECT (left branch of UNION) doesn't alias these,
        # so we expect to find 'name' in the CTE
        result = self.tracer.trace_column("name", sql)
        assert result is not None
