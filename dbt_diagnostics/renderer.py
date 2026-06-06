"""
dbt_diagnostics/renderer.py

Jinja2-based renderer. Loads templates from the templates/ directory
and produces formatted output from DiagnosticReport dataclasses.
"""

from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dbt_diagnostics.colors import (
    bold,
    bold_red,
    bold_yellow,
    bold_white,
    green,
    cyan,
    dim,
)
from dbt_diagnostics.models import DiagnosticReport, LintFinding

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _short_name(unique_id: str) -> str:
    """
    Extract a readable short name from a dbt unique_id.
    'model.artwork_pipeline.dim_artworks' -> 'dim_artworks'
    'test.artwork_pipeline.dbt_expectations_...' -> (test, handled separately)
    """
    parts = unique_id.split(".")
    if len(parts) >= 3:
        return parts[-1]
    return unique_id


def _summarize_skipped(skipped_models: list[str]) -> dict:
    """
    Partition skipped items into models and tests, returning short names
    for models and a count for tests.
    """
    models = []
    test_count = 0
    for uid in skipped_models:
        if uid.startswith("test."):
            test_count += 1
        else:
            models.append(_short_name(uid))
    return {"models": models, "test_count": test_count}


def _build_env(color_enabled: bool = False) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    env.filters["short_name"] = _short_name

    # Color filters: emit ANSI codes when enabled, pass-through otherwise
    env.filters["bold"] = lambda text: bold(text, enabled=color_enabled)
    env.filters["bold_red"] = lambda text: bold_red(text, enabled=color_enabled)
    env.filters["bold_yellow"] = lambda text: bold_yellow(text, enabled=color_enabled)
    env.filters["bold_white"] = lambda text: bold_white(text, enabled=color_enabled)
    env.filters["green"] = lambda text: green(text, enabled=color_enabled)
    env.filters["cyan"] = lambda text: cyan(text, enabled=color_enabled)
    env.filters["dim"] = lambda text: dim(text, enabled=color_enabled)

    return env


def render_text(
    reports: list[DiagnosticReport],
    total: int,
    errors: int,
    skipped: int,
    skipped_models: list[str],
    verbose: bool = False,
    color_enabled: bool = False,
) -> str:
    """Render all reports using the Jinja2 report template."""
    env = _build_env(color_enabled=color_enabled)
    template = env.get_template("report.j2")

    skipped_summary = _summarize_skipped(skipped_models)

    return template.render(
        reports=reports,
        total=total,
        errors=errors,
        skipped=skipped,
        skipped_models=skipped_models,
        skipped_summary=skipped_summary,
        verbose=verbose,
    )


def render_lint(
    findings: list[LintFinding],
    model_count: int,
    color_enabled: bool = False,
) -> str:
    """Render lint findings using the lint_report template."""
    env = _build_env(color_enabled=color_enabled)
    template = env.get_template("lint_report.j2")

    return template.render(
        findings=findings,
        model_count=model_count,
    )
