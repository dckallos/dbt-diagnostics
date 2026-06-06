"""
Tests for the enrichers module using mocked Snowflake connections.
No real Snowflake connection needed.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dbt_diagnostics.enrichers.connection import (
    _resolve_env_vars,
    _resolve_profile_values,
    parse_profile,
)
from dbt_diagnostics.enrichers.params import get_parameters, get_parameter_with_level
from dbt_diagnostics.enrichers.schema_inspector import (
    describe_table,
    table_exists,
    find_similar_columns,
)
from dbt_diagnostics.enrichers.query_history import _text_similarity
from dbt_diagnostics.enrichers.enrich import enrich_reports
from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    TraceLocation,
    EnrichmentData,
    ColumnInfo,
)


class TestEnvVarResolution:
    """Tests for profiles.yml env_var() substitution."""

    def test_simple_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_PASSWORD", "secret123")
        result = _resolve_env_vars("{{ env_var('MY_PASSWORD') }}")
        assert result == "secret123"

    def test_env_var_with_default(self):
        # Unset var falls back to default
        result = _resolve_env_vars("{{ env_var('NONEXISTENT_VAR_XYZ', 'fallback') }}")
        assert result == "fallback"

    def test_env_var_missing_no_default(self):
        with pytest.raises(ValueError, match="not set"):
            _resolve_env_vars("{{ env_var('TOTALLY_MISSING_VAR_ABC') }}")

    def test_mixed_text_and_env_var(self, monkeypatch):
        monkeypatch.setenv("DB_NAME", "analytics")
        result = _resolve_env_vars("prefix_{{ env_var('DB_NAME') }}_suffix")
        assert result == "prefix_analytics_suffix"

    def test_no_env_var_passthrough(self):
        result = _resolve_env_vars("plain_string_value")
        assert result == "plain_string_value"


class TestProfileParsing:
    """Tests for parse_profile with a temporary profiles.yml."""

    def test_parse_snowflake_profile(self, tmp_path, monkeypatch):
        profiles_yml = tmp_path / "profiles.yml"
        profiles_yml.write_text("""
artwork_pipeline:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: xy12345.us-east-1
      user: dbt_user
      password: my_password
      database: ANALYTICS
      schema: DEV
      warehouse: TRANSFORM_WH
      role: TRANSFORMER
      threads: 4
""")
        monkeypatch.setenv("DBT_PROFILES_DIR", str(tmp_path))

        result = parse_profile("artwork_pipeline", "dev")
        assert result is not None
        assert result["account"] == "xy12345.us-east-1"
        assert result["user"] == "dbt_user"
        assert result["password"] == "my_password"
        assert result["database"] == "ANALYTICS"
        assert result["warehouse"] == "TRANSFORM_WH"
        assert result["role"] == "TRANSFORMER"

    def test_parse_key_pair_profile(self, tmp_path, monkeypatch):
        profiles_yml = tmp_path / "profiles.yml"
        profiles_yml.write_text("""
artwork_pipeline:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: xy12345
      user: svc_user
      private_key_path: /path/to/key.p8
      database: DB
      schema: PUBLIC
      warehouse: WH
      role: ROLE
""")
        monkeypatch.setenv("DBT_PROFILES_DIR", str(tmp_path))

        result = parse_profile("artwork_pipeline", "dev")
        assert result is not None
        assert "password" not in result
        assert result["private_key_file"] == "/path/to/key.p8"

    def test_missing_profile_returns_none(self, tmp_path, monkeypatch):
        profiles_yml = tmp_path / "profiles.yml"
        profiles_yml.write_text("other_project:\n  target: dev\n  outputs:\n    dev:\n      type: postgres\n")
        monkeypatch.setenv("DBT_PROFILES_DIR", str(tmp_path))

        result = parse_profile("nonexistent", "dev")
        assert result is None


class TestParams:
    """Tests for SHOW PARAMETERS queries with mocked cursor."""

    def test_get_parameters(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Simulate SHOW PARAMETERS output: (key, value, default, level, desc, type)
        mock_cursor.fetchall.return_value = [
            ("TIMESTAMP_TYPE_MAPPING", "TIMESTAMP_LTZ", "TIMESTAMP_LTZ", "ACCOUNT", "", "STRING")
        ]

        result = get_parameters(mock_conn, ["TIMESTAMP_TYPE_MAPPING"])
        assert result == {"TIMESTAMP_TYPE_MAPPING": "TIMESTAMP_LTZ"}

    def test_get_parameter_with_level(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("TIMESTAMP_TYPE_MAPPING", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "SESSION", "", "STRING")
        ]

        result = get_parameter_with_level(mock_conn, "TIMESTAMP_TYPE_MAPPING")
        assert result["value"] == "TIMESTAMP_NTZ"
        assert result["level"] == "SESSION"
        assert result["default"] == "TIMESTAMP_LTZ"


class TestSchemaInspector:
    """Tests for DESCRIBE TABLE with mocked cursor."""

    def test_describe_table(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("OBJECT_ID", "NUMBER(38,0)", "COLUMN", "Y", None, "N"),
            ("TITLE", "VARCHAR(16777216)", "COLUMN", "Y", None, "N"),
            ("ARTIST_DISPLAY_NAME", "VARCHAR(500)", "COLUMN", "Y", None, "N"),
        ]

        columns = describe_table(mock_conn, "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS")
        assert len(columns) == 3
        assert columns[0].name == "OBJECT_ID"
        assert columns[0].data_type == "NUMBER(38,0)"
        assert columns[2].name == "ARTIST_DISPLAY_NAME"

    def test_table_exists_true(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [("some_row",)]

        result = table_exists(mock_conn, "DB.SCHEMA.TABLE")
        assert result is True

    def test_table_exists_false(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = table_exists(mock_conn, "DB.SCHEMA.TABLE")
        assert result is False

    def test_find_similar_columns(self):
        columns = [
            ColumnInfo(name="ARTWORK_ID", data_type="NUMBER"),
            ColumnInfo(name="TITLE", data_type="VARCHAR"),
            ColumnInfo(name="ARTIST_NAME", data_type="VARCHAR"),
        ]
        suggestions = find_similar_columns(columns, "ARTWORK_TITLE")
        # Should find ARTWORK_ID (shares "ARTWORK" prefix) and TITLE (substring)
        assert len(suggestions) > 0


class TestTextSimilarity:
    """Tests for query history text matching."""

    def test_identical_queries(self):
        assert _text_similarity("SELECT 1", "SELECT 1") == 1.0

    def test_similar_queries(self):
        a = "SELECT OBJECT_ID, TITLE FROM ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
        b = "CREATE TABLE AS SELECT OBJECT_ID, TITLE FROM ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
        score = _text_similarity(a, b)
        assert score > 0.7

    def test_different_queries(self):
        a = "SELECT 1 FROM foo"
        b = "INSERT INTO bar VALUES (1, 2, 3)"
        score = _text_similarity(a, b)
        assert score < 0.5


class TestEnrichReports:
    """Integration test for the enrich orchestrator with mocked connection."""

    def test_enriches_contract_violation(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            ("TIMESTAMP_TYPE_MAPPING", "TIMESTAMP_LTZ", "TIMESTAMP_LTZ", "ACCOUNT", "", "STRING")
        ]

        report = DiagnosticReport(
            unique_id="model.test.my_model",
            error_class="contract_violation",
            raw_message="contract failed",
            findings=[
                DiagnosticFinding(
                    summary="Column _LOADED_AT: mismatch",
                    location=TraceLocation(file_path="models/my_model.sql"),
                    session_params_to_check=["TIMESTAMP_TYPE_MAPPING"],
                )
            ],
        )

        run_results = {"results": [{"unique_id": "model.test.my_model", "timing": []}]}
        enrich_reports(mock_conn, [report], run_results)

        assert report.findings[0].enrichment is not None
        assert "TIMESTAMP_TYPE_MAPPING" in report.findings[0].enrichment.actual_param_values

    def test_enriches_runtime_error_object_not_found(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # table_exists returns empty (object doesn't exist)
        mock_cursor.fetchall.return_value = []

        report = DiagnosticReport(
            unique_id="model.test.stg_foo",
            error_class="runtime_error",
            raw_message="Object 'DB.SCHEMA.TABLE' does not exist",
            findings=[
                DiagnosticFinding(
                    summary="Object not found: DB.SCHEMA.TABLE",
                    location=TraceLocation(file_path="models/stg_foo.sql"),
                )
            ],
        )

        run_results = {"results": [{"unique_id": "model.test.stg_foo", "timing": []}]}
        enrich_reports(mock_conn, [report], run_results)

        assert report.findings[0].enrichment is not None
        assert report.findings[0].enrichment.object_exists is False
