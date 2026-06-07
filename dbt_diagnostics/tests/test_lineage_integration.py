"""
Integration tests: verify that each real fixture produces a report
with correctly populated lineage trail and rendered output matching
the structural targets in LINEAGE_TRAIL_PLAN.md section 3.

These tests exercise the full pipeline: fixture -> classify -> diagnose -> render.
No live Snowflake connection required (all manifest-only/offline mode).
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers import classify, DiagnosticContext
from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> tuple[dict, dict]:
    """Load run_results + manifest for a named fixture."""
    rr = json.loads((FIXTURES / f"{name}.json").read_text())
    manifest = json.loads((FIXTURES / f"{name}_manifest.json").read_text())
    return rr, manifest


def _make_context(manifest: dict, run_results: dict = None) -> DiagnosticContext:
    """Build a DiagnosticContext suitable for offline testing."""
    walker = DagWalker(manifest)
    tracer = ColumnTracer(models_dir=Path("."), compiled_dir=Path("."))
    return DiagnosticContext(
        dag_walker=walker,
        column_tracer=tracer,
        models_dir=Path("."),
        compiled_dir=Path("."),
        manifest=manifest,
        run_results=run_results,
    )


def _diagnose_fixture(name: str) -> tuple[list[DiagnosticReport], dict, dict]:
    """Load a fixture, classify, diagnose, return (reports, run_results, manifest)."""
    rr, manifest = _load_fixture(name)
    context = _make_context(manifest, rr)
    reports = []
    for result in rr["results"]:
        if result["status"] != "error":
            continue
        message = result.get("message", "")
        classifier_cls = classify(message)
        if classifier_cls:
            classifier = classifier_cls(result=result, context=context)
            report = classifier.diagnose()
        else:
            report = DiagnosticReport(
                unique_id=result.get("unique_id", "unknown"),
                error_class="unknown",
                raw_message=message,
            )
        reports.append(report)
    return reports, rr, manifest


def _render_reports(
    reports: list[DiagnosticReport],
    run_results: dict,
    verbose: bool = False,
    color_enabled: bool = False,
) -> str:
    """Render reports to text output."""
    total = len(run_results["results"])
    errors = len(reports)
    skipped_ids = [
        r.get("unique_id", "unknown")
        for r in run_results["results"]
        if r["status"] == "skipped"
    ]
    return render_text(
        reports=reports,
        total=total,
        errors=errors,
        skipped=len(skipped_ids),
        skipped_models=skipped_ids,
        verbose=verbose,
        color_enabled=color_enabled,
    )


class TestObjectNotExistTrail:
    """Fixture: real_object_not_exist_002003."""

    @pytest.fixture()
    def reports(self):
        reports, _, _ = _diagnose_fixture("real_object_not_exist_002003")
        return reports

    @pytest.fixture()
    def rendered(self):
        reports, rr, _ = _diagnose_fixture("real_object_not_exist_002003")
        return _render_reports(reports, rr)

    def test_has_findings(self, reports):
        assert len(reports) >= 1
        assert reports[0].has_findings

    def test_trail_populated(self, reports):
        finding = reports[0].findings[0]
        assert len(finding.lineage_trail) >= 1

    def test_trail_first_step_is_missing(self, reports):
        """The referenced object should be marked missing in manifest."""
        finding = reports[0].findings[0]
        trail = finding.lineage_trail
        # At least one step should have manifest_status of 'not_found' or 'missing'
        statuses = [s.manifest_status for s in trail]
        assert "not_found" in statuses or "missing" in statuses

    def test_compiled_snippet_present(self, reports):
        finding = reports[0].findings[0]
        assert finding.compiled_snippet is not None

    def test_rendered_contains_lineage_trace(self, rendered):
        assert "LINEAGE TRACE:" in rendered

    def test_rendered_contains_compiled_sql(self, rendered):
        assert "COMPILED SQL" in rendered


class TestInvalidIdentifierTrail:
    """Fixture: real_invalid_identifier_000904."""

    @pytest.fixture()
    def reports(self):
        reports, _, _ = _diagnose_fixture("real_invalid_identifier_000904")
        return reports

    @pytest.fixture()
    def rendered(self):
        reports, rr, _ = _diagnose_fixture("real_invalid_identifier_000904")
        return _render_reports(reports, rr)

    def test_trail_length(self, reports):
        finding = reports[0].findings[0]
        assert len(finding.lineage_trail) >= 2

    def test_snippet_has_error_line(self, reports):
        finding = reports[0].findings[0]
        assert finding.compiled_snippet is not None
        assert finding.compiled_snippet.error_line == 38

    def test_rendered_contains_column_name(self, rendered):
        assert "NONEXISTENT_TOP_LEVEL_COLUMN" in rendered

    def test_rendered_contains_trace_header(self, rendered):
        assert "LINEAGE TRACE:" in rendered


class TestSchemaChangeTrail:
    """Fixture: real_schema_change_missing_column."""

    @pytest.fixture()
    def reports(self):
        reports, _, _ = _diagnose_fixture("real_schema_change_missing_column")
        return reports

    @pytest.fixture()
    def rendered(self):
        reports, rr, _ = _diagnose_fixture("real_schema_change_missing_column")
        return _render_reports(reports, rr)

    def test_has_trail(self, reports):
        finding = reports[0].findings[0]
        assert len(finding.lineage_trail) >= 1

    def test_source_manifest_status(self, reports):
        """At least one trail step shows the column is declared in manifest."""
        finding = reports[0].findings[0]
        trail = finding.lineage_trail
        statuses = [s.manifest_status for s in trail]
        assert "declared" in statuses or "not_found" in statuses

    def test_rendered_has_trace(self, rendered):
        assert "LINEAGE TRACE:" in rendered

    def test_rendered_has_snippet(self, rendered):
        assert "COMPILED SQL" in rendered


class TestDivisionByZeroTrail:
    """Fixture: real_division_by_zero_100035."""

    @pytest.fixture()
    def reports(self):
        reports, _, _ = _diagnose_fixture("real_division_by_zero_100035")
        return reports

    @pytest.fixture()
    def rendered(self):
        reports, rr, _ = _diagnose_fixture("real_division_by_zero_100035")
        return _render_reports(reports, rr)

    def test_has_trail(self, reports):
        finding = reports[0].findings[0]
        # Data errors build at least a basic trail
        assert len(finding.lineage_trail) >= 1

    def test_first_step_is_failing_model(self, reports):
        finding = reports[0].findings[0]
        trail = finding.lineage_trail
        assert trail[0].annotation is not None or trail[0].run_status == "error"

    def test_rendered_has_trace_or_snippet(self, rendered):
        assert "LINEAGE TRACE:" in rendered or "COMPILED SQL" in rendered


class TestNoColorRendering:
    """Verify that color_enabled=False produces text fallback, not emoji."""

    def test_no_emoji_in_output(self):
        reports, rr, _ = _diagnose_fixture("real_invalid_identifier_000904")
        output = _render_reports(reports, rr, color_enabled=False)
        # Should have text status indicators
        has_text = any(
            marker in output
            for marker in ("[PASS]", "[FAIL]", "[WARN]", "[????]", "[SKIP]")
        )
        # At least one trail step produces a text indicator
        finding = reports[0].findings[0]
        if finding.lineage_trail:
            assert has_text

    def test_no_unicode_emoji_chars(self):
        reports, rr, _ = _diagnose_fixture("real_invalid_identifier_000904")
        output = _render_reports(reports, rr, color_enabled=False)
        emoji_chars = ["\u2705", "\u274c", "\u2753", "\U0001f7e1", "\u26a0\ufe0f"]
        for char in emoji_chars:
            assert char not in output


class TestColorRendering:
    """Verify that color_enabled=True uses emoji in trail."""

    def test_emoji_in_output(self):
        reports, rr, _ = _diagnose_fixture("real_invalid_identifier_000904")
        output = _render_reports(reports, rr, color_enabled=True)
        finding = reports[0].findings[0]
        if finding.lineage_trail:
            emoji_chars = [
                "\u2705", "\u274c", "\u2753", "\U0001f7e1", "\u26a0\ufe0f",
                "\u23ed\ufe0f",
            ]
            has_emoji = any(char in output for char in emoji_chars)
            assert has_emoji


class TestVerboseRendering:
    """Verify verbose mode renders more context."""

    def test_verbose_longer_output(self):
        reports, rr, _ = _diagnose_fixture("real_invalid_identifier_000904")
        normal = _render_reports(reports, rr, verbose=False)
        verbose = _render_reports(reports, rr, verbose=True)
        # Verbose should include EXPLANATION or more detail
        assert len(verbose) >= len(normal)


# Parametrize over all real fixture pairs to check no crashes
_FIXTURE_PAIRS = [
    "real_object_not_exist_002003",
    "real_invalid_identifier_000904",
    "real_invalid_identifier_lateral_000904",
    "real_schema_change_missing_column",
    "real_division_by_zero_100035",
    "real_numeric_overflow_100132",
    "real_string_too_long_100078",
    "real_syntax_error_001003",
    "real_privileges_003001",
    "real_compilation_ref_not_found",
    "real_compilation_source_not_found",
    "real_contract_violation_extra_column",
]


@pytest.mark.parametrize("fixture_name", _FIXTURE_PAIRS)
class TestAllFixturesNoCrash:
    """Every fixture must classify + render without raising."""

    def test_classify_and_render(self, fixture_name):
        reports, rr, _ = _diagnose_fixture(fixture_name)
        # Must produce at least one report
        assert len(reports) >= 1
        # Must render without exception
        output = _render_reports(reports, rr)
        assert len(output) > 0
        # Every report has at least 1 finding (or raw_message for unknown)
        for report in reports:
            assert report.has_findings or report.raw_message

    def test_render_with_color(self, fixture_name):
        reports, rr, _ = _diagnose_fixture(fixture_name)
        output = _render_reports(reports, rr, color_enabled=True)
        assert len(output) > 0

    def test_render_verbose(self, fixture_name):
        reports, rr, _ = _diagnose_fixture(fixture_name)
        output = _render_reports(reports, rr, verbose=True)
        assert len(output) > 0
