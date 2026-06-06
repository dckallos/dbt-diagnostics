#!/usr/bin/env python3
"""
dbt_diagnostics/demo.py

Runs the diagnostic tool against all fixture files to show output for
each supported error type. Version-controlled; no temporary files.

Usage:
    python -m dbt_diagnostics.demo
    python dbt_diagnostics/demo.py
"""

import json
import sys
from pathlib import Path

# Ensure the package is importable from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dbt_diagnostics.classifiers import classify, DiagnosticContext
from dbt_diagnostics.classifiers.contract_violation import ContractViolationClassifier
from dbt_diagnostics.classifiers.runtime_error import RuntimeErrorClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer
from dbt_diagnostics.main import render_report_human

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Manifests for each fixture (minimal, just enough for the DAG walker)
# ---------------------------------------------------------------------------

MANIFEST_CONTRACT = json.loads((FIXTURES_DIR / "manifest_minimal.json").read_text())

MANIFEST_RUNTIME = {
    "nodes": {
        "model.artwork_pipeline.stg_met__artworks": {
            "unique_id": "model.artwork_pipeline.stg_met__artworks",
            "resource_type": "model",
            "original_file_path": "models/staging/met/stg_met__artworks.sql",
            "relation_name": "ARTWORK_DB.SILVER.STG_MET__ARTWORKS",
            "compiled_code": "",
            "depends_on": {
                "nodes": ["source.artwork_pipeline.met.raw_met_objects"],
                "macros": [],
            },
            "columns": {},
        },
        "model.artwork_pipeline.dim_artworks": {
            "unique_id": "model.artwork_pipeline.dim_artworks",
            "resource_type": "model",
            "original_file_path": "models/marts/dim_artworks.sql",
            "relation_name": "ARTWORK_DB.GOLD.DIM_ARTWORKS",
            "compiled_code": "",
            "depends_on": {
                "nodes": ["model.artwork_pipeline.stg_met__artworks"],
                "macros": [],
            },
            "columns": {
                "artwork_id": {"name": "artwork_id"},
                "title": {"name": "title"},
            },
        },
        "model.artwork_pipeline.stg_met__departments": {
            "unique_id": "model.artwork_pipeline.stg_met__departments",
            "resource_type": "model",
            "original_file_path": "models/staging/met/stg_met__departments.sql",
            "relation_name": "ARTWORK_DB.SILVER.STG_MET__DEPARTMENTS",
            "compiled_code": "",
            "depends_on": {
                "nodes": ["source.artwork_pipeline.met.raw_met_departments"],
                "macros": [],
            },
            "columns": {},
        },
    },
    "sources": {
        "source.artwork_pipeline.met.raw_met_objects": {
            "unique_id": "source.artwork_pipeline.met.raw_met_objects",
            "resource_type": "source",
            "relation_name": "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS",
            "columns": {},
        },
    },
    "parent_map": {
        "model.artwork_pipeline.stg_met__artworks": [
            "source.artwork_pipeline.met.raw_met_objects"
        ],
        "model.artwork_pipeline.dim_artworks": [
            "model.artwork_pipeline.stg_met__artworks"
        ],
        "model.artwork_pipeline.stg_met__departments": [
            "source.artwork_pipeline.met.raw_met_departments"
        ],
    },
}


def make_context(manifest: dict) -> DiagnosticContext:
    """Build a DiagnosticContext from a manifest dict."""
    return DiagnosticContext(
        dag_walker=DagWalker(manifest),
        column_tracer=ColumnTracer(Path("/fake/models"), Path("/fake/compiled")),
        models_dir=Path("/fake/models"),
        compiled_dir=Path("/fake/compiled"),
    )


def demo_contract_type_mismatch():
    """Contract violation: model produces wrong type vs YAML contract."""
    rr = json.loads((FIXTURES_DIR / "contract_type_mismatch.json").read_text())
    ctx = make_context(MANIFEST_CONTRACT)

    print("\n")
    print("=" * 70)
    print("  SCENARIO: Contract Type Mismatch")
    print("  Induced by: CURRENT_TIMESTAMP() in dim_artists.sql (line 27)")
    print("  Contract expects: TIMESTAMP_NTZ(9)")
    print("  Model produces:   TIMESTAMP_LTZ (Snowflake default)")
    print("=" * 70)

    result = rr["results"][0]
    classifier = ContractViolationClassifier(result=result, context=ctx)
    report = classifier.diagnose()
    render_report_human(report)


def demo_object_not_found():
    """Runtime error: source table doesn't exist in Snowflake."""
    rr = json.loads((FIXTURES_DIR / "runtime_errors.json").read_text())
    ctx = make_context(MANIFEST_RUNTIME)

    print("\n")
    print("=" * 70)
    print("  SCENARIO: Object Does Not Exist (Snowflake 002003)")
    print("  Induced by: Running dbt before source DDL is applied")
    print("  Missing:    ARTWORK_DB.BRONZE.RAW_MET_OBJECTS")
    print("=" * 70)

    result = rr["results"][0]
    classifier = RuntimeErrorClassifier(result=result, context=ctx)
    report = classifier.diagnose()
    render_report_human(report)


def demo_invalid_identifier():
    """Runtime error: column name doesn't exist in source table."""
    rr = json.loads((FIXTURES_DIR / "runtime_errors.json").read_text())
    ctx = make_context(MANIFEST_RUNTIME)

    print("\n")
    print("=" * 70)
    print("  SCENARIO: Invalid Identifier (Snowflake 000904)")
    print("  Induced by: Referencing 'ARTWORK_TITLE' (correct: 'title')")
    print("  File:       models/marts/dim_artworks.sql, line 3")
    print("=" * 70)

    result = rr["results"][1]
    classifier = RuntimeErrorClassifier(result=result, context=ctx)
    report = classifier.diagnose()
    render_report_human(report)


def demo_insufficient_privileges():
    """Runtime error: role lacks GRANTs on the table."""
    rr = json.loads((FIXTURES_DIR / "runtime_errors.json").read_text())
    ctx = make_context(MANIFEST_RUNTIME)

    print("\n")
    print("=" * 70)
    print("  SCENARIO: Insufficient Privileges (Snowflake 003001)")
    print("  Induced by: Running as ARTWORK_TRANSFORMER without SELECT grant")
    print("  Object:     ARTWORK_DB.BRONZE.RAW_MET_DEPARTMENTS")
    print("=" * 70)

    result = rr["results"][2]
    classifier = RuntimeErrorClassifier(result=result, context=ctx)
    report = classifier.diagnose()
    render_report_human(report)


def main():
    print("\n" + "+" * 70)
    print("+  dbt_diagnostics -- Supported Error Scenarios (demo)")
    print("+  Errors diagnosed: 4 types across 2 classifiers")
    print("+" * 70)

    demo_contract_type_mismatch()
    demo_object_not_found()
    demo_invalid_identifier()
    demo_insufficient_privileges()

    print("\n" + "-" * 70)
    print("  End of demo. Run `python -m pytest dbt_diagnostics/tests/ -v`")
    print("  for the full test suite (43 tests).")
    print("-" * 70 + "\n")


if __name__ == "__main__":
    main()
