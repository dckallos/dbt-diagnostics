# Version-tolerant, never-raising accessors for the dbt artifact fields we consume.
# Mirrors the fallbacks declared in consumed_paths.REGISTRY so the runtime reader and
# the static schema-diff cannot drift apart.
# Co-authored with CoCo
"""
These helpers implement the runtime side of the cross-version contract: read the
primary key, fall back to known historical aliases, and return None (never raise)
when nothing matches so the caller can fall through to the live-warehouse recovery.
"""

from __future__ import annotations

from typing import Any, Optional


def dig(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely walk nested dict keys; return default on any miss or non-dict."""
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, default)
    return cur


def _first(node: dict, *keys: str) -> Optional[Any]:
    """First non-None value among keys (in order)."""
    for key in keys:
        val = node.get(key)
        if val is not None:
            return val
    return None


def node_compiled_sql(node: dict) -> Optional[str]:
    """compiled_code (manifest v7+/dbt 1.3+) with fallback to compiled_sql (<=v6)."""
    return _first(node, "compiled_code", "compiled_sql")


def node_raw_sql(node: dict) -> Optional[str]:
    """raw_code (manifest v7+/dbt 1.3+) with fallback to raw_sql (<=v6)."""
    return _first(node, "raw_code", "raw_sql")


def node_relation_name(node: dict) -> Optional[str]:
    """relation_name (present manifest v1-v12; None for seeds/tests -> live recovery)."""
    return node.get("relation_name")


def result_query_id(result: dict) -> Optional[str]:
    """Snowflake query id from adapter_response; absent on other adapters/operations."""
    return dig(result, "adapter_response", "query_id")


def result_rows_affected(result: dict) -> Optional[int]:
    return dig(result, "adapter_response", "rows_affected")
