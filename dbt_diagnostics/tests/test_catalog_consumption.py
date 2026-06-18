"""
Tests for catalog.json consumption (#42): last-known column types from
`dbt docs generate` feed schema_change_error reasoning, strictly best-effort.

Real-artifact policy (per project convention -- no fabricated fixture files):
  - `unit`: the pure `compat.safe` catalog accessors are exercised with INLINE
    dict literals. These are parser inputs (the same convention used by
    test_safe_artifact_accessors.py / test_compat_schema_diff.py), not golden
    fixtures, and they make no claim about a specific real dbt artifact.
  - `contract`: the end-to-end "schema_change_error consumes REAL cataloged
    types" guarantee runs against a real catalog.json captured from
    dckallos/artwork-db (scenario 12). It is skipped until that fixture is
    committed. See docs/FIXTURE_CAPTURE.md for the exact capture procedure.
  - `robustness`: absent/empty catalog must degrade silently; verified against
    the real manifest+run_results with catalog None / empty (no invented data).
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers.schema_change_error import SchemaChangeErrorClassifier
from dbt_diagnostics.compat import safe
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
# Real artifacts for scenario 12 (real_schema_change_missing_column). The
# run_results + manifest are captured by inject_failures.sh today; the catalog
# is captured separately from a healthy `dbt docs generate` (see the doc).
REAL_RUN_RESULTS = FIXTURES_DIR / "real_schema_change_missing_column.json"
REAL_MANIFEST = FIXTURES_DIR / "real_schema_change_missing_column_manifest.json"
REAL_CATALOG = FIXTURES_DIR / "real_schema_change_missing_column_catalog.json"


def _load(path: Path):
    with open(path) as f:
        return json.load(f)


def _context(manifest, catalog):
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(
            Path("/nonexistent/models"), Path("/nonexistent/compiled")
        ),
        models_dir=Path("/nonexistent/models"),
        compiled_dir=Path("/nonexistent/compiled"),
        manifest=manifest,
        catalog=catalog,
    )


# --- INLINE parser inputs (not fixtures): mirror catalog.json node shape -------
def _inline_catalog():
    """A catalog-shaped dict literal for exercising the pure safe accessors."""
    return {
        "metadata": {"dbt_schema_version": "catalog/v1.json"},
        "nodes": {
            "model.p.m": {
                "metadata": {"type": "BASE TABLE"},
                "columns": {
                    "OBJECT_ID": {"type": "NUMBER(38,0)", "index": 1, "name": "OBJECT_ID"},
                    "TITLE": {"type": "TEXT", "index": 2, "name": "TITLE"},
                },
            },
        },
        "sources": {
            "source.p.raw.t": {"columns": {"C": {"type": "FLOAT", "name": "C"}}},
        },
    }


@pytest.mark.unit
class TestCatalogSafeAccessors:
    def test_column_type_case_insensitive(self):
        c = _inline_catalog()
        assert safe.catalog_column_type(c, "model.p.m", "OBJECT_ID") == "NUMBER(38,0)"
        assert safe.catalog_column_type(c, "model.p.m", "object_id") == "NUMBER(38,0)"

    def test_sources_are_searched(self):
        c = _inline_catalog()
        assert safe.catalog_node(c, "source.p.raw.t") is not None
        assert safe.catalog_column_type(c, "source.p.raw.t", "c") == "FLOAT"

    def test_missing_node_or_column_returns_none(self):
        c = _inline_catalog()
        assert safe.catalog_node(c, "model.nope") is None
        assert safe.catalog_column_type(c, "model.p.m", "GHOST") is None

    def test_garbled_inputs_never_raise(self):
        for junk in (None, 42, "str", [], {}, {"nodes": "x"}, {"nodes": {"m": 1}}):
            assert safe.catalog_node(junk, "m") is None
            assert safe.catalog_column_type(junk, "m", "C") is None


@pytest.mark.robustness
class TestCatalogAbsentDegradesSilently:
    """Absent/empty catalog -> unchanged behavior, no crash, no false positive."""

    @pytest.mark.skipif(
        not (REAL_MANIFEST.exists() and REAL_RUN_RESULTS.exists()),
        reason="real schema-change fixtures not present",
    )
    def test_no_catalog_runs_without_crash(self):
        manifest = _load(REAL_MANIFEST)
        result = _load(REAL_RUN_RESULTS)["results"][0]
        report = SchemaChangeErrorClassifier(
            result=result, context=_context(manifest, None)
        ).diagnose()
        assert report.findings  # a finding is still produced
        assert "dbt docs generate" not in report.findings[0].explanation

    @pytest.mark.skipif(
        not (REAL_MANIFEST.exists() and REAL_RUN_RESULTS.exists()),
        reason="real schema-change fixtures not present",
    )
    def test_empty_catalog_no_type_hint(self):
        manifest = _load(REAL_MANIFEST)
        result = _load(REAL_RUN_RESULTS)["results"][0]
        # Empty catalog (no invented column data) must inject nothing.
        report = SchemaChangeErrorClassifier(
            result=result, context=_context(manifest, {"nodes": {}, "sources": {}})
        ).diagnose()
        assert report.findings
        assert "dbt docs generate" not in report.findings[0].explanation


@pytest.mark.contract
class TestSchemaChangeUsesRealCatalog:
    """Exercises the consumption path against a REAL captured catalog.json."""

    @pytest.mark.skipif(
        not REAL_CATALOG.exists(),
        reason="capture the real catalog first (see docs/FIXTURE_CAPTURE.md)",
    )
    def test_accessor_reads_real_catalog_faithfully(self):
        catalog = _load(REAL_CATALOG)
        # Prove our accessor returns exactly what the real dbt catalog records,
        # for whatever typed column the real artifact actually contains.
        found = False
        for collection in ("nodes", "sources"):
            for uid, node in (catalog.get(collection) or {}).items():
                for cname, col in (node.get("columns") or {}).items():
                    if isinstance(col, dict) and isinstance(col.get("type"), str):
                        assert safe.catalog_column_type(catalog, uid, cname) == col["type"]
                        found = True
                        break
                if found:
                    break
            if found:
                break
        assert found, "real catalog.json has no typed columns to verify"

    @pytest.mark.skipif(
        not (REAL_CATALOG.exists() and REAL_MANIFEST.exists() and REAL_RUN_RESULTS.exists()),
        reason="capture the real catalog first (see docs/FIXTURE_CAPTURE.md)",
    )
    def test_classifier_consumes_real_catalog(self):
        catalog = _load(REAL_CATALOG)
        manifest = _load(REAL_MANIFEST)
        result = _load(REAL_RUN_RESULTS)["results"][0]
        report = SchemaChangeErrorClassifier(
            result=result, context=_context(manifest, catalog)
        ).diagnose()
        assert report.findings  # consumes the real catalog without crashing
        finding = report.findings[0]
        # When the drift path fired AND the real catalog records the drifted
        # column's type, that exact type must be surfaced (deterministic, no
        # fabricated data -- recomputed from the same real artifact).
        origin = getattr(finding, "upstream_origin", None)
        if origin is not None and getattr(origin, "model_id", None):
            real_type = safe.catalog_column_type(
                catalog, origin.model_id, finding.target_identifier
            )
            if real_type:
                assert real_type in finding.explanation
