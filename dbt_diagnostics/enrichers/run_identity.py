"""
dbt_diagnostics/enrichers/run_identity.py

Recover the role a dbt run actually used, with an honest fallback ladder:

  Tier 0 (recovered): the failing statement's query_id -> ROLE_NAME in
          INFORMATION_SCHEMA.QUERY_HISTORY. This is the role the run really
          used, not a guess.
  Tier 2 (declared):  the role resolved from the dbt profile/target.
  Tier 3 (session):   CURRENT_ROLE() of the diagnostic's own connection.

When a query_id lookup returns nothing we distinguish "not yet" (history is
still catching up -- worth a short retry) from "never" (older than the ~7-day
INFORMATION_SCHEMA window, or not visible to this role) using a watermark
comparison against the run's own timestamp. We never block for long, and we
never raise: callers get a role plus its provenance and the queries used.
"""

import time
from typing import Optional

# Provenance strings mirror dbt_diagnostics.root_cause (kept local to avoid an
# import cycle; values must stay in sync).
PROV_RECOVERED = "recovered"
PROV_DECLARED = "declared"
PROV_SESSION = "session"
PROV_UNKNOWN = "unknown"

# Lookup status (for callers / tests that want the timing detail).
STATUS_RECOVERED = "recovered"
STATUS_LAGGING = "lagging"
STATUS_NOT_FOUND = "not_found"
STATUS_NO_QUERY_ID = "no_query_id"


def _end_time_for(run_results: Optional[dict], query_id: Optional[str]) -> Optional[str]:
    """Find the completion timestamp of the result whose query_id matches."""
    if not run_results or not query_id:
        return None
    for result in run_results.get("results", []):
        adapter = result.get("adapter_response") or {}
        if adapter.get("query_id") == query_id:
            for t in result.get("timing", []):
                if t.get("name") == "execute" and t.get("completed_at"):
                    return t["completed_at"]
            if result.get("timing"):
                return result["timing"][-1].get("completed_at")
    return None


def _row_role(conn, query_id: str) -> Optional[dict]:
    """Look up a single query_id in INFORMATION_SCHEMA.QUERY_HISTORY."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT ROLE_NAME, USER_NAME, WAREHOUSE_NAME, EXECUTION_STATUS, END_TIME
            FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(RESULT_LIMIT => 1000))
            WHERE QUERY_ID = %s
            """,
            (query_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "role": row[0],
            "user": row[1],
            "warehouse": row[2],
            "execution_status": row[3],
            "end_time": row[4],
        }
    except Exception:
        return None
    finally:
        cursor.close()


def _history_watermark(conn) -> Optional[object]:
    """Newest END_TIME currently visible in query history, or None."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT MAX(END_TIME)
            FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(RESULT_LIMIT => 1000))
            """
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _is_lagging(conn, run_end_time: Optional[str]) -> bool:
    """
    Decide whether an empty query_id lookup is "not yet" (history is behind the
    run) versus "never". If history's newest entry predates the run, history is
    still catching up -> lagging. If we cannot compare, assume not lagging so we
    do not retry pointlessly.
    """
    if not run_end_time:
        return False
    watermark = _history_watermark(conn)
    if watermark is None:
        return True  # nothing visible yet at all -> almost certainly catching up
    try:
        from datetime import datetime
        run_dt = datetime.fromisoformat(str(run_end_time).replace("Z", "+00:00"))
        wm_dt = watermark
        if isinstance(watermark, str):
            wm_dt = datetime.fromisoformat(watermark.replace("Z", "+00:00"))
        if run_dt.tzinfo and wm_dt.tzinfo is None:
            wm_dt = wm_dt.replace(tzinfo=run_dt.tzinfo)
        return wm_dt < run_dt
    except Exception:
        return False


def recover_role_by_query_id(
    conn,
    query_id: Optional[str],
    run_end_time: Optional[str] = None,
    retries: int = 1,
    sleep_s: float = 1.0,
) -> dict:
    """
    Tier-0 recovery. Returns {role, status, queries}. status is one of
    STATUS_RECOVERED / STATUS_LAGGING / STATUS_NOT_FOUND / STATUS_NO_QUERY_ID.
    Never raises.
    """
    queries = [
        "SELECT ROLE_NAME FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(...)) "
        f"WHERE QUERY_ID = '{query_id}'" if query_id else
        "SELECT ROLE_NAME FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(...)) "
        "WHERE QUERY_ID = '<failing-query-id>'"
    ]
    if not query_id:
        return {"role": None, "status": STATUS_NO_QUERY_ID, "queries": queries}

    attempt = 0
    while True:
        row = _row_role(conn, query_id)
        if row and row.get("role"):
            return {"role": row["role"], "status": STATUS_RECOVERED,
                    "queries": queries, "detail": row}
        # Empty: decide not-yet vs never.
        if attempt < retries and _is_lagging(conn, run_end_time):
            time.sleep(sleep_s)
            attempt += 1
            continue
        status = STATUS_LAGGING if _is_lagging(conn, run_end_time) else STATUS_NOT_FOUND
        return {"role": None, "status": status, "queries": queries}


def current_session_role(conn) -> Optional[str]:
    """Tier-3: the diagnostic connection's own role."""
    try:
        from dbt_diagnostics.enrichers.grants import get_current_role
        return get_current_role(conn)
    except Exception:
        return None


def recover_run_role(
    conn,
    query_id: Optional[str] = None,
    run_results: Optional[dict] = None,
    declared_role: Optional[str] = None,
    retries: int = 1,
    sleep_s: float = 1.0,
) -> dict:
    """
    Resolve the run's role using the full ladder.

    Returns {role, provenance, status, queries}. provenance is one of
    PROV_RECOVERED / PROV_DECLARED / PROV_SESSION / PROV_UNKNOWN. A drift note is
    added when a recovered role disagrees with the declared one.
    """
    run_end_time = _end_time_for(run_results, query_id)
    recovered = recover_role_by_query_id(
        conn, query_id, run_end_time=run_end_time, retries=retries, sleep_s=sleep_s
    )

    if recovered.get("role"):
        out = {
            "role": recovered["role"],
            "provenance": PROV_RECOVERED,
            "status": recovered["status"],
            "queries": recovered["queries"],
        }
        if declared_role and declared_role.upper() != recovered["role"].upper():
            out["drift"] = (
                f"run executed as {recovered['role']}, but the dbt profile "
                f"resolves to {declared_role}; using the recovered role"
            )
        return out

    # Tier 2: declared role from the profile.
    if declared_role:
        return {
            "role": declared_role,
            "provenance": PROV_DECLARED,
            "status": recovered["status"],
            "queries": recovered["queries"],
        }

    # Tier 3: the diagnostic session's own role.
    session_role = current_session_role(conn)
    if session_role:
        return {
            "role": session_role,
            "provenance": PROV_SESSION,
            "status": recovered["status"],
            "queries": recovered["queries"],
        }

    return {
        "role": None,
        "provenance": PROV_UNKNOWN,
        "status": recovered["status"],
        "queries": recovered["queries"],
    }
