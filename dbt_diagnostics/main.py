"""
dbt_diagnostics/main.py

Entry point. Loads dbt artifacts, classifies errors, traces root causes,
renders output via Jinja2 templates. Optionally enriches with live
Snowflake queries (--live).

The CLI is fully self-contained: it auto-detects the dbt project by walking
up from the current directory and reads profile/target from dbt_project.yml
and profiles.yml. Every value can be overridden by flags. No config file
is required.

Usage:
    dbt-diagnostics                       # auto-detect everything
    dbt-diagnostics --live                # enrich with Snowflake queries
    dbt-diagnostics --live --env-file .env  # explicit .env path for env_var()
    dbt-diagnostics --json                # machine-readable output
    dbt-diagnostics --verbose             # full diagnostic detail
    dbt-diagnostics --project-dir ./my_dbt_project
    dbt-diagnostics --run-results path/to/run_results.json
    dbt-diagnostics demo                  # run against bundled fixtures
"""

import argparse
import json
import sys

from pathlib import Path
from typing import Optional

import yaml

from dbt_diagnostics.classifiers import classify, DiagnosticContext
from dbt_diagnostics.discover import (
    find_dbt_project,
    read_profile_name,
    find_profiles_yml,
    read_default_target,
    resolve_project_paths,
)
from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


def _load_config(config_path: Optional[Path]) -> Optional[dict]:
    """Load an optional YAML config file. Returns None if not provided or missing."""
    if config_path is None:
        return None
    if not config_path.exists():
        return None
    with open(config_path) as f:
        return yaml.safe_load(f)


def _resolve_from_args(args) -> dict:
    """
    Resolve all paths and settings from CLI args + auto-detection.

    Priority (highest to lowest):
      1. Explicit CLI flags (--project-dir, --run-results, --manifest, etc.)
      2. Optional config file (--config)
      3. Auto-detection (walk up from cwd for dbt_project.yml)
    """
    # Load optional config for fallback values
    config = _load_config(args.config)
    config_dir = args.config.parent if args.config and args.config.exists() else Path.cwd()

    # Step 1: Determine project directory
    project_dir = None
    if args.project_dir:
        project_dir = Path(args.project_dir).resolve()
    elif config and config.get("project", {}).get("dbt_project_dir"):
        project_dir = (config_dir / config["project"]["dbt_project_dir"]).resolve()
    else:
        project_dir = find_dbt_project()

    if project_dir is None:
        print(
            "ERROR: Could not find a dbt project.\n"
            "  Searched upward from the current directory for dbt_project.yml.\n"
            "  Use --project-dir to specify the dbt project directory explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    paths = resolve_project_paths(project_dir)

    # Step 2: Override run_results/manifest if specified explicitly
    if args.run_results:
        paths["run_results"] = Path(args.run_results).resolve()
    if args.manifest:
        paths["manifest"] = Path(args.manifest).resolve()

    # Step 3: Resolve profile/target for --live connections
    profile_name = None
    target_name = None

    if args.profile:
        profile_name = args.profile
    elif config and config.get("connection", {}).get("profile_name"):
        profile_name = config["connection"]["profile_name"]
    else:
        profile_name = read_profile_name(project_dir)

    if args.target:
        target_name = args.target
    elif config and config.get("connection", {}).get("target_name"):
        target_name = config["connection"]["target_name"]
    else:
        if profile_name:
            profiles_path = find_profiles_yml(project_dir)
            if profiles_path:
                target_name = read_default_target(profiles_path, profile_name)

    paths["profile_name"] = profile_name or "default"
    paths["target_name"] = target_name or "dev"

    return paths


def load_json(path: Path, label: str) -> dict:
    """Load a JSON artifact, exit with a clear message if missing."""
    if not path.exists():
        print(f"ERROR: {label} not found at {path}", file=sys.stderr)
        print("  Run `dbt build` first to generate artifacts.", file=sys.stderr)
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

    # Post-classification: detect cascading errors
    _annotate_cascading_errors(reports, dag_walker)

    return reports, skipped_ids, total


def _annotate_cascading_errors(reports: list[DiagnosticReport], dag_walker: DagWalker):
    """
    If model A fails and model B (depends on A) also fails, annotate B's report
    with a cascade_note pointing to A. This tells the user to fix A first.
    """
    error_ids = {r.unique_id for r in reports}

    for report in reports:
        parents = dag_walker.get_parents(report.unique_id)
        failed_parents = [p for p in parents if p in error_ids]
        if failed_parents:
            parent_names = ", ".join(failed_parents)
            report.cascade_note = (
                f"This failure is likely caused by the error in "
                f"upstream model(s): {parent_names}. Fix that first."
            )


def _load_env_file(env_file: Optional[str], project_dir: Optional[Path]):
    """
    Load environment variables from a .env file.
    Priority: explicit --env-file flag > auto-detection by python-dotenv.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        if env_file:
            print(
                "  WARNING: --env-file requires python-dotenv.\n"
                "  Install with: pip install \"dbt_diagnostics[live]\"\n",
                file=sys.stderr,
            )
        return

    if env_file:
        path = Path(env_file).resolve()
        if not path.exists():
            print(
                f"  WARNING: --env-file path does not exist: {path}\n",
                file=sys.stderr,
            )
            return
        load_dotenv(path, override=False)
    elif project_dir:
        # Auto-detect: check project parent (repo root) then project dir
        candidates = [
            project_dir.parent / ".env",
            project_dir / ".env",
            Path.cwd() / ".env",
        ]
        for candidate in candidates:
            if candidate.exists():
                load_dotenv(candidate, override=False)
                return


def _try_enrich(reports, paths: dict, run_results: dict, env_file: Optional[str]):
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

    # Load .env before parsing profiles (env_var() references need env vars set)
    _load_env_file(env_file, paths.get("project_dir"))

    profile_name = paths["profile_name"]
    target_name = paths["target_name"]
    project_dir = paths.get("project_dir")

    conn = open_connection(profile_name, target_name, project_dir)
    if conn is None:
        print(
            "  WARNING: Could not connect to Snowflake.\n"
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
    paths = _resolve_from_args(args)

    run_results = load_json(paths["run_results"], "run_results.json")
    manifest = load_json(paths["manifest"], "manifest.json")

    reports, skipped_ids, total = _diagnose_all(run_results, manifest, paths)

    # Live enrichment (optional)
    if args.live:
        _try_enrich(reports, paths, run_results, args.env_file)

    if args.json:
        output = {
            "schema_version": "1.0",
            "total_results": total,
            "errors": len(reports),
            "skipped": len(skipped_ids),
            "reports": [r.to_json_dict() for r in reports],
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        text = render_text(
            reports=reports,
            total=total,
            errors=len(reports),
            skipped=len(skipped_ids),
            skipped_models=skipped_ids,
            verbose=args.verbose,
        )
        print(text)

    # Exit 1 when errors were diagnosed (CI can gate on this)
    if reports and not getattr(args, "no_fail", False):
        sys.exit(1)


def cmd_demo(args):
    """Demo command: run against bundled fixtures to show capabilities."""
    fixtures_dir = Path(__file__).parent / "fixtures"

    fixture_files = [
        ("contract_type_mismatch.json", "manifest_minimal.json"),
        ("runtime_errors.json", "manifest_runtime.json"),
        ("compilation_errors.json", "manifest_compilation.json"),
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
            verbose=args.verbose,
        )
        print(text)


def main():
    parser = argparse.ArgumentParser(
        prog="dbt-diagnostics",
        description="Lineage-aware error tracer for dbt projects on Snowflake.",
    )

    # Output control (global)
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show full diagnostic detail (all params, full model names, etc.)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of human-readable text",
    )

    # Project discovery (diagnose mode)
    parser.add_argument(
        "--project-dir", metavar="PATH",
        help="dbt project directory (default: walk up from cwd for dbt_project.yml)",
    )
    parser.add_argument(
        "--profile", metavar="NAME",
        help="dbt profile name (default: read from dbt_project.yml)",
    )
    parser.add_argument(
        "--target", metavar="NAME",
        help="dbt target name (default: read from profiles.yml default target)",
    )

    # Artifact paths (override auto-detection)
    parser.add_argument(
        "--run-results", metavar="PATH",
        help="Explicit path to run_results.json (overrides --project-dir)",
    )
    parser.add_argument(
        "--manifest", metavar="PATH",
        help="Explicit path to manifest.json (overrides --project-dir)",
    )

    # Environment and config
    parser.add_argument(
        "--env-file", metavar="PATH",
        help="Path to .env file for env_var() resolution (default: auto-detect)",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Optional config.yml (never required; CLI flags take priority)",
    )

    # Live enrichment
    parser.add_argument(
        "--live", action="store_true",
        help="Enrich findings with live Snowflake queries",
    )

    # Exit code control
    parser.add_argument(
        "--no-fail", action="store_true",
        help="Exit 0 even when errors are found (for interactive use)",
    )

    # Subcommands (demo is explicit; diagnose is the default)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("demo", help="Run against bundled fixtures to show capabilities")
    subparsers.add_parser("diagnose", help="Diagnose errors from dbt build artifacts (default)")

    args = parser.parse_args()

    # Default to diagnose when no subcommand is given
    if args.command is None:
        args.command = "diagnose"

    if args.command == "demo":
        cmd_demo(args)
    else:
        cmd_diagnose(args)


if __name__ == "__main__":
    main()
