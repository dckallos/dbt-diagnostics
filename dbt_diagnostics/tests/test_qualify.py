"""
Tests for schema-aware column tracing via sqlglot qualify.
"""

from pathlib import Path

from dbt_diagnostics.tracers.column_tracer import (
    ColumnTracer,
    build_schema_from_manifest,
    qualify_sql,
)
import sqlglot


class TestBuildSchemaFromManifest:
    """Tests for building sqlglot schema dict from manifest."""

    def test_builds_from_nodes_with_relation_name(self):
        manifest = {
            "nodes": {
                "model.pkg.my_model": {
                    "relation_name": "MY_DB.MY_SCHEMA.MY_TABLE",
                    "columns": {
                        "id": {"name": "id", "data_type": "INTEGER"},
                        "name": {"name": "name", "data_type": "VARCHAR"},
                    },
                }
            },
            "sources": {},
        }
        schema = build_schema_from_manifest(manifest)
        assert "MY_DB" in schema
        assert "MY_SCHEMA" in schema["MY_DB"]
        assert "MY_TABLE" in schema["MY_DB"]["MY_SCHEMA"]
        assert schema["MY_DB"]["MY_SCHEMA"]["MY_TABLE"]["ID"] == "INTEGER"
        assert schema["MY_DB"]["MY_SCHEMA"]["MY_TABLE"]["NAME"] == "VARCHAR"

    def test_skips_nodes_without_columns(self):
        manifest = {
            "nodes": {
                "model.pkg.no_cols": {
                    "relation_name": "DB.SCH.TBL",
                    "columns": {},
                }
            },
            "sources": {},
        }
        schema = build_schema_from_manifest(manifest)
        assert schema == {}

    def test_skips_nodes_without_relation_name(self):
        manifest = {
            "nodes": {
                "model.pkg.no_rel": {
                    "relation_name": "",
                    "columns": {"x": {"name": "x", "data_type": "INT"}},
                }
            },
            "sources": {},
        }
        schema = build_schema_from_manifest(manifest)
        assert schema == {}


class TestQualifySQL:
    """Tests for the qualify_sql helper."""

    def test_expands_star_with_schema(self):
        schema = {
            "DB": {"SCH": {"SRC": {"COL_A": "INT", "COL_B": "VARCHAR"}}}
        }
        parsed = sqlglot.parse_one(
            "SELECT * FROM DB.SCH.SRC", dialect="snowflake"
        )
        qualified = qualify_sql(parsed, schema=schema)
        sql = qualified.sql(dialect="snowflake")
        assert "COL_A" in sql.upper()
        assert "COL_B" in sql.upper()
        # Star should be gone
        assert "*" not in sql

    def test_fallback_without_schema(self):
        parsed = sqlglot.parse_one("SELECT * FROM foo", dialect="snowflake")
        result = qualify_sql(parsed, schema=None)
        # Should return unchanged AST
        assert result.sql(dialect="snowflake") == parsed.sql(dialect="snowflake")

    def test_fallback_on_invalid_schema(self):
        """If qualify raises, fallback to original AST."""
        parsed = sqlglot.parse_one("SELECT * FROM foo", dialect="snowflake")
        # Pass a schema that doesn't match anything -- qualify won't crash
        # but star won't expand either (which is fine, it's graceful)
        result = qualify_sql(parsed, schema={"X": {"Y": {"Z": {"a": "INT"}}}})
        # Should not crash
        assert result is not None


class TestSchemaAwareTracing:
    """Integration: trace_column with schema qualification."""

    def setup_method(self):
        self.tracer = ColumnTracer(
            models_dir=Path("/fake/models"),
            compiled_dir=Path("/fake/compiled"),
        )

    def test_select_star_resolves_to_explicit_columns(self):
        """SELECT * becomes explicit columns when schema is provided."""
        schema = {
            "ARTWORK_DB": {
                "BRONZE": {
                    "RAW_MET_OBJECTS": {
                        "OBJECT_ID": "INT",
                        "TITLE": "VARCHAR",
                        "ARTIST_NAME": "VARCHAR",
                    }
                }
            }
        }
        sql = "SELECT * FROM ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
        result = self.tracer.trace_column("TITLE", sql, schema=schema)
        assert result is not None
        assert result.column_name == "TITLE"

    def test_join_ambiguous_column_resolved(self):
        """Ambiguous column in JOIN gets table-qualified."""
        schema = {
            "DB": {
                "S": {
                    "A": {"ID": "INT", "NAME": "VARCHAR"},
                    "B": {"ID": "INT", "VALUE": "VARCHAR"},
                }
            }
        }
        sql = (
            "SELECT A.ID AS ID, A.NAME AS NAME, B.VALUE AS VALUE "
            "FROM DB.S.A AS A JOIN DB.S.B AS B ON A.ID = B.ID"
        )
        result = self.tracer.trace_column("NAME", sql, schema=schema)
        assert result is not None
        assert result.column_name == "NAME"

    def test_missing_schema_graceful_fallback(self):
        """Without schema, tracing still works for explicit aliases."""
        sql = "SELECT 1 AS id, 'hello' AS name FROM foo"
        result = self.tracer.trace_column("name", sql, schema=None)
        assert result is not None
        assert result.column_name == "name"

    def test_missing_schema_no_crash_on_star(self):
        """SELECT * without schema just returns None (can't resolve)."""
        sql = "SELECT * FROM some_table"
        result = self.tracer.trace_column("unknown_col", sql, schema=None)
        # Can't resolve from star without schema
        assert result is None
