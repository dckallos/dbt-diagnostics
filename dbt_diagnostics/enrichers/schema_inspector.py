"""
dbt_diagnostics/enrichers/schema_inspector.py

Queries Snowflake to inspect actual table structure and existence.
Used to ground "invalid identifier" and "object does not exist" findings.
"""

from typing import Optional

from dbt_diagnostics.models import ColumnInfo


def describe_table(conn, fq_table_name: str) -> list[ColumnInfo]:
    """
    Run DESCRIBE TABLE and return the actual column list.
    Returns empty list if the table doesn't exist or access is denied.

    fq_table_name: fully qualified like "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"DESCRIBE TABLE {fq_table_name}")
        rows = cursor.fetchall()
        # DESCRIBE TABLE returns: name, type, kind, null?, default, primary_key, ...
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in rows]
    except Exception:
        return []
    finally:
        cursor.close()


def table_exists(conn, fq_table_name: str) -> Optional[bool]:
    """
    Check if a table exists by running SHOW TABLES.
    Returns True/False, or None if the check itself failed (e.g., no USAGE on schema).

    fq_table_name: "DATABASE.SCHEMA.TABLE"
    """
    parts = fq_table_name.split(".")
    if len(parts) != 3:
        return None

    db, schema, table = parts
    cursor = conn.cursor()
    try:
        cursor.execute(f"SHOW TABLES LIKE '{table}' IN {db}.{schema}")
        rows = cursor.fetchall()
        return len(rows) > 0
    except Exception:
        return None
    finally:
        cursor.close()


def find_similar_columns(
    actual_columns: list[ColumnInfo], target_name: str
) -> list[str]:
    """
    Find column names similar to target_name (case-insensitive prefix/substring match).
    Returns up to 3 suggestions.
    """
    target_upper = target_name.upper()
    suggestions = []

    for col in actual_columns:
        col_upper = col.name.upper()
        # Exact match minus one char, substring, or shared prefix
        if (
            target_upper in col_upper
            or col_upper in target_upper
            or _common_prefix_len(target_upper, col_upper) >= len(target_upper) // 2
        ):
            suggestions.append(col.name)

    return suggestions[:3]


def _common_prefix_len(a: str, b: str) -> int:
    """Length of the common prefix between two strings."""
    length = 0
    for ca, cb in zip(a, b):
        if ca == cb:
            length += 1
        else:
            break
    return length
