"""
dbt_diagnostics/linters/duplicate_alias.py

Linter: Detect SELECT a AS x, b AS x (duplicate output column names).
Snowflake allows this but contract enforcement rejects it.
"""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope

from dbt_diagnostics.linters.base import BaseLinter
from dbt_diagnostics.models import LintFinding


class DuplicateAliasLinter(BaseLinter):
    """Detects duplicate column aliases in the outermost SELECT."""

    check_name = "duplicate_alias"

    def lint(
        self,
        model_id: str,
        compiled_sql: str,
        manifest_node: dict,
    ) -> list[LintFinding]:
        findings: list[LintFinding] = []

        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="snowflake")
        except sqlglot.errors.ParseError:
            return findings

        root_scope = build_scope(parsed)
        if not root_scope:
            return findings

        root_expr = root_scope.expression
        if isinstance(root_expr, exp.Select):
            outer_select = root_expr
        elif isinstance(root_expr, exp.Union):
            outer_select = root_expr.find(exp.Select)
        else:
            return findings

        if not outer_select:
            return findings

        # Collect aliases
        seen: dict[str, int] = {}
        for projection in outer_select.expressions:
            if isinstance(projection, exp.Alias):
                alias = projection.alias.upper()
            elif isinstance(projection, exp.Column):
                alias = projection.name.upper()
            else:
                continue

            if alias in seen:
                file_path = manifest_node.get("original_file_path")
                findings.append(LintFinding(
                    severity="error",
                    check_name=self.check_name,
                    model_id=model_id,
                    file_path=file_path,
                    line_number=None,
                    message=f"Duplicate column alias '{alias}' in SELECT projection",
                    fix_suggestion=(
                        f"Rename one of the duplicate '{alias}' columns to be unique."
                    ),
                ))
            else:
                seen[alias] = 1

        return findings
