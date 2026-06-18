# dbt_diagnostics/compat/safe.py
# Version-tolerant, never-raising accessors for the dbt artifact fields we consume.
# Mirrors the fallbacks declared in consumed_paths.REGISTRY so the runtime reader and
# the static schema-diff cannot drift apart.
"""
These helpers implement the runtime side of the cross-version contract: read the
primary key, fall back to known historical aliases, and return None (never raise)
when nothing matches so the caller can fall through to the live-warehouse recovery.
"""

from __future__ import annotations

from typing import Any, Optional


_MISSING = object()


def dig(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely walk nested dict keys; return default on any miss or non-dict."""
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, _MISSING)
        if cur is _MISSING:
            return default
    return cur


def _first(obj: Any, *keys: str) -> Optional[Any]:
    """First non-None value among keys (in order); None for non-dict input."""
    if not isinstance(obj, dict):
        return None

    for key in keys:
        val = obj.get(key)
        if val is not None:
            return val
    return None


def _string_or_none(value: Any) -> Optional[str]:
    """Return string artifact values only; malformed values degrade to None."""
    return value if isinstance(value, str) else None


def node_compiled_code(node: Any) -> Optional[str]:
    """compiled_code (manifest v7+/dbt 1.3+) with fallback to compiled_sql (<=v6)."""
    return _string_or_none(_first(node, "compiled_code", "compiled_sql"))


def node_compiled_sql(node: Any) -> Optional[str]:
    """Backward-compatible alias for callers that still use the SQL naming."""
    return node_compiled_code(node)


def node_raw_code(node: Any) -> Optional[str]:
    """raw_code (manifest v7+/dbt 1.3+) with fallback to raw_sql (<=v6)."""
    return _string_or_none(_first(node, "raw_code", "raw_sql"))


def node_raw_sql(node: Any) -> Optional[str]:
    """Backward-compatible alias for callers that still use the SQL naming."""
    return node_raw_code(node)


def node_relation_name(node: Any) -> Optional[str]:
    """relation_name (present manifest v1-v12; None for seeds/tests -> live recovery)."""
    return _string_or_none(dig(node, "relation_name"))


def result_query_id(result: Any) -> Optional[str]:
    """Snowflake query id from adapter_response; absent on other adapters/operations."""
    return _string_or_none(dig(result, "adapter_response", "query_id"))


def result_rows_affected(result: Any) -> Optional[int]:
    """Snowflake rows_affected from adapter_response; absent on other adapters."""
    value = dig(result, "adapter_response", "rows_affected")
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
