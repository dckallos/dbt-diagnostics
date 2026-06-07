"""
dbt_diagnostics/enrichers/grants.py

SHOW GRANTS TO ROLE wrapper for privilege-error diagnosis.
Uses only cloud-services-layer queries ($0 cost, no warehouse required).
"""

from typing import Optional


def check_role_grants(
    conn, role_name: str, target_object: str
) -> dict:
    """
    Check if the given role has SELECT/USAGE on the target object.

    Uses: SHOW GRANTS TO ROLE <role_name>
    This always succeeds for the current session role (no special
    privileges needed beyond being able to USE the role).

    Args:
        conn: Active Snowflake connection.
        role_name: The role to inspect (typically from profiles.yml).
        target_object: FQ object name, e.g. "ARTWORK_DB.GOLD.DIM_ARTISTS".

    Returns:
        {
            "has_access": bool,
            "grants_found": list[str],  # e.g. ["SELECT on TABLE DB.SCHEMA.TBL"]
            "role_checked": str,
        }
    """
    grants_found: list[str] = []
    has_access = False

    try:
        cursor = conn.cursor()
        cursor.execute(f"SHOW GRANTS TO ROLE {role_name}")
        rows = cursor.fetchall()
        # Column layout: created_on, privilege, granted_on, name, ...
        # We look for grants whose 'name' matches or contains the target
        target_upper = target_object.upper()
        for row in rows:
            privilege = row[1] if len(row) > 1 else ""
            granted_on = row[2] if len(row) > 2 else ""
            name = row[3] if len(row) > 3 else ""

            if target_upper in name.upper():
                grant_desc = f"{privilege} on {granted_on} {name}"
                grants_found.append(grant_desc)
                if privilege.upper() in ("SELECT", "USAGE", "ALL", "OWNERSHIP"):
                    has_access = True

            # Also check schema-level USAGE (needed for table access)
            parts = target_upper.split(".")
            if len(parts) >= 2:
                schema_fq = ".".join(parts[:2])
                if schema_fq in name.upper() and privilege.upper() in (
                    "USAGE", "ALL", "OWNERSHIP"
                ):
                    grant_desc = f"{privilege} on {granted_on} {name}"
                    if grant_desc not in grants_found:
                        grants_found.append(grant_desc)
    except Exception:
        # If SHOW GRANTS fails (e.g., role doesn't exist), return empty result
        pass

    return {
        "has_access": has_access,
        "grants_found": grants_found,
        "role_checked": role_name,
    }


def get_current_role(conn) -> Optional[str]:
    """Return the current session role name, or None on failure."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_ROLE()")
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None
