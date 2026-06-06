"""
dbt_diagnostics/classifiers/timeout_error.py

Classifies Snowflake statement timeout (001027) and warehouse suspended (000606)
errors during dbt model execution.
"""

import re

from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
)


_TIMEOUT_RE = re.compile(
    r"(statement.+?timeout|Statement reached its statement or warehouse timeout)",
    re.IGNORECASE,
)
_WAREHOUSE_SUSPENDED_RE = re.compile(
    r"warehouse\s+'?([^'\"]+?)'?\s+was suspended",
    re.IGNORECASE,
)
_WAREHOUSE_NAME_RE = re.compile(
    r"warehouse\s+'?([A-Z_][A-Z0-9_]*)'?",
    re.IGNORECASE,
)


class TimeoutErrorClassifier(BaseClassifier):
    """Diagnoses statement timeout and warehouse suspension errors."""

    error_class = "timeout_error"

    @classmethod
    def matches(cls, message: str) -> bool:
        return bool(_TIMEOUT_RE.search(message) or _WAREHOUSE_SUSPENDED_RE.search(message))

    def diagnose(self) -> DiagnosticReport:
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        if _WAREHOUSE_SUSPENDED_RE.search(self.message):
            finding = self._diagnose_warehouse_suspended(location)
        else:
            finding = self._diagnose_timeout(location)

        report.findings.append(finding)
        return report

    def _diagnose_timeout(self, location: TraceLocation) -> DiagnosticFinding:
        warehouse = self._extract_warehouse()
        summary = "Statement reached timeout limit before completing"
        if warehouse:
            summary += f" (warehouse: {warehouse})"

        fix_parts = []
        if warehouse:
            fix_parts.append(
                f"ALTER WAREHOUSE {warehouse} SET STATEMENT_TIMEOUT_IN_SECONDS = 3600;"
            )
        fix_parts.append(
            "Or optimize the model: add clustering keys, reduce scan scope, "
            "or break into incremental loads."
        )

        return DiagnosticFinding(
            summary=summary,
            location=location,
            explanation=(
                "The model's compiled SQL took longer than the configured "
                "STATEMENT_TIMEOUT_IN_SECONDS. This can be a warehouse-level or "
                "session-level setting. Large full-table scans, missing clustering, "
                "or complex joins are common causes."
            ),
            fix_suggestion="\n".join(fix_parts),
            session_params_to_check=["STATEMENT_TIMEOUT_IN_SECONDS"],
        )

    def _diagnose_warehouse_suspended(self, location: TraceLocation) -> DiagnosticFinding:
        warehouse = self._extract_warehouse()
        summary = "Warehouse was suspended during query execution"
        if warehouse:
            summary += f" (warehouse: {warehouse})"

        fix = (
            "Check if another user or automation suspended the warehouse. "
            "Consider setting AUTO_SUSPEND to a longer interval, or use a "
            "dedicated warehouse for long-running dbt models."
        )

        return DiagnosticFinding(
            summary=summary,
            location=location,
            explanation=(
                "The warehouse was suspended (manually or via AUTO_SUSPEND) while "
                "this model was still executing. The query was cancelled."
            ),
            fix_suggestion=fix,
            session_params_to_check=["STATEMENT_TIMEOUT_IN_SECONDS"],
        )

    def _extract_warehouse(self) -> str:
        match = _WAREHOUSE_NAME_RE.search(self.message)
        return match.group(1).upper() if match else ""
