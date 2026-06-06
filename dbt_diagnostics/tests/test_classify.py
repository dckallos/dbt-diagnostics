"""
Tests for main.py classify_error and artifact loading logic.
"""

from dbt_diagnostics.main import classify_error, _annotate_cascading_errors
from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.tracers.dag_walker import DagWalker


class TestClassifyError:
    """Unit tests for the error classification dispatcher."""

    def test_contract_violation(self):
        msg = "This model has an enforced contract that failed."
        assert classify_error(msg) == "contract_violation"

    def test_runtime_error(self):
        msg = "Database Error in model foo\n  002003: Object does not exist"
        assert classify_error(msg) == "runtime_error"

    def test_compilation_error(self):
        """Compilation errors are now classified."""
        msg = "Compilation Error in model bar\n  'ref' is undefined"
        assert classify_error(msg) == "compilation_error"

    def test_unknown_error(self):
        msg = "Something totally unexpected happened"
        assert classify_error(msg) == "unknown"

    def test_contract_violation_from_fixture(self, contract_type_mismatch_results):
        msg = contract_type_mismatch_results["results"][0]["message"]
        assert classify_error(msg) == "contract_violation"


class TestCascadingErrors:
    """Tests for cascading error detection."""

    def _make_manifest(self):
        return {
            "nodes": {
                "model.pkg.stg_foo": {"depends_on": {"nodes": ["source.pkg.raw"]}},
                "model.pkg.dim_foo": {"depends_on": {"nodes": ["model.pkg.stg_foo"]}},
                "model.pkg.fct_bar": {"depends_on": {"nodes": ["model.pkg.dim_foo"]}},
                "model.pkg.independent": {"depends_on": {"nodes": []}},
            },
            "sources": {},
            "parent_map": {
                "model.pkg.stg_foo": ["source.pkg.raw"],
                "model.pkg.dim_foo": ["model.pkg.stg_foo"],
                "model.pkg.fct_bar": ["model.pkg.dim_foo"],
                "model.pkg.independent": [],
            },
        }

    def test_downstream_gets_cascade_note(self):
        """dim_foo depends on stg_foo; both error -> dim_foo gets cascade note."""
        dag_walker = DagWalker(self._make_manifest())
        reports = [
            DiagnosticReport(unique_id="model.pkg.stg_foo", error_class="runtime_error", raw_message="err"),
            DiagnosticReport(unique_id="model.pkg.dim_foo", error_class="runtime_error", raw_message="err"),
        ]
        _annotate_cascading_errors(reports, dag_walker)
        assert reports[0].cascade_note is None  # root cause
        assert reports[1].cascade_note is not None
        assert "stg_foo" in reports[1].cascade_note

    def test_independent_errors_no_cascade(self):
        """Two independent errors should not be linked."""
        dag_walker = DagWalker(self._make_manifest())
        reports = [
            DiagnosticReport(unique_id="model.pkg.stg_foo", error_class="runtime_error", raw_message="err"),
            DiagnosticReport(unique_id="model.pkg.independent", error_class="runtime_error", raw_message="err"),
        ]
        _annotate_cascading_errors(reports, dag_walker)
        assert reports[0].cascade_note is None
        assert reports[1].cascade_note is None

    def test_three_level_cascade(self):
        """stg_foo -> dim_foo -> fct_bar all error. fct_bar should note dim_foo."""
        dag_walker = DagWalker(self._make_manifest())
        reports = [
            DiagnosticReport(unique_id="model.pkg.stg_foo", error_class="runtime_error", raw_message="err"),
            DiagnosticReport(unique_id="model.pkg.dim_foo", error_class="runtime_error", raw_message="err"),
            DiagnosticReport(unique_id="model.pkg.fct_bar", error_class="runtime_error", raw_message="err"),
        ]
        _annotate_cascading_errors(reports, dag_walker)
        assert reports[0].cascade_note is None
        assert reports[1].cascade_note is not None  # depends on stg_foo
        assert reports[2].cascade_note is not None  # depends on dim_foo
        assert "dim_foo" in reports[2].cascade_note
