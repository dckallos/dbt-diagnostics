"""
dbt_diagnostics/tracers/dag_walker.py

Walks the dbt DAG (from manifest.json) to trace column origins upstream.
Works directly with the raw manifest dict (stable across dbt versions).
"""

import re
from collections import deque
from typing import Optional

from dbt_diagnostics.models import LineageStep


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

    def _make_step(self, node_id: str, node: Optional[dict], depth: int) -> LineageStep:
        """
        Build a LineageStep from a node dict.

        Extracts node_type from the unique_id prefix (model.*, source.*, etc.)
        and short_name from the last segment.
        """
        # Parse node_type from unique_id prefix
        parts = node_id.split(".")
        node_type = parts[0] if parts else "unknown"
        short_name = parts[-1] if parts else node_id

        file_path = None
        relation_name = None
        if node:
            file_path = node.get("original_file_path") or node.get("path")
            relation_name = node.get("relation_name")

        return LineageStep(
            node_id=node_id,
            node_type=node_type,
            short_name=short_name,
            file_path=file_path,
            relation_name=relation_name,
            depth=depth,
        )

    def trace_column_lineage(
        self,
        unique_id: str,
        column_name: str,
        max_depth: int = 5,
        run_results: Optional[dict] = None,
    ) -> list[LineageStep]:
        """
        Trace a column upstream through the DAG, recording status at EVERY node.

        Unlike find_column_origin() which returns only the first match, this
        method returns the full trail so the renderer can show the user every
        hop the column takes (or doesn't take) through the lineage.

        Args:
            unique_id: The failing node to start from (depth 0).
            column_name: The column to trace.
            max_depth: Maximum BFS depth.
            run_results: Optional parsed run_results dict for cross-referencing
                         node run status.

        Returns:
            List of LineageStep ordered by depth (depth 0 first). The depth-0
            entry is the failing model itself.
        """
        trail: list[LineageStep] = []
        run_status_map = self._build_run_status_map(run_results)

        # Depth 0: the failing model itself
        root_node = self.get_node(unique_id)
        root_step = self._make_step(unique_id, root_node, depth=0)
        root_step.manifest_status = "declared"
        root_step.run_status = run_status_map.get(unique_id)
        root_step.annotation = "failing model"
        trail.append(root_step)

        # BFS upstream
        visited: set[str] = {unique_id}
        queue: deque[tuple[str, int]] = deque()

        for parent_id in self.get_parents(unique_id):
            if parent_id not in visited:
                queue.append((parent_id, 1))
                visited.add(parent_id)

        while queue:
            current_id, depth = queue.popleft()
            current_node = self.get_node(current_id)

            step = self._make_step(current_id, current_node, depth)
            step.run_status = run_status_map.get(current_id)

            if current_node and self._node_has_column(current_node, column_name):
                step.manifest_status = "declared"
                step.manifest_detail = f"column '{column_name}' found"
            else:
                step.manifest_status = "not_found"
                step.manifest_detail = f"column '{column_name}' not found"

            trail.append(step)

            # Continue BFS if within depth limit
            if depth < max_depth:
                for parent_id in self.get_parents(current_id):
                    if parent_id not in visited:
                        queue.append((parent_id, depth + 1))
                        visited.add(parent_id)

        return trail

    def trace_object_lineage(
        self,
        unique_id: str,
        object_fq_name: str,
        run_results: Optional[dict] = None,
    ) -> list[LineageStep]:
        """
        Trace an object reference upstream -- used for object-not-found errors.

        Checks manifest sources and upstream nodes for a matching relation_name.
        This answers: "where should this object come from in the DAG?"

        Args:
            unique_id: The failing node (depth 0).
            object_fq_name: Fully qualified object name from the error message
                            (e.g. "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS").
            run_results: Optional run_results dict for cross-referencing.

        Returns:
            List of LineageStep. If the object is found in the manifest (as a
            source or upstream model), that node appears in the trail with
            manifest_status="declared". Otherwise all upstream nodes show
            "not_found".
        """
        trail: list[LineageStep] = []
        run_status_map = self._build_run_status_map(run_results)
        object_upper = object_fq_name.upper()

        # Depth 0: the failing model
        root_node = self.get_node(unique_id)
        root_step = self._make_step(unique_id, root_node, depth=0)
        root_step.manifest_status = "declared"
        root_step.run_status = run_status_map.get(unique_id)
        root_step.annotation = "failing model"
        trail.append(root_step)

        # Check all sources in the manifest for a matching relation_name
        matched_source_id = None
        for source_id, source_node in self.sources.items():
            relation = source_node.get("relation_name", "")
            if relation and relation.upper() == object_upper:
                matched_source_id = source_id
                break

        # Also check upstream nodes for matching relation_name
        if not matched_source_id:
            for node_id, node in self.nodes.items():
                if node_id == unique_id:
                    continue
                relation = node.get("relation_name", "")
                if relation and relation.upper() == object_upper:
                    matched_source_id = node_id
                    break

        if matched_source_id:
            matched_node = self.get_node(matched_source_id)
            step = self._make_step(matched_source_id, matched_node, depth=1)
            step.manifest_status = "declared"
            step.manifest_detail = f"relation_name matches '{object_fq_name}'"
            step.run_status = run_status_map.get(matched_source_id)
            trail.append(step)
        else:
            # Object not found anywhere in the manifest -- record that fact
            # as a synthetic step at depth 1
            step = LineageStep(
                node_id=f"unknown.{object_fq_name}",
                node_type="unknown",
                short_name=object_fq_name.split(".")[-1] if "." in object_fq_name else object_fq_name,
                relation_name=object_fq_name,
                depth=1,
                manifest_status="missing",
                manifest_detail="object not found in manifest sources or nodes",
            )
            trail.append(step)

        return trail

    @staticmethod
    def _build_run_status_map(run_results: Optional[dict]) -> dict[str, str]:
        """
        Build a lookup from unique_id -> run status string.

        Parses the run_results dict (the full JSON structure with a 'results'
        key) into a flat map for O(1) lookups during trail building.
        """
        if not run_results:
            return {}
        status_map: dict[str, str] = {}
        for result in run_results.get("results", []):
            uid = result.get("unique_id", "")
            status = result.get("status", "")
            if uid and status:
                status_map[uid] = status
        return status_map
