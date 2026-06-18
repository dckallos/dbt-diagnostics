# dbt_diagnostics/tests/test_compat_path_resolver.py
"""
Unit tests for the schema path resolver's never-raise / degrade contract.

`path_resolver.resolve` walks a consumed dot-path against a dbt artifact JSON
schema. Issue #38 locks that it returns an empty result (never raises) when the
schema is missing keys or is not even a dict, so the static compatibility check
degrades cleanly on a malformed or unexpected schema document.
"""

import pytest

from dbt_diagnostics.compat.path_resolver import present_anywhere, resolve
from dbt_diagnostics.compat.schema_model import SchemaDoc

pytestmark = pytest.mark.unit


# A minimal but well-formed schema reaching nodes[].relation_name, used as the
# positive control so the degrade tests are not trivially passing on a resolver
# that always returns [].
_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {"relation_name": {"type": ["string", "null"]}},
                "required": [],
            },
        }
    },
}


def test_schema_doc_tolerates_non_dict_root():
    """A non-dict root degrades to an empty document instead of raising."""
    for bad_root in (None, [], "schema", 42):
        doc = SchemaDoc(bad_root)
        assert doc.root == {}
        assert doc.defs == {}


def test_resolve_returns_present_on_well_formed_schema():
    doc = SchemaDoc(_SCHEMA)
    presences = resolve(doc, "nodes[].relation_name")
    assert presences  # at least one concrete object reached
    assert any(p.present for p in presences)
    assert present_anywhere(doc, "nodes[].relation_name") is True


@pytest.mark.parametrize("bad_root", [None, [], "schema", 42, {}])
def test_resolve_returns_empty_on_non_dict_or_empty_schema(bad_root):
    doc = SchemaDoc(bad_root)
    assert resolve(doc, "nodes[].relation_name") == []
    assert present_anywhere(doc, "results[].status") is False


def test_resolve_returns_empty_on_missing_intermediate_key():
    """A path through a key the schema does not define yields no presence."""
    doc = SchemaDoc(_SCHEMA)
    assert resolve(doc, "does_not_exist[].whatever") == []
    assert present_anywhere(doc, "does_not_exist[].whatever") is False


def test_resolve_reports_absent_leaf_without_raising():
    """The container resolves but the leaf field is absent -> present=False."""
    doc = SchemaDoc(_SCHEMA)
    presences = resolve(doc, "nodes[].no_such_field")
    assert presences  # the node object was reached
    assert all(p.present is False for p in presences)
