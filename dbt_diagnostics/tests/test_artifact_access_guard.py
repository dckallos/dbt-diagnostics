# dbt_diagnostics/tests/test_artifact_access_guard.py
"""
Guard against reintroducing direct reads of version-sensitive dbt artifact keys.

Classifiers and enrichers must use dbt_diagnostics.compat.safe for these fields
so version fallbacks and never-raise behavior stay centralized.
"""

import ast
from pathlib import Path


FORBIDDEN_KEYS = {
    "adapter_response",
    "compiled_code",
    "compiled_sql",
    "query_id",
    "raw_code",
    "raw_sql",
    "relation_name",
    "rows_affected",
}

SCAN_DIRS = ("classifiers", "enrichers", "tracers")


def _literal_key(node):
    """Return a literal string subscript key for py3.8+ AST shapes."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    # Compatibility with older AST shapes if the project tests on older Python.
    if isinstance(node, ast.Index):
        return _literal_key(node.value)

    return None


def _violations_in(path: Path, package_root: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
        ):
            key_node = node.args[0]
            if isinstance(key_node, ast.Constant) and key_node.value in FORBIDDEN_KEYS:
                violations.append(
                    f"{path.relative_to(package_root)}:{node.lineno} "
                    f"direct .get({key_node.value!r})"
                )

        if isinstance(node, ast.Subscript):
            key = _literal_key(node.slice)
            if key in FORBIDDEN_KEYS:
                violations.append(
                    f"{path.relative_to(package_root)}:{node.lineno} "
                    f"direct subscript[{key!r}]"
                )

    return violations


def test_classifiers_and_enrichers_do_not_read_version_sensitive_keys_directly():
    package_root = Path(__file__).resolve().parents[1]
    violations = []

    for dirname in SCAN_DIRS:
        for path in sorted((package_root / dirname).rglob("*.py")):
            violations.extend(_violations_in(path, package_root))

    assert not violations, (
        "Use dbt_diagnostics.compat.safe accessors for version-sensitive "
        "artifact fields instead of direct dict reads:\n"
        + "\n".join(violations)
    )
