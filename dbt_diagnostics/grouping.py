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
    """
    Extract short model names from a list of reports.

    Prefers the lineage trail's short_name (lowercase, from manifest unique_id)
    over the target_object field (which may be a FQ uppercase relation name).
    Falls back to lowercasing the last segment of target_object/target_identifier.
    """
    names = []
    for report in reports:
        if not report.findings:
            continue

        name = None
        for finding in report.findings:
            # Best source: lineage trail step with live_status="missing"
            # These have short_name derived from the manifest (lowercase)
            if finding.lineage_trail:
                for step in finding.lineage_trail:
                    if step.live_status == "missing" and step.short_name:
                        name = step.short_name
                        break
                if name:
                    break

            # Second best: target_object that looks like a model unique_id
            # (e.g. "model.artwork_pipeline.dim_artists")
            if finding.target_object and finding.target_object.startswith("model."):
                name = finding.target_object.split(".")[-1]
                break

            # Fallback: target_object is a FQ relation name (UPPERCASE)
            # Lowercase the last segment for dbt selector compatibility
            if finding.target_object:
                name = finding.target_object.split(".")[-1].lower()
                break
            elif finding.target_identifier:
                name = finding.target_identifier.split(".")[-1].lower()
                break

        if name and name not in names:
            names.append(name)

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
