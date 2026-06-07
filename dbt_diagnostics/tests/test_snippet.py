"""
Tests for the compiled SQL snippet extractor.
"""

import pytest

from dbt_diagnostics.tracers.snippet import extract_snippet
from dbt_diagnostics.models import CompiledSnippet


SAMPLE_SQL = """\
SELECT
    object_id,
    raw_payload:title::STRING AS title,
    raw_payload:artistDisplayName::STRING AS artist_name,
    raw_payload:department::STRING AS department
FROM
    ARTWORK_DB.BRONZE.RAW_MET_OBJECTS
WHERE
    object_id IS NOT NULL""".strip()


class TestExtractSnippet:
    """Tests for extract_snippet() function."""

    def test_middle_of_file(self):
        """Normal case: error in the middle with 1 line of context."""
        result = extract_snippet(SAMPLE_SQL, error_line=4, context_lines=1)
        assert result is not None
        assert result.error_line == 4
        assert len(result.lines) == 3  # lines 3, 4, 5
        assert result.line_numbers == [3, 4, 5]
        assert "artistDisplayName" in result.lines[1]  # the error line

    def test_first_line(self):
        """Edge: error on line 1, no 'before' context available."""
        result = extract_snippet(SAMPLE_SQL, error_line=1, context_lines=1)
        assert result is not None
        assert result.error_line == 1
        assert result.line_numbers[0] == 1
        # Should have line 1 + line 2 (no line before 1)
        assert len(result.lines) == 2
        assert "SELECT" in result.lines[0]

    def test_last_line(self):
        """Edge: error on last line, no 'after' context available."""
        lines = SAMPLE_SQL.split("\n")
        last_line_num = len(lines)
        result = extract_snippet(SAMPLE_SQL, error_line=last_line_num, context_lines=1)
        assert result is not None
        assert result.error_line == last_line_num
        assert result.line_numbers[-1] == last_line_num
        # Should have (last-1) + last (no line after last)
        assert len(result.lines) == 2
        assert "IS NOT NULL" in result.lines[-1]

    def test_error_line_beyond_file(self):
        """Edge: error_line exceeds total lines -- clamp gracefully."""
        lines = SAMPLE_SQL.split("\n")
        total = len(lines)
        result = extract_snippet(SAMPLE_SQL, error_line=total + 10, context_lines=1)
        assert result is not None
        # Should clamp to last line
        assert result.error_line == total
        assert "IS NOT NULL" in result.lines[-1]

    def test_empty_compiled_code(self):
        """Edge: empty or whitespace-only input returns None."""
        assert extract_snippet("", error_line=1) is None
        assert extract_snippet("   \n  \n  ", error_line=1) is None

    def test_invalid_error_line_zero(self):
        """Edge: error_line < 1 returns None."""
        assert extract_snippet(SAMPLE_SQL, error_line=0) is None
        assert extract_snippet(SAMPLE_SQL, error_line=-1) is None

    def test_position_stored(self):
        """Position is passed through to the CompiledSnippet."""
        result = extract_snippet(SAMPLE_SQL, error_line=4, error_position=8)
        assert result is not None
        assert result.error_position == 8

    def test_larger_context(self):
        """Verbose mode: context_lines=3 gives wider window."""
        result = extract_snippet(SAMPLE_SQL, error_line=5, context_lines=3)
        assert result is not None
        # Lines 2-8 (5-3=2, 5+3=8)
        assert result.line_numbers[0] == 2
        assert result.line_numbers[-1] == 8
        assert len(result.lines) == 7

    def test_single_line_file(self):
        """Edge: file with only one line."""
        result = extract_snippet("SELECT 1", error_line=1, context_lines=1)
        assert result is not None
        assert result.lines == ["SELECT 1"]
        assert result.line_numbers == [1]
        assert result.error_line == 1

    def test_returns_compiled_snippet_type(self):
        """Verify return type is CompiledSnippet dataclass."""
        result = extract_snippet(SAMPLE_SQL, error_line=3)
        assert isinstance(result, CompiledSnippet)
