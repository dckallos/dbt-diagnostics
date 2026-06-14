"""
dbt_diagnostics/main.py

Entry point. Loads dbt artifacts, classifies errors, traces root causes,
renders output via Jinja2 templates. Enriches with live Snowflake queries
by default (suppress with --no-live).

The CLI is fully self-contained: it auto-detects the dbt project by walking
up from the current directory and reads profile/target from dbt_project.yml
and profiles.yml. Every value can be overridden by flags. No config file
is required.

Usage:
    dbt-diagnostics                       # auto-detect, live enrichment ON
    dbt-diagnostics --no-live             # skip live Snowflake queries
    dbt-diagnostics --env-file .env       # explicit .env path for env_var()
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

from dbt_diagnostics.classifiers import classify, DiagnosticContext, TestFailureClassifier
from dbt_diagnostics.colors import should_use_color
from dbt_diagnostics.discover import (
    find_dbt_project,
    read_profile_name,
    find_profiles_yml,
    read_default_target,
    resolve_project_paths,
)
from dbt_diagnostics.models import DiagnosticReport
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.root_cause import build_root_cause_groups
from dbt_diagnostics.tracers.diff_tracer import diff_node
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


# Known dbt packages that produce project-hygiene warnings (not data quality)
_HYGIENE_PACKAGES = frozenset([
    "dbt_project_evaluator",
    "dbt_meta_testing",
    "dbt_checkpoint",
])


def _classify_warn_category(unique_id: str) -> str:
    """Classify a warning as 'project_hygiene' or 'data_quality'."""
    parts = unique_id.split(".")
    if len(parts) >= 2 and parts[1] in _HYGIENE_PACKAGES:
        return "project_hygiene"
    return "data_quality"


def _extract_warn_name(unique_id: str) -> str:
    """Extract a readable test name from a warn result's unique_id."""
    parts = unique_id.split(".")
    if len(parts) >= 3:
        # Strip trailing hash and leading 'is_empty_' prefix
        name = parts[2]
        if name.startswith("is_empty_"):
            name = name[len("is_empty_"):]
        # Remove trailing underscore
        if name.endswith("_"):
            name = name[:-1]
        return name
    return unique_id


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
    """
    Core logic: classify and diagnose all errors and failures.

    Returns (reports, skipped_ids, total, error_count, fail_count, warn_details).
    warn_details is a list of dicts: [{name, category, failures, message, unique_id}].
    """
    dag_walker = DagWalker(manifest)
    column_tracer = ColumnTracer(paths["models_dir"], paths["compiled_dir"])
    context = DiagnosticContext(
        dag_walker=dag_walker,
        column_tracer=column_tracer,
        models_dir=paths["models_dir"],
        compiled_dir=paths["compiled_dir"],
        manifest=manifest,
        run_results=run_results,
    )

    errors = []
    failures = []
    skipped = []
    warns = []
    for result in run_results["results"]:
        status = result["status"]
        if status == "error":
            errors.append(result)
        elif status == "fail":
            failures.append(result)
        elif status == "skipped":
            skipped.append(result)
        elif status == "warn":
            warns.append(result)

    reports = []

    # Process errors (SQL compilation/runtime failures)
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

    # Process test failures (assertion violations)
    for result in failures:
        classifier = TestFailureClassifier(result=result, context=context)
        report = classifier.diagnose()
        reports.append(report)

    skipped_ids = [s.get("unique_id", "unknown") for s in skipped]
    total = len(run_results["results"])

    # Build structured warn details
    warn_details = []
    for result in warns:
        uid = result.get("unique_id", "unknown")
        warn_details.append({
            "unique_id": uid,
            "name": _extract_warn_name(uid),
            "category": _classify_warn_category(uid),
            "failures": result.get("failures", 0),
            "message": result.get("message", ""),
        })

    # Post-classification: detect cascading errors
    _annotate_cascading_errors(reports, dag_walker)

    return reports, skipped_ids, total, len(errors), len(failures), warn_details


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


def _declared_role(paths: dict) -> Optional[str]:
    """Resolve the role declared in the dbt profile/target, if any."""
    try:
        from dbt_diagnostics.enrichers.connection import parse_profile
        kwargs = parse_profile(
            paths["profile_name"], paths["target_name"], paths.get("project_dir")
        )
        if kwargs:
            return kwargs.get("role")
    except Exception:
        pass
    return None


def _representative_query_id(reports) -> Optional[str]:
    """Any failing query_id from the reports, used to recover the run's role."""
    for report in reports:
        if getattr(report, "query_id", None):
            return report.query_id
    return None


def _try_enrich(reports, paths: dict, run_results: dict, env_file: Optional[str]):
    """
    Attempt live enrichment and build root-cause groups while the connection is
    open. Returns the list of RootCauseGroup (possibly empty) on success, or
    None when no live connection was available (caller then builds offline,
    "unverified" groups).
    """
    try:
        from dbt_diagnostics.enrichers import open_connection, enrich_reports
    except ImportError:
        print(
            "  WARNING: snowflake-connector-python not installed.\n"
            "  Install with: pip install \"dbt_diagnostics[live]\"\n"
            "  Falling back to offline mode.\n",
            file=sys.stderr,
        )
        return None

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
        return None

    try:
        enrich_reports(conn, reports, run_results)
        from dbt_diagnostics.root_cause import LiveObjectProbe
        probe = LiveObjectProbe(
            conn,
            declared_role=_declared_role(paths),
            run_results=run_results,
            representative_query_id=_representative_query_id(reports),
        )
        return build_root_cause_groups(reports, probe=probe)
    finally:
        conn.close()


def cmd_diagnose(args):
    """Default command: diagnose errors from dbt artifacts."""
    paths = _resolve_from_args(args)

    run_results = load_json(paths["run_results"], "run_results.json")
    manifest = load_json(paths["manifest"], "manifest.json")

    reports, skipped_ids, total, error_count, fail_count, warn_details = _diagnose_all(
        run_results, manifest, paths
    )
    warn_count = len(warn_details)

    # Diff-aware diagnosis (optional)
    prev_manifest_path = getattr(args, "previous_manifest", None)
    if prev_manifest_path:
        prev_manifest = load_json(Path(prev_manifest_path), "previous manifest")
        for report in reports:
            report.diff = diff_node(report.unique_id, manifest, prev_manifest)

    # Live enrichment (default ON; --no-live suppresses). The live path also
    # builds the disambiguated root-cause groups while the connection is open.
    root_cause_groups = None
    if not args.no_live:
        root_cause_groups = _try_enrich(reports, paths, run_results, args.env_file)
    if root_cause_groups is None:
        # Offline (or no connector / connect failure): group anyway and degrade
        # each verdict to "unverified" with the query to run.
        root_cause_groups = build_root_cause_groups(reports, probe=None)

    color_enabled = should_use_color(
        force_color=getattr(args, "color", False),
        no_color=getattr(args, "no_color", False),
        is_json=args.json,
    )

    if args.json:
        output = {
            "schema_version": "1.1",
            "total_results": total,
            "errors": error_count,
            "fails": fail_count,
            "warns": warn_count,
            "skipped": len(skipped_ids),
            "reports": [r.to_json_dict() for r in reports],
            "root_cause_groups": [g.to_json_dict() for g in root_cause_groups],
            "warn_details": warn_details,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        text = render_text(
            reports=reports,
            total=total,
            errors=error_count,
            fails=fail_count,
            warns=warn_count,
            skipped=len(skipped_ids),
            skipped_models=skipped_ids,
            verbose=args.verbose,
            color_enabled=color_enabled,
            warn_details=warn_details,
            root_cause_groups=root_cause_groups,
        )
        print(text)

    # Exit 1 when errors or failures were diagnosed (CI can gate on this)
    if reports and not getattr(args, "no_fail", False):
        sys.exit(1)


def cmd_demo(args):
    """Demo command: run against bundled fixtures to show capabilities."""
    fixtures_dir = Path(__file__).parent / "fixtures"

    color_enabled = should_use_color(
        force_color=getattr(args, "color", False),
        no_color=getattr(args, "no_color", False),
        is_json=getattr(args, "json", False),
    )

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

        reports, skipped_ids, total, error_count, fail_count, warn_details = _diagnose_all(
            run_results, manifest, paths
        )
        warn_count = len(warn_details)

        # Offline grouping for the demo (no live connection).
        root_cause_groups = build_root_cause_groups(reports, probe=None)

        text = render_text(
            reports=reports,
            total=total,
            errors=error_count,
            fails=fail_count,
            warns=warn_count,
            skipped=len(skipped_ids),
            skipped_models=skipped_ids,
            verbose=args.verbose,
            color_enabled=color_enabled,
            warn_details=warn_details,
            root_cause_groups=root_cause_groups,
        )
        print(text)


def cmd_lint(args):
    """Lint command: check compiled SQL for issues before dbt build."""
    from dbt_diagnostics.linters import LINTER_REGISTRY
    from dbt_diagnostics.renderer import render_lint

    paths = _resolve_from_args(args)

    manifest_path = paths.get("manifest")
    if not manifest_path or not manifest_path.exists():
        print("Error: manifest.json not found. Run `dbt compile` first.", file=sys.stderr)
        sys.exit(2)

    manifest = load_json(manifest_path, "manifest.json")
    compiled_dir = paths.get("compiled_dir")

    # Collect compiled SQL from manifest nodes (compiled_code field)
    nodes = manifest.get("nodes", {})
    model_count = 0
    all_findings = []

    for node_id, node in nodes.items():
        if node.get("resource_type") != "model":
            continue
        compiled_sql = node.get("compiled_code", "") or ""
        if not compiled_sql:
            # Try loading from target/compiled/ directory
            if compiled_dir:
                rel_path = node.get("path", "")
                compiled_file = compiled_dir / rel_path
                if compiled_file.exists():
                    compiled_sql = compiled_file.read_text()
            if not compiled_sql:
                continue

        model_count += 1
        for linter_cls in LINTER_REGISTRY:
            linter = linter_cls()
            findings = linter.lint(node_id, compiled_sql, node)
            all_findings.extend(findings)

    color_enabled = should_use_color(
        force_color=getattr(args, "color", False),
        no_color=getattr(args, "no_color", False),
        is_json=getattr(args, "json", False),
    )

    if getattr(args, "json", False):
        output = {
            "schema_version": "1.0",
            "lint_findings": [f.to_json_dict() for f in all_findings],
            "model_count": model_count,
            "total_findings": len(all_findings),
        }
        print(json.dumps(output, indent=2))
    else:
        text = render_lint(
            findings=all_findings,
            model_count=model_count,
            color_enabled=color_enabled,
        )
        print(text)

    if all_findings and not getattr(args, "no_fail", False):
        sys.exit(1)


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
    parser.add_argument(
        "--no-color", action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--color", action="store_true",
        help="Force colored output even when piped (for less -R, etc.)",
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
    parser.add_argument(
        "--previous-manifest", metavar="PATH",
        help="Path to a previous manifest.json for diff-aware diagnosis",
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

    # Live enrichment (ON by default; opt out with --no-live)
    parser.add_argument(
        "--no-live", action="store_true",
        help="Skip live Snowflake queries (manifest-only diagnosis)",
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
    subparsers.add_parser("lint", help="Pre-execution lint: check compiled SQL for issues without running dbt")

    args = parser.parse_args()

    # Default to diagnose when no subcommand is given
    if args.command is None:
        args.command = "diagnose"

    if args.command == "demo":
        cmd_demo(args)
    elif args.command == "lint":
        cmd_lint(args)
    else:
        cmd_diagnose(args)


if __name__ == "__main__":
    main()
