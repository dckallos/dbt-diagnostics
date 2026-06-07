"""
Tests for trace_column_lineage() and trace_object_lineage() in DagWalker.
Uses real fixtures where possible and synthetic manifests for edge cases.
"""
import json
from pathlib import Path

import pytest

from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.models import LineageStep

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestTraceColumnLineage:
    """Tests for DagWalker.trace_column_lineage()."""

    def test_column_found_in_parent(self):
        """Column declared in immediate parent gets manifest_status='declared'."""
        manifest = {
            "nodes": {
                "model.pkg.child": {
                    "unique_id": "model.pkg.child",
                    "original_file_path": "models/child.sql",
                    "columns": {},
                    "compiled_code": "SELECT artist_id FROM ref_parent",
                },
                "model.pkg.parent": {
                    "unique_id": "model.pkg.parent",
                    "original_file_path": "models/parent.sql",
                    "columns": {"artist_id": {"name": "artist_id"}},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.child": ["model.pkg.parent"],
                "model.pkg.parent": [],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage("model.pkg.child", "artist_id")

        assert len(trail) == 2
        assert trail[0].node_id == "model.pkg.child"
        assert trail[0].depth == 0
        assert trail[0].annotation == "failing model"
        assert trail[1].node_id == "model.pkg.parent"
        assert trail[1].depth == 1
        assert trail[1].manifest_status == "declared"
        assert "found" in trail[1].manifest_detail

    def test_column_not_found_anywhere(self):
        """Column not in any upstream node gets 'not_found' on all steps."""
        manifest = {
            "nodes": {
                "model.pkg.child": {
                    "unique_id": "model.pkg.child",
                    "original_file_path": "models/child.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.parent": {
                    "unique_id": "model.pkg.parent",
                    "original_file_path": "models/parent.sql",
                    "columns": {"other_col": {"name": "other_col"}},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.child": ["model.pkg.parent"],
                "model.pkg.parent": [],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage("model.pkg.child", "nonexistent_col")

        assert len(trail) == 2
        assert trail[1].manifest_status == "not_found"
        assert "not found" in trail[1].manifest_detail

    def test_three_hop_trace(self):
        """Column found 3 levels up -- all intermediate nodes recorded."""
        manifest = {
            "nodes": {
                "model.pkg.a": {
                    "unique_id": "model.pkg.a",
                    "original_file_path": "models/a.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.b": {
                    "unique_id": "model.pkg.b",
                    "original_file_path": "models/b.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.c": {
                    "unique_id": "model.pkg.c",
                    "original_file_path": "models/c.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.d": {
                    "unique_id": "model.pkg.d",
                    "original_file_path": "models/d.sql",
                    "columns": {"deep_col": {"name": "deep_col"}},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.a": ["model.pkg.b"],
                "model.pkg.b": ["model.pkg.c"],
                "model.pkg.c": ["model.pkg.d"],
                "model.pkg.d": [],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage("model.pkg.a", "deep_col")

        assert len(trail) == 4
        assert trail[0].depth == 0
        assert trail[1].depth == 1
        assert trail[2].depth == 2
        assert trail[3].depth == 3
        assert trail[3].manifest_status == "declared"

    def test_respects_max_depth(self):
        """BFS stops at max_depth -- nodes beyond are not in trail."""
        manifest = {
            "nodes": {
                "model.pkg.a": {
                    "unique_id": "model.pkg.a",
                    "original_file_path": "models/a.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.b": {
                    "unique_id": "model.pkg.b",
                    "original_file_path": "models/b.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.c": {
                    "unique_id": "model.pkg.c",
                    "original_file_path": "models/c.sql",
                    "columns": {"target": {"name": "target"}},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.a": ["model.pkg.b"],
                "model.pkg.b": ["model.pkg.c"],
                "model.pkg.c": [],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage("model.pkg.a", "target", max_depth=1)

        assert len(trail) == 2
        assert trail[1].node_id == "model.pkg.b"

    def test_handles_cycle(self):
        """Cycle in parent_map does not cause infinite loop."""
        manifest = {
            "nodes": {
                "model.pkg.a": {
                    "unique_id": "model.pkg.a",
                    "original_file_path": "models/a.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.b": {
                    "unique_id": "model.pkg.b",
                    "original_file_path": "models/b.sql",
                    "columns": {},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.a": ["model.pkg.b"],
                "model.pkg.b": ["model.pkg.a"],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage("model.pkg.a", "some_col")

        assert len(trail) == 2

    def test_run_results_cross_reference(self):
        """run_status populated from run_results when provided."""
        manifest = {
            "nodes": {
                "model.pkg.child": {
                    "unique_id": "model.pkg.child",
                    "original_file_path": "models/child.sql",
                    "columns": {},
                    "compiled_code": "",
                },
                "model.pkg.parent": {
                    "unique_id": "model.pkg.parent",
                    "original_file_path": "models/parent.sql",
                    "columns": {"col": {"name": "col"}},
                    "compiled_code": "",
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.child": ["model.pkg.parent"],
                "model.pkg.parent": [],
            },
        }
        run_results = {
            "results": [
                {"unique_id": "model.pkg.child", "status": "error"},
                {"unique_id": "model.pkg.parent", "status": "pass"},
            ]
        }
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage(
            "model.pkg.child", "col", run_results=run_results
        )

        assert trail[0].run_status == "error"
        assert trail[1].run_status == "pass"

    def test_real_fixture_invalid_identifier(self):
        """Use real fixture to trace the invalid identifier column."""
        manifest_path = FIXTURES / "real_invalid_identifier_000904_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        walker = DagWalker(manifest)
        trail = walker.trace_column_lineage(
            "model.artwork_pipeline.stg_met__artworks", "NONEXISTENT_COLUMN"
        )

        assert len(trail) >= 1
        assert trail[0].node_id == "model.artwork_pipeline.stg_met__artworks"
        assert trail[0].depth == 0


class TestTraceObjectLineage:
    """Tests for DagWalker.trace_object_lineage()."""

    def test_object_matches_source(self):
        """Object found in manifest sources gets manifest_status='declared'."""
        manifest = {
            "nodes": {
                "model.pkg.stg": {
                    "unique_id": "model.pkg.stg",
                    "original_file_path": "models/stg.sql",
                    "columns": {},
                },
            },
            "sources": {
                "source.pkg.raw.my_table": {
                    "unique_id": "source.pkg.raw.my_table",
                    "original_file_path": "models/sources.yml",
                    "relation_name": "DB.SCHEMA.MY_TABLE",
                    "columns": {},
                },
            },
            "parent_map": {
                "model.pkg.stg": ["source.pkg.raw.my_table"],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage("model.pkg.stg", "DB.SCHEMA.MY_TABLE")

        assert len(trail) == 2
        assert trail[0].node_id == "model.pkg.stg"
        assert trail[1].node_id == "source.pkg.raw.my_table"
        assert trail[1].manifest_status == "declared"
        assert "relation_name matches" in trail[1].manifest_detail

    def test_object_matches_upstream_model(self):
        """Object found as relation_name on an upstream model node."""
        manifest = {
            "nodes": {
                "model.pkg.downstream": {
                    "unique_id": "model.pkg.downstream",
                    "original_file_path": "models/downstream.sql",
                    "columns": {},
                },
                "model.pkg.upstream": {
                    "unique_id": "model.pkg.upstream",
                    "original_file_path": "models/upstream.sql",
                    "relation_name": "DB.SILVER.UPSTREAM_TABLE",
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {
                "model.pkg.downstream": ["model.pkg.upstream"],
            },
        }
        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage(
            "model.pkg.downstream", "DB.SILVER.UPSTREAM_TABLE"
        )

        assert len(trail) == 2
        assert trail[1].node_id == "model.pkg.upstream"
        assert trail[1].manifest_status == "declared"

    def test_object_not_in_manifest(self):
        """Object not found anywhere produces a synthetic 'missing' step."""
        manifest = {
            "nodes": {
                "model.pkg.stg": {
                    "unique_id": "model.pkg.stg",
                    "original_file_path": "models/stg.sql",
                    "columns": {},
                },
            },
            "sources": {},
            "parent_map": {"model.pkg.stg": []},
        }
        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage("model.pkg.stg", "DB.SCHEMA.GHOST_TABLE")

        assert len(trail) == 2
        assert trail[1].manifest_status == "missing"
        assert trail[1].short_name == "GHOST_TABLE"
        assert "not found in manifest" in trail[1].manifest_detail

    def test_case_insensitive_match(self):
        """relation_name matching is case-insensitive."""
        manifest = {
            "nodes": {
                "model.pkg.stg": {
                    "unique_id": "model.pkg.stg",
                    "original_file_path": "models/stg.sql",
                    "columns": {},
                },
            },
            "sources": {
                "source.pkg.raw.tbl": {
                    "unique_id": "source.pkg.raw.tbl",
                    "original_file_path": "models/sources.yml",
                    "relation_name": "artwork_db.bronze.raw_met_objects",
                    "columns": {},
                },
            },
            "parent_map": {"model.pkg.stg": []},
        }
        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage(
            "model.pkg.stg", "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
        )

        assert trail[1].manifest_status == "declared"

    def test_run_results_cross_reference(self):
        """run_status set on the root from run_results."""
        manifest = {
            "nodes": {
                "model.pkg.stg": {
                    "unique_id": "model.pkg.stg",
                    "original_file_path": "models/stg.sql",
                    "columns": {},
                },
            },
            "sources": {
                "source.pkg.raw.tbl": {
                    "unique_id": "source.pkg.raw.tbl",
                    "original_file_path": "models/sources.yml",
                    "relation_name": "DB.RAW.TBL",
                    "columns": {},
                },
            },
            "parent_map": {"model.pkg.stg": ["source.pkg.raw.tbl"]},
        }
        run_results = {
            "results": [
                {"unique_id": "model.pkg.stg", "status": "error"},
            ]
        }
        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage(
            "model.pkg.stg", "DB.RAW.TBL", run_results=run_results
        )

        assert trail[0].run_status == "error"
        assert trail[1].run_status is None

    def test_real_fixture_object_not_exist(self):
        """Use real fixture: object does not exist error."""
        rr_path = FIXTURES / "real_object_not_exist_002003.json"
        manifest_path = FIXTURES / "real_object_not_exist_002003_manifest.json"
        run_results = json.loads(rr_path.read_text())
        manifest = json.loads(manifest_path.read_text())

        walker = DagWalker(manifest)
        trail = walker.trace_object_lineage(
            "model.artwork_pipeline.stg_met__artworks",
            "ARTWORK_DB.BRONZE.DOES_NOT_EXIST_TABLE",
            run_results=run_results,
        )

        assert trail[0].node_id == "model.artwork_pipeline.stg_met__artworks"
        assert trail[0].run_status == "error"
        assert trail[1].manifest_status == "missing"


class TestLineageStepProperties:
    """Test the status_emoji and status_text properties."""

    def test_emoji_live_exists(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
            live_status="exists",
        )
        assert step.status_emoji == "\u2705"
        assert step.status_text == "[PASS]"

    def test_emoji_live_missing(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
            live_status="missing",
        )
        assert step.status_emoji == "\u274c"
        assert step.status_text == "[FAIL]"

    def test_emoji_manifest_declared(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
            manifest_status="declared",
        )
        assert step.status_emoji == "\u2705"
        assert step.status_text == "[PASS]"

    def test_emoji_run_error(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
            run_status="error",
        )
        assert step.status_emoji == "\u274c"
        assert step.status_text == "[FAIL]"

    def test_emoji_unknown(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
        )
        assert step.status_emoji == "\u2753"
        assert step.status_text == "[????]"

    def test_emoji_skipped(self):
        step = LineageStep(
            node_id="m.p.x",
            node_type="model",
            short_name="x",
            run_status="skipped",
        )
        assert step.status_text == "[SKIP]"
