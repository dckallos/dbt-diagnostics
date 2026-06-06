"""
dbt_diagnostics/tracers/diff_tracer.py

Compares a failing model (and its upstream) against a previous manifest
to identify what changed. Produces a DiffResult attached to the report.
"""

import difflib
from typing import Optional

from dbt_diagnostics.models import DiffResult


def diff_node(
    unique_id: str,
    current_manifest: dict,
    previous_manifest: dict,
) -> Optional[DiffResult]:
    """
    Compare a node between current and previous manifest.

    Returns a DiffResult describing what changed, or None if the node
    doesn't exist in the current manifest.
    """
    current_nodes = current_manifest.get("nodes", {})
    previous_nodes = previous_manifest.get("nodes", {})

    current_node = current_nodes.get(unique_id)
    if not current_node:
        return None

    previous_node = previous_nodes.get(unique_id)

    if previous_node is None:
        # New model (not in previous manifest)
        return DiffResult(
            node_changed=True,
            changed_lines=["+ (new model, not present in previous manifest)"],
            upstream_changes=[],
            columns_added=list(current_node.get("columns", {}).keys()),
        )

    # Compare compiled_code
    current_code = current_node.get("compiled_code", "") or ""
    previous_code = previous_node.get("compiled_code", "") or ""
    node_changed = current_code != previous_code

    changed_lines: list[str] = []
    if node_changed and current_code and previous_code:
        diff = difflib.unified_diff(
            previous_code.splitlines(),
            current_code.splitlines(),
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
        changed_lines = list(diff)[:20]  # cap at 20 lines

    # Compare columns
    current_cols = current_node.get("columns", {})
    previous_cols = previous_node.get("columns", {})

    columns_added = [c for c in current_cols if c not in previous_cols]
    columns_removed = [c for c in previous_cols if c not in current_cols]

    columns_type_changed = []
    for col_name in current_cols:
        if col_name in previous_cols:
            cur_type = (current_cols[col_name].get("data_type") or "").upper()
            prev_type = (previous_cols[col_name].get("data_type") or "").upper()
            if cur_type and prev_type and cur_type != prev_type:
                columns_type_changed.append({
                    "name": col_name,
                    "old_type": prev_type,
                    "new_type": cur_type,
                })

    # Check upstream changes if THIS node didn't change
    upstream_changes: list[dict] = []
    if not node_changed:
        parent_map = current_manifest.get("parent_map", {})
        depends_on = parent_map.get(unique_id, [])
        if not depends_on:
            depends_on = current_node.get("depends_on", {}).get("nodes", [])

        for parent_id in depends_on:
            parent_current = current_nodes.get(parent_id)
            parent_previous = previous_nodes.get(parent_id)

            if parent_current and parent_previous:
                parent_cur_code = parent_current.get("compiled_code", "") or ""
                parent_prev_code = parent_previous.get("compiled_code", "") or ""
                if parent_cur_code != parent_prev_code:
                    upstream_changes.append({
                        "model_id": parent_id,
                        "change_summary": "compiled_code changed",
                    })
            elif parent_current and not parent_previous:
                upstream_changes.append({
                    "model_id": parent_id,
                    "change_summary": "new model (not in previous manifest)",
                })

    return DiffResult(
        node_changed=node_changed,
        changed_lines=changed_lines,
        upstream_changes=upstream_changes,
        columns_added=columns_added,
        columns_removed=columns_removed,
        columns_type_changed=columns_type_changed,
    )
