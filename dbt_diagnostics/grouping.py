"""
dbt_diagnostics/grouping.py

Post-classification grouping of related diagnostic reports.

When multiple test failures share a common root cause (e.g., several tests
all fail because their target model was never materialized), this module
groups them into a single presentation unit with a combined fix command.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from dbt_diagnostics.models import DiagnosticReport


@dataclass
class ReportGroup:
    """A group of related reports sharing a common root cause."""
    key: str  # grouping key (e.g. "runtime_error:ARTWORK_DB.GOLD")
    title: str  # human-readable group title
    reports: list[DiagnosticReport] = field(default_factory=list)
    combined_fix: Optional[str] = None
    error_class: str = ""  # for template dispatching


def _extract_schema_prefix(report: DiagnosticReport) -> Optional[str]:
    """
    Extract the DB.SCHEMA prefix from a report's target.

    For runtime_error: from the lineage trail's relation_name.
    For test_failure: from the report.relation field.
    """
    # Try report-level relation (test_failure classifier sets this)
    if report.relation:
        parts = report.relation.split(".")
        if len(parts) >= 2:
            return ".".join(parts[:2])

    # Try lineage trail (runtime_error classifier sets this)
    if report.findings:
        for finding in report.findings:
            if finding.lineage_trail:
                for step in finding.lineage_trail:
                    if step.relation_name:
                        parts = step.relation_name.split(".")
                        if len(parts) >= 2:
                            return ".".join(parts[:2])
            # Try target_identifier
            if finding.target_identifier:
                parts = finding.target_identifier.split(".")
                if len(parts) >= 2:
                    return ".".join(parts[:2])

    # Try raw_message for "Object 'DB.SCHEMA.TABLE'" pattern
    match = re.search(r"Object '(\w+\.\w+)\.\w+'|Object not found: (\w+\.\w+)\.\w+",
                      report.raw_message)
    if match:
        return match.group(1) or match.group(2)

    return None


def _extract_model_names(reports: list[DiagnosticReport]) -> list[str]:
    """Extract short model names from a list of reports."""
    names = []
    for report in reports:
        if report.findings:
            for finding in report.findings:
                if finding.target_object:
                    short = finding.target_object.split(".")[-1]
                    if short not in names:
                        names.append(short)
                    break
                elif finding.target_identifier:
                    short = finding.target_identifier.split(".")[-1]
                    if short not in names:
                        names.append(short)
                    break
    return names


def group_reports(
    reports: list[DiagnosticReport],
    min_group_size: int = 2,
) -> tuple[list[ReportGroup], list[DiagnosticReport]]:
    """
    Group related reports by common root cause.

    Returns (groups, ungrouped) where:
    - groups: list of ReportGroup with >= min_group_size members
    - ungrouped: reports that don't belong to any group
    """
    # Build grouping key for each report
    keyed: dict[str, list[DiagnosticReport]] = {}
    unkeyed: list[DiagnosticReport] = []

    for report in reports:
        schema_prefix = _extract_schema_prefix(report)
        if schema_prefix:
            key = f"{report.error_class}:{schema_prefix}"
            keyed.setdefault(key, []).append(report)
        else:
            unkeyed.append(report)

    # Build groups from keys with enough members
    groups = []
    for key, group_reports_list in keyed.items():
        if len(group_reports_list) >= min_group_size:
            error_class = key.split(":")[0]
            schema = key.split(":")[1] if ":" in key else ""
            model_names = _extract_model_names(group_reports_list)

            # Build title based on error class
            if error_class == "runtime_error":
                title = (
                    f"{len(group_reports_list)} tests failed -- "
                    f"{schema} models not yet materialized"
                )
                combined_fix = (
                    f"These models have not been materialized yet. Run:\n"
                    f"  dbt run -s {' '.join(model_names)}\n"
                    f"Then re-run tests:\n"
                    f"  dbt test -s {' '.join(model_names)}"
                )
            elif error_class == "test_failure":
                title = (
                    f"{len(group_reports_list)} test assertion failures "
                    f"in {schema}"
                )
                combined_fix = (
                    f"Check row counts in {schema}:\n"
                    f"  dbt run -s {' '.join('+' + n for n in model_names)}\n"
                    f"Then re-run tests:\n"
                    f"  dbt test -s {' '.join(model_names)}"
                )
            else:
                title = (
                    f"{len(group_reports_list)} related {error_class} failures "
                    f"in {schema}"
                )
                combined_fix = None

            group = ReportGroup(
                key=key,
                title=title,
                reports=group_reports_list,
                combined_fix=combined_fix,
                error_class=error_class,
            )
            groups.append(group)
        else:
            # Not enough to form a group -- render individually
            unkeyed.extend(group_reports_list)

    return groups, unkeyed
