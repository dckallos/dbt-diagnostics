# Unit tests for the cross-version compat engine: schema resolver, consumed-path
# diffing (incl. the dbt 1.3 compiled_sql->compiled_code rename), and safe accessors.
"""Synthetic-schema tests so the engine is provable offline, with no network or real
artifacts. Real first-party schemas are exercised separately via the contract tier."""

import pytest

from dbt_diagnostics.compat.schema_model import SchemaDoc
from dbt_diagnostics.compat.path_resolver import resolve, present_anywhere
from dbt_diagnostics.compat import safe
from dbt_diagnostics.compat.consumed_paths import REGISTRY, for_artifact

pytestmark = pytest.mark.unit


def _manifest(compiled_key: str) -> dict:
    """A tiny manifest-like schema; `nodes` is a union of model + seed node types."""
    return {
        "type": "object",
        "properties": {"nodes": {"type": "object", "additionalProperties": {
            "anyOf": [{"$ref": "#/$defs/ModelNode"}, {"$ref": "#/$defs/SeedNode"}]}}},
        "$defs": {
            "ModelNode": {"title": "ModelNode", "type": "object", "required": ["relation_name"],
                          "properties": {
                              "relation_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                              compiled_key: {"type": "string"}}},
            "SeedNode": {"title": "SeedNode", "type": "object", "properties": {
                "relation_name": {"type": ["string", "null"]}}},
        },
    }


def test_resolve_crosses_node_union_and_detects_nullable():
    doc = SchemaDoc(_manifest("compiled_code"))
    recs = {p.defn: p for p in resolve(doc, "nodes[].relation_name")}
    assert recs["ModelNode"].present and recs["ModelNode"].required
    assert recs["SeedNode"].present and not recs["SeedNode"].required
    assert recs["ModelNode"].nullable and "string" in recs["ModelNode"].types


def test_rename_boundary_compiled_code_vs_compiled_sql():
    v7, v6 = SchemaDoc(_manifest("compiled_code")), SchemaDoc(_manifest("compiled_sql"))
    assert present_anywhere(v7, "nodes[].compiled_code")
    assert not present_anywhere(v6, "nodes[].compiled_code")
    assert present_anywhere(v6, "nodes[].compiled_sql")   # the pre-1.3 name survives as fallback


def test_missing_path_returns_absent_not_raise():
    doc = SchemaDoc(_manifest("compiled_code"))
    assert resolve(doc, "nodes[].does_not_exist")          # returns records, all absent
    assert not present_anywhere(doc, "nodes[].does_not_exist")


def test_safe_accessors_fallback_and_never_raise():
    assert safe.node_compiled_sql({"compiled_code": "A"}) == "A"
    assert safe.node_compiled_sql({"compiled_sql": "B"}) == "B"     # 1.3 fallback
    assert safe.node_compiled_sql({}) is None                       # degrade, no raise
    assert safe.node_relation_name({}) is None
    assert safe.result_query_id({"adapter_response": {"query_id": "01a"}}) == "01a"
    assert safe.result_query_id({}) is None                         # non-Snowflake/op result


def test_safe_fallbacks_match_registry():
    """The runtime fallback aliases must match what the registry declares (no drift)."""
    reg = {cp.path: cp.fallbacks for cp in REGISTRY}
    assert reg["nodes[].compiled_code"] == ("compiled_sql",)
    assert reg["nodes[].raw_code"] == ("raw_sql",)


def test_registry_partitions_by_artifact():
    arts = {cp.artifact for cp in REGISTRY}
    assert arts == {"manifest", "run-results", "catalog"}
    assert for_artifact("manifest") and for_artifact("run-results")
    assert for_artifact("catalog")
    assert for_artifact("catalog")
