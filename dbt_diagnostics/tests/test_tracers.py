"""
Tests for the DAG walker and column tracer.
"""

from pathlib import Path

from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer, ColumnTraceResult


class TestDagWalker:
    """Tests for manifest DAG navigation."""

    def test_get_node_returns_model(self, manifest_minimal):
        walker = DagWalker(manifest_minimal)
        node = walker.get_node("model.artwork_pipeline.dim_artists")
        assert node is not None
        assert node["original_file_path"] == "models/marts/dim_artists.sql"

    def test_get_node_returns_none_for_unknown(self, manifest_minimal):
        walker = DagWalker(manifest_minimal)
        assert walker.get_node("model.artwork_pipeline.nonexistent") is None

    def test_get_parents_from_depends_on(self, manifest_minimal):
        walker = DagWalker(manifest_minimal)
        parents = walker.get_parents("model.artwork_pipeline.dim_artists")
        assert "model.artwork_pipeline.stg_met__artists" in parents

    def test_get_model_path(self, manifest_minimal):
        walker = DagWalker(manifest_minimal)
        path = walker.get_model_path("model.artwork_pipeline.dim_artists")
        assert path == "models/marts/dim_artists.sql"

    def test_find_column_origin_inherited(self, manifest_minimal):
        """_extracted_at exists in parent columns dict -> inherited."""
        walker = DagWalker(manifest_minimal)
        # dim_artists depends on stg_met__artists, which declares _extracted_at
        # But dim_artists references _loaded_at, not _extracted_at -- check artist_id
        origin = walker.find_column_origin(
            "model.artwork_pipeline.dim_artists", "artist_id"
        )
        assert origin is not None
        assert origin["model"] == "model.artwork_pipeline.stg_met__artists"

    def test_find_column_origin_not_inherited(self, manifest_minimal):
        """_loaded_at is NOT in the parent's columns -> introduced here."""
        walker = DagWalker(manifest_minimal)
        origin = walker.find_column_origin(
            "model.artwork_pipeline.dim_artists", "_loaded_at"
        )
        assert origin is None


class TestDagWalkerMultiHop:
    """Tests for multi-hop BFS column origin tracing (Work Item 3)."""

    @staticmethod
    def _three_level_manifest():
        """
        Synthetic 3-level chain:
        source.raw.users -> model.stg_users -> model.int_users -> model.dim_users

        user_id is declared in stg_users' columns dict.
        """
        return {
            "nodes": {
                "model.pkg.stg_users": {
                    "unique_id": "model.pkg.stg_users",
                    "resource_type": "model",
                    "path": "staging/stg_users.sql",
                    "compiled_code": "",
                    "depends_on": {"nodes": ["source.pkg.raw.users"], "macros": []},
                    "columns": {
                        "user_id": {"name": "user_id", "data_type": "INTEGER"},
                        "email": {"name": "email", "data_type": "VARCHAR"},
                    },
                },
                "model.pkg.int_users": {
                    "unique_id": "model.pkg.int_users",
                    "resource_type": "model",
                    "path": "intermediate/int_users.sql",
                    "compiled_code": "",
                    "depends_on": {"nodes": ["model.pkg.stg_users"], "macros": []},
                    "columns": {},  # No columns declared here
                },
                "model.pkg.dim_users": {
                    "unique_id": "model.pkg.dim_users",
                    "resource_type": "model",
                    "path": "marts/dim_users.sql",
                    "compiled_code": "",
                    "depends_on": {"nodes": ["model.pkg.int_users"], "macros": []},
                    "columns": {},
                },
            },
            "sources": {
                "source.pkg.raw.users": {
                    "unique_id": "source.pkg.raw.users",
                    "resource_type": "source",
                    "path": "",
                    "compiled_code": "",
                    "columns": {},
                },
            },
            "parent_map": {
                "model.pkg.stg_users": ["source.pkg.raw.users"],
                "model.pkg.int_users": ["model.pkg.stg_users"],
                "model.pkg.dim_users": ["model.pkg.int_users"],
            },
        }

    def test_finds_column_three_levels_up(self):
        """BFS finds user_id in stg_users (2 hops from dim_users)."""
        manifest = self._three_level_manifest()
        walker = DagWalker(manifest)
        origin = walker.find_column_origin("model.pkg.dim_users", "user_id")
        assert origin is not None
        assert origin["model"] == "model.pkg.stg_users"
        assert origin["file"] == "staging/stg_users.sql"

    def test_returns_closest_origin(self):
        """BFS returns the closest ancestor that declares the column."""
        manifest = self._three_level_manifest()
        # Also declare user_id in int_users (closer to dim_users)
        manifest["nodes"]["model.pkg.int_users"]["columns"] = {
            "user_id": {"name": "user_id", "data_type": "INTEGER"},
        }
        walker = DagWalker(manifest)
        origin = walker.find_column_origin("model.pkg.dim_users", "user_id")
        assert origin is not None
        # Should find int_users (1 hop) before stg_users (2 hops)
        assert origin["model"] == "model.pkg.int_users"

    def test_respects_max_depth(self):
        """Column at depth 3 is not found with max_depth=1."""
        manifest = self._three_level_manifest()
        walker = DagWalker(manifest)
        origin = walker.find_column_origin(
            "model.pkg.dim_users", "user_id", max_depth=1
        )
        # user_id is at depth 2 (dim_users -> int_users -> stg_users)
        # max_depth=1 only checks int_users (which has no columns)
        assert origin is None

    def test_handles_cycle_safely(self):
        """Circular parent_map doesn't cause infinite loop."""
        manifest = {
            "nodes": {
                "model.pkg.a": {
                    "unique_id": "model.pkg.a",
                    "resource_type": "model",
                    "path": "a.sql",
                    "compiled_code": "",
                    "columns": {},
                },
                "model.pkg.b": {
                    "unique_id": "model.pkg.b",
                    "resource_type": "model",
                    "path": "b.sql",
                    "compiled_code": "",
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.a": ["model.pkg.b"],
                "model.pkg.b": ["model.pkg.a"],  # cycle!
            },
        }
        walker = DagWalker(manifest)
        # Should terminate without error, return None (column not found)
        origin = walker.find_column_origin("model.pkg.a", "some_col")
        assert origin is None


class TestColumnTracer:
    """Tests for sqlglot-based column tracing."""

    SAMPLE_SQL = """
    WITH met_artists AS (
        SELECT
            artist_id,
            CURRENT_TIMESTAMP() AS _loaded_at
        FROM ARTWORK_DB.SILVER.STG_MET__ARTISTS
    )
    SELECT
        artist_id,
        _loaded_at
    FROM met_artists
    """

    def test_trace_column_finds_alias_in_cte(self):
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("_loaded_at", self.SAMPLE_SQL)
        assert result is not None
        assert result.column_name == "_loaded_at"
        # _loaded_at is defined as CURRENT_TIMESTAMP() AS _loaded_at in the CTE.
        # The tracer finds the CTE definition (where the column is created)
        # over the outer SELECT pass-through.
        assert "CURRENT_TIMESTAMP" in result.expression.upper()
        assert result.is_function_call is True
        assert result.cte_name == "met_artists"

    def test_trace_column_alias_only_in_cte(self):
        """Column only defined as an alias in a CTE (not in outer SELECT)."""
        sql = """
        WITH met_artists AS (
            SELECT
                artist_id,
                CURRENT_TIMESTAMP() AS _loaded_at
            FROM ARTWORK_DB.SILVER.STG_MET__ARTISTS
        )
        SELECT artist_id FROM met_artists
        """
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("_loaded_at", sql)
        assert result is not None
        assert result.column_name == "_loaded_at"
        assert "CURRENT_TIMESTAMP" in result.expression.upper()
        assert result.is_function_call is True
        assert result.cte_name == "met_artists"

    def test_trace_column_not_found(self):
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("nonexistent_col", self.SAMPLE_SQL)
        assert result is None

    def test_trace_column_outer_select_passthrough(self):
        """artist_id in outer SELECT is a bare column ref, not an alias."""
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("artist_id", self.SAMPLE_SQL)
        assert result is not None
        assert result.column_name == "artist_id"
        assert result.is_function_call is False
        # Bare column reference: expression is the column itself
        assert "artist_id" in result.expression.lower()

    def test_find_line_number(self, tmp_path):
        source = tmp_path / "dim_artists.sql"
        source.write_text(
            "SELECT\n"
            "    artist_id,\n"
            "    CURRENT_TIMESTAMP() AS _loaded_at\n"
            "FROM {{ ref('stg_met__artists') }}\n"
        )
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        line = tracer.find_line_number(source, "_loaded_at")
        assert line == 3

    def test_find_line_number_missing_file(self):
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        line = tracer.find_line_number(Path("/does/not/exist.sql"), "col")
        assert line is None


class TestBareColumnTracing:
    """Tests for bare column reference resolution (Work Item 2)."""

    MULTI_CTE_SQL = """
    WITH base AS (SELECT user_id, email FROM raw_users)
    SELECT user_id, email FROM base
    """

    def test_bare_column_found_in_outer_select(self):
        """Bare column 'user_id' in outer SELECT should be found."""
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("user_id", self.MULTI_CTE_SQL)
        assert result is not None
        assert result.column_name == "user_id"
        assert result.is_function_call is False

    def test_bare_column_email_found(self):
        """Second bare column 'email' should also be found."""
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("email", self.MULTI_CTE_SQL)
        assert result is not None
        assert result.column_name == "email"

    def test_alias_takes_priority_over_bare_column(self):
        """When both alias and bare exist, alias should win."""
        sql = "SELECT user_id, email AS user_id FROM raw_users"
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("user_id", sql)
        assert result is not None
        # The alias match (email AS user_id) should win
        assert "email" in result.expression.lower()
        assert result.is_function_call is False

    def test_star_returns_none(self):
        """SELECT * should not resolve individual columns."""
        sql = "SELECT * FROM raw_users"
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("user_id", sql)
        assert result is None

    def test_qualified_bare_column(self):
        """Table-qualified bare column (t.user_id) should still match."""
        sql = "SELECT t.user_id, t.email FROM raw_users AS t"
        tracer = ColumnTracer(Path("/fake/models"), Path("/fake/compiled"))
        result = tracer.trace_column("user_id", sql)
        assert result is not None
        assert result.column_name == "user_id"
