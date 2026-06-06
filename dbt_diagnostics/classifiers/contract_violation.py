"""
dbt_diagnostics/classifiers/contract_violation.py

Classifies and diagnoses dbt model contract violations. Parses the mismatch
table from the error message, then uses the column tracer and DAG walker to
find the root cause (file, line, CTE, expression).
"""

import re
from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
    UpstreamOrigin,
)


# Regex for pipe-delimited mismatch table rows
_TABLE_ROW_RE = re.compile(
    r"\|\s*(?P<column_name>\S+)\s*\|"
    r"\s*(?P<definition_type>[^|]*?)\s*\|"
    r"\s*(?P<contract_type>[^|]*?)\s*\|"
    r"\s*(?P<mismatch_reason>[^|]*?)\s*\|"
)
_HEADER_RE = re.compile(r"\|\s*column_name\s*\|", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"\|\s*-+\s*\|")

# Session params relevant to specific type mismatches
TIMESTAMP_PARAMS = [
    "TIMESTAMP_TYPE_MAPPING",
    "TIMESTAMP_INPUT_FORMAT",
    "TIMESTAMP_OUTPUT_FORMAT",
    "TIMEZONE",
]


def parse_mismatch_table(message: str) -> list[dict]:
    """Extract structured mismatch records from the pipe-delimited error table."""
    records = []
    for line in message.splitlines():
        line = line.strip()
        if _HEADER_RE.search(line) or _SEPARATOR_RE.search(line):
            continue
        match = _TABLE_ROW_RE.search(line)
        if match:
            records.append({
                "column_name": match.group("column_name").strip(),
                "definition_type": match.group("definition_type").strip(),
                "contract_type": match.group("contract_type").strip(),
                "mismatch_reason": match.group("mismatch_reason").strip(),
            })
    return records


class ContractViolationClassifier(BaseClassifier):
    """Diagnoses a dbt contract violation with full root cause tracing."""

    error_class = "contract_violation"

    @classmethod
    def matches(cls, message: str) -> bool:
        return "enforced contract that failed" in message

    def diagnose(self) -> DiagnosticReport:
        """Run the full diagnosis and return a structured report."""
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        mismatches = parse_mismatch_table(self.message)
        if not mismatches:
            report.findings.append(DiagnosticFinding(
                summary="Could not parse mismatch table from error message.",
            ))
            return report

        for mismatch in mismatches:
            finding = self._diagnose_single_mismatch(mismatch)
            report.findings.append(finding)

        return report

    def _diagnose_single_mismatch(self, mismatch: dict) -> DiagnosticFinding:
        """Diagnose one column mismatch: trace the column, find root cause."""
        col = mismatch["column_name"]
        def_type = mismatch["definition_type"] or "(missing)"
        con_type = mismatch["contract_type"] or "(missing)"
        reason = mismatch["mismatch_reason"]

        summary = (
            f"Column {col}: model produces {def_type}, "
            f"contract expects {con_type} ({reason})"
        )

        # Trace the column through compiled SQL (sqlglot)
        location = TraceLocation()
        if self.compiled_code:
            trace_result = self.context.column_tracer.trace_column(
                col, self.compiled_code
            )
            if trace_result:
                location.cte_name = trace_result.cte_name
                location.expression = trace_result.expression

        # Find the source file and line number
        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        if model_path:
            location.file_path = model_path
            source_file = self.context.models_dir.parent / model_path
            line = self.context.column_tracer.find_line_number(source_file, col)
            if line:
                location.line_number = line

        # Trace upstream to find if column is inherited or introduced here
        upstream_origin = None
        origin = self.context.dag_walker.find_column_origin(self.unique_id, col)
        if origin:
            upstream_origin = UpstreamOrigin(
                model_id=origin["model"],
                file_path=origin.get("file"),
            )

        # Build explanation
        explanation = self._build_explanation(
            col, def_type, con_type, reason, location, upstream_origin
        )

        # Build fix suggestion
        fix = self._build_fix_suggestion(col, def_type, con_type, location)

        # Session params
        params = []
        diagnostic = []
        if "TIMESTAMP" in def_type or "TIMESTAMP" in con_type:
            params = TIMESTAMP_PARAMS
            diagnostic = ["TIMESTAMP_TYPE_MAPPING"]

        return DiagnosticFinding(
            summary=summary,
            location=location,
            upstream_origin=upstream_origin,
            explanation=explanation,
            fix_suggestion=fix,
            session_params_to_check=params,
            diagnostic_params=diagnostic,
        )

    def _build_explanation(
        self, col, def_type, con_type, reason, location, upstream_origin
    ) -> str:
        """Build a human-readable explanation of WHY the mismatch occurs."""
        parts = []

        if reason == "missing in definition":
            parts.append(
                f"The contract declares {col} but the model SQL does not produce it."
            )
        elif reason == "missing in contract":
            parts.append(
                f"The model SQL produces {col} but the contract does not declare it."
            )
        elif location.expression:
            expr_upper = location.expression.upper()
            if "CURRENT_TIMESTAMP" in expr_upper:
                parts.append(
                    "CURRENT_TIMESTAMP() returns TIMESTAMP_LTZ by default in Snowflake. "
                    "The account parameter TIMESTAMP_TYPE_MAPPING controls this."
                )
            elif "SYSDATE" in expr_upper:
                parts.append("SYSDATE() returns TIMESTAMP_LTZ in Snowflake.")
            else:
                parts.append(
                    f"The expression `{location.expression}` produces {def_type}."
                )

        if upstream_origin:
            parts.append(
                f"This column is INHERITED from {upstream_origin.model_id}."
            )
        else:
            parts.append(
                "This column is INTRODUCED in this model (not inherited from upstream)."
            )

        return " ".join(parts)

    def _build_fix_suggestion(
        self, col, def_type, con_type, location
    ) -> Optional[str]:
        """Suggest a fix if we can determine one."""
        if not location.expression:
            return None

        expr_upper = location.expression.upper()
        if "CURRENT_TIMESTAMP" in expr_upper and "NTZ" in con_type.upper():
            return f"Cast explicitly: CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS {col.lower()}"
        if "SYSDATE" in expr_upper and "NTZ" in con_type.upper():
            return f"Cast explicitly: SYSDATE()::TIMESTAMP_NTZ AS {col.lower()}"
        return None
