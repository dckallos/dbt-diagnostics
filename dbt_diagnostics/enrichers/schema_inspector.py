"""
dbt_diagnostics/enrichers/schema_inspector.py

Queries Snowflake to inspect actual table structure and existence.
Used to ground "invalid identifier" and "object does not exist" findings.
"""

from difflib import get_close_matches
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
    Find column names similar to target_name using edit distance.
    Uses difflib.get_close_matches for proper fuzzy matching.
    Returns up to 3 suggestions with their edit distance.
    """
    column_names = [col.name.upper() for col in actual_columns]
    target_upper = target_name.upper()

    matches = get_close_matches(target_upper, column_names, n=3, cutoff=0.6)
    return matches


def _edit_distance(a: str, b: str) -> int:
    """
    Compute Levenshtein edit distance between two strings.
    Used to display the distance alongside "did you mean?" suggestions.
    """
    if len(a) < len(b):
        return _edit_distance(b, a)

    if len(b) == 0:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        current_row = [i + 1]
        for j, cb in enumerate(b):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (ca != cb)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
