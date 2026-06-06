"""
dbt_diagnostics/main.py

Entry point for the dbt diagnostic tracer. Loads dbt artifacts, classifies
errors, and traces root causes through the model DAG.

Usage:
    python dbt_diagnostics/main.py
    python dbt_diagnostics/main.py --config dbt_diagnostics/config.yml
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from dbt_diagnostics.classifiers.contract_violation import ContractViolationClassifier
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer


def load_config(config_path: Path) -> dict:
    """Load the YAML config file."""
    if not config_path.exists():
        print(f"ERROR: Config not found: {config_path}")
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
        print(f"ERROR: {label} not found at {path}")
        print(f"  Run `dbt build` first to generate artifacts in target/.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def classify_error(message: str) -> str:
    """Classify a dbt error message into a category."""
    if "enforced contract that failed" in message:
        return "contract_violation"
    if "Database Error" in message:
        return "database_error"
    if "Compilation Error" in message:
        return "compilation_error"
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="dbt diagnostic tracer")
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).parent / "config.yml",
        help="Path to config.yml",
    )
    args = parser.parse_args()

    # Load config and resolve paths
    config = load_config(args.config)
    config_dir = args.config.parent
    paths = resolve_project_paths(config, config_dir)

    # Load artifacts
    run_results = load_json(paths["run_results"], "run_results.json")
    manifest = load_json(paths["manifest"], "manifest.json")

    # Initialize tracers
    dag_walker = DagWalker(manifest)
    column_tracer = ColumnTracer(paths["models_dir"], paths["compiled_dir"])

    # Find errors
    errors = []
    skipped = []
    for result in run_results["results"]:
        if result["status"] == "error":
            errors.append(result)
        elif result["status"] == "skipped":
            skipped.append(result)

    # Summary
    total = len(run_results["results"])
    print(f"\n{'='*70}")
    print(f"  dbt Diagnostics: {total} results | {len(errors)} error(s) | {len(skipped)} skipped")
    print(f"{'='*70}")

    if not errors:
        print("\n  No errors found.\n")
        return

    # Diagnose each error
    for result in errors:
        unique_id = result.get("unique_id", "unknown")
        message = result.get("message", "")
        classification = classify_error(message)

        print(f"\n  ERROR: {unique_id}")
        print(f"  Type:  {classification}")
        print(f"  {'─'*66}")

        if classification == "contract_violation":
            classifier = ContractViolationClassifier(
                result=result,
                dag_walker=dag_walker,
                column_tracer=column_tracer,
            )
            classifier.diagnose()
        else:
            print(f"\n  Message:\n    {message[:500]}")

    # Skipped summary
    if skipped:
        print(f"\n  {'─'*66}")
        print(f"  SKIPPED ({len(skipped)} downstream of the above error):")
        for s in skipped[:5]:
            print(f"    - {s.get('unique_id')}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped) - 5} more")

    print()


if __name__ == "__main__":
    main()
