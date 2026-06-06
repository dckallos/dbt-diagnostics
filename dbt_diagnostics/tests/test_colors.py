"""
Tests for the colors module (ANSI output control).
"""

import os
from unittest.mock import patch

from dbt_diagnostics.colors import (
    should_use_color,
    colorize,
    bold,
    bold_red,
    BOLD,
    BOLD_RED,
    RESET,
)
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.models import DiagnosticReport, DiagnosticFinding, TraceLocation


class TestShouldUseColor:
    """Unit tests for color decision logic."""

    def test_no_color_flag_disables(self):
        assert should_use_color(no_color=True, force_color=False, is_json=False) is False

    def test_json_mode_disables(self):
        assert should_use_color(no_color=False, force_color=True, is_json=True) is False

    def test_force_color_enables(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove NO_COLOR if present
            os.environ.pop("NO_COLOR", None)
            assert should_use_color(force_color=True, no_color=False, is_json=False) is True

    def test_no_color_env_var_disables(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert should_use_color(force_color=False, no_color=False, is_json=False) is False

    def test_no_color_env_empty_string_does_not_disable(self):
        with patch.dict(os.environ, {"NO_COLOR": ""}):
            # Empty string = not set per no-color.org
            # In non-TTY context default would be False anyway
            # but force_color should still work
            assert should_use_color(force_color=True, no_color=False, is_json=False) is True


class TestColorize:
    """Unit tests for ANSI code wrapping."""

    def test_enabled_wraps(self):
        result = colorize("hello", BOLD, enabled=True)
        assert result == f"{BOLD}hello{RESET}"

    def test_disabled_passes_through(self):
        result = colorize("hello", BOLD, enabled=False)
        assert result == "hello"

    def test_bold_helper(self):
        assert bold("x", enabled=True) == f"{BOLD}x{RESET}"
        assert bold("x", enabled=False) == "x"


class TestColorInRenderedOutput:
    """Integration tests: color in rendered templates."""

    def _make_report(self):
        return DiagnosticReport(
            unique_id="model.artwork_pipeline.dim_artworks",
            error_class="runtime_error",
            raw_message="Database Error",
            findings=[
                DiagnosticFinding(
                    summary="Object does not exist",
                    location=TraceLocation(file_path="models/dim_artworks.sql"),
                    fix_suggestion="Run the DDL",
                )
            ],
        )

    def test_color_enabled_emits_ansi(self):
        report = self._make_report()
        text = render_text(
            reports=[report],
            total=1,
            errors=1,
            skipped=0,
            skipped_models=[],
            color_enabled=True,
        )
        assert "\033[" in text

    def test_color_disabled_no_ansi(self):
        report = self._make_report()
        text = render_text(
            reports=[report],
            total=1,
            errors=1,
            skipped=0,
            skipped_models=[],
            color_enabled=False,
        )
        assert "\033[" not in text

    def test_json_output_never_has_ansi(self):
        """JSON mode must never contain ANSI codes (tested via should_use_color)."""
        # When is_json=True, should_use_color returns False regardless
        assert should_use_color(force_color=True, no_color=False, is_json=True) is False
