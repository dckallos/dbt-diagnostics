"""
dbt_diagnostics/main.py

Entry point. Loads dbt artifacts, classifies errors, traces root causes,
renders output via Jinja2 templates. Optionally enriches with live
Snowflake queries (--live).

Usage:
    python -m dbt_diagnostics
    python -m dbt_diagnostics --live
    python -m dbt_diagnostics --json
    python -m dbt_diagnostics --config path/to/config.yml
    python -m dbt_diagnostics demo
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from dbt_diagnostics.classifiers import classify, DiagnosticContext
from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


def load_config(config_path: Path) -> dict:
    """Load the YAML config file."""
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def resolve_project_paths(config: dict, config_dir: Path) -> dict:
    """Derive all standard dbt paths from the project directory."""
    project_dir = (config_dir / config["project"]["dbt_project_dir"]).resolve()
    return {
        "project_dir": project_dir,
        "target_dir": project_dir / "target",
        "run_results": project_dir / "target" / "run_results.json",
        "manifest": project_dir / "target" / "manifest.json",
        "compiled_dir": project_dir / "target" / "compiled",
        "models_dir": project_dir / "models",
    }


def load_json(path: Path, label: str) -> dict:
    """Load a JSON artifact, exit with a clear message if missing."""
    if not path.exists():
        print(f"ERROR: {label} not found at {path}", file=sys.stderr)
        print(f"  Run `dbt build` first to generate artifacts.", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def classify_error(message: str) -> str:
    """Classify a dbt error message into a category string."""
    cls = classify(message)
    return cls.error_class if cls else "unknown"


def _diagnose_all(run_results: dict, manifest: dict, paths: dict) -> tuple:
    """Core logic: classify and diagnose all errors. Returns (reports, skipped_ids, total)."""
    dag_walker = DagWalker(manifest)
    column_tracer = ColumnTracer(paths["models_dir"], paths["compiled_dir"])
    context = DiagnosticContext(
        dag_walker=dag_walker,
        column_tracer=column_tracer,
        models_dir=paths["models_dir"],
        compiled_dir=paths["compiled_dir"],
    )

    errors = []
    skipped = []
    for result in run_results["results"]:
        if result["status"] == "error":
            errors.append(result)
        elif result["status"] == "skipped":
            skipped.append(result)

    reports = []
    for result in errors:
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

    skipped_ids = [s.get("unique_id", "unknown") for s in skipped]
    total = len(run_results["results"])
    return reports, skipped_ids, total


def _try_enrich(reports, config, run_results):
    """Attempt live enrichment. Warn and return gracefully on failure."""
    try:
        from dbt_diagnostics.enrichers import open_connection, enrich_reports
    except ImportError:
        print(
            "  WARNING: snowflake-connector-python not installed.\n"
            "  Install with: pip install \"dbt_diagnostics[live]\"\n"
            "  Falling back to offline mode.\n",
            file=sys.stderr,
        )
        return

    conn_config = config.get("connection", {})
    profile_name = conn_config.get("profile_name", "default")
    target_name = conn_config.get("target_name", "dev")

    conn = open_connection(profile_name, target_name)
    if conn is None:
        print(
            "  WARNING: Could not connect to Snowflake.\n"
            "  Check profiles.yml and credentials.\n"
            "  Falling back to offline mode.\n",
            file=sys.stderr,
        )
        return

    try:
        enrich_reports(conn, reports, run_results)
    finally:
        conn.close()


def cmd_diagnose(args):
    """Default command: diagnose errors from dbt artifacts."""
    config = load_config(args.config)
    config_dir = args.config.parent
    paths = resolve_project_paths(config, config_dir)

    run_results = load_json(paths["run_results"], "run_results.json")
    manifest = load_json(paths["manifest"], "manifest.json")

    reports, skipped_ids, total = _diagnose_all(run_results, manifest, paths)

    # Live enrichment (optional)
    if args.live:
        _try_enrich(reports, config, run_results)

    if args.json:
        output = {
            "total_results": total,
            "errors": len(reports),
            "skipped": len(skipped_ids),
            "reports": [asdict(r) for r in reports],
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        text = render_text(
            reports=reports,
            total=total,
            errors=len(reports),
            skipped=len(skipped_ids),
            skipped_models=skipped_ids,
        )
        print(text)


def cmd_demo(args):
    """Demo command: run against bundled fixtures to show capabilities."""
    fixtures_dir = Path(__file__).parent / "fixtures"

    fixture_files = [
        ("contract_type_mismatch.json", "manifest_minimal.json"),
        ("runtime_errors.json", "manifest_runtime.json"),
    ]

    for rr_file, manifest_file in fixture_files:
        rr_path = fixtures_dir / rr_file
        manifest_path = fixtures_dir / manifest_file
        if not rr_path.exists() or not manifest_path.exists():
            continue

        run_results = json.loads(rr_path.read_text())
        manifest = json.loads(manifest_path.read_text())

        paths = {
            "models_dir": Path("/project/models"),
            "compiled_dir": Path("/project/target/compiled"),
        }

        reports, skipped_ids, total = _diagnose_all(run_results, manifest, paths)

        text = render_text(
            reports=reports,
            total=total,
            errors=len(reports),
            skipped=len(skipped_ids),
            skipped_models=skipped_ids,
        )
        print(text)


def main():
    parser = argparse.ArgumentParser(
        prog="dbt_diagnostics",
        description="Lineage-aware error tracer for dbt projects.",
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).parent / "config.yml",
        help="Path to config.yml",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Enrich findings with live Snowflake queries (requires snowflake-connector-python)",
    )
    parser.add_argument(
        "command", nargs="?", default="diagnose",
        choices=["diagnose", "demo"],
        help="Subcommand (default: diagnose)",
    )
    args = parser.parse_args()

    if args.command == "demo":
        cmd_demo(args)
    else:
        cmd_diagnose(args)


if __name__ == "__main__":
    main()
