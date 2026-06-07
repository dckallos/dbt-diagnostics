"""
dbt_diagnostics/tracers/snippet.py

Extracts a window of compiled SQL around the error line, producing a
CompiledSnippet that the renderer can display with highlighting.

Why this exists: dbt error messages say "error line 38 at position 8" but
the user has to manually open the compiled SQL to see what's there. This
module does that extraction automatically, handling edge cases (first/last
line, position caret, empty input).
"""

from typing import Optional

from dbt_diagnostics.models import CompiledSnippet


def extract_snippet(
    compiled_code: str,
    error_line: int,
    context_lines: int = 1,
    error_position: Optional[int] = None,
) -> Optional[CompiledSnippet]:
    """
    Extract a window of compiled SQL around the error line.

    Args:
        compiled_code: The full compiled SQL string from run_results or manifest.
        error_line: 1-based line number where the error occurred.
        context_lines: Number of lines to include before and after the error.
        error_position: Optional 1-based column position within the error line.

    Returns:
        CompiledSnippet with the extracted window, or None if input is empty
        or error_line is invalid (< 1).
    """
    if not compiled_code or not compiled_code.strip():
        return None

    if error_line < 1:
        return None

    all_lines = compiled_code.split("\n")
    total_lines = len(all_lines)

    # Clamp error_line to file bounds (graceful degradation)
    clamped_line = min(error_line, total_lines)

    # Calculate window bounds (0-based indexing internally)
    start_idx = max(0, clamped_line - 1 - context_lines)
    end_idx = min(total_lines, clamped_line + context_lines)

    window_lines = all_lines[start_idx:end_idx]
    # 1-based line numbers for display
    line_numbers = list(range(start_idx + 1, end_idx + 1))

    return CompiledSnippet(
        lines=window_lines,
        line_numbers=line_numbers,
        error_line=clamped_line,
        error_position=error_position,
    )
