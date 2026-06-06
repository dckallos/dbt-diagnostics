"""
dbt_diagnostics/enrichers/connection.py

Opens a Snowflake connection by parsing the dbt profiles.yml file.
Handles env_var() substitution via regex (covers 95%+ of real profiles).
Does NOT depend on dbt-core internals.

Search order for profiles.yml:
  1. DBT_PROFILES_DIR env var
  2. <dbt_project_dir>/profiles.yml (project-local)
  3. ~/.dbt/profiles.yml (global default)
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional

import yaml


# Matches {{ env_var('KEY') }} and {{ env_var('KEY', 'default') }}
_ENV_VAR_RE = re.compile(
    r"\{\{\s*env_var\(\s*['\"]([^'\"]+)['\"]\s*"
    r"(?:,\s*['\"]([^'\"]*)['\"])?\s*\)\s*\}\}"
)


def _resolve_env_vars(value: str) -> str:
    """Replace {{ env_var('X') }} and {{ env_var('X', 'default') }} with os.environ."""
    def _replace(match):
        key = match.group(1)
        default = match.group(2)
        result = os.environ.get(key, default)
        if result is None:
            raise ValueError(
                f"Environment variable '{key}' is not set and no default provided "
                f"in profiles.yml"
            )
        return result

    return _ENV_VAR_RE.sub(_replace, value)


def _resolve_profile_values(data: dict) -> dict:
    """Recursively resolve env_var() in all string values."""
    resolved = {}
    for key, value in data.items():
        if isinstance(value, str) and "{{" in value:
            resolved[key] = _resolve_env_vars(value)
        elif isinstance(value, dict):
            resolved[key] = _resolve_profile_values(value)
        else:
            resolved[key] = value
    return resolved


def _load_dotenv(project_dir: Optional[Path] = None):
    """
    Load .env file into os.environ if python-dotenv is available.
    Searches project_dir first, then cwd.
    Does not override existing env vars.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    candidates = []
    if project_dir:
        candidates.append(project_dir.parent / ".env")  # repo root .env
        candidates.append(project_dir / ".env")
    candidates.append(Path.cwd() / ".env")

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            return


def _find_profiles_yml(project_dir: Optional[Path] = None) -> Optional[Path]:
    """Locate profiles.yml using dbt's standard search order."""
    # 1. DBT_PROFILES_DIR env var
    env_dir = os.environ.get("DBT_PROFILES_DIR")
    if env_dir:
        candidate = Path(env_dir) / "profiles.yml"
        if candidate.exists():
            return candidate

    # 2. Project-local profiles.yml (common in this repo's setup)
    if project_dir:
        candidate = project_dir / "profiles.yml"
        if candidate.exists():
            return candidate

    # 3. ~/.dbt/profiles.yml (standard location)
    home = Path.home() / ".dbt" / "profiles.yml"
    if home.exists():
        return home

    return None


def parse_profile(
    profile_name: str,
    target_name: str,
    project_dir: Optional[Path] = None,
) -> Optional[dict]:
    """
    Parse profiles.yml and return connection kwargs for snowflake.connector.connect().

    Returns None if the profile can't be found or parsed.
    Raises ValueError if env_var() references unset variables with no defaults.
    """
    # Load .env before resolving env_var() references
    _load_dotenv(project_dir)

    profiles_path = _find_profiles_yml(project_dir)
    if not profiles_path:
        return None

    with open(profiles_path) as f:
        raw = yaml.safe_load(f)

    if profile_name not in raw:
        return None

    profile = raw[profile_name]
    outputs = profile.get("outputs", {})
    target = target_name or profile.get("target", "dev")

    if target not in outputs:
        return None

    target_config = _resolve_profile_values(outputs[target])

    if target_config.get("type") != "snowflake":
        return None

    # Map dbt profile fields to snowflake-connector-python kwargs
    connect_kwargs = {
        "account": target_config.get("account"),
        "user": target_config.get("user"),
        "database": target_config.get("database"),
        "schema": target_config.get("schema"),
        "warehouse": target_config.get("warehouse"),
        "role": target_config.get("role"),
    }

    # Authentication: key-pair takes priority over password
    if "private_key_path" in target_config:
        key_path = target_config["private_key_path"]
        if key_path:  # Skip empty string from env_var('...', '')
            connect_kwargs["private_key_file"] = key_path
        passphrase = target_config.get("private_key_passphrase", "")
        if passphrase:  # Only pass if non-empty
            connect_kwargs["private_key_file_pwd"] = passphrase
    elif "password" in target_config:
        password = target_config["password"]
        if password:
            connect_kwargs["password"] = password
    elif "authenticator" in target_config:
        connect_kwargs["authenticator"] = target_config["authenticator"]

    # Remove None and empty-string values
    return {k: v for k, v in connect_kwargs.items() if v}


def open_connection(
    profile_name: str,
    target_name: str,
    project_dir: Optional[Path] = None,
):
    """
    Open a Snowflake connection using credentials from profiles.yml.

    Returns a snowflake.connector connection object, or None if:
    - profiles.yml can't be found
    - snowflake-connector-python is not installed
    - connection fails

    Prints the failure reason to stderr for debugging.
    """
    try:
        import snowflake.connector
    except ImportError:
        print(
            "  snowflake-connector-python is not installed.\n"
            "  Install with: pip install \"dbt_diagnostics[live]\"",
            file=sys.stderr,
        )
        return None

    try:
        kwargs = parse_profile(profile_name, target_name, project_dir)
    except ValueError as e:
        print(f"  Profile parse error: {e}", file=sys.stderr)
        return None

    if not kwargs:
        print(
            f"  Could not find profile '{profile_name}' target '{target_name}' "
            f"in profiles.yml.\n"
            f"  Searched: DBT_PROFILES_DIR, {project_dir}/profiles.yml, ~/.dbt/profiles.yml",
            file=sys.stderr,
        )
        return None

    try:
        return snowflake.connector.connect(**kwargs)
    except Exception as e:
        print(f"  Snowflake connection failed: {e}", file=sys.stderr)
        return None
