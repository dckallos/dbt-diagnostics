"""
dbt_diagnostics/colors.py

ANSI escape code utilities for terminal color output.
Respects TTY detection, --no-color, --color, and NO_COLOR env var.
No external dependencies (no colorama, no rich).
"""

import os
import sys


# ANSI escape sequences
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BOLD_RED = "\033[1;31m"
BOLD_YELLOW = "\033[1;33m"
BOLD_WHITE = "\033[1;37m"
BOLD_GREEN = "\033[1;32m"


def should_use_color(
    *,
    force_color: bool = False,
    no_color: bool = False,
    is_json: bool = False,
) -> bool:
    """
    Determine whether to emit ANSI color codes.

    Priority:
      1. JSON mode -> never color
      2. --no-color flag -> no color
      3. NO_COLOR env var (any non-empty value) -> no color
      4. --color flag -> force color (even when piped)
      5. Default: color only if stdout is a TTY
    """
    if is_json:
        return False
    if no_color:
        return False
    if os.environ.get("NO_COLOR", ""):
        return False
    if force_color:
        return True
    return sys.stdout.isatty()


def colorize(text: str, code: str, *, enabled: bool = True) -> str:
    """Wrap text in ANSI escape codes if color is enabled."""
    if not enabled:
        return text
    return f"{code}{text}{RESET}"


# Convenience helpers used by Jinja filters
def bold(text: str, *, enabled: bool = True) -> str:
    return colorize(text, BOLD, enabled=enabled)


def bold_red(text: str, *, enabled: bool = True) -> str:
    return colorize(text, BOLD_RED, enabled=enabled)


def bold_yellow(text: str, *, enabled: bool = True) -> str:
    return colorize(text, BOLD_YELLOW, enabled=enabled)


def bold_white(text: str, *, enabled: bool = True) -> str:
    return colorize(text, BOLD_WHITE, enabled=enabled)


def green(text: str, *, enabled: bool = True) -> str:
    return colorize(text, GREEN, enabled=enabled)


def cyan(text: str, *, enabled: bool = True) -> str:
    return colorize(text, CYAN, enabled=enabled)


def dim(text: str, *, enabled: bool = True) -> str:
    return colorize(text, DIM, enabled=enabled)
