"""
dbt_diagnostics/tracers/dag_walker.py

Walks the dbt DAG (from manifest.json) to trace column origins upstream.
Works directly with the raw manifest dict (stable across dbt versions).
"""

import re
from collections import deque
from typing import Optional


class DagWalker:
    """
    Navigates the dbt DAG to find upstream dependencies and column origins.
    Wraps manifest.json loaded as a raw dict.
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

    def find_column_origin(
        self, unique_id: str, column_name: str, max_depth: int = 5
    ) -> Optional[dict]:
        """
        Determine if a column is inherited from an upstream model.

        Uses BFS to walk upstream through the DAG, checking each ancestor's
        columns dict and compiled SQL for the target column. BFS ensures we
        find the CLOSEST upstream origin (not an arbitrary deep ancestor).

        Args:
            unique_id: The node to start searching from.
            column_name: The column to trace upstream.
            max_depth: Maximum levels to traverse (default 5, prevents runaway).

        Returns:
            dict with 'model' (unique_id) and 'file' (path) if inherited,
            or None if the column is introduced in the current model.
        """
        visited: set[str] = {unique_id}
        # BFS queue: (node_id, current_depth)
        queue: deque[tuple[str, int]] = deque()

        # Seed with immediate parents
        for parent_id in self.get_parents(unique_id):
            if parent_id not in visited:
                queue.append((parent_id, 1))
                visited.add(parent_id)

        while queue:
            current_id, depth = queue.popleft()

            current_node = self.get_node(current_id)
            if not current_node:
                continue

            # Check if this node declares the column
            if self._node_has_column(current_node, column_name):
                return {
                    "model": current_id,
                    "file": current_node.get("path", ""),
                }

            # If not at max depth, enqueue this node's parents
            if depth < max_depth:
                for parent_id in self.get_parents(current_id):
                    if parent_id not in visited:
                        queue.append((parent_id, depth + 1))
                        visited.add(parent_id)

        return None

    def _node_has_column(self, node: dict, column_name: str) -> bool:
        """
        Check if a node declares a column by name.

        Checks both the columns dict (from YAML schema declarations) and
        the compiled SQL (via regex for AS alias patterns).
        """
        # Check columns dict (case-insensitive)
        columns = node.get("columns", {})
        col_lower = column_name.lower()
        col_upper = column_name.upper()
        if col_lower in columns or col_upper in columns:
            return True

        # Check compiled SQL for the column alias
        compiled = node.get("compiled_code", "")
        if compiled:
            pattern = re.compile(
                rf"\bAS\s+{re.escape(column_name)}\b", re.IGNORECASE
            )
            if pattern.search(compiled):
                return True

        return False
