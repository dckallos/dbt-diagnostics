"""
dbt_diagnostics/classifiers/schema_change_error.py

Classifies errors where an upstream source/model schema changed (column
removed or type changed), causing downstream 'invalid identifier' failures.

Extends the RuntimeErrorClassifier's invalid_identifier handling with
richer diagnosis when live enrichment data reveals a schema drift.
"""

import re

from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
    UpstreamOrigin,
)


_INVALID_IDENTIFIER_RE = re.compile(
    r"invalid identifier\s+'([^']+)'", re.IGNORECASE
)
_ERROR_LINE_RE = re.compile(r"error line (\d+)")


class SchemaChangeErrorClassifier(BaseClassifier):
    """
    Diagnoses schema drift: column exists in manifest but not in the live table.

    This classifier matches 'invalid identifier' errors but distinguishes from
    simple typos by checking if the column is declared in the manifest's parent
    node. If it is, the column likely existed and was removed (schema drift).
    """

    error_class = "schema_change_error"

    @classmethod
    def matches(cls, message: str) -> bool:
        """
        Never match from the registry dispatcher.

        SchemaChangeError is invoked by delegation from RuntimeErrorClassifier
        when find_column_origin() confirms drift evidence (column declared in
        upstream manifest but missing at runtime). This prevents the greedy
        overlap where SchemaChangeError would claim ALL 'invalid identifier'
        messages before RuntimeError gets a chance.
        """
        return False

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

        id_match = _INVALID_IDENTIFIER_RE.search(self.message)
        column_name = id_match.group(1) if id_match else "UNKNOWN"

        # Check if the column is declared in any upstream parent
        origin = self.context.dag_walker.find_column_origin(self.unique_id, column_name)

        if origin:
            # Column IS in manifest (upstream declared it) => schema drift
            finding = self._diagnose_drift(column_name, location, origin)
        else:
            # Column is NOT in any parent's manifest declaration => simpler case
            finding = self._diagnose_possible_drift(column_name, location)

        report.findings.append(finding)
        return report

    def _diagnose_drift(
        self, column_name: str, location: TraceLocation, origin: dict
    ) -> DiagnosticFinding:
        upstream_model = origin["model"]
        upstream_file = origin.get("file", "")

        return DiagnosticFinding(
            summary=(
                f"Schema drift: column '{column_name}' declared in manifest "
                f"(from {upstream_model.split('.')[-1]}) but missing at runtime"
            ),
            location=location,
            upstream_origin=UpstreamOrigin(
                model_id=upstream_model, file_path=upstream_file
            ),
            explanation=(
                f"The column '{column_name}' exists in the manifest's column declarations "
                f"for upstream model {upstream_model}, but Snowflake reports it as invalid. "
                "This means the upstream table's schema was altered outside dbt "
                "(e.g., a column was dropped or renamed in the source system)."
            ),
            fix_suggestion=(
                f"1. Check the upstream model/source: has '{column_name}' been renamed or removed?\n"
                f"2. Run `dbt run -s {upstream_model.split('.')[-1]}` to rebuild upstream first.\n"
                f"3. Update your manifest: `dbt parse` to refresh column declarations."
            ),
            target_identifier=column_name,
        )

    def _diagnose_possible_drift(
        self, column_name: str, location: TraceLocation
    ) -> DiagnosticFinding:
        return DiagnosticFinding(
            summary=(
                f"Invalid identifier '{column_name}': possible schema change or typo"
            ),
            location=location,
            explanation=(
                f"Column '{column_name}' is not found in the target table and is also "
                "not declared in any upstream manifest node. This could be a typo in "
                "the SQL, or a column that was removed from the source without updating "
                "the dbt model."
            ),
            fix_suggestion=(
                f"1. Verify spelling of '{column_name}' against the source table.\n"
                "2. Run DESCRIBE TABLE on the upstream source to check available columns.\n"
                "3. If renamed, update this model's SQL accordingly."
            ),
            target_identifier=column_name,
        )
