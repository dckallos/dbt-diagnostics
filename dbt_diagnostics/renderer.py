"""
dbt_diagnostics/renderer.py

Jinja2-based renderer. Loads templates from the templates/ directory
and produces formatted output from DiagnosticReport dataclasses.
"""

from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dbt_diagnostics.models import DiagnosticReport

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render_text(
    reports: list[DiagnosticReport],
    total: int,
    errors: int,
    skipped: int,
    skipped_models: list[str],
) -> str:
    """Render all reports using the Jinja2 report template."""
    env = _build_env()
    template = env.get_template("report.j2")
    return template.render(
        reports=reports,
        total=total,
        errors=errors,
        skipped=skipped,
        skipped_models=skipped_models,
    )
