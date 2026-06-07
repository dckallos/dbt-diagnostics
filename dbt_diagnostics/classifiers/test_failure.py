"""
dbt_diagnostics/classifiers/test_failure.py

Classifies dbt test assertion failures (status="fail").

These are NOT SQL compilation/runtime errors. They mean the test SQL
ran successfully but returned rows (assertion violated) or breached
a configured threshold. The test itself worked -- the data failed.
"""

import re
from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
)


# Regex patterns for extracting structured info from compiled SQL
_THRESHOLD_PATTERN = re.compile(
    r"count\(\*\)\s*>=\s*(\d+)\s+and\s+count\(\*\)\s*<=\s*(\d+)"
)
_RELATION_PATTERN = re.compile(
    r"\bfrom\s+(\w+\.\w+\.\w+)", re.IGNORECASE
)
# Extract a readable test type from dbt_expectations unique_ids
_DBT_EXPECTATIONS_TYPE_PATTERN = re.compile(
    r"dbt_expectations_(expect_\w+?)_(?:stg_|dim_|fct_|int_|raw_|src_)"
)


class TestFailureClassifier(BaseClassifier):
    """
    Handles dbt test results with status="fail".

    Unlike error classifiers, this is dispatched by status (not by message
    pattern matching). It is NOT registered in CLASSIFIER_REGISTRY -- it is
    called directly from _diagnose_all() for fail-status results.
    """

    error_class = "test_failure"

    @classmethod
    def matches(cls, message: str) -> bool:
        # Not used for dispatch -- test failures are dispatched by status
        return False

    def diagnose(self) -> DiagnosticReport:
        report = DiagnosticReport(
            unique_id=self.unique_id,
            error_class=self.error_class,
            raw_message=self.message,
        )

        # Extract test metadata
        test_name = self._extract_test_name()
        tested_model = self._extract_tested_model()
        failures_count = self.result.get("failures", None)
        compiled_sql = self.result.get("compiled_code", "") or ""

        # Extract structured info from compiled SQL
        threshold = self._extract_threshold(compiled_sql)
        relation = self._extract_relation(compiled_sql)
        query_id = self._extract_query_id()

        # Build summary
        if threshold:
            summary = f"Row count expected between {threshold[0]:,} and {threshold[1]:,}"
        elif tested_model:
            summary = f"Test '{test_name}' failed on model {tested_model}"
        else:
            summary = f"Test '{test_name}' failed"

        if failures_count is not None and not threshold:
            summary += f" ({failures_count} record(s) violated the assertion)"

        # Build location from test file path
        test_node = self.context.dag_walker.get_node(self.unique_id)
        file_path = None
        if test_node:
            file_path = test_node.get("original_file_path") or test_node.get("path")

        location = TraceLocation(file_path=file_path)

        # Build fix suggestion
        fix = self._build_fix_suggestion(tested_model, relation, threshold)

        # Build explanation
        explanation = (
            "This is a test assertion failure, not a SQL error. "
            "The test query executed successfully but returned rows that "
            "violate the assertion (e.g., row count outside expected range, "
            "unexpected NULLs, duplicate keys). "
            "The model SQL is correct -- the DATA is the problem."
        )

        finding = DiagnosticFinding(
            summary=summary,
            location=location,
            explanation=explanation,
            fix_suggestion=fix,
            target_object=tested_model,
            target_identifier=relation,
        )

        # Attach structured metadata as additional report context
        report.findings.append(finding)

        # Store extra metadata on the report for template consumption
        report.threshold = threshold
        report.relation = relation
        report.query_id = query_id
        report.dbt_message = self.message

        return report

    def _extract_test_name(self) -> str:
        """Extract a human-readable test name from the unique_id."""
        parts = self.unique_id.split(".")
        if len(parts) < 3:
            return self.unique_id

        test_part = parts[2]

        # Try to extract dbt_expectations test type
        match = _DBT_EXPECTATIONS_TYPE_PATTERN.match(test_part)
        if match:
            return match.group(1).replace("_", " ")

        # Fallback: return the test name portion
        return ".".join(parts[2:])

    def _extract_tested_model(self) -> Optional[str]:
        """
        Determine which model this test is testing.

        Uses depends_on.nodes from the manifest to find the model ref.
        """
        test_node = self.context.dag_walker.get_node(self.unique_id)
        if not test_node:
            return None

        depends_on = test_node.get("depends_on", {}).get("nodes", [])
        # Filter to model dependencies (not sources)
        model_deps = [d for d in depends_on if d.startswith("model.")]
        if model_deps:
            return model_deps[0]
        return None

    @staticmethod
    def _extract_threshold(compiled_sql: str) -> Optional[tuple[int, int]]:
        """
        Parse row-count thresholds from compiled test SQL.

        Returns (min_rows, max_rows) or None if not a row-count test.
        """
        match = _THRESHOLD_PATTERN.search(compiled_sql)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return None

    @staticmethod
    def _extract_relation(compiled_sql: str) -> Optional[str]:
        """
        Extract the fully-qualified relation name from compiled test SQL.

        Looks for 'from DB.SCHEMA.TABLE' pattern.
        """
        match = _RELATION_PATTERN.search(compiled_sql)
        if match:
            return match.group(1)
        return None

    def _extract_query_id(self) -> Optional[str]:
        """Extract the Snowflake query_id from adapter_response."""
        adapter_resp = self.result.get("adapter_response", {})
        return adapter_resp.get("query_id")

    def _build_fix_suggestion(
        self,
        tested_model: Optional[str],
        relation: Optional[str],
        threshold: Optional[tuple[int, int]],
    ) -> str:
        """Build an actionable fix suggestion with concrete SQL."""
        model_short = ""
        if tested_model:
            model_short = (
                tested_model.split(".")[-1] if "." in tested_model else tested_model
            )

        lines = ["Investigate the failing rows:"]

        if relation:
            lines.append("  1. Check current row count:")
            lines.append(f"     SELECT COUNT(*) FROM {relation};")
        else:
            lines.append("  1. Run the test SQL manually to see which rows fail:")
            if model_short:
                lines.append(f"     dbt test -s {model_short} --store-failures")

        if model_short:
            lines.append("  2. If empty, run the upstream pipeline:")
            lines.append(f"     dbt run -s +{model_short}")
            lines.append("  3. Re-run with stored failures for inspection:")
            lines.append(f"     dbt test -s {model_short} --store-failures")
        else:
            lines.append("  2. Run the test with --store-failures to inspect:")
            lines.append("     dbt test -s <test_name> --store-failures")

        return "\n".join(lines)
