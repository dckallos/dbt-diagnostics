"""
dbt_diagnostics/enrichers/query_history.py

Queries INFORMATION_SCHEMA.QUERY_HISTORY to find the exact Snowflake error
for a failed dbt model execution. Uses timing from run_results.json to
narrow the search window.

Uses INFORMATION_SCHEMA (not ACCOUNT_USAGE) so:
- No latency (real-time)
- Only sees queries from the current role's session history
- 7-day retention
"""

from typing import Optional
from difflib import SequenceMatcher


def find_matching_query(
    conn,
    compiled_sql: str,
    started_at: str,
    completed_at: str,
) -> Optional[dict]:
    """
    Search query history for the executed version of compiled_sql.

    Uses the time window from run_results.json timing to narrow results,
    then matches by text similarity to the compiled SQL.

    Returns {"query_text": ..., "error_message": ..., "error_code": ...}
    if a confident match is found (>= 80% similarity), else None.
    """
    if not compiled_sql or not started_at:
        return None

    cursor = conn.cursor()
    try:
        # Query INFORMATION_SCHEMA for recent failed queries in the time window.
        # Expand window by 30 seconds on each side to account for clock drift.
        sql = """
            SELECT
                QUERY_TEXT,
                ERROR_CODE,
                ERROR_MESSAGE,
                EXECUTION_STATUS
            FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
                END_TIME_RANGE_START => TO_TIMESTAMP_LTZ(%s) - INTERVAL '30 SECONDS',
                END_TIME_RANGE_END => TO_TIMESTAMP_LTZ(%s) + INTERVAL '30 SECONDS',
                RESULT_LIMIT => 50
            ))
            WHERE EXECUTION_STATUS = 'FAIL'
            ORDER BY START_TIME DESC
        """
        cursor.execute(sql, (started_at, completed_at))
        rows = cursor.fetchall()

        if not rows:
            return None

        # Find the best match by text similarity
        best_match = None
        best_score = 0.0

        for row in rows:
            query_text = row[0] or ""
            score = _text_similarity(compiled_sql, query_text)
            if score > best_score:
                best_score = score
                best_match = row

        # Only return if confidence is high enough
        if best_score >= 0.80 and best_match:
            return {
                "query_text": best_match[0],
                "error_code": best_match[1],
                "error_message": best_match[2],
            }

        return None

    except Exception:
        return None
    finally:
        cursor.close()


def _text_similarity(a: str, b: str) -> float:
    """
    Compute similarity ratio between two SQL strings.
    Normalizes whitespace before comparing.
    """
    a_norm = " ".join(a.split()).upper()
    b_norm = " ".join(b.split()).upper()

    # For very long strings, compare just the first 2000 chars
    # (dbt wraps compiled SQL in CREATE TABLE AS which adds boilerplate)
    if len(a_norm) > 2000:
        a_norm = a_norm[:2000]
    if len(b_norm) > 2000:
        b_norm = b_norm[:2000]

    return SequenceMatcher(None, a_norm, b_norm).ratio()
