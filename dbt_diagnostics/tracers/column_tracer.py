"""
dbt_diagnostics/tracers/column_tracer.py

Uses sqlglot to parse compiled SQL and trace a column back to its source
expression. Identifies the CTE, line number, and expression that produces
a given output column.
"""

from pathlib import Path
from typing import Optional

import sqlglot
from sqlglot import exp


class ColumnTraceResult:
    """Result of tracing a column through a SQL model."""

    def __init__(
        self,
        column_name: str,
        expression: str,
        cte_name: Optional[str],
        line_number: Optional[int],
        file_path: Optional[str],
        is_function_call: bool,
        source_columns: list[str],
    ):
        self.column_name = column_name
        self.expression = expression
        self.cte_name = cte_name
        self.line_number = line_number
        self.file_path = file_path
        self.is_function_call = is_function_call
        self.source_columns = source_columns

    def __repr__(self):
        return (
            f"ColumnTraceResult(column={self.column_name}, "
            f"expr={self.expression}, cte={self.cte_name}, "
            f"line={self.line_number}, file={self.file_path})"
        )


class ColumnTracer:
    """Traces columns through SQL using sqlglot AST parsing."""

    def __init__(self, models_dir: Path, compiled_dir: Path):
        self.models_dir = models_dir
        self.compiled_dir = compiled_dir

    def trace_column(
        self,
        column_name: str,
        compiled_sql: str,
        source_file_path: Optional[str] = None,
    ) -> Optional[ColumnTraceResult]:
        """
        Parse compiled SQL and find the expression that produces column_name.

        Uses sqlglot to parse the AST, then walks SELECT lists looking for
        the alias that matches column_name.

        Search order:
          1. Outer SELECT's direct projection list (not recursing into CTEs)
          2. Each CTE's SELECT (with cte_name populated)
        """
        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="snowflake")
        except sqlglot.errors.ParseError:
            return None

        # Find the outermost SELECT (skip CTE definitions)
        outer_select = parsed.find(exp.Select)
        if outer_select:
            result = self._find_alias_in_select(outer_select, column_name, cte_name=None)
            if result:
                return result

        # Search each CTE explicitly (with cte_name set)
        for cte in parsed.find_all(exp.CTE):
            cte_alias = cte.alias
            cte_select = cte.find(exp.Select)
            if cte_select:
                result = self._find_alias_in_select(cte_select, column_name, cte_name=cte_alias)
                if result:
                    return result

        return None

    def _find_alias_in_select(
        self,
        select_node,
        column_name: str,
        cte_name: Optional[str] = None,
    ) -> Optional[ColumnTraceResult]:
        """
        Search a SELECT's direct projection list for a column alias match.
        Uses select_node.expressions (the top-level projections) to avoid
        recursing into subqueries or CTE definitions.
        """
        for projection in select_node.expressions:
            # Handle aliased expressions: expr AS name
            if isinstance(projection, exp.Alias):
                alias = projection.alias
                if alias and alias.upper() == column_name.upper():
                    expr_node = projection.this
                    expression_sql = expr_node.sql(dialect="snowflake")

                    is_function = isinstance(expr_node, exp.Func) or bool(
                        expr_node.find(exp.Func)
                    )

                    source_cols = [
                        col.sql(dialect="snowflake")
                        for col in expr_node.find_all(exp.Column)
                    ]

                    return ColumnTraceResult(
                        column_name=column_name,
                        expression=expression_sql,
                        cte_name=cte_name,
                        line_number=None,
                        file_path=None,
                        is_function_call=is_function,
                        source_columns=source_cols,
                    )

        return None

    def find_line_number(
        self, source_file: Path, column_name: str
    ) -> Optional[int]:
        """
        Find the line number where a column is defined in the source .sql file.

        Uses simple text search (the source file has Jinja, not pure SQL,
        so sqlglot can't parse it directly).
        """
        if not source_file.exists():
            return None

        text = source_file.read_text()
        target = column_name.lower()

        for i, line in enumerate(text.splitlines(), start=1):
            line_lower = line.lower()
            # Match "AS column_name" or "as _loaded_at"
            if f"as {target}" in line_lower or f"as {target}," in line_lower:
                return i

        return None
