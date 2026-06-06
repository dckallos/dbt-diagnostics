"""
Tests for dbt_diagnostics/discover.py -- project auto-detection logic.
"""

import os
from pathlib import Path

import pytest

from dbt_diagnostics.discover import (
    find_dbt_project,
    read_profile_name,
    find_profiles_yml,
    read_default_target,
    resolve_project_paths,
)


class TestFindDbtProject:
    """Tests for walking up to find dbt_project.yml."""

    def test_finds_project_in_start_dir(self, tmp_path):
        (tmp_path / "dbt_project.yml").write_text("name: test\nprofile: test_profile\n")
        assert find_dbt_project(tmp_path) == tmp_path

    def test_finds_project_in_parent(self, tmp_path):
        (tmp_path / "dbt_project.yml").write_text("name: test\n")
        child = tmp_path / "models" / "staging"
        child.mkdir(parents=True)
        assert find_dbt_project(child) == tmp_path

    def test_returns_none_when_not_found(self, tmp_path):
        child = tmp_path / "some" / "deep" / "path"
        child.mkdir(parents=True)
        assert find_dbt_project(child) is None


class TestReadProfileName:
    """Tests for extracting profile name from dbt_project.yml."""

    def test_reads_profile_field(self, tmp_path):
        (tmp_path / "dbt_project.yml").write_text(
            "name: artwork_pipeline\nprofile: artwork_pipeline\nversion: '1.0.0'\n"
        )
        assert read_profile_name(tmp_path) == "artwork_pipeline"

    def test_returns_none_when_no_profile_field(self, tmp_path):
        (tmp_path / "dbt_project.yml").write_text("name: test\nversion: '1.0.0'\n")
        assert read_profile_name(tmp_path) is None

    def test_returns_none_when_file_missing(self, tmp_path):
        assert read_profile_name(tmp_path) is None

    def test_returns_none_for_invalid_yaml(self, tmp_path):
        (tmp_path / "dbt_project.yml").write_text(": invalid: yaml: [[[")
        assert read_profile_name(tmp_path) is None


class TestFindProfilesYml:
    """Tests for profiles.yml location logic."""

    def test_finds_project_local(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text("artwork_pipeline:\n  target: dev\n")
        assert find_profiles_yml(tmp_path) == profiles

    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        env_dir = tmp_path / "env_profiles"
        env_dir.mkdir()
        (env_dir / "profiles.yml").write_text("test:\n  target: dev\n")
        monkeypatch.setenv("DBT_PROFILES_DIR", str(env_dir))
        # Even if project-local exists, env var wins
        (tmp_path / "profiles.yml").write_text("local:\n  target: dev\n")
        assert find_profiles_yml(tmp_path) == env_dir / "profiles.yml"

    def test_returns_none_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DBT_PROFILES_DIR", raising=False)
        # Ensure ~/.dbt/profiles.yml doesn't interfere
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "fake_home"))
        assert find_profiles_yml(tmp_path) is None


class TestReadDefaultTarget:
    """Tests for reading the default target from profiles.yml."""

    def test_reads_target(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text(
            "artwork_pipeline:\n"
            "  target: prod\n"
            "  outputs:\n"
            "    dev:\n"
            "      type: snowflake\n"
            "    prod:\n"
            "      type: snowflake\n"
        )
        assert read_default_target(profiles, "artwork_pipeline") == "prod"

    def test_returns_none_for_missing_profile(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text("other_profile:\n  target: dev\n")
        assert read_default_target(profiles, "artwork_pipeline") is None

    def test_returns_none_for_invalid_yaml(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text(": bad yaml [[[")
        assert read_default_target(profiles, "artwork_pipeline") is None


class TestResolveProjectPaths:
    """Tests for deriving artifact paths from a project directory."""

    def test_all_paths_derived(self, tmp_path):
        paths = resolve_project_paths(tmp_path)
        assert paths["project_dir"] == tmp_path
        assert paths["target_dir"] == tmp_path / "target"
        assert paths["run_results"] == tmp_path / "target" / "run_results.json"
        assert paths["manifest"] == tmp_path / "target" / "manifest.json"
        assert paths["compiled_dir"] == tmp_path / "target" / "compiled"
        assert paths["models_dir"] == tmp_path / "models"
