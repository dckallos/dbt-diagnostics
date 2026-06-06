"""
dbt_diagnostics/enrichers/params.py

Queries Snowflake session and account parameters to ground explanations
with actual runtime values.
"""

import re
from typing import Optional

# Valid Snowflake parameter names: uppercase letters, digits, underscores only
_VALID_PARAM_RE = re.compile(r"^[A-Z][A-Z0-9_]*$", re.IGNORECASE)


def _validate_param_name(name: str) -> bool:
    """Validate that a parameter name is safe to interpolate into SQL."""
    return bool(_VALID_PARAM_RE.match(name))


def get_parameters(conn, param_names: list[str]) -> dict[str, str]:
    """
    Query SHOW PARAMETERS IN SESSION once and filter client-side.
    Returns {param_name: value} for params that exist.
    Much faster than one round-trip per parameter (~100ms vs ~400ms for 4 params).
    """
    # Validate all names up-front; skip invalid ones
    valid_names = {n.upper() for n in param_names if _validate_param_name(n)}
    if not valid_names:
        return {}

    cursor = conn.cursor()
    try:
        cursor.execute("SHOW PARAMETERS IN SESSION")
        rows = cursor.fetchall()
        # SHOW PARAMETERS returns: key, value, default, level, description, type
        return {
            row[0]: row[1]
            for row in rows
            if row[0] in valid_names
        }
    except Exception:
        return {}
    finally:
        cursor.close()


def get_parameter_with_level(conn, param_name: str) -> Optional[dict]:
    """
    Get a single parameter's value AND where it's set (account/user/session/warehouse).
    Returns {"value": "...", "level": "...", "default": "..."} or None.
    """
    if not _validate_param_name(param_name):
        return None

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
