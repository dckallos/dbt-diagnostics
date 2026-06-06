"""
Tests for main.py classify_error and artifact loading logic.
"""

from dbt_diagnostics.main import classify_error


class TestClassifyError:
    """Unit tests for the error classification dispatcher."""

    def test_contract_violation(self):
        msg = "This model has an enforced contract that failed."
        assert classify_error(msg) == "contract_violation"

    def test_runtime_error(self):
        msg = "Database Error in model foo\n  002003: Object does not exist"
        assert classify_error(msg) == "runtime_error"

    def test_unregistered_compilation_error(self):
        """Compilation errors are not yet registered -- returns unknown."""
        msg = "Compilation Error in model bar\n  'ref' is undefined"
        assert classify_error(msg) == "unknown"

    def test_unknown_error(self):
        msg = "Something totally unexpected happened"
        assert classify_error(msg) == "unknown"

    def test_contract_violation_from_fixture(self, contract_type_mismatch_results):
        msg = contract_type_mismatch_results["results"][0]["message"]
        assert classify_error(msg) == "contract_violation"
