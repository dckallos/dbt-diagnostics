"""
Tests for dbt_diagnostics/schema_version.py.

These lock the auto-detect-and-degrade contract: the tool reads the dbt
schema version out of the artifact (never from user config) and NEVER raises,
even on garbage input. Unvalidated/unknown versions produce a note and are
reported as not-supported; validated versions produce no note.
"""

import json
from pathlib import Path

from dbt_diagnostics.schema_version import (
    ArtifactVersion,
    check_compatibility,
    detect_artifact_version,
    SUPPORTED_SCHEMAS,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load(name):
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


class TestDetectValidated:
    """Versions we have captured golden fixtures for are 'supported'."""

    def test_real_run_results_v6_supported(self):
        rr = _load("real_object_not_exist_002003.json")
        av = detect_artifact_version(rr, "run-results")
        assert av.kind == "run-results"
        assert av.schema_major == 6
        assert av.supported is True
        assert av.note is None
        assert av.dbt_version == "1.11.11"

    def test_real_manifest_v12_supported(self):
        manifest = _load("real_object_not_exist_002003_manifest.json")
        av = detect_artifact_version(manifest, "manifest")
        assert av.kind == "manifest"
        assert av.schema_major == 12
        assert av.supported is True
        assert av.note is None

    def test_index_html_url_variant_still_parses(self):
        # The AI-guessed fixtures use ".../v6/index.html" instead of ".../v6.json".
        rr = _load("runtime_errors.json")
        av = detect_artifact_version(rr, "run-results")
        assert av.kind == "run-results"
        assert av.schema_major == 6
        assert av.supported is True


class TestDetectUnvalidated:
    """An unknown major degrades to not-supported with a clear note."""

    def test_future_manifest_version_noted_not_raised(self):
        artifact = {
            "metadata": {
                "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v999.json",
                "dbt_version": "9.9.9",
            },
            "nodes": {},
        }
        av = detect_artifact_version(artifact, "manifest")
        assert av.kind == "manifest"
        assert av.schema_major == 999
        assert av.supported is False
        assert av.note is not None
        assert "not been validated" in av.note

    def test_missing_metadata_degrades(self):
        av = detect_artifact_version({"results": []}, "run-results")
        # Kind inferred from shape; version unknown -> not supported + note.
        assert av.kind == "run-results"
        assert av.schema_major is None
        assert av.supported is False
        assert av.note is not None


class TestNeverRaises:
    """The detector must tolerate any input shape without raising."""

    def test_garbage_inputs(self):
        for junk in (None, 42, "string", [], {}, {"metadata": "not-a-dict"},
                     {"metadata": {"dbt_schema_version": 123}}):
            av = detect_artifact_version(junk, "manifest")
            assert isinstance(av, ArtifactVersion)
            assert av.supported is False

    def test_malformed_schema_url(self):
        av = detect_artifact_version(
            {"metadata": {"dbt_schema_version": "https://example.com/nope"}},
            "manifest",
        )
        assert isinstance(av, ArtifactVersion)
        # No vN token -> major unknown, not supported, has a note.
        assert av.schema_major is None
        assert av.supported is False
        assert av.note is not None


class TestCompatibilityReport:
    def test_real_pair_all_supported_no_notes(self):
        rr = _load("real_object_not_exist_002003.json")
        manifest = _load("real_object_not_exist_002003_manifest.json")
        compat = check_compatibility(rr, manifest)
        assert compat.all_supported is True
        assert compat.notes == []
        d = compat.to_json_dict()
        assert d["all_supported"] is True
        assert d["run_results"]["schema_major"] == 6
        assert d["manifest"]["schema_major"] == 12

    def test_mixed_pair_collects_notes(self):
        rr = _load("real_object_not_exist_002003.json")
        bad_manifest = {
            "metadata": {
                "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v13.json"
            },
            "nodes": {},
        }
        compat = check_compatibility(rr, bad_manifest)
        assert compat.all_supported is False
        assert len(compat.notes) == 1
        assert "v13" in compat.notes[0]

    def test_check_never_raises_on_junk(self):
        compat = check_compatibility(None, None)
        assert compat.all_supported is False
        assert len(compat.notes) == 2


class TestSupportedSet:
    def test_current_ground_truth(self):
        # Guards against accidental widening without a captured fixture.
        assert SUPPORTED_SCHEMAS["manifest"] == {12}
        assert SUPPORTED_SCHEMAS["run-results"] == {6}
