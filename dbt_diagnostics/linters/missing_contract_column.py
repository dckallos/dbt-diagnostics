"""
dbt_diagnostics/linters/missing_contract_column.py

Linter: Contract declares column X, but compiled SQL's SELECT projection
list doesn't produce it. Catches missing columns before runtime.
"""

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope

from dbt_diagnostics.linters.base import BaseLinter
from dbt_diagnostics.models import LintFinding


class MissingContractColumnLinter(BaseLinter):
    """Detects contract-declared columns missing from the compiled SQL projection."""

    check_name = "missing_contract_column"

    def lint(
        self,
        model_id: str,
        compiled_sql: str,
        manifest_node: dict,
    ) -> list[LintFinding]:
        findings: list[LintFinding] = []

        columns = manifest_node.get("columns", {})
        contract = manifest_node.get("contract", {})
        if not columns:
            return findings
        if not contract.get("enforced", False):
            return findings

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

        # Collect produced column names from projections
        produced: set[str] = set()
        has_star = False
        for projection in outer_select.expressions:
            if isinstance(projection, exp.Star):
                has_star = True
                break
            elif isinstance(projection, exp.Alias):
                produced.add(projection.alias.upper())
            elif isinstance(projection, exp.Column):
                produced.add(projection.name.upper())

        if has_star:
            # Can't validate with unexpanded star
            return findings

        # Check each contract column
        file_path = manifest_node.get("original_file_path")
        for col_name in columns:
            if col_name.upper() not in produced:
                findings.append(LintFinding(
                    severity="error",
                    check_name=self.check_name,
                    model_id=model_id,
                    file_path=file_path,
                    line_number=None,
                    message=(
                        f"Contract declares column '{col_name}' but compiled SQL "
                        "does not produce it"
                    ),
                    fix_suggestion=(
                        f"Add '{col_name}' to the SELECT projection, or remove it "
                        "from the contract YAML."
                    ),
                ))

        return findings
