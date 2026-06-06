"""
dbt_diagnostics/tracers/dag_walker.py

Walks the dbt DAG (from manifest.json) to trace column origins upstream.
Uses dbt-artifacts-parser for typed access to manifest nodes.
"""

import re
from typing import Optional

try:
    from dbt_artifacts_parser.parser import parse_manifest

    ARTIFACTS_PARSER_AVAILABLE = True
except ImportError:
    ARTIFACTS_PARSER_AVAILABLE = False


class DagWalker:
    """
    Navigates the dbt DAG to find upstream dependencies and column origins.

    Wraps manifest.json (loaded as a dict). If dbt-artifacts-parser is
    available, uses typed access; otherwise works with raw dicts.
    """

    def __init__(self, manifest: dict):
        self.manifest = manifest
        self.nodes = manifest.get("nodes", {})
        self.sources = manifest.get("sources", {})
        self.parent_map = manifest.get("parent_map", {})

    def get_node(self, unique_id: str) -> Optional[dict]:
        """Get a node dict by its unique_id."""
        return self.nodes.get(unique_id) or self.sources.get(unique_id)

    def get_parents(self, unique_id: str) -> list[str]:
        """Get the immediate parent node IDs of a given node."""
        # parent_map is the preferred source
        if self.parent_map:
            return self.parent_map.get(unique_id, [])
        # Fallback: read depends_on from the node itself
        node = self.get_node(unique_id)
        if node:
            return node.get("depends_on", {}).get("nodes", [])
        return []

    def get_model_path(self, unique_id: str) -> str:
        """Get the relative file path for a model node."""
        node = self.get_node(unique_id)
        if node:
            return node.get("path", "") or node.get("original_file_path", "")
        return ""

    def find_column_origin(self, unique_id: str, column_name: str) -> Optional[dict]:
        """
        Determine if a column is inherited from an upstream model.

        Walks parents and checks if any upstream node declares the same column
        in its columns dict (from the YAML schema). If found, reports the
        upstream model as the origin.

        Returns:
            dict with 'model' (unique_id) and 'file' (path) if inherited,
            or None if the column is introduced in the current model.
        """
        parents = self.get_parents(unique_id)

        for parent_id in parents:
            parent_node = self.get_node(parent_id)
            if not parent_node:
                continue

            # Check if the parent's columns include this column name
            parent_columns = parent_node.get("columns", {})
            # Column names in manifest are typically lowercase keys
            col_lower = column_name.lower()
            col_upper = column_name.upper()

            if col_lower in parent_columns or col_upper in parent_columns:
                return {
                    "model": parent_id,
                    "file": parent_node.get("path", ""),
                }

            # Also check the compiled SQL for the column alias (if columns not declared)
            compiled = parent_node.get("compiled_code", "")
            if compiled:
                pattern = re.compile(
                    rf"\bAS\s+{re.escape(column_name)}\b", re.IGNORECASE
                )
                if pattern.search(compiled):
                    return {
                        "model": parent_id,
                        "file": parent_node.get("path", ""),
                    }

        return None
