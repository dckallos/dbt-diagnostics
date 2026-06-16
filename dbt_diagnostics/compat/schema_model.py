# Minimal JSON Schema graph walker for dbt artifact schemas: resolves $ref, $defs vs
# definitions, allOf merges, and anyOf/oneOf unions into concrete object subschemas.
# Co-authored with CoCo
"""
dbt's published artifact schemas mix JSON Schema draft-07 (`definitions`) and 2020-12
(`$defs`), reference node types via `$ref`, and express the `nodes`/`results`
collections as `anyOf`/`oneOf` unions of many node-type objects. This module provides
just enough resolution to ask, for a given field, "is it present, required, and of
what type" across every concrete object a path can reach. Stdlib-only and offline.
"""

from __future__ import annotations

from typing import Any


class SchemaDoc:
    """Wraps a parsed JSON Schema document and resolves its internal references."""

    def __init__(self, root: dict):
        self.root = root
        self.defs: dict = root.get("$defs") or root.get("definitions") or {}

    def deref(self, node: Any) -> dict:
        """Follow a $ref chain to a concrete schema dict; tolerate cycles and leaves."""
        seen: set[str] = set()
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if ref in seen:                      # cycle guard
                return {}
            seen.add(ref)
            node = self.defs.get(ref.split("/")[-1], {})
        return node if isinstance(node, dict) else {}

    def members(self, node: Any) -> list[dict]:
        """Flatten a possibly-union schema into a list of concrete object subschemas."""
        node = self.deref(node)
        if not node:
            return []
        for key in ("anyOf", "oneOf"):
            if key in node:
                out: list[dict] = []
                for sub in node[key]:
                    out.extend(self.members(sub))
                return out
        if "allOf" in node:                      # merge allOf branches into one object
            merged: dict = {"type": "object", "properties": {}, "required": []}
            for sub in node["allOf"]:
                sub = self.deref(sub)
                merged["properties"].update(sub.get("properties", {}))
                merged["required"].extend(sub.get("required", []))
            return [merged]
        return [node]

    def item_schema(self, node: dict) -> dict:
        """Schema of a collection's members: dict values or array items."""
        node = self.deref(node)
        ap = node.get("additionalProperties")
        if isinstance(ap, dict):
            return ap
        if "items" in node:
            return node["items"]
        # patternProperties: take the first defined pattern's schema
        pp = node.get("patternProperties")
        if isinstance(pp, dict) and pp:
            return next(iter(pp.values()))
        return {}

    @staticmethod
    def norm_type(spec: dict) -> tuple[frozenset[str], bool]:
        """Normalize a field spec to (non-null type names, nullable?)."""
        types: set[str] = set()
        nullable = False
        t = spec.get("type")
        if isinstance(t, list):
            nullable = "null" in t
            types = {x for x in t if x != "null"}
        elif isinstance(t, str):
            types = {t}
        for key in ("anyOf", "oneOf"):
            for sub in spec.get(key, []):
                if not isinstance(sub, dict):
                    continue
                st = sub.get("type")
                if st == "null":
                    nullable = True
                elif isinstance(st, str):
                    types.add(st)
                elif "$ref" in sub:
                    types.add("object")
        return frozenset(types or {"any"}), nullable

    def root_object(self) -> dict:
        """The top-level object schema (the root may itself be a $ref into $defs)."""
        return self.deref(self.root) if "$ref" in self.root else self.root
