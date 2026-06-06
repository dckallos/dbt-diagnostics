"""
Tests for the diff_tracer module (diff-aware diagnosis).
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.tracers.diff_tracer import diff_node
from dbt_diagnostics.models import DiffResult


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def previous_manifest():
    path = FIXTURES_DIR / "manifest_previous.json"
    with open(path) as f:
        return json.load(f)


class TestDiffNodeChanged:
    """Tests for detecting changes in the failing model itself."""

    def test_changed_compiled_code_produces_diff_lines(self, previous_manifest):
        """When compiled_code differs, changed_lines has unified diff."""
        current_manifest = {
            "nodes": {
                "model.artwork_pipeline.dim_artists": {
                    "unique_id": "model.artwork_pipeline.dim_artists",
                    "compiled_code": "SELECT artist_id, NEW_COLUMN FROM stg_met__artists",
                    "depends_on": {"nodes": ["model.artwork_pipeline.stg_met__artists"]},
                    "columns": {
                        "artist_id": {"name": "artist_id", "data_type": "varchar(32)"},
                        "new_column": {"name": "new_column", "data_type": "varchar(200)"},
                    },
                },
                "model.artwork_pipeline.stg_met__artists": {
                    "unique_id": "model.artwork_pipeline.stg_met__artists",
                    "compiled_code": "SELECT artist_id, name FROM raw_artists",
                    "depends_on": {"nodes": []},
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {
                "model.artwork_pipeline.dim_artists": [
                    "model.artwork_pipeline.stg_met__artists"
                ]
            },
        }

        result = diff_node(
            "model.artwork_pipeline.dim_artists",
            current_manifest,
            previous_manifest,
        )

        assert result is not None
        assert result.node_changed is True
        assert len(result.changed_lines) > 0
        # Should contain diff indicators
        diff_text = "\n".join(result.changed_lines)
        assert "-" in diff_text or "+" in diff_text

    def test_unchanged_node_with_changed_upstream(self, previous_manifest):
        """When this node didn't change but upstream did, report upstream_changes."""
        current_manifest = {
            "nodes": {
                "model.artwork_pipeline.dim_artists": {
                    "unique_id": "model.artwork_pipeline.dim_artists",
                    # Same compiled code as previous
                    "compiled_code": "SELECT artist_id, OLD_COLUMN FROM stg_met__artists",
                    "depends_on": {"nodes": ["model.artwork_pipeline.stg_met__artists"]},
                    "columns": {
                        "artist_id": {"name": "artist_id", "data_type": "varchar(32)"},
                        "old_column": {"name": "old_column", "data_type": "varchar(100)"},
                    },
                },
                "model.artwork_pipeline.stg_met__artists": {
                    "unique_id": "model.artwork_pipeline.stg_met__artists",
                    # DIFFERENT compiled code from previous
                    "compiled_code": "SELECT artist_id, name, bio FROM raw_artists",
                    "depends_on": {"nodes": []},
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {
                "model.artwork_pipeline.dim_artists": [
                    "model.artwork_pipeline.stg_met__artists"
                ]
            },
        }

        result = diff_node(
            "model.artwork_pipeline.dim_artists",
            current_manifest,
            previous_manifest,
        )

        assert result is not None
        assert result.node_changed is False
        assert len(result.upstream_changes) == 1
        assert "stg_met__artists" in result.upstream_changes[0]["model_id"]

    def test_new_model_not_in_previous(self, previous_manifest):
        """A model that's new (not in previous manifest) reports as new."""
        current_manifest = {
            "nodes": {
                "model.artwork_pipeline.brand_new_model": {
                    "unique_id": "model.artwork_pipeline.brand_new_model",
                    "compiled_code": "SELECT 1 AS id",
                    "depends_on": {"nodes": []},
                    "columns": {"id": {"name": "id", "data_type": "INT"}},
                },
            },
            "sources": {},
            "parent_map": {},
        }

        result = diff_node(
            "model.artwork_pipeline.brand_new_model",
            current_manifest,
            previous_manifest,
        )

        assert result is not None
        assert result.node_changed is True
        assert "new model" in result.changed_lines[0].lower()

    def test_column_changes_detected(self, previous_manifest):
        """Detects added, removed, and type-changed columns."""
        current_manifest = {
            "nodes": {
                "model.artwork_pipeline.dim_artists": {
                    "unique_id": "model.artwork_pipeline.dim_artists",
                    "compiled_code": "SELECT artist_id, NEW_COL FROM stg_met__artists",
                    "depends_on": {"nodes": []},
                    "columns": {
                        "artist_id": {"name": "artist_id", "data_type": "INTEGER"},
                        "new_col": {"name": "new_col", "data_type": "VARCHAR"},
                    },
                },
            },
            "sources": {},
            "parent_map": {},
        }

        result = diff_node(
            "model.artwork_pipeline.dim_artists",
            current_manifest,
            previous_manifest,
        )

        assert result is not None
        # old_column was removed
        assert "old_column" in result.columns_removed
        # new_col was added
        assert "new_col" in result.columns_added
        # artist_id type changed from varchar(32) to INTEGER
        assert len(result.columns_type_changed) == 1
        assert result.columns_type_changed[0]["name"] == "artist_id"

    def test_node_not_in_current_returns_none(self, previous_manifest):
        """If the node doesn't exist in current manifest, returns None."""
        current_manifest = {"nodes": {}, "sources": {}, "parent_map": {}}
        result = diff_node(
            "model.artwork_pipeline.dim_artists",
            current_manifest,
            previous_manifest,
        )
        assert result is None
