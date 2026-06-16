"""
Property tier: Hypothesis-generated artifacts must hold invariants.

Where the chaos tier perturbs REAL artifacts with a fixed catalog of mutations,
this tier generates SYNTHETIC-but-structurally-valid run_results from scratch
across a wide input space, and asserts properties that must hold for every
shape -- not just the handful we thought to write fixtures for.

Invariants:
  - classify() returns a known classifier class or None, and never raises, for
    any string.
  - _diagnose_all() returns the documented 6-tuple and never raises for any
    generated run_results, however odd.
  - total equals the number of generated result entries (accounting rule).
  - error_count never exceeds the number of entries whose status is "error".

PR CI runs the default (bounded) Hypothesis profile; the nightly job runs a
larger example budget. Profiles are registered in conftest-level settings.
"""

import pytest
from hypothesis import given, settings, strategies as st

from dbt_diagnostics.classifiers import classify
from dbt_diagnostics.classifiers.base import BaseClassifier
from dbt_diagnostics.main import _diagnose_all

pytestmark = pytest.mark.property


# Snowflake-ish error fragments mixed with arbitrary text, so generated
# messages sometimes hit a classifier signature and sometimes do not.
_ERROR_FRAGMENTS = st.sampled_from([
    "Database Error",
    "Compilation Error",
    "enforced contract that failed",
    "Numeric value '9e9' is out of range",
    "String 'xxxx' is too long",
    "Division by zero",
    "Statement reached its statement or warehouse timeout",
    "warehouse 'WH' was suspended",
    "002003 (42S02): Object 'X' does not exist",
    "some entirely unstructured failure text",
    "",
])

_messages = st.one_of(
    st.text(max_size=200),
    _ERROR_FRAGMENTS,
    st.builds(lambda a, b: f"{a}\n  {b}", _ERROR_FRAGMENTS, st.text(max_size=80)),
)

_statuses = st.sampled_from(["error", "fail", "skipped", "warn", "success", "pass", ""])

_result_entries = st.fixed_dictionaries(
    {
        "status": _statuses,
        "message": _messages,
        "unique_id": st.text(min_size=1, max_size=40),
    }
)

_run_results = st.fixed_dictionaries(
    {
        "results": st.lists(_result_entries, max_size=12),
    }
)

_MINIMAL_MANIFEST = {"nodes": {}}
_PATHS = {"models_dir": "/nonexistent/models", "compiled_dir": "/nonexistent/compiled"}


@settings()
@given(message=_messages)
def test_classify_total_function_over_strings(message):
    """classify() is total over strings: a class or None, never a raise."""
    result = classify(message)
    assert result is None or (
        isinstance(result, type) and issubclass(result, BaseClassifier)
    )


@settings(deadline=None)
@given(run_results=_run_results)
def test_diagnose_all_invariants(run_results):
    """_diagnose_all holds its accounting invariants for any generated input."""
    from pathlib import Path

    paths = {k: Path(v) for k, v in _PATHS.items()}
    reports, skipped_ids, total, error_count, fail_count, warn_details = _diagnose_all(
        run_results, _MINIMAL_MANIFEST, paths
    )

    entries = run_results["results"]
    n_error = sum(1 for r in entries if r.get("status") == "error")
    n_fail = sum(1 for r in entries if r.get("status") == "fail")

    assert total == len(entries)
    assert error_count == n_error
    assert fail_count == n_fail
    # Reports cover errors + fails (each error -> one report, each fail -> one).
    assert len(reports) == n_error + n_fail
    assert isinstance(warn_details, list)


@settings(deadline=None)
@given(
    run_results=st.one_of(
        st.none(),
        st.dictionaries(st.text(max_size=5), st.text(max_size=5), max_size=3),
        _run_results,
    )
)
def test_diagnose_all_never_raises_on_arbitrary_shapes(run_results):
    """Even shapes that violate the run_results schema must not raise."""
    from pathlib import Path

    paths = {k: Path(v) for k, v in _PATHS.items()}
    out = _diagnose_all(run_results, _MINIMAL_MANIFEST, paths)
    assert len(out) == 6
