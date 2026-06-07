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
    LineageStep,
    TraceLocation,
)
from dbt_diagnostics.tracers.column_tracer import build_schema_from_manifest
from dbt_diagnostics.tracers.snippet import extract_snippet


_NUMERIC_OVERFLOW_RE = re.compile(
    r"Numeric value\s+'?([^']*?)'?\s+is\s+(not recognized|out of range)",
    re.IGNORECASE,
)
_STRING_TOO_LONG_RE = re.compile(
    r"String\s+'([^']*)'\s+is too long", re.IGNORECASE
)
_DIVISION_BY_ZERO_RE = re.compile(r"Division by zero", re.IGNORECASE)
_ERROR_LINE_RE = re.compile(r"error line (\d+)")
_LINE_POS_RE = re.compile(r"error line (\d+) at position (\d+)")


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

        # Build compiled snippet around the error line
        snippet = None
        if self.compiled_code and location.line_number:
            pos_match = _LINE_POS_RE.search(self.message)
            error_position = int(pos_match.group(2)) if pos_match else None
            snippet = extract_snippet(
                self.compiled_code, location.line_number,
                error_position=error_position,
            )

        # Build a basic 2-node trail: failing model -> upstream source(s)
        lineage_trail = self._build_basic_trail()

        if _DIVISION_BY_ZERO_RE.search(self.message):
            finding = self._diagnose_division_by_zero(location)
        elif _STRING_TOO_LONG_RE.search(self.message):
            finding = self._diagnose_string_too_long(location)
        else:
            finding = self._diagnose_numeric_overflow(location)

        # Attach snippet and lineage trail to the finding
        finding.compiled_snippet = snippet
        finding.lineage_trail = lineage_trail

        report.findings.append(finding)
        return report

    def _build_basic_trail(self) -> list[LineageStep]:
        """
        Build a simple 2-node trail: the failing model and its immediate parents.

        Data errors originate inside the model's SQL (a cast or division),
        not from a missing column/object. The trail shows the model and
        the source(s) that supply data with potentially bad values.
        """
        trail = []

        # Step 0: the failing model itself
        node = self.context.dag_walker.get_node(self.unique_id)
        short_name = self.unique_id.split(".")[-1] if self.unique_id else "unknown"
        node_type = self.unique_id.split(".")[0] if "." in self.unique_id else "model"

        trail.append(LineageStep(
            node_id=self.unique_id,
            node_type=node_type,
            short_name=short_name,
            file_path=(node or {}).get("original_file_path"),
            relation_name=(node or {}).get("relation_name"),
            depth=0,
            manifest_status="not_checked",
            manifest_detail=None,
            run_status=self._get_run_status(self.unique_id),
            annotation="failing model (data error in expression)",
        ))

        # Step 1: immediate parents (sources or upstream models)
        parents = self.context.dag_walker.get_parents(self.unique_id)
        for pid in parents:
            parent_node = (
                self.context.dag_walker.get_node(pid)
                or self.context.dag_walker.sources.get(pid)
            )
            p_short = pid.split(".")[-1] if pid else "unknown"
            p_type = pid.split(".")[0] if "." in pid else "source"

            trail.append(LineageStep(
                node_id=pid,
                node_type=p_type,
                short_name=p_short,
                file_path=(parent_node or {}).get("original_file_path"),
                relation_name=(parent_node or {}).get("relation_name"),
                depth=1,
                manifest_status="declared",
                manifest_detail="supplies data that may contain bad values",
                run_status=self._get_run_status(pid),
                annotation=None,
            ))

        return trail

    def _get_run_status(self, unique_id: str) -> Optional[str]:
        """Look up run_status from run_results if available."""
        if not self.context.run_results:
            return None
        results = self.context.run_results.get("results", [])
        for r in results:
            if r.get("unique_id") == unique_id:
                return r.get("status")
        return None

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
