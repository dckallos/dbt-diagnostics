"""
Tests for the linters layer (pre-execution static checks).
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from io import StringIO

import pytest

from dbt_diagnostics.linters import LINTER_REGISTRY
from dbt_diagnostics.linters.contract_column_count import ContractColumnCountLinter
from dbt_diagnostics.linters.type_hazard import TypeHazardLinter
from dbt_diagnostics.linters.duplicate_alias import DuplicateAliasLinter
from dbt_diagnostics.linters.missing_contract_column import MissingContractColumnLinter
from dbt_diagnostics.models import LintFinding


# --- ContractColumnCountLinter ---


class TestContractColumnCount:
    """Tests for the contract_column_count linter."""

    def test_mismatch_triggers_finding(self):
        """SQL has 3 columns, contract declares 2 -> error."""
        linter = ContractColumnCountLinter()
        sql = "SELECT 1 AS id, 'hello' AS name, 42 AS age FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {
                "id": {"name": "id", "data_type": "INT"},
                "name": {"name": "name", "data_type": "VARCHAR"},
            },
            "contract": {"enforced": True},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "3" in findings[0].message
        assert "2" in findings[0].message

    def test_matching_count_no_finding(self):
        """SQL and contract agree on column count -> no finding."""
        linter = ContractColumnCountLinter()
        sql = "SELECT 1 AS id, 'hello' AS name FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {
                "id": {"name": "id", "data_type": "INT"},
                "name": {"name": "name", "data_type": "VARCHAR"},
            },
            "contract": {"enforced": True},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 0

    def test_no_contract_skips(self):
        """Model without enforced contract is skipped."""
        linter = ContractColumnCountLinter()
        sql = "SELECT 1 AS id, 'hello' AS name, 42 AS age FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {"id": {"name": "id"}},
            "contract": {"enforced": False},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 0


# --- TypeHazardLinter ---


class TestTypeHazard:
    """Tests for the type_hazard linter."""

    def test_current_timestamp_without_cast_triggers(self):
        """CURRENT_TIMESTAMP() without ::TIMESTAMP_NTZ when contract expects NTZ."""
        linter = TypeHazardLinter()
        sql = "SELECT id, CURRENT_TIMESTAMP() AS loaded_at FROM foo"
        node = {
            "original_file_path": "models/stg_test.sql",
            "columns": {
                "id": {"name": "id", "data_type": "INT"},
                "loaded_at": {"name": "loaded_at", "data_type": "TIMESTAMP_NTZ"},
            },
        }
        findings = linter.lint("model.pkg.stg_test", sql, node)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "CURRENT_TIMESTAMP" in findings[0].message

    def test_current_timestamp_with_cast_clean(self):
        """CURRENT_TIMESTAMP()::TIMESTAMP_NTZ -> no finding."""
        linter = TypeHazardLinter()
        sql = "SELECT id, CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS loaded_at FROM foo"
        node = {
            "original_file_path": "models/stg_test.sql",
            "columns": {
                "loaded_at": {"name": "loaded_at", "data_type": "TIMESTAMP_NTZ"},
            },
        }
        findings = linter.lint("model.pkg.stg_test", sql, node)
        assert len(findings) == 0

    def test_no_ntz_contract_skips(self):
        """No TIMESTAMP_NTZ in contract -> skip entirely."""
        linter = TypeHazardLinter()
        sql = "SELECT CURRENT_TIMESTAMP() AS ts FROM foo"
        node = {
            "original_file_path": "models/stg_test.sql",
            "columns": {"ts": {"name": "ts", "data_type": "TIMESTAMP_LTZ"}},
        }
        findings = linter.lint("model.pkg.stg_test", sql, node)
        assert len(findings) == 0


# --- DuplicateAliasLinter ---


class TestDuplicateAlias:
    """Tests for the duplicate_alias linter."""

    def test_duplicate_alias_triggers(self):
        """SELECT a AS x, b AS x -> error."""
        linter = DuplicateAliasLinter()
        sql = "SELECT 1 AS x, 2 AS x FROM foo"
        node = {"original_file_path": "models/test.sql"}
        findings = linter.lint("model.pkg.test", sql, node)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert "X" in findings[0].message

    def test_unique_aliases_clean(self):
        """SELECT a AS x, b AS y -> no finding."""
        linter = DuplicateAliasLinter()
        sql = "SELECT 1 AS x, 2 AS y FROM foo"
        node = {"original_file_path": "models/test.sql"}
        findings = linter.lint("model.pkg.test", sql, node)
        assert len(findings) == 0


# --- MissingContractColumnLinter ---


class TestMissingContractColumn:
    """Tests for the missing_contract_column linter."""

    def test_missing_column_triggers(self):
        """Contract declares col X but SQL doesn't produce it."""
        linter = MissingContractColumnLinter()
        sql = "SELECT 1 AS id, 'hello' AS name FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {
                "id": {"name": "id", "data_type": "INT"},
                "name": {"name": "name", "data_type": "VARCHAR"},
                "missing_col": {"name": "missing_col", "data_type": "VARCHAR"},
            },
            "contract": {"enforced": True},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 1
        assert "missing_col" in findings[0].message

    def test_all_columns_present_clean(self):
        """All contract columns present in SQL -> no finding."""
        linter = MissingContractColumnLinter()
        sql = "SELECT 1 AS id, 'hello' AS name FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {
                "id": {"name": "id", "data_type": "INT"},
                "name": {"name": "name", "data_type": "VARCHAR"},
            },
            "contract": {"enforced": True},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 0

    def test_star_does_not_crash(self):
        """SELECT * with contract -> skipped (can't validate)."""
        linter = MissingContractColumnLinter()
        sql = "SELECT * FROM foo"
        node = {
            "original_file_path": "models/dim_test.sql",
            "columns": {"x": {"name": "x", "data_type": "INT"}},
            "contract": {"enforced": True},
        }
        findings = linter.lint("model.pkg.dim_test", sql, node)
        assert len(findings) == 0


# --- CLI integration ---


class TestLintCLI:
    """Integration test: running lint via the CLI entry point."""

    def test_lint_with_manifest(self, tmp_path):
        """dbt-diagnostics lint against a temp manifest with lint issues."""
        # Create a minimal dbt project structure
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text("name: test_project\nprofile: test\n")
        target_dir = project_dir / "target"
        target_dir.mkdir()

        manifest = {
            "nodes": {
                "model.test_project.my_model": {
                    "unique_id": "model.test_project.my_model",
                    "resource_type": "model",
                    "original_file_path": "models/my_model.sql",
                    "path": "my_model.sql",
                    "compiled_code": "SELECT 1 AS x, 2 AS x FROM foo",
                    "depends_on": {"nodes": []},
                    "columns": {},
                    "contract": {"enforced": False},
                }
            },
            "sources": {},
        }
        (target_dir / "manifest.json").write_text(json.dumps(manifest))

        from dbt_diagnostics.main import main

        with patch("sys.argv", ["dbt-diagnostics", "--project-dir", str(project_dir), "lint"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Should exit 1 because duplicate alias is found
            assert exc_info.value.code == 1
