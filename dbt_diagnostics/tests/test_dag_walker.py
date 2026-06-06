"""
Tests for the DAG walker (manifest navigation).
"""

from dbt_diagnostics.tracers.dag_walker import DagWalker


class TestDagWalker:
    """Unit tests for manifest DAG navigation."""

    def test_get_node(self, manifest_minimal):
        walker = DagWalker(manifest_minimal)
        node = walker.get_node("model.artwork_pipeline.dim_artists")
        assert node is not None
        assert node["original_file_path"] == "models/marts/dim_artists.sql"

    def test_get_node_missing(self, manifest_minimal):
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

    def test_find_column_origin_not_inherited(self, manifest_minimal):
        """_loaded_at is NOT declared in parent, so it's introduced here."""
        walker = DagWalker(manifest_minimal)
        origin = walker.find_column_origin(
            "model.artwork_pipeline.dim_artists", "_loaded_at"
        )
        assert origin is None

    def test_find_column_origin_inherited(self, manifest_minimal):
        """artist_id IS declared in parent, so it should be found upstream."""
        walker = DagWalker(manifest_minimal)
        origin = walker.find_column_origin(
            "model.artwork_pipeline.dim_artists", "artist_id"
        )
        assert origin is not None
        assert origin["model"] == "model.artwork_pipeline.stg_met__artists"
