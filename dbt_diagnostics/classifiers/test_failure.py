"""
dbt_diagnostics/classifiers/test_failure.py

Classifies dbt test assertion failures (status="fail").

These are NOT SQL compilation/runtime errors. They mean the test SQL
ran successfully but returned rows (assertion violated) or breached
a configured threshold. The test itself worked -- the data failed.
"""

from typing import Optional

from dbt_diagnostics.classifiers.base import BaseClassifier, DiagnosticContext
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
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

        # Build summary
        if tested_model:
            summary = f"Test '{test_name}' failed on model {tested_model}"
        else:
            summary = f"Test '{test_name}' failed"

        if failures_count is not None:
            summary += f" ({failures_count} record(s) violated the assertion)"

        # Build location from test file path
        test_node = self.context.dag_walker.get_node(self.unique_id)
        file_path = None
        if test_node:
            file_path = test_node.get("original_file_path") or test_node.get("path")

        location = TraceLocation(file_path=file_path)

        # Build fix suggestion
        if tested_model:
            model_short = tested_model.split(".")[-1] if "." in tested_model else tested_model
            fix = (
                f"Investigate the failing rows:\n"
                f"  1. Run the test SQL manually to see which rows fail:\n"
                f"     dbt test -s {model_short} --store-failures\n"
                f"  2. Check the source data in model '{model_short}' for "
                f"data quality issues."
            )
        else:
            fix = (
                "Run the test SQL manually to inspect failing rows:\n"
                "  dbt test -s <test_name> --store-failures"
            )

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
        )

        # Attach compiled SQL as a note (useful for debugging)
        if compiled_sql:
            finding.target_identifier = "(see compiled SQL)"

        report.findings.append(finding)
        return report

    def _extract_test_name(self) -> str:
        """Extract a readable test name from the unique_id."""
        # unique_id like: test.artwork_pipeline.dbt_expectations_expect_table_row_count_to_be_between_stg_met__artworks_1_None.abc123
        parts = self.unique_id.split(".")
        if len(parts) >= 3:
            # Return the test name portion (everything after project name)
            return ".".join(parts[2:])
        return self.unique_id

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
