"""
dbt_diagnostics/enrichers/params.py

Queries Snowflake session and account parameters to ground explanations
with actual runtime values.
"""

from typing import Optional


def get_parameters(conn, param_names: list[str]) -> dict[str, str]:
    """
    Query SHOW PARAMETERS for each requested parameter name.
    Returns {param_name: value} for params that exist.
    Queries at session level (reflects the effective value for this connection).
    """
    results = {}
    cursor = conn.cursor()

    try:
        for name in param_names:
            try:
                cursor.execute(f"SHOW PARAMETERS LIKE '{name}' IN SESSION")
                rows = cursor.fetchall()
                if rows:
                    # SHOW PARAMETERS returns: key, value, default, level, description, type
                    results[name] = rows[0][1]
            except Exception:
                continue
    finally:
        cursor.close()

    return results


def get_parameter_with_level(conn, param_name: str) -> Optional[dict]:
    """
    Get a single parameter's value AND where it's set (account/user/session/warehouse).
    Returns {"value": "...", "level": "...", "default": "..."} or None.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"SHOW PARAMETERS LIKE '{param_name}' IN SESSION")
        rows = cursor.fetchall()
        if rows:
            return {
                "value": rows[0][1],
                "default": rows[0][2],
                "level": rows[0][3],  # e.g. "ACCOUNT", "SESSION", ""
            }
    except Exception:
        pass
    finally:
        cursor.close()

    return None
