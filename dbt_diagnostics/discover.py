"""
dbt_diagnostics/discover.py

Auto-detects dbt project structure by walking up from the current directory.
Mirrors dbt's own project resolution logic:
  1. Walk up from cwd (or --project-dir) looking for dbt_project.yml
  2. Read profile name from dbt_project.yml
  3. Find profiles.yml (project-local first, then ~/.dbt/)
  4. Read the default target from the profile

Every value can be overridden by a CLI flag, making the tool zero-config
in any dbt project directory.
"""

from pathlib import Path
from typing import Optional

import yaml


def find_dbt_project(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Walk up from start_dir (default: cwd) looking for dbt_project.yml.
    Returns the directory containing it, or None.
    """
    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "dbt_project.yml").exists():
            return directory
    return None


def read_profile_name(project_dir: Path) -> Optional[str]:
    """
    Read the `profile:` field from dbt_project.yml.
    Returns None if the file doesn't exist or has no profile field.
    """
    dbt_project_path = project_dir / "dbt_project.yml"
    if not dbt_project_path.exists():
        return None
    try:
        with open(dbt_project_path) as f:
            data = yaml.safe_load(f)
        return data.get("profile") if isinstance(data, dict) else None
    except (yaml.YAMLError, OSError):
        return None


def find_profiles_yml(project_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Locate profiles.yml using dbt's search order:
      1. DBT_PROFILES_DIR env var
      2. <project_dir>/profiles.yml (project-local)
      3. ~/.dbt/profiles.yml
    """
    import os

    env_dir = os.environ.get("DBT_PROFILES_DIR")
    if env_dir:
        candidate = Path(env_dir) / "profiles.yml"
        if candidate.exists():
            return candidate

    if project_dir:
        candidate = project_dir / "profiles.yml"
        if candidate.exists():
            return candidate

    home = Path.home() / ".dbt" / "profiles.yml"
    if home.exists():
        return home

    return None


def read_default_target(
    profiles_path: Path, profile_name: str
) -> Optional[str]:
    """
    Read the default target name from a profiles.yml for a given profile.
    """
    try:
        with open(profiles_path) as f:
            data = yaml.safe_load(f)
        profile = data.get(profile_name, {})
        return profile.get("target") if isinstance(profile, dict) else None
    except (yaml.YAMLError, OSError):
        return None


def resolve_project_paths(project_dir: Path) -> dict:
    """
    Derive all standard dbt artifact paths from the project directory.
    """
    return {
        "project_dir": project_dir,
        "target_dir": project_dir / "target",
        "run_results": project_dir / "target" / "run_results.json",
        "manifest": project_dir / "target" / "manifest.json",
        "compiled_dir": project_dir / "target" / "compiled",
        "models_dir": project_dir / "models",
    }
