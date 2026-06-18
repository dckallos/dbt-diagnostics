# dbt_diagnostics/tests/test_safe_artifact_accessors.py
"""
Tests for version-tolerant dbt artifact accessors.

These lock the dbt 1.3 compiled/raw rename boundary and the never-raise
contract expected by classifiers and enrichers.
"""

import pytest

from dbt_diagnostics.compat import safe


def test_compiled_and_raw_accessors_prefer_new_manifest_keys():
    """Current manifests expose compiled_code/raw_code."""
    manifest = {
        "nodes": {
            "model.pkg.current": {
                "compiled_code": "select 1 as current_value",
                "compiled_sql": "select 1 as old_value",
                "raw_code": "select {{ current_value }}",
                "raw_sql": "select {{ old_value }}",
            }
        }
    }

    node = manifest["nodes"]["model.pkg.current"]

    assert safe.node_compiled_code(node) == "select 1 as current_value"
    assert safe.node_compiled_sql(node) == "select 1 as current_value"
    assert safe.node_raw_code(node) == "select {{ current_value }}"
    assert safe.node_raw_sql(node) == "select {{ current_value }}"


def test_compiled_and_raw_accessors_fall_back_to_old_manifest_keys():
    """Old manifests expose compiled_sql/raw_sql."""
    manifest = {
        "nodes": {
            "model.pkg.old": {
                "compiled_sql": "select 1 as old_value",
                "raw_sql": "select {{ old_value }}",
            }
        }
    }

    node = manifest["nodes"]["model.pkg.old"]

    assert safe.node_compiled_code(node) == "select 1 as old_value"
    assert safe.node_compiled_sql(node) == "select 1 as old_value"
    assert safe.node_raw_code(node) == "select {{ old_value }}"
    assert safe.node_raw_sql(node) == "select {{ old_value }}"


@pytest.mark.parametrize(
    ("accessor", "value"),
    [
        (safe.node_compiled_code, None),
        (safe.node_compiled_code, []),
        (safe.node_compiled_code, "not a node"),
        (safe.node_compiled_code, {}),
        (safe.node_raw_code, None),
        (safe.node_raw_code, []),
        (safe.node_raw_code, "not a node"),
        (safe.node_raw_code, {}),
        (safe.node_relation_name, None),
        (safe.node_relation_name, []),
        (safe.node_relation_name, "not a node"),
        (safe.node_relation_name, {}),
        (safe.result_query_id, None),
        (safe.result_query_id, []),
        (safe.result_query_id, "not a result"),
        (safe.result_query_id, {}),
        (safe.result_query_id, {"adapter_response": None}),
        (safe.result_query_id, {"adapter_response": "not a dict"}),
        (safe.result_rows_affected, None),
        (safe.result_rows_affected, []),
        (safe.result_rows_affected, "not a result"),
        (safe.result_rows_affected, {}),
        (safe.result_rows_affected, {"adapter_response": None}),
        (safe.result_rows_affected, {"adapter_response": "not a dict"}),
    ],
)
def test_accessors_return_none_for_missing_or_non_dict_input(accessor, value):
    """Missing and malformed artifact input degrades to None, never an exception."""
    assert accessor(value) is None


def test_adapter_response_accessors_return_present_values():
    result = {
        "adapter_response": {
            "query_id": "01abc-0000-1234",
            "rows_affected": 17,
        }
    }

    assert safe.result_query_id(result) == "01abc-0000-1234"
    assert safe.result_rows_affected(result) == 17


def test_dig_returns_default_for_missing_or_non_dict_input():
    assert safe.dig(None, "a", "b") is None
    assert safe.dig({"a": None}, "a", "b", default="fallback") == "fallback"
    assert safe.dig({"a": {"b": "value"}}, "a", "b") == "value"
