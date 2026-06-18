"""
Contract test that PROVES the CI schema gate (scripts/compat/schema_diff.py):
dropping a consumed field with no declared fallback must make the gate fail
(nonzero exit). Uses synthetic first-party-shaped schemas so it runs offline
with no committed cache and no network (#40).
"""

import json
import sys
from pathlib import Path

import pytest

# scripts/ is not a package on the import path; add the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.compat import schema_diff  # noqa: E402

pytestmark = pytest.mark.contract


def _manifest_schema(*, with_relation_name: bool) -> dict:
    """A manifest-like schema whose `nodes` is a union with a ModelNode."""
    model_props = {"compiled_code": {"type": "string"}}
    required = []
    if with_relation_name:
        model_props["relation_name"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
        required = ["relation_name"]
    return {
        "type": "object",
        "properties": {"nodes": {"type": "object", "additionalProperties": {
            "anyOf": [{"$ref": "#/$defs/ModelNode"}]}}},
        "$defs": {
            "ModelNode": {
                "title": "ModelNode", "type": "object",
                "required": required, "properties": model_props,
            },
        },
    }


def _write(tmp_path: Path, name: str, doc: dict) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return str(p)


def test_gate_fails_when_consumed_field_dropped_without_fallback(tmp_path):
    # relation_name is a consumed manifest path with NO declared fallback.
    base = _write(tmp_path, "base.json", _manifest_schema(with_relation_name=True))
    new = _write(tmp_path, "new.json", _manifest_schema(with_relation_name=False))

    # diff() returns the unguarded-break count...
    assert schema_diff.diff(base, new, "manifest") >= 1
    # ...and the CLI surfaces it as a nonzero exit (the CI gate fails).
    assert schema_diff.main([base, new, "--artifact", "manifest"]) == 1


def test_gate_passes_when_schema_is_stable(tmp_path):
    base = _write(tmp_path, "base.json", _manifest_schema(with_relation_name=True))
    new = _write(tmp_path, "new.json", _manifest_schema(with_relation_name=True))

    assert schema_diff.diff(base, new, "manifest") == 0
    assert schema_diff.main([base, new, "--artifact", "manifest"]) == 0
