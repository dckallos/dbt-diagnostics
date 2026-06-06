"""
dbt_diagnostics/enrichers/enrich.py

Orchestrator: takes classified DiagnosticReports and enriches their findings
with live Snowflake data. Each error class gets different enrichment logic.
"""

import re
from typing import Optional

from dbt_diagnostics.models import DiagnosticReport, EnrichmentData, ColumnInfo
from dbt_diagnostics.enrichers.params import get_parameters, get_parameter_with_level
from dbt_diagnostics.enrichers.schema_inspector import (
    describe_table,
    table_exists,
    find_similar_columns,
)
from dbt_diagnostics.enrichers.query_history import find_matching_query


# Regex to extract FQ object name from finding summaries
_OBJECT_RE = re.compile(r"Object not found: (\S+)")
_IDENTIFIER_RE = re.compile(r"Invalid identifier: (\S+)")
_PRIVILEGE_RE = re.compile(r"privileges on \w+ (\S+)")


def enrich_reports(conn, reports: list[DiagnosticReport], run_results: dict):
    """
    Enrich all reports in-place with live Snowflake data.
    Modifies finding.enrichment on each DiagnosticFinding.
    After enrichment, runs reconciliation to adjust fix suggestions
    based on actual parameter values.
    """
    for report in reports:
        # Find the matching result for timing info
        result_data = _find_result(run_results, report.unique_id)

        for finding in report.findings:
            if report.error_class == "contract_violation":
                _enrich_contract_violation(conn, finding)
            elif report.error_class == "runtime_error":
                _enrich_runtime_error(conn, finding, report, result_data)

    # Post-enrichment reconciliation pass
    _reconcile_findings(reports)


def _enrich_contract_violation(conn, finding):
    """Enrich contract violations with actual session parameter values."""
    if not finding.session_params_to_check:
        return

    param_values = get_parameters(conn, finding.session_params_to_check)
    if param_values:
        enrichment = finding.enrichment or EnrichmentData()
        enrichment.actual_param_values = param_values

        # Get the level for the primary param (TIMESTAMP_TYPE_MAPPING)
        if "TIMESTAMP_TYPE_MAPPING" in finding.session_params_to_check:
            detail = get_parameter_with_level(conn, "TIMESTAMP_TYPE_MAPPING")
            if detail:
                level = detail.get("level") or "default"
                enrichment.actual_param_values["_TIMESTAMP_TYPE_MAPPING_LEVEL"] = level

        finding.enrichment = enrichment


def _enrich_runtime_error(conn, finding, report, result_data):
    """Enrich runtime errors with table existence, column lists, or query history."""
    enrichment = finding.enrichment or EnrichmentData()

    # Object not found: check existence + describe
    obj_match = _OBJECT_RE.search(finding.summary)
    if obj_match:
        fq_name = obj_match.group(1)
        enrichment.object_exists = table_exists(conn, fq_name)
        if enrichment.object_exists:
            enrichment.actual_columns = describe_table(conn, fq_name)

    # Invalid identifier: describe the source table to find correct columns
    id_match = _IDENTIFIER_RE.search(finding.summary)
    if id_match:
        identifier = id_match.group(1)
        # Try to extract the source table from compiled_code
        source_table = _extract_from_table(report)
        if source_table:
            columns = describe_table(conn, source_table)
            if columns:
                enrichment.actual_columns = columns
                suggestions = find_similar_columns(columns, identifier)
                if suggestions:
                    # Compute edit distance for the top suggestion
                    from dbt_diagnostics.enrichers.schema_inspector import _edit_distance
                    top = suggestions[0]
                    dist = _edit_distance(identifier.upper(), top.upper())
                    finding.fix_suggestion = (
                        f"Did you mean: {top}? (edit distance: {dist})\n"
                        f"Available columns in {source_table}:\n"
                        + "\n".join(f"  {c.name} ({c.data_type})" for c in columns[:15])
                    )

    # Privilege errors: check if object exists (to disambiguate)
    priv_match = _PRIVILEGE_RE.search(finding.summary)
    if priv_match:
        fq_name = priv_match.group(1)
        enrichment.object_exists = table_exists(conn, fq_name)

    # Query history: try to find the exact error from Snowflake
    if result_data:
        timing = result_data.get("timing", [])
        execute_timing = next((t for t in timing if t["name"] == "execute"), None)
        if execute_timing:
            compiled = result_data.get("compiled_code", "")
            match = find_matching_query(
                conn,
                compiled,
                execute_timing.get("started_at", ""),
                execute_timing.get("completed_at", ""),
            )
            if match:
                enrichment.matched_query_text = match["query_text"]
                enrichment.matched_error_message = match["error_message"]
                enrichment.matched_error_code = match["error_code"]

    finding.enrichment = enrichment


def _find_result(run_results: dict, unique_id: str) -> Optional[dict]:
    """Find the run_results entry for a given unique_id."""
    for result in run_results.get("results", []):
        if result.get("unique_id") == unique_id:
            return result
    return None


def _extract_from_table(report: DiagnosticReport) -> Optional[str]:
    """
    Extract the FROM table name from the raw_message or compiled code.
    Looks for fully-qualified Snowflake names (DB.SCHEMA.TABLE).
    """
    # Look for "FROM DB.SCHEMA.TABLE" in the message
    match = re.search(
        r"FROM\s+([A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]*)",
        report.raw_message,
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def _reconcile_findings(reports: list[DiagnosticReport]):
    """
    Post-enrichment reconciliation pass.

    For contract violations with TIMESTAMP_TYPE_MAPPING in the enrichment data,
    checks whether the live parameter value is consistent with the error and
    adjusts the fix suggestion accordingly.

    Scenarios:
    1. Live mapping matches the CONTRACT expectation (both NTZ):
       The current session is correctly configured. The failing build must have
       run under different session settings. Replace the cast suggestion with
       advice to check the build-time role/warehouse.
    2. Live mapping does NOT match the contract (mapping is LTZ, contract wants NTZ):
       Keep the cast suggestion -- the parameter is the root cause.
    3. Live mapping matches what the MODEL produced (both LTZ):
       The parameter is the confirmed root cause. Strengthen the fix message.
    """
    for report in reports:
        if report.error_class != "contract_violation":
            continue

        for finding in report.findings:
            if not finding.enrichment:
                continue
            if "TIMESTAMP_TYPE_MAPPING" not in finding.enrichment.actual_param_values:
                continue

            actual_mapping = finding.enrichment.actual_param_values[
                "TIMESTAMP_TYPE_MAPPING"
            ].upper()

            # Parse the expected type from the summary
            # Summary format: "Column X: model produces DEF_TYPE, contract expects CON_TYPE (...)"
            summary = finding.summary.upper()
            contract_type = _extract_type_from_summary(summary, "CONTRACT EXPECTS")
            model_type = _extract_type_from_summary(summary, "MODEL PRODUCES")

            if not contract_type:
                continue

            if actual_mapping == "TIMESTAMP_NTZ" and "NTZ" in contract_type:
                # Scenario 1: mapping already matches what the contract wants
                finding.fix_suggestion = (
                    "Your current TIMESTAMP_TYPE_MAPPING is NTZ (matches the contract). "
                    "The failing build ran under different session settings "
                    "(different role/warehouse may have a session-level override). "
                    "Verify the role and warehouse in your dbt profile match "
                    "what dbt uses at build time."
                )
            elif actual_mapping == "TIMESTAMP_LTZ" and "NTZ" in contract_type:
                # Scenario 2: mapping is LTZ, contract wants NTZ -- cast is correct
                # Keep existing fix but strengthen it
                if finding.fix_suggestion:
                    finding.fix_suggestion = (
                        f"CONFIRMED: TIMESTAMP_TYPE_MAPPING = TIMESTAMP_LTZ "
                        f"(set at {finding.enrichment.actual_param_values.get('_TIMESTAMP_TYPE_MAPPING_LEVEL', 'unknown')} level) "
                        f"causes CURRENT_TIMESTAMP() to return LTZ.\n"
                        f"{finding.fix_suggestion}"
                    )
            elif model_type and actual_mapping in model_type:
                # Scenario 3: mapping matches what the model produced
                if finding.fix_suggestion:
                    finding.fix_suggestion = (
                        f"ROOT CAUSE CONFIRMED: TIMESTAMP_TYPE_MAPPING = {actual_mapping} "
                        f"is producing the {model_type} output.\n"
                        f"{finding.fix_suggestion}"
                    )


def _extract_type_from_summary(summary: str, prefix: str) -> Optional[str]:
    """Extract a type like TIMESTAMP_NTZ from a summary string after a prefix."""
    idx = summary.find(prefix)
    if idx < 0:
        return None
    after = summary[idx + len(prefix):].strip()
    # Take the first word (the type)
    parts = after.split()
    if parts:
        return parts[0].strip(",()")
    return None
