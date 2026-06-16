"""
Robustness tier: malformed / partially-written artifacts must DEGRADE, never
raise.

dbt writes artifacts atomically, but an interrupted `dbt build`, a partial
copy, or a hand-edited file can still hand the tool a run_results.json that is
truncated, missing keys, or holds junk entries. The contract these tests lock:

  - load_json (CLI boundary): a corrupt artifact raises ArtifactLoadError
    (not a JSONDecodeError traceback). The CLI catches it and exits cleanly.
  - _diagnose_all (core logic): a structurally-broken run_results yields a
    partial-but-valid result (skip the junk), never an exception.

These tests target the orchestration around classify()/schema_version, which
were already defensive; the orchestration was not until this change.
"""

import json
from pathlib import Path

import pytest

from dbt_diagnostics.main import ArtifactLoadError, _diagnose_all, load_json

pytestmark = pytest.mark.robustness


def _paths(tmp_path: Path) -> dict:
    """Minimal paths dict for _diagnose_all; dirs need not contain files."""
    return {
        "models_dir": tmp_path / "models",
        "compiled_dir": tmp_path / "compiled",
    }


# --------------------------------------------------------------------------
# load_json: corrupt artifact -> ArtifactLoadError, not a traceback
# --------------------------------------------------------------------------

def test_truncated_json_raises_artifact_load_error(tmp_path):
    bad = tmp_path / "run_results.json"
    bad.write_text('{"results": [ {"status": "err')  # truncated mid-object
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(bad, "run_results.json")
    assert "not valid JSON" in str(exc_info.value)


def test_empty_file_raises_artifact_load_error(tmp_path):
    bad = tmp_path / "manifest.json"
    bad.write_text("")
    with pytest.raises(ArtifactLoadError):
        load_json(bad, "manifest.json")


def test_missing_file_raises_artifact_load_error(tmp_path):
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(tmp_path / "nope.json", "run_results.json")
    assert "file not found" in str(exc_info.value)


def test_valid_json_loads_successfully(tmp_path):
    good = tmp_path / "run_results.json"
    good.write_text('{"results": []}')
    result = load_json(good, "run_results.json")
    assert result == {"results": []}


# --------------------------------------------------------------------------
# _diagnose_all: structurally-broken run_results -> degrade, never raise
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "broken_run_results",
    [
        {},                                   # no "results" key at all
        {"results": None},                    # results present but null
        {"results": "not-a-list"},            # results wrong type
        {"results": [None, 42, "x"]},         # all entries junk
        {"results": [{}]},                    # entry with no status/message
        {"results": [{"status": "error"}]},   # error with no message
        {"results": [{"status": "weird"}]},   # unrecognized status
        {"results": [{"status": "error", "message": None}]},  # null message
    ],
    ids=[
        "no-results-key",
        "results-null",
        "results-wrong-type",
        "all-junk-entries",
        "empty-entry",
        "error-no-message",
        "unknown-status",
        "null-message",
    ],
)
def test_diagnose_all_degrades_on_broken_run_results(
    broken_run_results, manifest_minimal, tmp_path
):
    # Must not raise; must return the documented 6-tuple.
    out = _diagnose_all(broken_run_results, manifest_minimal, _paths(tmp_path))
    assert isinstance(out, tuple) and len(out) == 6
    reports, skipped_ids, total, error_count, fail_count, warn_details = out
    assert isinstance(reports, list)
    assert isinstance(total, int) and total >= 0


def test_diagnose_all_skips_junk_but_keeps_valid(manifest_minimal, tmp_path):
    """A mix of junk and one real error: the junk is skipped, the error kept."""
    run_results = {
        "results": [
            None,
            "garbage",
            {"status": "error", "message": "Database Error in model x\n  002003: boom"},
            {},
        ]
    }
    reports, _, total, error_count, _, _ = _diagnose_all(
        run_results, manifest_minimal, _paths(tmp_path)
    )
    # total counts every entry; the one real error becomes a report.
    assert total == 4
    assert error_count == 1
    assert len(reports) == 1


def test_diagnose_all_never_raises_on_pure_garbage(manifest_minimal, tmp_path):
    for junk in (None, [], "string", 0, {"results": {"nested": "dict"}}):
        out = _diagnose_all(junk, manifest_minimal, _paths(tmp_path))
        assert len(out) == 6
