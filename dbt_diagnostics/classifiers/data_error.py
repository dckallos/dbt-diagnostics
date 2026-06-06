"""
dbt_diagnostics/classifiers/data_error.py

Classifies Snowflake data errors: numeric overflow (100132),
string too long (100078), and division by zero (100035).
"""

import re
from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
)
from dbt_diagnostics.tracers.column_tracer import build_schema_from_manifest


_NUMERIC_OVERFLOW_RE = re.compile(
    r"Numeric value\s+'?([^']*?)'?\s+is\s+(not recognized|out of range)",
    re.IGNORECASE,
)
_STRING_TOO_LONG_RE = re.compile(
    r"String\s+'([^']*)'\s+is too long", re.IGNORECASE
)
_DIVISION_BY_ZERO_RE = re.compile(r"Division by zero", re.IGNORECASE)
_ERROR_LINE_RE = re.compile(r"error line (\d+)")


class DataErrorClassifier(BaseClassifier):
    """Diagnoses data-type and arithmetic errors at query runtime."""

    error_class = "data_error"

    @classmethod
    def matches(cls, message: str) -> bool:
        return bool(
            _NUMERIC_OVERFLOW_RE.search(message)
            or _STRING_TOO_LONG_RE.search(message)
            or _DIVISION_BY_ZERO_RE.search(message)
        )

    def diagnose(self) -> DiagnosticReport:
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        model_path = self.context.dag_walker.get_model_path(self.unique_id)
        location = TraceLocation(file_path=model_path or None)

        line_match = _ERROR_LINE_RE.search(self.message)
        if line_match:
            location.line_number = int(line_match.group(1))

        if _DIVISION_BY_ZERO_RE.search(self.message):
            finding = self._diagnose_division_by_zero(location)
        elif _STRING_TOO_LONG_RE.search(self.message):
            finding = self._diagnose_string_too_long(location)
        else:
            finding = self._diagnose_numeric_overflow(location)

        report.findings.append(finding)
        return report

    def _diagnose_numeric_overflow(self, location: TraceLocation) -> DiagnosticFinding:
        match = _NUMERIC_OVERFLOW_RE.search(self.message)
        value = match.group(1) if match else "?"

        return DiagnosticFinding(
            summary=f"Numeric overflow: value '{value}' out of range for target type",
            location=location,
            explanation=(
                "A value in the source data exceeds the range of the target column type. "
                "This commonly happens when casting strings to NUMBER with insufficient "
                "precision, or when upstream data contains unexpected large values."
            ),
            fix_suggestion=(
                "Use TRY_CAST(value AS target_type) to safely handle out-of-range values,\n"
                "or widen the target column precision (e.g., NUMBER(38,0) instead of NUMBER(10,0))."
            ),
        )

    def _diagnose_string_too_long(self, location: TraceLocation) -> DiagnosticFinding:
        match = _STRING_TOO_LONG_RE.search(self.message)
        value_preview = match.group(1)[:50] if match else "?"

        return DiagnosticFinding(
            summary=f"String value too long for target column",
            location=location,
            explanation=(
                f"A string value (starting with '{value_preview}...') exceeds the "
                "maximum length of the target column. This is common with free-text "
                "fields or concatenated values."
            ),
            fix_suggestion=(
                "Widen the target column (e.g., VARCHAR(16777216) for max),\n"
                "or truncate: LEFT(value, max_len) AS column_name."
            ),
        )

    def _diagnose_division_by_zero(self, location: TraceLocation) -> DiagnosticFinding:
        return DiagnosticFinding(
            summary="Division by zero in expression",
            location=location,
            explanation=(
                "A division operation encountered a zero divisor at runtime. "
                "This typically happens with ratio/percentage calculations when "
                "the denominator column contains zeros or NULLs."
            ),
            fix_suggestion=(
                "Wrap the divisor: NULLIF(divisor, 0) to return NULL instead of error,\n"
                "or use IFF(divisor = 0, NULL, numerator / divisor) AS result."
            ),
        )
