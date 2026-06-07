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
from sqlglot.optimizer.scope import build_scope


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


def build_schema_from_manifest(manifest: dict) -> dict:
    """
    Build a sqlglot-compatible schema dict from a dbt manifest.

    Format: {"db": {"schema": {"table": {"col": "type"}}}}
    Uses relation_name from manifest nodes to determine db.schema.table,
    and the columns dict for column names/types.
    """
    schema: dict = {}
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    for node in list(nodes.values()) + list(sources.values()):
        relation_name = node.get("relation_name", "")
        columns = node.get("columns", {})
        if not relation_name or not columns:
            continue

        # relation_name is like "ARTWORK_DB.SILVER.STG_MET__ARTWORKS"
        parts = relation_name.replace('"', "").split(".")
        if len(parts) != 3:
            continue

        db, sch, table = parts[0].upper(), parts[1].upper(), parts[2].upper()

        if db not in schema:
            schema[db] = {}
        if sch not in schema[db]:
            schema[db][sch] = {}

        table_cols: dict = {}
        for col_name, col_info in columns.items():
            dtype = col_info.get("data_type", "VARCHAR") or "VARCHAR"
            table_cols[col_name.upper()] = dtype.upper()

        schema[db][sch][table] = table_cols

    return schema


def qualify_sql(
    parsed: exp.Expression,
    schema: Optional[dict] = None,
) -> exp.Expression:
    """
    Run sqlglot's qualify optimizer pass on the parsed AST.

    This expands SELECT *, qualifies ambiguous columns with table names,
    and resolves CTE column references. Falls back to the original AST
    if qualification fails for any reason.
    """
    if not schema:
        return parsed

    try:
        from sqlglot.optimizer.qualify import qualify

        qualified = qualify(
            parsed,
            schema=schema,
            dialect="snowflake",
            validate_qualify_columns=False,
        )
        return qualified
    except Exception:
        # Graceful fallback: if qualify fails (missing schema, unsupported SQL),
        # return the original unmodified AST
        return parsed


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
        schema: Optional[dict] = None,
    ) -> Optional[ColumnTraceResult]:
        """
        Parse compiled SQL and find the expression that produces column_name.

        Uses sqlglot's scope module to correctly identify the outermost SELECT
        (handles CTEs, UNIONs, and subqueries without DFS ordering issues).

        When a schema dict is provided, runs sqlglot qualify first to expand
        SELECT * and resolve ambiguous column references.

        Search order:
          1. Outer SELECT's direct projection list (not recursing into CTEs)
          2. Each CTE's SELECT (with cte_name populated)
        """
        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="snowflake")
        except sqlglot.errors.ParseError:
            return None

        # Run qualify to expand SELECT * and resolve ambiguity
        parsed = qualify_sql(parsed, schema=schema)

        # Use build_scope to find the true outermost SELECT.
        # For UNION statements, build_scope returns the Union as root;
        # for simple SELECTs (with or without CTEs), it returns the outer Select.
        root_scope = build_scope(parsed)
        outer_select = None
        if root_scope:
            root_expr = root_scope.expression
            if isinstance(root_expr, exp.Select):
                outer_select = root_expr
            elif isinstance(root_expr, exp.Union):
                # For UNIONs, check the left branch first (the "primary" SELECT)
                outer_select = root_expr.find(exp.Select)

        if outer_select:
            result = self._find_alias_in_select(
                outer_select, column_name, cte_name=None, include_bare_columns=False
            )
            if result:
                return result

        # Search each CTE explicitly (with cte_name set)
        for cte in parsed.find_all(exp.CTE):
            cte_alias = cte.alias
            cte_select = cte.find(exp.Select)
            if cte_select:
                result = self._find_alias_in_select(
                    cte_select, column_name, cte_name=cte_alias, include_bare_columns=True
                )
                if result:
                    return result

        # Last resort: bare column match in outer SELECT (pass-through references)
        if outer_select:
            result = self._find_bare_column_in_select(
                outer_select, column_name, cte_name=None
            )
            if result:
                return result

        return None

    def _find_alias_in_select(
        self,
        select_node,
        column_name: str,
        cte_name: Optional[str] = None,
        include_bare_columns: bool = True,
    ) -> Optional[ColumnTraceResult]:
        """
        Search a SELECT's direct projection list for a column match.

        Priority order:
          1. Aliased expressions (exp.Alias) -- most specific match.
          2. Bare column references (exp.Column) -- only when include_bare_columns=True.
          3. exp.Star returns None (can't resolve without schema).
        """
        # Pass 1: Alias matches (highest priority)
        for projection in select_node.expressions:
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

        # Pass 2: Bare column references (when enabled)
        if include_bare_columns:
            return self._find_bare_column_in_select(select_node, column_name, cte_name)

        return None

    def _find_bare_column_in_select(
        self,
        select_node,
        column_name: str,
        cte_name: Optional[str] = None,
    ) -> Optional[ColumnTraceResult]:
        """
        Search a SELECT's projection list for bare column references (exp.Column).
        Returns None for exp.Star since we can't resolve without schema.
        """
        for projection in select_node.expressions:
            if isinstance(projection, exp.Column):
                if projection.name.upper() == column_name.upper():
                    expression_sql = projection.sql(dialect="snowflake")

                    return ColumnTraceResult(
                        column_name=column_name,
                        expression=expression_sql,
                        cte_name=cte_name,
                        line_number=None,
                        file_path=None,
                        is_function_call=False,
                        source_columns=[expression_sql],
                    )
            elif isinstance(projection, exp.Star):
                # SELECT * -- can't resolve specific columns without schema
                continue

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
