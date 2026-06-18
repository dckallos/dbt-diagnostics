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

from dbt_diagnostics.main import (
    ArtifactLoadError,
    _corrupt_artifact_note,
    _diagnose_all,
    load_json,
)
from dbt_diagnostics.schema_version import detect_artifact_version

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
    assert exc_info.value.kind == "corrupt"
    assert "truncated or corrupted (interrupted run?)" in str(exc_info.value)
    assert exc_info.value.reason == _corrupt_artifact_note("run_results.json")


def test_empty_file_raises_corrupt_artifact_load_error(tmp_path):
    bad = tmp_path / "manifest.json"
    bad.write_text("")
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(bad, "manifest.json")
    assert exc_info.value.kind == "corrupt"
    assert "truncated or corrupted (interrupted run?)" in str(exc_info.value)


def test_whitespace_only_file_is_corrupt(tmp_path):
    bad = tmp_path / "run_results.json"
    bad.write_text("   \n\t  ")
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(bad, "run_results.json")
    assert exc_info.value.kind == "corrupt"


def test_non_utf8_bytes_raise_corrupt_not_unicode_error(tmp_path):
    """Garbage/non-UTF8 bytes must degrade to a corrupt ArtifactLoadError, not
    let a UnicodeDecodeError (a ValueError, not OSError) escape as a traceback."""
    bad = tmp_path / "manifest.json"
    bad.write_bytes(b"\xff\xfe\x00\x01\x80\x81 not utf-8 at all")
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(bad, "manifest.json")
    assert exc_info.value.kind == "corrupt"
    assert "truncated or corrupted (interrupted run?)" in str(exc_info.value)


def test_missing_file_raises_not_found(tmp_path):
    with pytest.raises(ArtifactLoadError) as exc_info:
        load_json(tmp_path / "nope.json", "run_results.json")
    assert exc_info.value.kind == "not_found"
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


# --------------------------------------------------------------------------
# detect_artifact_version: every threat case degrades, never raises
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "artifact, expected_kind",
    [
        (None, "manifest"),                       # not a JSON object at all
        ([], "manifest"),                         # list where dict expected
        ("a string", "run-results"),              # scalar where dict expected
        ({}, "manifest"),                         # empty dict, no shape clues
        ({"nodes": None}, "manifest"),            # nodes present but null
        ({"results": None}, "run-results"),       # results present but null
        ({"metadata": "not-a-dict"}, "manifest"),  # metadata wrong type
        ({"metadata": {"dbt_schema_version": 123}}, "manifest"),  # url not a string
        ({"metadata": {"dbt_schema_version": "file:///nope"}}, "run-results"),  # non-getdbt URL
        ({"metadata": {}}, "manifest"),           # metadata present, url missing
    ],
    ids=[
        "none",
        "list-not-dict",
        "scalar-not-dict",
        "empty-dict",
        "nodes-null",
        "results-null",
        "metadata-wrong-type",
        "schema-url-not-string",
        "schema-url-not-getdbt",
        "schema-url-missing",
    ],
)
def test_detect_artifact_version_degrades_never_raises(artifact, expected_kind):
    av = detect_artifact_version(artifact, expected_kind)
    # Contract: never raises, never claims "supported", always carries a note.
    assert av.supported is False
    assert av.note is not None and av.note != ""


def test_detect_artifact_version_no_kwarg_still_degrades():
    """The never-raise contract holds even without the expected_kind hint."""
    for artifact in (None, [], "x", 42, {}, {"metadata": []}):
        av = detect_artifact_version(artifact)
        assert av.supported is False
        assert av.note
