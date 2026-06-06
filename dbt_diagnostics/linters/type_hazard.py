"""
dbt_diagnostics/linters/type_hazard.py

Linter: Detect CURRENT_TIMESTAMP(), SYSDATE(), GETDATE() without explicit
::TIMESTAMP_NTZ cast in models whose contract declares a TIMESTAMP_NTZ column.
These will fail at runtime under default session settings.
"""

import re

from dbt_diagnostics.linters.base import BaseLinter
from dbt_diagnostics.models import LintFinding


# Functions that return TIMESTAMP_LTZ by default
_TIMESTAMP_FUNCS_RE = re.compile(
    r"\b(CURRENT_TIMESTAMP|SYSDATE|GETDATE)\s*\(\s*\)",
    re.IGNORECASE,
)
# Cast to NTZ
_NTZ_CAST_RE = re.compile(
    r"(::TIMESTAMP_NTZ|CAST\s*\([^)]+\s+AS\s+TIMESTAMP_NTZ\))",
    re.IGNORECASE,
)


class TypeHazardLinter(BaseLinter):
    """Detects timestamp function calls that will produce LTZ when NTZ is expected."""

    check_name = "type_hazard"

    def lint(
        self,
        model_id: str,
        compiled_sql: str,
        manifest_node: dict,
    ) -> list[LintFinding]:
        findings: list[LintFinding] = []

        # Check if any contract column expects TIMESTAMP_NTZ
        columns = manifest_node.get("columns", {})
        has_ntz_contract = any(
            "TIMESTAMP_NTZ" in (col.get("data_type") or "").upper()
            for col in columns.values()
        )
        if not has_ntz_contract:
            return findings

        # Search for timestamp functions without NTZ cast
        file_path = manifest_node.get("original_file_path")

        for i, line in enumerate(compiled_sql.splitlines(), start=1):
            func_match = _TIMESTAMP_FUNCS_RE.search(line)
            if func_match and not _NTZ_CAST_RE.search(line):
                func_name = func_match.group(1).upper()
                findings.append(LintFinding(
                    severity="warning",
                    check_name=self.check_name,
                    model_id=model_id,
                    file_path=file_path,
                    line_number=i,
                    message=(
                        f"{func_name}() returns TIMESTAMP_LTZ by default but "
                        f"contract expects TIMESTAMP_NTZ"
                    ),
                    fix_suggestion=(
                        f"Cast explicitly: {func_name}()::TIMESTAMP_NTZ"
                    ),
                ))

        return findings
