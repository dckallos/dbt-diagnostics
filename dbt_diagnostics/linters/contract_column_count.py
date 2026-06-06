"""
dbt_diagnostics/linters/contract_column_count.py

Linter: For models with contracts, parse compiled SQL projections (via sqlglot)
and compare count against manifest column declarations. Flag if mismatch.
"""

import sqlglot
from sqlglot import exp

from dbt_diagnostics.linters.base import BaseLinter
from dbt_diagnostics.models import LintFinding


class ContractColumnCountLinter(BaseLinter):
    """Checks that compiled SQL projection count matches contract column count."""

    check_name = "contract_column_count"

    def lint(
        self,
        model_id: str,
        compiled_sql: str,
        manifest_node: dict,
    ) -> list[LintFinding]:
        findings: list[LintFinding] = []

        # Only applies to models with contracts (columns declared in manifest)
        columns = manifest_node.get("columns", {})
        contract = manifest_node.get("contract", {})
        if not columns:
            return findings
        # Only check models that have contract enforcement
        if not contract.get("enforced", False):
            return findings

        contract_count = len(columns)

        try:
            parsed = sqlglot.parse_one(compiled_sql, dialect="snowflake")
        except sqlglot.errors.ParseError:
            return findings

        # Find the outermost SELECT's projection list
        from sqlglot.optimizer.scope import build_scope

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

        # Count projections (skip Star nodes -- those expand at runtime)
        projections = outer_select.expressions
        has_star = any(isinstance(p, exp.Star) for p in projections)
        if has_star:
            # Can't count with unexpanded star
            return findings

        sql_count = len(projections)

        if sql_count != contract_count:
            file_path = manifest_node.get("original_file_path")
            findings.append(LintFinding(
                severity="error",
                check_name=self.check_name,
                model_id=model_id,
                file_path=file_path,
                line_number=None,
                message=(
                    f"Contract declares {contract_count} column(s) but compiled SQL "
                    f"produces {sql_count} column(s)"
                ),
                fix_suggestion=(
                    f"Align the SELECT projection count ({sql_count}) with the "
                    f"contract declaration ({contract_count}). "
                    "Add or remove columns from the SQL or the contract YAML."
                ),
            ))

        return findings
