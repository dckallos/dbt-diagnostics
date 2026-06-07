"""
dbt_diagnostics/enrichers/enrich.py

Orchestrator: takes classified DiagnosticReports and enriches their findings
with live Snowflake data. Each error class gets different enrichment logic.
"""

import re
from typing import Optional

from dbt_diagnostics.models import (
    DiagnosticReport,
    DisconnectVerdict,
    EnrichmentData,
    ColumnInfo,
)
from dbt_diagnostics.enrichers.params import get_parameters, get_parameter_with_level
from dbt_diagnostics.enrichers.schema_inspector import (
    describe_table,
    table_exists,
    find_similar_columns,
    _edit_distance,
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

            # Enrich lineage trail steps with live DESCRIBE TABLE data
            if finding.lineage_trail:
                _enrich_lineage_trail(conn, finding)

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

    # Object not found: check existence + describe.
    # Prefer structured target_object field; fall back to regex on summary.
    fq_name = finding.target_object
    if not fq_name:
        obj_match = _OBJECT_RE.search(finding.summary)
        if obj_match:
            fq_name = obj_match.group(1)

    if fq_name:
        enrichment.object_exists = table_exists(conn, fq_name)
        if enrichment.object_exists:
            enrichment.actual_columns = describe_table(conn, fq_name)

    # Invalid identifier: describe the source table to find correct columns.
    # Prefer structured target_identifier field; fall back to regex on summary.
    identifier = finding.target_identifier
    if not identifier:
        id_match = _IDENTIFIER_RE.search(finding.summary)
        if id_match:
            identifier = id_match.group(1)

    if identifier:
        # Try to extract the source table from compiled_code
        source_table = _extract_from_table(report)
        if source_table:
            columns = describe_table(conn, source_table)
            if columns:
                enrichment.actual_columns = columns
                suggestions = find_similar_columns(columns, identifier)
                if suggestions:
                    # Compute edit distance for the top suggestion
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
        priv_fq_name = priv_match.group(1)
        enrichment.object_exists = table_exists(conn, priv_fq_name)

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


def _enrich_lineage_trail(conn, finding) -> None:
    """
    For each LineageStep with a relation_name, run DESCRIBE TABLE to populate
    live_status and live_detail. For column-lineage findings, also checks
    whether the specific target column exists in each relation.

    This uses cloud-services-layer metadata queries (DESCRIBE TABLE, table_exists)
    which cost $0 and don't require a running warehouse.
    """
    for step in finding.lineage_trail:
        if not step.relation_name:
            continue

        try:
            exists = table_exists(conn, step.relation_name)
        except Exception:
            # Graceful degradation: if DESCRIBE fails, leave live fields None
            continue

        if exists:
            step.live_status = "exists"
            # For column-lineage: check if specific column is present
            if finding.target_identifier:
                try:
                    cols = describe_table(conn, step.relation_name)
                    col_names = [c.name.upper() for c in cols]
                    target_upper = finding.target_identifier.upper()
                    if target_upper in col_names:
                        step.live_detail = f"column '{finding.target_identifier}' found"
                    else:
                        step.live_status = "no_column"
                        step.live_detail = (
                            f"column '{finding.target_identifier}' NOT found"
                        )
                except Exception:
                    step.live_detail = "table exists (column check failed)"
            else:
                step.live_detail = "table exists"
        else:
            step.live_status = "missing"
            step.live_detail = "table does NOT exist in Snowflake"

    # After populating live_status, identify the disconnect point
    _identify_disconnect(finding)


def _identify_disconnect(finding) -> None:
    """
    Scan the lineage trail for the point where status flips from passing to
    failing. Sets finding.disconnect with a DisconnectVerdict.

    A node is "passing" if live_status is "exists" or manifest_status is
    "declared". A node is "failing" if live_status is "missing"/"no_column"
    or manifest_status is "not_found"/"missing".
    """
    trail = finding.lineage_trail
    if len(trail) < 2:
        return
    # Don't overwrite an existing disconnect verdict from the classifier
    if finding.disconnect is not None:
        return

    for i in range(len(trail) - 1):
        current = trail[i]
        next_step = trail[i + 1]
        if _is_passing(current) and _is_failing(next_step):
            finding.disconnect = DisconnectVerdict(
                between_node_a=next_step.short_name,
                between_node_b=current.short_name,
                explanation=_build_verdict_text(current, next_step, finding),
                confidence="high" if next_step.live_status else "medium",
            )
            return

    # No clear pass->fail boundary but there are failures
    failing_steps = [s for s in trail if _is_failing(s)]
    if failing_steps:
        last_fail = failing_steps[-1]
        finding.disconnect = DisconnectVerdict(
            between_node_a=trail[0].short_name,
            between_node_b=last_fail.short_name,
            explanation=(
                f"'{last_fail.short_name}' is the furthest upstream failure."
            ),
            confidence="low",
        )


def _is_passing(step) -> bool:
    """A step is passing if live says exists or manifest says declared."""
    if step.live_status == "exists":
        return True
    if step.live_status in ("missing", "no_column"):
        return False
    if step.manifest_status == "declared":
        return True
    if step.run_status == "pass":
        return True
    return False


def _is_failing(step) -> bool:
    """A step is failing if live/manifest/run indicate absence or error."""
    if step.live_status in ("missing", "no_column"):
        return True
    if step.manifest_status in ("not_found", "missing"):
        return True
    if step.run_status == "error":
        return True
    return False


def _build_verdict_text(passing_step, failing_step, finding) -> str:
    """Build a human-readable verdict explanation."""
    target = finding.target_identifier or "target"
    if failing_step.live_status == "missing":
        return (
            f"'{failing_step.short_name}' does not exist in Snowflake. "
            f"'{passing_step.short_name}' references it but it was never materialized."
        )
    if failing_step.live_status == "no_column":
        return (
            f"'{failing_step.short_name}' exists but column '{target}' is not present. "
            f"The column may have been renamed or removed."
        )
    if failing_step.manifest_status in ("not_found", "missing"):
        return (
            f"'{failing_step.short_name}' is not declared in the dbt manifest. "
            f"It may be a typo or the source/model was never added."
        )
    return (
        f"Disconnect between '{passing_step.short_name}' and "
        f"'{failing_step.short_name}'."
    )


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

    Uses the structured definition_type/contract_type fields on DiagnosticFinding
    (populated by the contract violation classifier) instead of parsing the summary.

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

            # Use structured fields directly (no summary parsing)
            contract_type = (finding.contract_type or "").upper()
            model_type = (finding.definition_type or "").upper()

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
