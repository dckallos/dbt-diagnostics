"""
Tests for the write-access enrichment check.

Verifies that _check_write_access_for_unmaterialized() correctly
adjusts fix suggestions based on role privileges.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from dbt_diagnostics.enrichers.enrich import _check_write_access_for_unmaterialized
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    LineageStep,
    TraceLocation,
)


def _make_unmaterialized_report(relation_name: str = "ARTWORK_DB.GOLD.DIM_ARTISTS") -> DiagnosticReport:
    """Build a runtime_error report with a missing lineage step."""
    report = DiagnosticReport(
        unique_id="test.artwork_pipeline.some_test.abc123",
        error_class="runtime_error",
        raw_message="Object does not exist",
    )
    finding = DiagnosticFinding(
        summary="Object not found: " + relation_name,
        fix_suggestion="Model has not been materialized. Run:\n  dbt run -s dim_artists",
        target_object="model.artwork_pipeline.dim_artists",
    )
    finding.lineage_trail = [
        LineageStep(
            node_id="test.artwork_pipeline.some_test.abc123",
            node_type="test",
            short_name="abc123",
            file_path="models/marts/_marts__models.yml",
            run_status="error",
        ),
        LineageStep(
            node_id="model.artwork_pipeline.dim_artists",
            node_type="model",
            short_name="dim_artists",
            relation_name=relation_name,
            file_path="models/marts/dim_artists.sql",
            live_status="missing",
            live_detail="table does NOT exist in Snowflake",
        ),
    ]
    report.findings.append(finding)
    return report


class TestWriteAccessCheck:
    """Test the write-access enrichment for unmaterialized models."""

    def test_no_create_prepends_warning(self):
        """When role lacks CREATE TABLE, fix gets a privilege warning."""
        conn = MagicMock()

        with patch(
            "dbt_diagnostics.enrichers.enrich.get_current_role",
            return_value="ARTWORK_TRANSFORMER",
        ), patch(
            "dbt_diagnostics.enrichers.enrich.check_write_access",
            return_value={
                "can_create": False,
                "has_usage": True,
                "grants_found": ["USAGE on SCHEMA ARTWORK_DB.GOLD"],
                "role_checked": "ARTWORK_TRANSFORMER",
                "schema_checked": "ARTWORK_DB.GOLD",
            },
        ):
            report = _make_unmaterialized_report()
            _check_write_access_for_unmaterialized(conn, [report])

            fix = report.findings[0].fix_suggestion
            assert "WARNING" in fix
            assert "does NOT have CREATE TABLE" in fix
            assert "GRANT CREATE TABLE" in fix
            assert "ARTWORK_TRANSFORMER" in fix
            assert "ARTWORK_DB.GOLD" in fix
            # Original fix still present after the warning
            assert "dbt run -s" in fix

    def test_has_create_adds_verification(self):
        """When role has CREATE TABLE, fix notes the verification."""
        conn = MagicMock()

        with patch(
            "dbt_diagnostics.enrichers.enrich.get_current_role",
            return_value="ARTWORK_TRANSFORMER",
        ), patch(
            "dbt_diagnostics.enrichers.enrich.check_write_access",
            return_value={
                "can_create": True,
                "has_usage": True,
                "grants_found": [
                    "USAGE on SCHEMA ARTWORK_DB.GOLD",
                    "CREATE TABLE on SCHEMA ARTWORK_DB.GOLD",
                ],
                "role_checked": "ARTWORK_TRANSFORMER",
                "schema_checked": "ARTWORK_DB.GOLD",
            },
        ):
            report = _make_unmaterialized_report()
            _check_write_access_for_unmaterialized(conn, [report])

            fix = report.findings[0].fix_suggestion
            assert "Verified" in fix
            assert "CREATE TABLE" in fix
            assert "dbt run -s" in fix
            assert "WARNING" not in fix

    def test_no_role_skips_check(self):
        """When current role can't be determined, fix is unchanged."""
        conn = MagicMock()

        with patch(
            "dbt_diagnostics.enrichers.enrich.get_current_role",
            return_value=None,
        ):
            report = _make_unmaterialized_report()
            original_fix = report.findings[0].fix_suggestion
            _check_write_access_for_unmaterialized(conn, [report])

            assert report.findings[0].fix_suggestion == original_fix

    def test_non_runtime_error_skipped(self):
        """Test failure reports are not checked for write access."""
        conn = MagicMock()

        report = DiagnosticReport(
            unique_id="test.pkg.a.1",
            error_class="test_failure",
            raw_message="Got 1 result",
        )
        report.findings.append(
            DiagnosticFinding(
                summary="Row count test failed",
                fix_suggestion="dbt test -s model",
            )
        )

        with patch(
            "dbt_diagnostics.enrichers.enrich.get_current_role",
            return_value="SOME_ROLE",
        ):
            original_fix = report.findings[0].fix_suggestion
            _check_write_access_for_unmaterialized(conn, [report])
            assert report.findings[0].fix_suggestion == original_fix

    def test_missing_usage_includes_full_grant_chain(self):
        """When role lacks both USAGE and CREATE, fix includes all GRANTs."""
        conn = MagicMock()

        with patch(
            "dbt_diagnostics.enrichers.enrich.get_current_role",
            return_value="ARTWORK_TRANSFORMER",
        ), patch(
            "dbt_diagnostics.enrichers.enrich.check_write_access",
            return_value={
                "can_create": False,
                "has_usage": False,
                "grants_found": [],
                "role_checked": "ARTWORK_TRANSFORMER",
                "schema_checked": "ARTWORK_DB.GOLD",
            },
        ):
            report = _make_unmaterialized_report()
            _check_write_access_for_unmaterialized(conn, [report])

            fix = report.findings[0].fix_suggestion
            assert "GRANT USAGE ON DATABASE" in fix
            assert "GRANT USAGE ON SCHEMA" in fix
            assert "GRANT CREATE TABLE ON SCHEMA" in fix
